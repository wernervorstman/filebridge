"""Application state and the JSON API used by the browser interface."""
import os
import posixpath
import threading
import time

from . import deploy, extract, localfs, perms, sync, system, transfer
from .common import ApiError
from .jobs import JobManager
from .plugins import PluginContext, PluginManager
from .ftp import FtpRemote
from .remote import Remote
from .sites import SiteStore


class App:
    def __init__(self, base):
        self.base = base
        self._log = []
        self._log_lock = threading.Lock()
        self.sites = SiteStore()
        self.jobs = JobManager(self.log)
        self.remote = None
        self.plugins = PluginManager(system.plugins_dir(), self.log)
        self.plugins.load()

    # --- plumbing ---
    def log(self, msg, level='info'):
        with self._log_lock:
            self._log.append({'t': time.strftime('%H:%M:%S'), 'level': level, 'msg': msg})
            del self._log[:-500]

    def call(self, name, body):
        fn = getattr(self, 'api_' + name, None)
        if not fn:
            raise ApiError(f'Unknown action: {name}')
        return fn(body) or {}

    def shutdown(self):
        self.jobs.cancel_all()
        if self.remote:
            self.remote.close()

    def need_remote(self):
        if not self.remote:
            raise ApiError('Not connected')
        if not self.remote.alive():
            self.remote.close()
            self.remote = None
            self.log('Connection lost', 'error')
            raise ApiError('Connection lost – please reconnect')
        return self.remote

    def _status(self):
        r = self.remote
        if r and r.alive():
            s = r.site
            proto = 'FTP' if s.get('protocol') == 'ftp' else 'SFTP'
            return {'connected': True, 'site_id': s['id'], 'protocol': proto,
                    'label': f'{s["username"] or "anonymous"}@{s["host"]} · {proto}',
                    'color': s.get('color') or '', 'can_exec': r._can_exec}
        return {'connected': False}

    def _max_connections(self, site):
        try:
            site = self.sites.get(site['id'])
        except ApiError:
            pass
        try:
            return max(1, min(10, int(site.get('max_connections') or 3)))
        except (TypeError, ValueError):
            return 3

    def _upload_perms(self, site):
        """(folder_mode, file_mode) to set after uploading, from the site's current settings."""
        try:
            site = self.sites.get(site['id'])  # pick up changes made while connected
        except ApiError:
            pass
        if not site.get('upload_perms'):
            return None
        conv = lambda v: int(str(v), 8) if str(v or '').strip() else None
        d, f = conv(site.get('upload_dir_mode')), conv(site.get('upload_file_mode'))
        return (d, f) if d is not None or f is not None else None

    def _job(self, kind, title, fn, refresh=(), remote=True):
        """Submit a job; remote jobs get their own SFTP channel."""
        if remote:
            r = self.need_remote()

            def run(job):
                job.upload_perms = self._upload_perms(r.site)
                job.new_client = r.new_sftp            # extra connections for parallel transfers
                job.parallel = self._max_connections(r.site)
                sftp = r.new_sftp()
                try:
                    return fn(job, sftp)
                finally:
                    sftp.close()
        else:
            def run(job):
                return fn(job, None)
        job = self.jobs.submit(kind, title, run, refresh)
        return {'job_id': job.id}

    # --- general ---
    def api_init(self, b):
        return {'home': os.path.expanduser('~'), 'sites': self.sites.list(), 'folders': self.sites.folders,
                'platform': {'file_manager': system.file_manager_name(), 'keychain': system.keychain_name(), 'window': system.WINDOW is not None,
                             'sep': os.sep},
                'plugins': self.plugins.list(), 'status': self._status(),
                'ignore': sync.DEFAULT_IGNORE}

    def api_jobs(self, b):
        with self._log_lock:
            log = list(self._log[-300:])
        return {'jobs': self.jobs.list(), 'log': log, 'status': self._status()}

    def api_job_cancel(self, b):
        self.jobs.cancel(b['id'])

    def api_jobs_clear(self, b):
        self.jobs.clear_finished()

    def api_reveal(self, b):
        """Show a local path in Finder / Explorer (default: the plugins folder)."""
        system.reveal(localfs.norm(b.get('path') or self.plugins.folder))

    def api_pick(self, b):
        """Native 'choose folder / choose file' dialog."""
        kind = 'file' if b.get('kind') == 'file' else 'folder'
        start = localfs.norm(b.get('start') or '~')
        while localfs.parent(start) and not os.path.isdir(start):
            start = localfs.parent(start)
        types = [t.strip().lstrip('.') for t in b.get('types') or [] if t.strip()]
        path = system.pick(kind, start, types, bool(b.get('invisibles')),
                           b.get('prompt') or ('Choose a file' if kind == 'file' else 'Choose a folder'))
        if path and len(path) > 1 and not path.endswith(':\\'):
            path = path.rstrip('/\\')
        return {'path': path or None}

    # --- sites ---
    def api_sites(self, b):
        return {'sites': self.sites.list(), 'folders': self.sites.folders}

    def api_sites_apply(self, b):
        """Site Manager OK/Connect: save all changes (new, edited, deleted sites and folders) at once."""
        ids = self.sites.apply(b.get('sites') or [], b.get('deleted') or [], b.get('folders') or [],
                               b.get('secrets') or {})
        self.log('Site Manager changes saved')
        return {'ids': ids, 'sites': self.sites.list(), 'folders': self.sites.folders}

    def api_site_save(self, b):
        site = self.sites.save(b['site'], b.get('password'), b.get('passphrase'))
        self.log(f'Site saved: {site["name"]}')
        return {'site': site, 'sites': self.sites.list()}

    def api_site_update(self, b):
        site = self.sites.update(b['id'], b.get('patch') or {})
        return {'site': site, 'sites': self.sites.list()}

    def api_site_delete(self, b):
        self.sites.delete(b['id'])
        return {'sites': self.sites.list()}

    def api_site_forget_password(self, b):
        self.sites.forget_password(b['id'])
        return {'sites': self.sites.list()}

    # --- connection ---
    def api_connect(self, b):
        site = self.sites.get(b['site_id'])
        auth = site.get('auth', 'password')
        password = b.get('password') or None
        passphrase = self.sites.get_secret(site['id'], 'passphrase')
        if auth == 'anonymous':
            site = {**site, 'username': 'anonymous'}
            password = 'anonymous@'
        elif auth in ('password', 'ask') and not password:
            if auth == 'password':
                password = self.sites.get_secret(site['id'], 'password')
            if not password:
                raise ApiError('NEED_PASSWORD' + ('_ASK' if auth == 'ask' else ''))
        if self.remote:
            self.api_disconnect({})
        is_ftp = site.get('protocol') == 'ftp'
        self.log(f'Connecting to {site["username"]}@{site["host"]}:{site.get("port")} '
                 f'({"FTP" if is_ftp else "SFTP"}) …')
        r = (FtpRemote if is_ftp else Remote)(site, password, passphrase)
        try:
            r.connect()
        except ApiError as e:
            if str(e).startswith('Login failed') and auth in ('password', 'ask'):
                self.log(f'Login failed for {site["username"]}@{site["host"]}', 'error')
                raise ApiError('NEED_PASSWORD:' + str(e))
            raise
        self.remote = r
        if b.get('password') and b.get('save') and auth == 'password':
            self.sites.save(site, password=b['password'])
        if r.new_host_key:
            self.log(f'New server – host key trusted and remembered: {r.fingerprint}', 'warn')
        self.log(f'Connected to {site["host"]} ({r.fingerprint})', 'ok')
        start = site.get('remote_dir') or ''
        try:
            path = r.list(start)[0] if start else r.home()
        except IOError:
            path = r.home()
        threading.Thread(target=r.can_exec, daemon=True).start()
        return {'status': self._status(), 'remote_path': path, 'sites': self.sites.list()}

    def api_disconnect(self, b):
        if self.remote:
            host = self.remote.site['host']
            self.remote.close()
            self.remote = None
            self.log(f'Disconnected from {host}')
        return {'status': self._status()}

    # --- browsing and file operations ---
    def api_list(self, b):
        if b['side'] == 'local':
            path, entries = localfs.list_dir(b.get('path'))
            return {'path': path, 'entries': entries, 'parent': localfs.parent(path)}
        else:
            try:
                path, entries = self.need_remote().list(b.get('path'))
            except IOError as e:
                raise ApiError(f'Cannot open {b.get("path")}: {e}')
        return {'path': path, 'entries': entries}

    def _join(self, side, d, name):
        if '/' in name or name in ('', '.', '..'):
            raise ApiError('Invalid name')
        return posixpath.join(d, name) if side == 'remote' else os.path.join(localfs.norm(d), name)

    def api_mkdir(self, b):
        path = self._join(b['side'], b['dir'], b['name'].strip())
        if b['side'] == 'local':
            try:
                localfs.mkdir(path)
            except FileExistsError:
                raise ApiError(f'"{b["name"]}" already exists')
        else:
            self.need_remote().mkdir(path)
        self.log(f'Created folder {path}')

    def api_rename(self, b):
        src = b['path']
        parent = posixpath.dirname(src) if b['side'] == 'remote' else os.path.dirname(src)
        dst = self._join(b['side'], parent, b['name'].strip())
        if b['side'] == 'local':
            localfs.rename(src, dst)
        else:
            self.need_remote().rename(src, dst)
        self.log(f'Renamed {src} → {dst}')

    def api_move(self, b):
        if b['side'] == 'local':
            localfs.move(b['paths'], b['dest'])
        else:
            self.need_remote().move(b['paths'], b['dest'])
        self.log(f'Moved {len(b["paths"])} item(s) to {b["dest"]}')

    def api_delete(self, b):
        paths = b['paths']
        if b['side'] == 'local':
            localfs.delete(paths)
            self.log(f'Moved {len(paths)} local item(s) to the Trash')
        else:
            self.need_remote().delete(paths)
            self.log(f'Deleted {len(paths)} item(s) on the server', 'warn')

    def api_chmod(self, b):
        """Change permissions: bits in `set` are switched on, bits in `clear` off, others kept per item."""
        side = b.get('side', 'remote')
        set_bits, clear_bits = int(b.get('set', 0)), int(b.get('clear', 0))
        if not (0 <= set_bits <= 0o7777 and 0 <= clear_bits <= 0o7777) or set_bits & clear_bits:
            raise ApiError('Invalid permissions')
        only_if = None
        if str(b.get('only_if') or '').strip():
            try:
                only_if = int(str(b['only_if']).strip(), 8)
                assert 0 <= only_if <= 0o7777
            except (ValueError, AssertionError):
                raise ApiError('"Only change items that currently have" must be octal, e.g. 777 or 0644')
        apply_to = b.get('apply_to') if b.get('apply_to') in ('all', 'files', 'dirs') else 'all'
        recursive = bool(b.get('recursive'))
        paths = b['paths']
        title = f'Permissions on {len(paths)} item(s){" + subfolders" if recursive else ""}'
        fn = lambda job, sftp: perms.chmod_job(job, side, sftp, paths, set_bits, clear_bits,
                                               recursive, apply_to, only_if)
        return self._job('chmod', title, fn, [side], remote=side == 'remote')

    # --- transfers ---
    def api_transfer(self, b):
        paths, dest = b['paths'], b['dest']
        policy = b.get('policy') if b.get('policy') in transfer.POLICIES else 'overwrite'
        n = len(paths)
        first = os.path.basename(paths[0].rstrip('/')) if n else ''
        what = f'"{first}"' if n == 1 else f'{n} items'
        if b['direction'] == 'upload':
            def fn(job, sftp):
                c = transfer.upload_paths(job, sftp, [localfs.norm(p) for p in paths], dest, policy)
                msg = f'Upload finished: {transfer.summary(c, "upload")}.'
                job.log(msg)
                return {'message': msg, 'counts': c}
            return self._job('upload', f'Upload {what} → {dest}', fn, ['remote'])

        def fn(job, sftp):
            c = transfer.download_paths(job, sftp, paths, localfs.norm(dest), policy)
            msg = f'Download finished: {transfer.summary(c, "download")}.'
            job.log(msg)
            return {'message': msg, 'counts': c}
        return self._job('download', f'Download {what} → {dest}', fn, ['local'])

    # --- compare & sync ---
    def api_compare(self, b):
        patterns = [p.strip() for p in (b.get('ignore') or '').split(',') if p.strip()]
        return self._job('compare', f'Compare {b["local"]} ↔ {b["remote"]}',
                         lambda job, sftp: sync.compare(job, sftp, b['local'], b['remote'], patterns))

    def api_sync(self, b):
        items = [i for i in b['items'] if i.get('action') in
                 ('upload', 'download', 'delete_remote', 'delete_local')]
        return self._job('sync', f'Sync {len(items)} item(s)',
                         lambda job, sftp: sync.apply(job, sftp, b['local_root'], b['remote_root'], items),
                         ['local', 'remote'])

    # --- extract zip ---
    def api_zip_info(self, b):
        """Contents of a zip (top folder + sample paths) for the Extract dialog preview."""
        zp = b['zip']
        if b.get('side') == 'local':
            try:
                return {'info': deploy.inspect(localfs.norm(zp))}
            except Exception as e:
                raise ApiError(f'Not a valid zip file: {e}')
        r = self.need_remote()
        if r.has_command('unzip'):
            names = extract._remote_names(r, zp)
            files = [n for n in names if not n.endswith('/') and not n.startswith('__MACOSX/')]
            return {'info': {'top_folder': deploy.top_folder(names), 'files': len(files), 'sample': files[:12]}}
        with r.lock:
            size = r.sftp.stat(zp).st_size or 0
        if size > 300 * 1024 * 1024:
            return {'info': None}
        import tempfile
        with tempfile.TemporaryDirectory(prefix='filebridge_') as td:
            lz = os.path.join(td, 'preview.zip')
            with r.lock:
                r.sftp.get(zp, lz) if hasattr(r.sftp, 'get') else self._ftp_fetch(r.sftp, zp, lz)
            return {'info': deploy.inspect(lz)}

    @staticmethod
    def _ftp_fetch(client, remote_path, local_path):
        with client.open(remote_path, 'rb') as rf, open(local_path, 'wb') as f:
            while True:
                data = rf.read(256 * 1024)
                if not data:
                    break
                f.write(data)

    def api_extract(self, b):
        """Upload & extract a local zip, or extract a zip that is already on the server."""
        r = self.need_remote()
        zp, dest = b['zip'], (b.get('dest') or '').strip()
        if not dest:
            raise ApiError('Choose the server folder to extract into')
        perms = None
        if b.get('perms'):
            conv = lambda v: int(str(v).strip(), 8) if str(v or '').strip() else None
            try:
                perms = (conv(b['perms'].get('dirs')), conv(b['perms'].get('files')))
                assert all(p is None or 0 <= p <= 0o7777 for p in perms)
            except (ValueError, AssertionError):
                raise ApiError('Permissions must be octal, e.g. 755 and 644')
            if perms == (None, None):
                perms = None
        local = b.get('side') == 'local'
        if local and not os.path.isfile(localfs.norm(zp)):
            raise ApiError(f'Zip not found: {zp}')
        kwargs = dict(
            dest=dest, into_folder=bool(b.get('into_folder')), strip=bool(b.get('strip', True)),
            policy='skip_exists' if b.get('policy') == 'skip_exists' else 'overwrite', perms=perms,
            delete_zip=bool(b.get('delete_zip')) and not local,
            method=b.get('method') if b.get('method') in ('auto', 'server', 'local') else 'auto',
            **({'zip_local': localfs.norm(zp)} if local else {'zip_remote': zp}))
        name = os.path.basename(zp)
        return self._job('extract', f'{"Upload & extract" if local else "Extract"} {name} → {dest}',
                         lambda job, sftp: extract.run(job, r, sftp, **kwargs), ['remote'])

    # --- deploy ---
    def api_deploy_preview(self, b):
        try:
            return {'info': deploy.inspect(deploy.resolve_zip(b.get('cfg') or {}))}
        except (ValueError, OSError) as e:
            raise ApiError(str(e))
        except Exception as e:
            raise ApiError(f'Not a valid zip file: {e}')

    def api_deploy(self, b):
        cfg = b.get('cfg') or {}
        r = self.need_remote()
        site_name = r.site['name']
        return self._job('deploy', f'Deploy to {r.site["host"]}:{cfg.get("remote_dir", "")}',
                         lambda job, sftp: deploy.run(job, r, sftp, cfg, site_name), ['remote'])

    # --- plugins ---
    def api_plugins(self, b):
        return {'plugins': self.plugins.list()}

    def api_plugins_reload(self, b):
        self.plugins.load()
        return {'plugins': self.plugins.list(), 'errors': self.plugins.errors}

    def api_plugin_run(self, b):
        action = self.plugins.get(b['id'])
        if not action:
            raise ApiError('Plugin action not found – try reloading plugins')
        side = b.get('side', 'local')
        needs_remote = side == 'remote' or action.get('side') == 'remote' or action.get('needs_connection')
        if needs_remote:
            self.need_remote()

        def fn(job, sftp):
            ctx = PluginContext(self, job, side, b.get('cwd'), b.get('paths') or [], b.get('input'), sftp)
            out = action['run'](ctx)
            return {'message': out} if isinstance(out, str) else out

        return self._job('plugin', f'{action["label"]}', fn, [side], remote=bool(self.remote))
