"""Example plugin: calculate the total size of the selection (or current folder)."""
import os

from filebridge import remote as R

NAME = 'Tools'


def _fmt(n):
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if n < 1024 or unit == 'TB':
            return f'{n:.1f} {unit}' if unit != 'B' else f'{n} B'
        n /= 1024


def folder_size(ctx):
    paths = ctx.paths or [ctx.cwd]
    lines, grand = [], 0
    for p in paths:
        total = files = 0
        ctx.progress(0, current=p)
        if ctx.side == 'remote':
            if R.is_dir(ctx.sftp, p):
                for _, a in R.walk(ctx.sftp, p):
                    ctx.check_cancelled()
                    if not (a.st_mode or 0) & 0o040000:
                        total += a.st_size or 0
                        files += 1
            else:
                total, files = ctx.sftp.stat(p).st_size, 1
        else:
            if os.path.isdir(p):
                for d, _, names in os.walk(p):
                    ctx.check_cancelled()
                    for n in names:
                        try:
                            total += os.path.getsize(os.path.join(d, n))
                            files += 1
                        except OSError:
                            pass
            else:
                total, files = os.path.getsize(p), 1
        grand += total
        lines.append(f'{_fmt(total):>10}  {files:>7} files  {p}')
    if len(paths) > 1:
        lines.append(f'{_fmt(grand):>10}  total')
    return '\n'.join(lines)


ACTIONS = [
    {'id': 'size', 'label': 'Calculate size', 'side': 'any', 'run': folder_size,
     'description': 'Total size and file count of the selection, including subfolders.'},
]
