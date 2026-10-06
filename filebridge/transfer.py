"""Uploads and downloads with progress, cancel, skip and resume.

Speed: on a connection with a lot of latency every command to the server costs a
round trip, so this module avoids them where it can (one listing per folder
instead of a check per file, no check at all when overwriting) and sends several
files at the same time over separate connections (job.parallel).
"""
import os
import posixpath
import queue
import stat
import threading
import time

from . import remote as R
from .i18n import tr

CHUNK = 256 * 1024
# overwrite   – always replace
# newer       – replace only when the source is newer or has a different size
# skip_same   – skip when the size is the same
# skip_exists – never touch a file that already exists at the destination
# resume      – continue a partial transfer
POLICIES = ('overwrite', 'newer', 'skip_same', 'skip_exists', 'resume')
MTIME_SLACK = 2  # seconds
UNKNOWN = object()  # "we haven't looked whether the destination exists"


class Limiter:
    """Speed limit shared by all transfers in one direction (token bucket)."""

    def __init__(self):
        self.rate = 0  # bytes per second, 0 = unlimited
        self.lock = threading.Lock()
        self.allowance = 0.0
        self.last = time.monotonic()

    def set(self, kb_per_s):
        with self.lock:
            self.rate = max(0, int(kb_per_s or 0)) * 1024
            self.allowance = float(self.rate)
            self.last = time.monotonic()

    def consume(self, n):
        while True:
            with self.lock:
                if not self.rate:
                    return
                now = time.monotonic()
                self.allowance = min(self.rate, self.allowance + (now - self.last) * self.rate)
                self.last = now
                if self.allowance >= n or self.allowance >= self.rate:
                    self.allowance -= n
                    return
                wait = (n - self.allowance) / self.rate
            time.sleep(min(wait, 0.5))


LIMIT = {'up': Limiter(), 'down': Limiter()}


def set_limits(up_kb, down_kb):
    LIMIT['up'].set(up_kb)
    LIMIT['down'].set(down_kb)


def _excluded(job, name):
    ex = getattr(job, 'exclude', None)
    return bool(ex and ex(name))


def _record_failure(job, direction, src, dst, err):
    """Remember a failed file so it can be retried; the rest of the job carries on."""
    with job._lock:
        job.failed.append({'direction': direction, 'src': src, 'dst': dst, 'error': str(err) or type(err).__name__})
    job.log(tr('Failed: {name} – {error}', name=posixpath.basename(dst) if direction == 'upload' else os.path.basename(dst), error=err), 'error')


def _skip(policy, src_size, src_mtime, dst_size, dst_mtime):
    if policy == 'skip_exists':
        return True
    if policy in ('skip_same', 'resume') and src_size == dst_size:
        return True
    if policy == 'newer' and src_size == dst_size and src_mtime <= (dst_mtime or 0) + MTIME_SLACK:
        return True
    return False


