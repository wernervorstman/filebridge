"""Shared helpers: file entries, config location, errors."""
import os


CONF_DIR = os.path.expanduser('~/.filebridge')


class ApiError(Exception):
    """An error with a message that is safe and useful to show in the UI."""


def ext_of(name, is_dir):
    if is_dir:
        return ''
    base, ext = os.path.splitext(name)
    return ext[1:].lower() if base else ''


def make_entry(name, path, is_dir, size, mtime, perms, link=False, mode=None):
    return {
        'name': name,
        'path': path,
        'dir': bool(is_dir),
        'size': None if is_dir else (size or 0),
        'mtime': mtime or 0,
        'perms': perms,
        'mode': None if mode is None else mode & 0o7777,
        'ext': ext_of(name, is_dir),
        'link': bool(link),
        'hidden': name.startswith('.'),
    }
