"""Example plugin: find files by name pattern on the server, or large files."""
import fnmatch
import posixpath
import stat

from filebridge import remote as R

NAME = 'Tools'


def find(ctx):
    pattern = (ctx.input or '*').strip()
    hits = []
    for full, a in R.walk(ctx.sftp, ctx.cwd):
        ctx.check_cancelled()
        ctx.progress(len(hits), current=posixpath.dirname(full))
        if fnmatch.fnmatch(posixpath.basename(full).lower(), pattern.lower()):
            hits.append(full + ('/' if stat.S_ISDIR(a.st_mode or 0) else ''))
            if len(hits) >= 1000:
                hits.append('… stopped after 1000 results')
                break
    return f'{len(hits)} match(es) for "{pattern}" in {ctx.cwd}\n\n' + '\n'.join(hits)


def largest(ctx):
    files = []
    for full, a in R.walk(ctx.sftp, ctx.cwd):
        ctx.check_cancelled()
        if stat.S_ISREG(a.st_mode or 0):
            files.append((a.st_size or 0, full))
    files.sort(reverse=True)
    lines = [f'{s / 1048576:10.1f} MB  {p}' for s, p in files[:30]]
    return f'Largest files in {ctx.cwd}\n\n' + '\n'.join(lines)


ACTIONS = [
    {'id': 'find', 'label': 'Find files by name…', 'side': 'remote', 'run': find,
     'ask': 'File name pattern (wildcards allowed), searched in the current folder and below',
     'default': '*.log'},
    {'id': 'largest', 'label': 'Show 30 largest files', 'side': 'remote', 'run': largest},
]