def _copy(job, src, dst, direction):
    limiter = LIMIT[direction]
    chunk = CHUNK if not limiter.rate else max(8192, min(CHUNK, limiter.rate // 4))
    while True:
        job.check()
        data = src.read(chunk)
        if not data:
            break
        limiter.consume(len(data))
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
            job.log(tr('Could not set permissions after upload ({error}); the server may not allow it.', error=e), 'warn')


def set_dir_perm(job, sftp, path):
    _set_perm(job, sftp, path, 0)


def set_file_perm(job, sftp, path):
    _set_perm(job, sftp, path, 1)


def upload_file(job, sftp, local, remote_path, policy='overwrite', existing=UNKNOWN):
    """existing: the remote file's attributes if already known (None = it doesn't exist)."""
    result = _upload_file(job, sftp, local, remote_path, policy, existing)
    if result != 'skipped':  # skipped files are left exactly as they are
        set_file_perm(job, sftp, remote_path)
    return result


def _upload_file(job, sftp, local, remote_path, policy, existing=UNKNOWN):
    size = os.path.getsize(local)
    job.current = os.path.basename(local)
    if policy == 'overwrite':
        rst = None  # replacing anyway: no need to ask the server first
    elif existing is not UNKNOWN:
        rst = existing
    else:
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
            _copy(job, f, rf, 'up')
    st = os.stat(local)
    try:
        sftp.utime(remote_path, (st.st_atime, st.st_mtime))
    except IOError:
        pass
    return 'resumed' if offset else 'uploaded'


def download_file(job, sftp, remote_path, local, policy='overwrite', rst=None):
    """rst: the remote file's attributes if already known from a listing."""
    if rst is None or not stat.S_ISREG(getattr(rst, 'st_mode', 0) or 0):
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
            _copy(job, rf, f, 'down')
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


def run_parallel(job, sftp, tasks, work):
    """Run work(client, task) for every task, spread over up to job.parallel connections.

    The first connection is the job's own and starts right away; extra ones are opened
    by job.new_client() at the same time (logging in costs several round trips), and
    simply join in when ready. Returns the results. The first error stops the others."""
    tasks = list(tasks)
    n = max(1, min(getattr(job, 'parallel', 1) or 1, len(tasks)))
    if n == 1 or not getattr(job, 'new_client', None):
        return [work(sftp, t) for t in tasks if not job.check()]
    q = queue.Queue()
    for t in tasks:
        q.put(t)
    results, errors, lock = [], [], threading.Lock()

    def worker(client):
        own = client is not None
        try:
            if not own:
                try:
                    client = job.new_client()
                except Exception as e:  # the server may limit connections – the others carry on
                    with lock:
                        if not getattr(job, '_conn_warned', False):
                            job._conn_warned = True
                            job.log(tr('Could not open an extra connection ({error}); continuing with fewer.', error=e), 'warn')
                    return
            while not errors:
                try:
                    t = q.get_nowait()
                except queue.Empty:
                    return
                r = work(client, t)
                with lock:
                    results.append(r)
        except BaseException as e:  # noqa: BLE001 – includes Cancelled
            with lock:
                errors.append(e)
        finally:
            if not own and client is not None:
                try:
                    client.close()
                except Exception:
                    pass

    threads = [threading.Thread(target=worker, args=(sftp,), daemon=True)]
    threads += [threading.Thread(target=worker, args=(None,), daemon=True) for _ in range(n - 1)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    if errors:
        raise errors[0]
    return results


class _Listings:
    """Remote folder listings, fetched once per folder, lazily and thread-safely."""

    def __init__(self):
        self.data, self.locks, self.lock = {}, {}, threading.Lock()

    def set_empty(self, path):
        with self.lock:
            self.data[path] = {}

    def get(self, client, path):
        with self.lock:
            if path in self.data:
                return self.data[path]
            lk = self.locks.setdefault(path, threading.Lock())
        with lk:  # only one worker lists a folder; the others wait for its result
            with self.lock:
                if path in self.data:
                    return self.data[path]
            listing = _listing(client, path)
            with self.lock:
                self.data[path] = listing
            return listing


def _count(results):
    counts = {}
    for r in results:
        counts[r] = counts.get(r, 0) + 1
    return counts


def _listing(sftp, path):
    """{name: attrs} of a remote folder (one round trip), or {} if it doesn't exist."""
    try:
        return {a.filename: a for a in sftp.listdir_attr(path)}
    except IOError:
        return {}


def upload_paths(job, sftp, local_paths, remote_dir, policy='overwrite'):
    job.total += _local_total(local_paths)
    need_listing = policy != 'overwrite'
    R.makedirs(sftp, remote_dir, lambda d: set_dir_perm(job, sftp, d))
    listings = _Listings()

    def ensure_dir(rdir):
        """Create rdir; if it already exists that's fine (1 round trip for a new folder)."""
        try:
            sftp.mkdir(rdir)
            listings.set_empty(rdir)  # brand new: nothing in it, no need to list it later
        except IOError:
            if not R.is_dir(sftp, rdir):
                raise
        set_dir_perm(job, sftp, rdir)

    # 1) folders first (parents before children), and the list of files to send
    tasks = []  # (local, remote folder, name)
    skip = getattr(job, 'skip_paths', None) or set()  # files the user chose to leave out
    for p in local_paths:
        job.check()
        name = os.path.basename(p.rstrip(os.sep))
        if _excluded(job, name) or p in skip:
            job.skipped_filtered += 1
            continue
        if os.path.isdir(p):
            target = posixpath.join(remote_dir, name)
            ensure_dir(target)
            for d, dirs, files in os.walk(p):
                job.check()
                kept = [x for x in dirs if not _excluded(job, x)]
                job.skipped_filtered += len(dirs) - len(kept)
                dirs[:] = kept  # don't walk into filtered folders
                rel = os.path.relpath(d, p)
                rdir = target if rel == '.' else posixpath.join(target, *rel.split(os.sep))
                for sub in dirs:
                    ensure_dir(posixpath.join(rdir, sub))
                for f in files:
                    if _excluded(job, f) or os.path.join(d, f) in skip:
                        job.skipped_filtered += 1
                    else:
                        tasks.append((os.path.join(d, f), rdir, f))
        else:
            tasks.append((p, remote_dir, name))

    # 2) the files, several at a time; folder listings only when the policy needs them
    def work(client, t):
        local, rdir, name = t
        remote_path = posixpath.join(rdir, name)
        try:
            existing = listings.get(client, rdir).get(name) if need_listing else UNKNOWN
            return upload_file(job, client, local, remote_path, policy, existing)
        except (OSError, EOFError) as e:  # this file failed – continue with the others
            if not os.path.exists(local):
                raise
            _record_failure(job, 'upload', local, remote_path, e)
            return 'failed'

    return _count(run_parallel(job, sftp, tasks, work))


def download_paths(job, sftp, remote_paths, local_dir, policy='overwrite'):
    tasks = []  # (remote, local, attrs)
    dirs = []
    for p in remote_paths:
        name = posixpath.basename(p.rstrip('/'))
        if _excluded(job, name):
            job.skipped_filtered += 1
            continue
        target = os.path.join(local_dir, name)
        st = sftp.stat(p)
        if stat.S_ISDIR(st.st_mode or 0):
            dirs.append(target)
            base = p.rstrip('/') + '/'
            for full, a in R.walk(sftp, p):
                job.check()
                rel = full[len(base):]
                if any(_excluded(job, part) for part in rel.split('/')):
                    job.skipped_filtered += 1
                    continue
                lpath = os.path.join(target, *rel.split('/'))
                if stat.S_ISDIR(a.st_mode or 0):
                    dirs.append(lpath)
                else:
                    tasks.append((full, lpath, a))
                    job.total += a.st_size or 0
        else:
            tasks.append((p, target, st))
            job.total += st.st_size or 0
    os.makedirs(local_dir, exist_ok=True)
    for d in dirs:
        os.makedirs(d, exist_ok=True)

    def work(client, t):
        try:
            os.makedirs(os.path.dirname(t[1]), exist_ok=True)
            return download_file(job, client, t[0], t[1], policy, t[2])
        except PermissionError:
            raise  # e.g. macOS blocks the folder: the whole job should explain that
        except (OSError, EOFError) as e:
            _record_failure(job, 'download', t[0], t[1], e)
            return 'failed'

    return _count(run_parallel(job, sftp, tasks, work))


def summary(counts, direction='upload'):
    labels = {'uploaded': '{n} uploaded', 'downloaded': '{n} downloaded', 'resumed': '{n} resumed',
              'skipped': '{n} skipped (already on the server)' if direction == 'upload' else '{n} skipped (already here)',
              'failed': '{n} FAILED'}
    parts = [tr(labels[k], n=counts[k]) for k in ('uploaded', 'downloaded', 'resumed', 'skipped', 'failed') if counts.get(k)]
    return ', '.join(parts) if parts else tr('nothing to do')
