"""One-click deploy: upload a zip and unpack it into a remote folder."""
import glob
import os
import posixpath
import shlex
import tempfile
import time
import zipfile

from . import transfer
from . import remote as R
from .i18n import tr

SKIP = ('__MACOSX', '.DS_Store')


def copy_contents_cmd(src, target, skip_existing=False):
    """Shell command that copies everything inside src into target (portable GNU/BSD cp).

    Copies the entries one by one instead of `cp -a src/. target/`, so the target
    folder's own permissions are never changed."""
    q = shlex.quote
    opt = '-n ' if skip_existing else ''
    on_err = '|| true' if skip_existing else '|| exit 1'  # cp -n may exit 1 when it skips
    return (f'for f in {q(src)}/* {q(src)}/.[!.]* {q(src)}/..?*; do [ -e "$f" ] || [ -L "$f" ] || continue; '
            f'cp -a {opt}"$f" {q(target)}/ {on_err}; done')


def top_folder(names):
    """The single top folder of a zip (e.g. "site/"), or None."""
    names = [n for n in names if not n.startswith('__MACOSX/') and os.path.basename(n.rstrip('/')) != '.DS_Store']
    tops = {n.split('/', 1)[0] for n in names}
    if len(tops) == 1:
        t = next(iter(tops))
        if all(n.startswith(t + '/') for n in names):
            return t
    return None


def resolve_zip(cfg):
    zp = (cfg.get('zip_path') or '').strip()
    if zp:
        zp = os.path.expanduser(zp)
        if not os.path.isfile(zp):
            raise ValueError(tr('Zip file not found: {path}', path=zp))
        return zp
    folder = os.path.expanduser((cfg.get('zip_folder') or '').strip())
    pattern = (cfg.get('zip_pattern') or '*.zip').strip()
    if not folder or not os.path.isdir(folder):
        raise ValueError(tr('Choose a zip file, or a folder to take the newest zip from.'))
    matches = [f for f in glob.glob(os.path.join(folder, pattern)) if os.path.isfile(f)]
    if not matches:
        raise ValueError(tr('No file matching "{pattern}" in {folder}', pattern=pattern, folder=folder))
    return max(matches, key=os.path.getmtime)


def inspect(zp):
    with zipfile.ZipFile(zp) as z:
        names = [n for n in z.namelist()
                 if not n.startswith('__MACOSX/') and os.path.basename(n.rstrip('/')) != '.DS_Store']
    files = [n for n in names if not n.endswith('/')]
    tops = {n.split('/', 1)[0] for n in names}
    top = None
    if len(tops) == 1:
        t = next(iter(tops))
        if all(n.startswith(t + '/') for n in names):
            top = t
    st = os.stat(zp)
    return {'zip': zp, 'name': os.path.basename(zp), 'size': st.st_size, 'mtime': st.st_mtime,
            'files': len(files), 'top_folder': top, 'sample': files[:12]}


def _backup(job, remote, sftp, remote_dir, ts, site_name):
    parent, name = posixpath.split(remote_dir.rstrip('/'))
    if not name:
        job.log(tr('Backup skipped: cannot back up the root folder.'), 'warn')
        return
    if remote.has_command('tar'):
        archive = f'{name}_backup_{ts}.tar.gz'
        rc, _, err = remote.exec(f'cd {shlex.quote(parent or "/")} && tar czf {shlex.quote(archive)} {shlex.quote(name)}',
                                 timeout=900)
        if rc == 0:
            job.log(tr('Backup created on server: {path}', path=posixpath.join(parent, archive)), 'ok')
            return
        job.log(tr('Server backup failed ({error}), downloading a copy instead.', error=err.strip()[:200]), 'warn')
    dest = os.path.join(os.path.expanduser('~/FileBridge backups'), site_name, f'{name}_{ts}')
    job.current = tr('backup')
    transfer.download_paths(job, sftp, [remote_dir], dest, 'overwrite')
    job.log(tr('Backup downloaded to {path}', path=dest), 'ok')


def run(job, remote, sftp, cfg, site_name):
    zp = resolve_zip(cfg)
    info = inspect(zp)
    remote_dir = (cfg.get('remote_dir') or '').strip().rstrip('/')
    if not remote_dir:
        raise ValueError(tr('Choose the remote folder to deploy to.'))
    remote_dir = sftp.normalize(remote_dir) if R.exists(sftp, remote_dir) else remote_dir
    strip_top = bool(cfg.get('strip', True) and info['top_folder'])
    method = cfg.get('method') or 'auto'
    ts = time.strftime('%Y%m%d_%H%M%S')

    has_unzip = method != 'local' and remote.has_command('unzip')
    if method == 'server' and not has_unzip:
        raise ValueError(tr('This server does not allow running "unzip" over SSH. Use method "Unpack locally".'))
    if method == 'auto':
        method = 'server' if has_unzip else 'local'
    how = tr('on the server') if method == 'server' else tr('locally')
    job.log(tr('Deploying {name} → {target} (unpacked {how})', name=info['name'], target=remote_dir, how=how)
            + (' – ' + tr('contents of {folder}/', folder=info['top_folder']) if strip_top else ''))

    R.makedirs(sftp, remote_dir, lambda d: transfer.set_dir_perm(job, sftp, d))
    if cfg.get('backup'):
        _backup(job, remote, sftp, remote_dir, ts, site_name)

    if method == 'server':
        zname, tmpname = f'.filebridge_deploy_{ts}.zip', f'.filebridge_tmp_{ts}'
        job.total += info['size']
        transfer.upload_file(job, sftp, zp, posixpath.join(remote_dir, zname), 'overwrite')
        src = f'{tmpname}/{info["top_folder"]}' if strip_top else tmpname
        q = shlex.quote
        cmd = (f'set -e; cd {q(remote_dir)}; mkdir -p {q(tmpname)}; unzip -oq {q(zname)} -d {q(tmpname)}; '
               f'rm -rf {q(tmpname + "/__MACOSX")}; ')
        perms = getattr(job, 'upload_perms', None)
        if perms and perms[0] is not None:
            cmd += f'find {q(src)} -type d -exec chmod {perms[0]:04o} {{}} +; '
        if perms and perms[1] is not None:
            cmd += f'find {q(src)} -type f -exec chmod {perms[1]:04o} {{}} +; '
        cmd += copy_contents_cmd(src, '.', skip_existing=False)
        job.current = tr('unpacking on the server')
        try:
            rc, _, err = remote.exec(cmd, timeout=900)
        finally:
            remote.exec(f'cd {q(remote_dir)} && rm -rf {q(tmpname)} {q(zname)}', timeout=300)
        if rc != 0:
            raise RuntimeError(tr('Unpacking on the server failed: {error}', error=err.strip()[:300]))
    else:
        with tempfile.TemporaryDirectory(prefix='filebridge_') as tmp:
            job.current = tr('unpacking on this computer')
            with zipfile.ZipFile(zp) as z:
                z.extractall(tmp)
            root = os.path.join(tmp, info['top_folder']) if strip_top else tmp
            sources = [os.path.join(root, n) for n in sorted(os.listdir(root)) if n not in SKIP]
            transfer.upload_paths(job, sftp, sources, remote_dir, 'overwrite')

    return {'message': tr('Deployed {name} to {target} ({n} files, unpacked on the server).' if method == 'server' else
                          'Deployed {name} to {target} ({n} files, unpacked locally and uploaded).',
                          name=info['name'], target=remote_dir, n=info['files'])}
