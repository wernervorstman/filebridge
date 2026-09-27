"""Compare a local folder with a remote folder and apply sync actions."""
import fnmatch
import os
import posixpath
import stat
from collections import Counter

from . import localfs, transfer
from . import remote as R

DEFAULT_IGNORE = ['.DS_Store', '.git', 'node_modules', '__pycache__', 'Thumbs.db', '.filebridge_*']
MTIME_TOLERANCE = 2  # seconds


def _ignored(name, patterns):
    return any(fnmatch.fnmatch(name, p) for p in patterns)


def scan_local(job, root, patterns):
    files = {}
    for d, dirs, names in os.walk(root):
        job.check()
        job.current = d
        dirs[:] = [x for x in dirs if not _ignored(x, patterns)]
        for n in names:
            if _ignored(n, patterns):
                continue
            full = os.path.join(d, n)
            try:
                st = os.stat(full)
            except OSError:
                continue
            files[os.path.relpath(full, root).replace(os.sep, '/')] = (st.st_size, st.st_mtime)
    return files


def scan_remote(job, sftp, root, patterns):
    files = {}
    stack = ['']
    while stack:
        job.check()
        rel = stack.pop()
        job.current = posixpath.join(root, rel)
        for a in sftp.listdir_attr(posixpath.join(root, rel) if rel else root):
            if _ignored(a.filename, patterns):
                continue
            r = f'{rel}/{a.filename}' if rel else a.filename
            mode = a.st_mode or 0
            if stat.S_ISLNK(mode):
                try:
                    a = sftp.stat(posixpath.join(root, r))
                    mode = a.st_mode
                except IOError:
                    continue
                if stat.S_ISDIR(mode):
                    continue
            if stat.S_ISDIR(mode):
                stack.append(r)
            elif stat.S_ISREG(mode):
                files[r] = (a.st_size or 0, a.st_mtime or 0)
    return files


def compare(job, sftp, local_root, remote_root, patterns):
    local_root = localfs.norm(local_root)
    if not os.path.isdir(local_root):
        raise ValueError(f'Local folder not found: {local_root}')
    if not R.is_dir(sftp, remote_root):
        raise ValueError(f'Remote folder not found: {remote_root}')
    L = scan_local(job, local_root, patterns)
    Rm = scan_remote(job, sftp, remote_root, patterns)
    rows = []
    for p in sorted(set(L) | set(Rm), key=str.lower):
        l, r = L.get(p), Rm.get(p)
        if l and not r:
            status = 'local_only'
        elif r and not l:
            status = 'remote_only'
        elif l[0] == r[0] and abs(l[1] - r[1]) <= MTIME_TOLERANCE:
            status = 'same'
        elif l[1] > r[1] + MTIME_TOLERANCE:
            status = 'local_newer'
        elif r[1] > l[1] + MTIME_TOLERANCE:
            status = 'remote_newer'
        else:
            status = 'different'
        rows.append({
            'path': p, 'status': status,
            'local_size': l[0] if l else None, 'local_mtime': l[1] if l else None,
            'remote_size': r[0] if r else None, 'remote_mtime': r[1] if r else None,
        })
    return {'rows': rows, 'local_root': local_root, 'remote_root': remote_root,
            'counts': dict(Counter(r['status'] for r in rows))}


def apply(job, sftp, local_root, remote_root, items):
    local_root = localfs.norm(local_root)
    for it in items:
        if it['action'] == 'upload':
            job.total += it.get('local_size') or 0
        elif it['action'] == 'download':
            job.total += it.get('remote_size') or 0
    # folders first (sequentially), then the files several at a time
    for it in items:
        if it['action'] == 'upload':
            p = it['path']
            if p.startswith('/') or '..' in p.split('/'):
                raise ValueError(f'Invalid path: {p}')
            R.makedirs(sftp, posixpath.dirname(posixpath.join(remote_root, p)),
                       lambda d: transfer.set_dir_perm(job, sftp, d))

    def work(client, it):
        job.check()
        p, action = it['path'], it['action']
        if p.startswith('/') or '..' in p.split('/'):
            raise ValueError(f'Invalid path: {p}')
        lp = os.path.join(local_root, *p.split('/'))
        rp = posixpath.join(remote_root, p)
        if action == 'upload':
            transfer.upload_file(job, client, lp, rp, 'overwrite')
        elif action == 'download':
            os.makedirs(os.path.dirname(lp), exist_ok=True)
            transfer.download_file(job, client, rp, lp, 'overwrite')
        elif action == 'delete_remote':
            client.remove(rp)
        elif action == 'delete_local':
            localfs.trash(lp)
        return action

    counts = Counter(transfer.run_parallel(job, sftp, [i for i in items if i['action'] in
                     ('upload', 'download', 'delete_remote', 'delete_local')], work))
    labels = {'upload': 'uploaded', 'download': 'downloaded',
              'delete_remote': 'deleted on server', 'delete_local': 'moved to Trash'}
    msg = ', '.join(f'{n} {labels[k]}' for k, n in counts.items()) or 'nothing to do'
    return {'message': f'Sync finished: {msg}.'}
