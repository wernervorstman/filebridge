"""Operations on the local file system."""
import os
import shutil
import stat

from . import system
from .common import ApiError, make_entry
from .i18n import tr


def norm(path):
    return os.path.abspath(os.path.expanduser(path or '~'))


def list_dir(path):
    path = norm(path)
    if not os.path.isdir(path):
        raise ApiError(tr('Folder not found: {path}', path=path))
    entries = []
    try:
        it = os.scandir(path)
    except PermissionError:
        raise ApiError(system.permission_hint(path))
    with it:
        for e in it:
            try:
                st = e.stat(follow_symlinks=True)
            except OSError:
                st = e.stat(follow_symlinks=False)
            is_dir = stat.S_ISDIR(st.st_mode)
            entries.append(make_entry(e.name, os.path.join(path, e.name), is_dir,
                                      st.st_size, st.st_mtime, stat.filemode(st.st_mode),
                                      e.is_symlink(), st.st_mode))
    return path, entries


def parent(path):
    """Parent folder, or None at the top (/ or a drive such as C:\\)."""
    p = os.path.dirname(path.rstrip('/\\') or path)
    return None if not p or os.path.normcase(p) == os.path.normcase(path) else p


def mkdir(path):
    os.makedirs(norm(path), exist_ok=False)


def rename(src, dst):
    src, dst = norm(src), norm(dst)
    if os.path.exists(dst):
        raise ApiError(tr('"{name}" already exists', name=os.path.basename(dst)))
    os.rename(src, dst)


def move(paths, dest):
    dest = norm(dest)
    if not os.path.isdir(dest):
        raise ApiError(tr('Folder not found: {path}', path=dest))
    for p in paths:
        p = norm(p)
        target = os.path.join(dest, os.path.basename(p))
        if dest == p or dest.startswith(p + os.sep):
            raise ApiError(tr('Cannot move "{name}" into itself', name=os.path.basename(p)))
        if os.path.exists(target):
            raise ApiError(tr('"{name}" already exists in {dest}', name=os.path.basename(p), dest=dest))
        shutil.move(p, target)


def trash(path):
    """Move to the Trash / Recycle Bin (recoverable) instead of deleting permanently."""
    system.trash(norm(path))


def delete(paths):
    for p in paths:
        trash(p)
