"""Extract a zip into a server folder: a local zip (Upload & extract) or a zip already on the server.

On a server that allows SSH commands with `unzip`, the zip is unpacked on the server.
Otherwise (FTP, or SFTP without SSH commands) it is unpacked on this computer and the files
are uploaded. Either way the chosen permissions are set on the extracted folders/files.
"""
import os
import posixpath
import shlex
import tempfile
import time
import zipfile

from . import deploy, transfer
from . import remote as R
from .i18n import tr


def _remote_names(remote, zip_path):
    rc, out, err = remote.exec(f'unzip -Z1 {shlex.quote(zip_path)}', timeout=300)
    if rc != 0:
        raise RuntimeError(tr('Cannot read the zip on the server: {error}', error=(err or out).strip()[:200]))
    return [n for n in out.splitlines() if n.strip()]


def run(job, remote, sftp, *, dest, zip_local=None, zip_remote=None, into_folder=False, strip=True,
        policy='overwrite', perms=None, delete_zip=False, method='auto'):
    zip_name = os.path.basename(zip_local) if zip_local else posixpath.basename(zip_remote)
    base = zip_name[:-4] if zip_name.lower().endswith('.zip') else zip_name
    target = posixpath.join(dest, base) if into_folder else dest
    job.upload_perms = perms  # this job uses the permissions chosen in the dialog
    skip = policy == 'skip_exists'

    has_unzip = method != 'local' and remote.has_command('unzip')
    if method == 'server' and not has_unzip:
        raise ValueError(tr('This server cannot run "unzip" (FTP, or SSH commands are not allowed). '
                            'Choose "On this computer, then upload".'))
    R.makedirs(sftp, target, lambda d: transfer.set_dir_perm(job, sftp, d))
    ts = time.strftime('%Y%m%d_%H%M%S')

    if has_unzip:
        q = shlex.quote
        temp_zip = bool(zip_local)
        if zip_local:
            rzip = posixpath.join(target, f'.filebridge_upload_{ts}.zip')
            job.total += os.path.getsize(zip_local)
            transfer._upload_file(job, sftp, zip_local, rzip, 'overwrite')
        else:
            rzip = zip_remote
        tmp = posixpath.join(target, f'.filebridge_extract_{ts}')
        try:
            job.current = tr('reading zip')
            names = _remote_names(remote, rzip)
            top = deploy.top_folder(names) if strip else None
            src = posixpath.join(tmp, top) if top else tmp
            cmd = f'set -e; mkdir -p {q(tmp)}; unzip -oq {q(rzip)} -d {q(tmp)}; rm -rf {q(tmp + "/__MACOSX")}; '
            if perms and perms[0] is not None:
                cmd += f'find {q(src)} -type d -exec chmod {perms[0]:04o} {{}} +; '
            if perms and perms[1] is not None:
                cmd += f'find {q(src)} -type f -exec chmod {perms[1]:04o} {{}} +; '
            cmd += deploy.copy_contents_cmd(src, target, skip_existing=skip)
            job.current = tr('unpacking on the server')
            rc, _, err = remote.exec(cmd, timeout=1800)
            if rc != 0:
                raise RuntimeError(tr('Unpacking on the server failed: {error}', error=err.strip()[:300]))
        finally:
            remote.exec(f'rm -rf {q(tmp)}' + (f' {q(rzip)}' if temp_zip else ''), timeout=300)
        files = len([n for n in names if not n.endswith('/') and not n.startswith('__MACOSX/')])
        how = tr('{n} file(s), unpacked on the server', n=files) + (', ' + tr('existing files kept') if skip else '')
    else:
        with tempfile.TemporaryDirectory(prefix='filebridge_') as td:
            if zip_remote:
                lz = os.path.join(td, 'archive.zip')
                job.total += sftp.stat(zip_remote).st_size or 0
                job.current = tr('downloading zip')
                transfer.download_file(job, sftp, zip_remote, lz, 'overwrite')
            else:
                lz = zip_local
            info = deploy.inspect(lz)
            out = os.path.join(td, 'x')
            job.current = tr('unpacking on this computer')
            with zipfile.ZipFile(lz) as z:
                z.extractall(out)  # extractall refuses absolute and ../ paths
            root = os.path.join(out, info['top_folder']) if strip and info['top_folder'] else out
            sources = [os.path.join(root, n) for n in sorted(os.listdir(root)) if n not in deploy.SKIP]
            counts = transfer.upload_paths(job, sftp, sources, target, policy)
        how = transfer.summary(counts, 'upload')

    if delete_zip and zip_remote:
        sftp.remove(zip_remote)
        how += '; ' + tr('zip deleted')
    msg = tr('Extracted {name} into {target}: {how}.', name=zip_name, target=target, how=how)
    job.log(msg, 'ok')
    return {'message': msg}
