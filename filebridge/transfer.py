"""Uploads and downloads with progress, cancel, skip and resume."""
import os
import posixpath
import stat

from . import remote as R

CHUNK = 256 * 1024
# overwrite   – always replace
# newer       – replace only when the source is newer or has a different size
# skip_same   – skip when the size is the same
# skip_exists – never touch a file that already exists at the destination
# resume      – continue a partial transfer
POLICIES = ('overwrite', 'newer', 'skip_same', 'skip_exists', 'resume')
MTIME_SLACK = 2  # seconds


def _skip(policy, src_size, src_mtime, dst_size, dst_mtime):
    if policy == 'skip_exists':
        return True
    if policy in ('skip_same', 'resume') and src_size == dst_size:
        return True
    if policy == 'newer' and src_size == dst_size and src_mtime <= (dst_mtime or 0) + MTIME_SLACK:
        return True
    return False


def _copy(job, src, dst):
    while True:
        job.check()
        data = src.read(CHUNK)
        if not data:
            break
        dst.write(data)
        job.add(len(data))


# --- permissions after upload (Site Manager → Transfer Settings) ---
# job.upload_perms = (folder_mode, file_mode); either may be None = leave alone.

def _set_perm(job, sftp, path, which):
    perms = getattr(job, 'upload_perms', None)
    mode = perms and perms[which]
    if mode is None:
        return
    try:
        sftp.chmod(path, mode)
    except IOError as e:
        if not getattr(job, '_perm_warned', False):
            job._perm_warned = True
            job.log(f'Could not set permissions after upload ({e}); the server may not allow it.', 'warn')


def set_dir_perm(job, sftp, path):
    _set_perm(job, sftp, path, 0)


def set_file_perm(job, sftp, path):
    _set_perm(job, sftp, path, 1)


def upload_file(job, sftp, local, remote_path, policy='overwrite'):
    result = _upload_file(job, sftp, local, remote_path, policy)
    if result != 'skipped':  # skipped files are left exactly as they are
        set_file_perm(job, sftp, remote_path)
    return result


def _upload_file(job, sftp, local, remote_path, policy):
    size = os.path.getsize(local)
    job.current = os.path.basename(local)
    try:
        rst = sftp.stat(remote_path)
    except IOError:
        rst = None
    offset = 0
    if rst is not None:
        if _skip(policy, size, os.path.getmtime(local), rst.st_size, rst.st_mtime):
            job.add(size)
            return 'skipped'
        if policy == 'resume' and rst.st_size < size:
            offset = rst.st_size
    with open(local, 'rb') as f:
        f.seek(offset)
        with sftp.open(remote_path, 'r+b' if offset else 'wb') as rf:
            rf.set_pipelined(True)
            if offset:
                rf.seek(offset)
                job.add(offset)
            _copy(job, f, rf)
    st = os.stat(local)
    try:
        sftp.utime(remote_path, (st.st_atime, st.st_mtime))
    except IOError:
        pass
    return 'resumed' if offset else 'uploaded'


def download_file(job, sftp, remote_path, local, policy='overwrite'):
    rst = sftp.stat(remote_path)
    size = rst.st_size or 0
    job.current = posixpath.basename(remote_path)
    offset = 0
    if os.path.exists(local):
        lsize = os.path.getsize(local)
        if _skip(policy, size, rst.st_mtime or 0, lsize, os.path.getmtime(local)):
            job.add(size)
            return 'skipped'
        if policy == 'resume' and lsize < size:
            offset = lsize
    with sftp.open(remote_path, 'rb') as rf:
        if offset:
            rf.seek(offset)
            job.add(offset)
        rf.prefetch(size)
        with open(local, 'r+b' if offset else 'wb') as f:
            if offset:
                f.seek(offset)
            _copy(job, rf, f)
    try:
        os.utime(local, (rst.st_atime, rst.st_mtime))
    except OSError:
        pass
    return 'resumed' if offset else 'downloaded'


def _local_total(paths):
    total = 0
    for p in paths:
        if os.path.isdir(p):
            for d, _, files in os.walk(p):
                for f in files:
                    try:
                        total += os.path.getsize(os.path.join(d, f))
                    except OSError:
                        pass
        elif os.path.isfile(p):
            total += os.path.getsize(p)
    return total


def upload_paths(job, sftp, local_paths, remote_dir, policy='overwrite'):
    job.total += _local_total(local_paths)
    counts = {}
    mkdir_perm = lambda d: set_dir_perm(job, sftp, d)
    R.makedirs(sftp, remote_dir, mkdir_perm)
    for p in local_paths:
        job.check()
        name = os.path.basename(p.rstrip(os.sep))
        target = posixpath.join(remote_dir, name)
        if os.path.isdir(p):
            R.makedirs(sftp, target)
            set_dir_perm(job, sftp, target)
            for d, dirs, files in os.walk(p):
                job.check()
                rel = os.path.relpath(d, p)
                rdir = target if rel == '.' else posixpath.join(target, *rel.split(os.sep))
                for sub in dirs:
                    R.makedirs(sftp, posixpath.join(rdir, sub))
                    set_dir_perm(job, sftp, posixpath.join(rdir, sub))
                for f in files:
                    r = upload_file(job, sftp, os.path.join(d, f), posixpath.join(rdir, f), policy)
                    counts[r] = counts.get(r, 0) + 1
        else:
            r = upload_file(job, sftp, p, target, policy)
            counts[r] = counts.get(r, 0) + 1
    return counts


def download_paths(job, sftp, remote_paths, local_dir, policy='overwrite'):
    plan = []  # (remote, local, is_dir)
    for p in remote_paths:
        name = posixpath.basename(p.rstrip('/'))
        target = os.path.join(local_dir, name)
        if R.is_dir(sftp, p):
            plan.append((p, target, True))
            base = p.rstrip('/') + '/'
            for full, a in R.walk(sftp, p):
                job.check()
                rel = full[len(base):]
                d = stat.S_ISDIR(a.st_mode or 0)
                plan.append((full, os.path.join(target, *rel.split('/')), d))
                if not d:
                    job.total += a.st_size or 0
        else:
            plan.append((p, target, False))
            job.total += sftp.stat(p).st_size or 0
    os.makedirs(local_dir, exist_ok=True)
    counts = {}
    for rpath, lpath, d in plan:
        job.check()
        if d:
            os.makedirs(lpath, exist_ok=True)
        else:
            os.makedirs(os.path.dirname(lpath), exist_ok=True)
            r = download_file(job, sftp, rpath, lpath, policy)
            counts[r] = counts.get(r, 0) + 1
    return counts


def summary(counts, direction='upload'):
    labels = {'uploaded': 'uploaded', 'downloaded': 'downloaded', 'resumed': 'resumed',
              'skipped': 'skipped (already on the server)' if direction == 'upload' else 'skipped (already here)'}
    parts = [f'{counts[k]} {labels[k]}' for k in ('uploaded', 'downloaded', 'resumed', 'skipped') if counts.get(k)]
    return ', '.join(parts) if parts else 'nothing to do'
