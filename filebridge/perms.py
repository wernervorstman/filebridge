"""Change permissions (chmod) the way FileZilla does: per bit set / clear / keep,
optionally recursive, for files only or folders only, and only on items that
currently have a given permission."""
import os
import posixpath
import stat

from . import localfs
from . import remote as R


def new_mode(old, set_bits, clear_bits):
    return ((old & ~clear_bits) | set_bits) & 0o7777


def _mode(attr):
    """Permission bits, or None when the (FTP) server didn't report them."""
    return (attr.st_mode or 0) & 0o7777 if getattr(attr, 'mode_known', True) else None


def _collect(job, side, sftp, paths, recursive):
    """Return [(path, is_dir, mode)] for the selection (and everything below it)."""
    items = []
    for p in paths:
        job.check()
        if side == 'remote':
            st = sftp.stat(p)
            is_dir = stat.S_ISDIR(st.st_mode or 0)
            items.append((p, is_dir, _mode(st)))
            if recursive and is_dir:
                for full, a in R.walk(sftp, p):
                    job.check()
                    job.current = posixpath.dirname(full)
                    items.append((full, stat.S_ISDIR(a.st_mode or 0), _mode(a)))
        else:
            p = localfs.norm(p)
            st = os.stat(p)
            is_dir = stat.S_ISDIR(st.st_mode)
            items.append((p, is_dir, st.st_mode & 0o7777))
            if recursive and is_dir:
                for d, dirs, files in os.walk(p):
                    job.check()
                    job.current = d
                    for n in dirs + files:
                        full = os.path.join(d, n)
                        lst = os.lstat(full)
                        if stat.S_ISLNK(lst.st_mode):
                            continue  # never follow links out of the folder
                        items.append((full, stat.S_ISDIR(lst.st_mode), lst.st_mode & 0o7777))
    return items


def chmod_job(job, side, sftp, paths, set_bits, clear_bits, recursive, apply_to, only_if):
    job.unit = 'items'
    job.current = 'scanning…'
    items = _collect(job, side, sftp, paths, recursive)
    job.total = len(items)
    changed = unchanged = filtered = unknown = 0
    all_bits_given = (set_bits | clear_bits) & 0o777 == 0o777
    for path, is_dir, mode in items:
        job.check()
        job.done += 1
        job.current = posixpath.basename(path) if side == 'remote' else os.path.basename(path)
        if (apply_to == 'files' and is_dir) or (apply_to == 'dirs' and not is_dir):
            filtered += 1
            continue
        if mode is None:
            # The server didn't tell us the current permissions: only safe when every bit is given.
            if only_if is not None or not all_bits_given:
                unknown += 1
                continue
            mode = 0
        if only_if is not None and mode != only_if:
            filtered += 1
            continue
        target = new_mode(mode, set_bits, clear_bits)
        if target == mode:
            unchanged += 1
            continue
        if side == 'remote':
            sftp.chmod(path, target)
        else:
            os.chmod(path, target)
        changed += 1
    msg = f'Permissions changed on {changed} item(s)'
    extra = []
    if unchanged:
        extra.append(f'{unchanged} already correct')
    if filtered:
        extra.append(f'{filtered} skipped by your filter')
    if unknown:
        extra.append(f'{unknown} skipped because the server does not report their current permissions')
    if extra:
        msg += f' ({", ".join(extra)})'
    job.log(msg)
    return {'message': msg + '.'}
