"""Application state and the JSON API used by the browser interface."""
import os
import posixpath
import threading
import time

from . import __version__, deploy, diagnose, extract, filezilla_import, localfs, perms, sync, system, transfer, webinfo
from .editing import EditManager
from .settings import Settings
from .common import ApiError, LoginFailed
from .i18n import tr
from .jobs import JobManager
from .plugins import PluginContext, PluginManager
from .ftp import FtpRemote, FtpTimeout
from .remote import Remote
from .sites import SiteStore


class App:
    def __init__(self, base):
        self.base = base
        self._log = []
        self._log_lock = threading.Lock()
        self.sites = SiteStore()
        self.settings = Settings()
        transfer.set_limits(self.settings.get('limit_up'), self.settings.get('limit_down'))
        self.jobs = JobManager(self.log)
        self.conns = {}        # tab id -> Remote/FtpRemote (one per tab)
        self.active = None     # tab id of the tab shown in the server pane
        self._tab_seq = 0
        self.plugins = PluginManager(system.plugins_dir(), self.log)
        self.plugins.load()
        self.edits = EditManager(self)
        self.quit_hook = None  # set by the launcher: closes the window (app) or stops the server (browser)

    # --- plumbing ---
    def log(self, msg, level='info'):
        with self._log_lock:
            self._log.append({'t': time.strftime('%H:%M:%S'), 'level': level, 'msg': msg})
            del self._log[:-500]
            self._log_to_file(level, msg)

    LOG_FILE = os.path.join(os.path.expanduser('~/.filebridge'), 'filebridge.log')

    def _log_to_file(self, level, msg):
        """Keep the log on disk too (at most ~2 MB in two files), so a problem can be looked up after closing."""
        try:
            path = self.LOG_FILE
            if os.path.exists(path) and os.path.getsize(path) > 1024 * 1024:
                os.replace(path, path + '.1')
            with open(path, 'a', encoding='utf-8') as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {level.upper():5} {msg}\n")
        except OSError:
            pass  # the log on screen still works

    def call(self, name, body):
        fn = getattr(self, 'api_' + name, None)
        if not fn:
            raise ApiError(tr('Unknown action: {name}', name=name))
        return fn(body) or {}

    @property
    def remote(self):
        """The connection of the active tab (None when no tab is open)."""
        return self.conns.get(self.active)

    def shutdown(self):
        self.jobs.cancel_all()
        for r in list(self.conns.values()):
            r.close()

    def _close_tab(self, tab_id):
        r = self.conns.pop(tab_id, None)
        if r:
            r.close()
        if self.active == tab_id:
            self.active = next(reversed(self.conns), None) if self.conns else None
        return r

    def need_remote(self):
        r = self.remote
        if not r:
            raise ApiError(tr('Not connected'))
        if not r.alive():
            self._close_tab(self.active)
            self.log(tr('Connection to {host} lost', host=r.site['host']), 'error')
            raise ApiError(tr('Connection lost – please reconnect'))
        return r

    @staticmethod
    def _describe(r):
        s = r.site
        proto = 'FTP' if s.get('protocol') == 'ftp' else 'SFTP'
        return {'site_id': s['id'], 'protocol': proto, 'name': s.get('name') or s['host'],
                'label': f'{s["username"] or "anonymous"}@{s["host"]} · {proto}',
                'color': s.get('color') or '', 'can_exec': r._can_exec}

    def _status(self):
        tabs = [{'id': tid, **self._describe(r)} for tid, r in self.conns.items()]
        r = self.remote
        if r and r.alive():
            return {'connected': True, 'tab': self.active, 'tabs': tabs, **self._describe(r)}
        return {'connected': False, 'tabs': tabs}

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

    def _job(self, kind, title, fn, refresh=(), remote=True, conn=None):
        """Submit a job; remote jobs get their own SFTP channel (on `conn`, default the active connection)."""
        if remote:
            r = conn or self.need_remote()

            def run(job):
                job.exclude = self.settings.excluded
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
                'plugins': self.plugins.list(), 'status': self._status(), 'settings': self.settings.all(),
                'version': __version__, 'log_file': self.LOG_FILE,
                'ignore': sync.DEFAULT_IGNORE}

    def api_jobs(self, b):
        with self._log_lock:
            log = list(self._log[-300:])
        return {'jobs': self.jobs.list(), 'log': log, 'status': self._status(), 'edits': self.edits.list()}

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

    # --- web: public folders, web addresses, updates ---
    def api_risk_check(self, b):
        """Before an upload: is the destination public, and are there risky files (zip, sql, …)?"""
        r = self.remote
        site = r.site if r else {}
        dest = b.get('dest') or ''
        public = webinfo.is_public(site, dest)
        risky = webinfo.risky_local([localfs.norm(p) for p in b.get('paths') or []], self.settings.excluded) if public else []
        return {'public': public, 'url': webinfo.web_url(site, dest), 'risky': risky[:500], 'count': len(risky)}

    def api_open_url(self, b):
        url = str(b.get('url') or '')
        if not url.lower().startswith(('http://', 'https://')):
            raise ApiError(tr('Only web addresses can be opened'))
        import webbrowser
        webbrowser.open(url)

    def api_quit(self, b):
        """Close FileBridge (Quit button). Runs a moment later so this answer still reaches the page."""
        if not self.quit_hook:
            raise ApiError(tr('Quitting is not available here'))

        def later():
            time.sleep(0.3)
            self.quit_hook()
        threading.Thread(target=later, daemon=True).start()

    def api_update_check(self, b):
        if not self.settings.get('check_updates') and not b.get('force'):
            return {'update': None}
        return {'update': webinfo.check_update(force=bool(b.get('force')))}

    # --- View/Edit ---
    def api_edit_open(self, b):
        """Download a server file and open it in the editor; changes are offered for upload."""
        r = self.need_remote()
        try:
            return {'id': self.edits.start(r, b['path'])}
        except (OSError, EOFError) as e:
            raise ApiError(tr('Could not open {name} for editing: {error}', name=posixpath.basename(b['path']), error=e))

    def api_edit_upload(self, b):
        try:
            return self.edits.upload(b['id'])
        except ValueError as e:
            raise ApiError(str(e))

    def api_edit_discard(self, b):
        self.edits.discard(b['id'])

    def api_edit_stop(self, b):
        self.edits.stop(b['id'])

    def api_open_local(self, b):
        """Open a local file with its default app, or in the text editor (edit=True)."""
        path = localfs.norm(b['path'])
        if not os.path.isfile(path):
            raise ApiError(tr('Not a file'))
        if b.get('edit'):
            system.edit_file(path, self.settings.get('editor'))
        else:
            system.open_file(path)

    # --- app settings (filters, speed limits, editing) ---
    def api_settings(self, b):
        return {'settings': self.settings.all()}

    def api_settings_save(self, b):
        s = self.settings.update(b.get('settings') or {})
        transfer.set_limits(s['limit_up'], s['limit_down'])
        self.log(tr('Settings saved'))
        return {'settings': s}

    # --- retry failed files ---
    def api_job_retry(self, b):
        old = self.jobs.get(b['id'])
        if not old or not old.failed:
            raise ApiError(tr('Nothing to retry'))
        items = list(old.failed)

        def fn(job, sftp):
            def work(client, it):
                job.check()
                try:
                    if it['direction'] == 'upload':
                        transfer.R.makedirs(client, posixpath.dirname(it['dst']))
                        return transfer.upload_file(job, client, it['src'], it['dst'], 'overwrite')
                    os.makedirs(os.path.dirname(it['dst']), exist_ok=True)
                    return transfer.download_file(job, client, it['src'], it['dst'], 'overwrite')
                except (OSError, EOFError) as e:
                    transfer._record_failure(job, it['direction'], it['src'], it['dst'], e)
                    return 'failed'
            for it in items:
                if it['direction'] == 'upload' and os.path.exists(it['src']):
                    job.total += os.path.getsize(it['src'])
            c = transfer._count(transfer.run_parallel(job, sftp, items, work))
            msg = tr('Retry finished: {summary}.', summary=transfer.summary(c, items[0]['direction']))
            job.log(msg)
            return {'message': msg}

        old.failed = []  # handed over to the retry job
        return self._job('retry', tr('Retry {n} failed file(s)', n=len(items)), fn, list(old.refresh))

    # --- import from FileZilla ---
    def api_filezilla_read(self, b):
        data = filezilla_import.read(b.get('path'))
        existing = {(s['host'].lower(), (s.get('username') or '').lower(), s.get('protocol', 'sftp')) for s in self.sites.list()}
        out = []
        for i, item in enumerate(data['sites']):
            s = item['site']
            out.append({'index': i, 'site': s, 'has_password': bool(item['password']),
                        'password_note': item['password_note'],
                        'exists': (s['host'].lower(), s['username'].lower(), s['protocol']) in existing})
        self._fz_cache = data
        return {'path': data['path'], 'sites': out, 'skipped': data['skipped']}

    def api_filezilla_import(self, b):
        data = getattr(self, '_fz_cache', None)
        if not data:
            raise ApiError(tr('Read the FileZilla site list first'))
        chosen = set(b.get('indexes') or [])
        imported = []
        for i, item in enumerate(data['sites']):
            if i not in chosen:
                continue
            site = dict(item['site'])
            if not site.get('username') and site.get('auth') != 'anonymous':
                site['username'] = '?'
            saved = self.sites.save(site, password=item['password'] or None)
            imported.append(saved['name'])
        self._fz_cache = None  # don't keep passwords in memory
        self.log(tr('Imported {n} site(s) from FileZilla', n=len(imported)), 'ok')
        return {'imported': imported, 'sites': self.sites.list(), 'folders': self.sites.folders}

    # --- sites ---
    def api_sites(self, b):
        return {'sites': self.sites.list(), 'folders': self.sites.folders}

    def api_sites_apply(self, b):
        """Site Manager OK/Connect: save all changes (new, edited, deleted sites and folders) at once."""
        ids = self.sites.apply(b.get('sites') or [], b.get('deleted') or [], b.get('folders') or [],
                               b.get('secrets') or {})
        self.log(tr('Site Manager changes saved'))
        return {'ids': ids, 'sites': self.sites.list(), 'folders': self.sites.folders}

    def api_site_save(self, b):
        site = self.sites.save(b['site'], b.get('password'), b.get('passphrase'))
        self.log(tr('Site saved: {name}', name=site['name']))
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
        if b.get('quick'):
            site = self._quick_site(b['quick'])
        else:
            site = self.sites.get(b['site_id'])
        auth = site.get('auth', 'password')
        password = b.get('password') or (b.get('quick') or {}).get('password') or None
        passphrase = self.sites.get_secret(site['id'], 'passphrase')
        if auth == 'anonymous':
            site = {**site, 'username': 'anonymous'}
            password = 'anonymous@'
        elif auth in ('password', 'ask') and not password:
            if auth == 'password':
                password = self.sites.get_secret(site['id'], 'password')
            if not password:
                raise ApiError('NEED_PASSWORD' + ('_ASK' if auth == 'ask' else ''))
        is_ftp = site.get('protocol') == 'ftp'
        self.log(tr('Connecting to {user}@{host}:{port} ({protocol}) …', user=site['username'], host=site['host'],
                    port=site.get('port'), protocol='FTP' if is_ftp else 'SFTP'))
        r = (FtpRemote if is_ftp else Remote)(site, password, passphrase)
        try:
            try:
                r.connect()
            except FtpTimeout as e:
                if not site.get('fallback_sftp'):
                    raise
                r = self._sftp_fallback(site, password, passphrase, e)
        except ApiError as e:
            if isinstance(e, LoginFailed) and auth in ('password', 'ask'):
                said = e.server_reply
                self.log(tr('Login failed for {user}@{host}', user=site['username'], host=site['host'])
                         + (' – ' + tr('server: {reply}', reply=said) if said else ''), 'error')
                raise ApiError('NEED_PASSWORD:' + str(e))
            raise
        self._tab_seq += 1
        tab_id = f't{self._tab_seq}'
        self.conns[tab_id] = r          # every connection opens in its own tab
        self.active = tab_id
        if b.get('password') and b.get('save') and auth == 'password':
            self.sites.save(site, password=b['password'])
        if r.new_host_key:
            self.log(tr('New server – host key trusted and remembered: {key}', key=r.fingerprint), 'warn')
        self.log(tr('Connected to {host} ({key})', host=site['host'], key=r.fingerprint), 'ok')
        start = site.get('remote_dir') or ''
        try:
            path = r.list(start)[0] if start else r.home()
        except IOError:
            path = r.home()
        threading.Thread(target=r.can_exec, daemon=True).start()
        return {'status': self._status(), 'remote_path': path, 'sites': self.sites.list()}

    def _sftp_fallback(self, site, password, passphrase, ftp_error):
        """FTP didn't answer (blocked network?): connect to the same server with SFTP instead."""
        port = int(site.get('fallback_port') or 22)
        alt = {**site, 'protocol': 'sftp', 'port': port, 'username': site.get('fallback_user') or site['username'],
               'auth': 'password' if site.get('auth') in ('password', 'ask') else site.get('auth')}
        self.log(tr('FTP did not answer – trying SFTP on port {port} as {user} …', port=port, user=alt['username']), 'warn')
        r = Remote(alt, password, passphrase)
        try:
            r.connect()
        except ApiError as e:  # not a password prompt: the FTP password may simply not work for SSH
            raise ApiError(f'{ftp_error} ' + tr('The SFTP fallback (port {port}) failed too: {error}', port=port, error=e))
        return r

    def api_site_test(self, b):
        """Site Manager → Test connection: try the form's settings step by step (nothing is saved)."""
        raw = dict(b.get('site') or {})
        raw['name'] = raw.get('name') or 'test'
        site = self.sites.clean(raw)
        site['id'] = raw.get('id') or 'test'
        sid = b.get('site_id')
        password = b.get('password') or (self.sites.get_secret(sid, 'password') if sid else None)
        passphrase = b.get('passphrase') or (self.sites.get_secret(sid, 'passphrase') if sid else None)
        self.log(tr('Testing connection to {host} …', host=site['host']))
        return diagnose.test_connection(site, password, passphrase, (Remote, FtpRemote))

    def api_panel_detect(self, b):
        panel = diagnose.detect_panel(b.get('host'))
        return {'panel': panel, 'name': diagnose.PANEL_NAMES.get(panel, ''),
                'hint': tr(diagnose.USERNAME_HINT[panel]) if panel else '',
                'suggest': diagnose.username_suggestion(panel, b.get('username'))}

    @staticmethod
    def _quick_site(q):
        """A temporary site for the Quickconnect bar (never saved)."""
        host = (q.get('host') or '').strip()
        if not host:
            raise ApiError(tr('Fill in a host'))
        protocol, encryption = 'sftp', 'auto'
        for prefix, proto, enc in (('sftp://', 'sftp', 'auto'), ('ftps://', 'ftp', 'implicit'),
                                   ('ftpes://', 'ftp', 'explicit'), ('ftp://', 'ftp', 'auto')):
            if host.lower().startswith(prefix):
                host, protocol, encryption = host[len(prefix):], proto, enc
                break
        else:
            port = str(q.get('port') or '').strip()
            if port in ('21', '990'):
                protocol, encryption = 'ftp', 'implicit' if port == '990' else 'auto'
        host = host.rstrip('/')
        try:
            port = int(q.get('port') or 0) or (22 if protocol == 'sftp' else 990 if encryption == 'implicit' else 21)
        except ValueError:
            raise ApiError(tr('Port must be a number'))
        user = (q.get('username') or '').strip()
        return {'id': 'quick', 'name': f'{user}@{host}' if user else host, 'host': host, 'port': port,
                'username': user or 'anonymous', 'protocol': protocol, 'encryption': encryption,
                'auth': 'password' if user else ('anonymous' if protocol == 'ftp' else 'password'),
                'charset': 'auto', 'transfer_mode': 'default'}

    def api_disconnect(self, b):
        """Close a tab (default: the active one)."""
        r = self._close_tab(b.get('tab') or self.active)
        if r:
            self.log(tr('Disconnected from {host}', host=r.site['host']))
        return {'status': self._status()}

    def api_tab_switch(self, b):
        if b.get('tab') not in self.conns:
            raise ApiError(tr('This tab is closed'))
        self.active = b['tab']
        return {'status': self._status()}

    # --- browsing and file operations ---
    def api_list(self, b):
        if b['side'] == 'local':
            path, entries = localfs.list_dir(b.get('path'))
            extra = {'parent': localfs.parent(path)}
        else:
            try:
                path, entries = self.need_remote().list(b.get('path'))
            except IOError as e:
                raise ApiError(tr('Cannot open {path}: {error}', path=b.get('path'), error=e))
            extra = {}
        shown = [e for e in entries if not self.settings.hidden(e['name'])]
        return {'path': path, 'entries': shown, 'filtered': len(entries) - len(shown), **extra}

    def _join(self, side, d, name):
        if '/' in name or name in ('', '.', '..'):
            raise ApiError(tr('Invalid name'))
        return posixpath.join(d, name) if side == 'remote' else os.path.join(localfs.norm(d), name)

    def api_mkdir(self, b):
        path = self._join(b['side'], b['dir'], b['name'].strip())
        if b['side'] == 'local':
            try:
                localfs.mkdir(path)
            except FileExistsError:
                raise ApiError(tr('"{name}" already exists', name=b['name']))
        else:
            self.need_remote().mkdir(path)
        self.log(tr('Created folder {path}', path=path))

    def api_rename(self, b):
        src = b['path']
        parent = posixpath.dirname(src) if b['side'] == 'remote' else os.path.dirname(src)
        dst = self._join(b['side'], parent, b['name'].strip())
        if b['side'] == 'local':
            localfs.rename(src, dst)
        else:
            self.need_remote().rename(src, dst)
        self.log(tr('Renamed {src} → {dst}', src=src, dst=dst))

    def api_move(self, b):
        if b['side'] == 'local':
            localfs.move(b['paths'], b['dest'])
        else:
            self.need_remote().move(b['paths'], b['dest'])
        self.log(tr('Moved {n} item(s) to {dest}', n=len(b['paths']), dest=b['dest']))

    def api_delete(self, b):
        paths = b['paths']
        if b['side'] == 'local':
            localfs.delete(paths)
            self.log(tr('Moved {n} local item(s) to the Trash', n=len(paths)))
        else:
            self.need_remote().delete(paths)
            self.log(tr('Deleted {n} item(s) on the server', n=len(paths)), 'warn')

    def api_chmod(self, b):
        """Change permissions: bits in `set` are switched on, bits in `clear` off, others kept per item."""
        side = b.get('side', 'remote')
        set_bits, clear_bits = int(b.get('set', 0)), int(b.get('clear', 0))
        if not (0 <= set_bits <= 0o7777 and 0 <= clear_bits <= 0o7777) or set_bits & clear_bits:
            raise ApiError(tr('Invalid permissions'))
        only_if = None
        if str(b.get('only_if') or '').strip():
            try:
                only_if = int(str(b['only_if']).strip(), 8)
                assert 0 <= only_if <= 0o7777
            except (ValueError, AssertionError):
                raise ApiError(tr('"Only change items that currently have" must be octal, e.g. 777 or 0644'))
        apply_to = b.get('apply_to') if b.get('apply_to') in ('all', 'files', 'dirs') else 'all'
        recursive = bool(b.get('recursive'))
        paths = b['paths']
        title = tr('Permissions on {n} item(s) + subfolders' if recursive else 'Permissions on {n} item(s)', n=len(paths))
        fn = lambda job, sftp: perms.chmod_job(job, side, sftp, paths, set_bits, clear_bits,
                                               recursive, apply_to, only_if)
        return self._job('chmod', title, fn, [side], remote=side == 'remote')

    # --- transfers ---
    def api_transfer(self, b):
        paths, dest = b['paths'], b['dest']
        policy = b.get('policy') if b.get('policy') in transfer.POLICIES else 'overwrite'
        n = len(paths)
        first = os.path.basename(paths[0].rstrip('/')) if n else ''
        what = f'"{first}"' if n == 1 else tr('{n} items', n=n)
        skip = {localfs.norm(p) for p in b.get('skip') or []}
        if b['direction'] == 'upload':
            def fn(job, sftp):
                job.skip_paths = skip
                c = transfer.upload_paths(job, sftp, [localfs.norm(p) for p in paths], dest, policy)
                msg = tr('Upload finished: {summary}.', summary=transfer.summary(c, 'upload'))
                job.log(msg)
                return {'message': msg, 'counts': c}
            return self._job('upload', tr('Upload {what} → {dest}', what=what, dest=dest), fn, ['remote'])

        def fn(job, sftp):
            c = transfer.download_paths(job, sftp, paths, localfs.norm(dest), policy)
            msg = tr('Download finished: {summary}.', summary=transfer.summary(c, 'download'))
            job.log(msg)
            return {'message': msg, 'counts': c}
        return self._job('download', tr('Download {what} → {dest}', what=what, dest=dest), fn, ['local'])

    # --- compare & sync ---
    def api_compare(self, b):
        patterns = [p.strip() for p in (b.get('ignore') or '').split(',') if p.strip()]
        return self._job('compare', tr('Compare {local} ↔ {remote}', local=b['local'], remote=b['remote']),
                         lambda job, sftp: sync.compare(job, sftp, b['local'], b['remote'], patterns))

    def api_sync(self, b):
        items = [i for i in b['items'] if i.get('action') in
                 ('upload', 'download', 'delete_remote', 'delete_local')]
        return self._job('sync', tr('Sync {n} item(s)', n=len(items)),
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
                raise ApiError(tr('Not a valid zip file: {error}', error=e))
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
            raise ApiError(tr('Choose the server folder to extract into'))
        perms = None
        if b.get('perms'):
            conv = lambda v: int(str(v).strip(), 8) if str(v or '').strip() else None
            try:
                perms = (conv(b['perms'].get('dirs')), conv(b['perms'].get('files')))
                assert all(p is None or 0 <= p <= 0o7777 for p in perms)
            except (ValueError, AssertionError):
                raise ApiError(tr('Permissions must be octal, e.g. 755 and 644'))
            if perms == (None, None):
                perms = None
        local = b.get('side') == 'local'
        if local and not os.path.isfile(localfs.norm(zp)):
            raise ApiError(tr('Zip not found: {path}', path=zp))
        kwargs = dict(
            dest=dest, into_folder=bool(b.get('into_folder')), strip=bool(b.get('strip', True)),
            policy='skip_exists' if b.get('policy') == 'skip_exists' else 'overwrite', perms=perms,
            delete_zip=bool(b.get('delete_zip')) and not local,
            method=b.get('method') if b.get('method') in ('auto', 'server', 'local') else 'auto',
            **({'zip_local': localfs.norm(zp)} if local else {'zip_remote': zp}))
        name = os.path.basename(zp)
        return self._job('extract', tr('Upload & extract {name} → {dest}' if local else 'Extract {name} → {dest}', name=name, dest=dest),
                         lambda job, sftp: extract.run(job, r, sftp, **kwargs), ['remote'])

    # --- deploy ---
    def api_deploy_preview(self, b):
        try:
            return {'info': deploy.inspect(deploy.resolve_zip(b.get('cfg') or {}))}
        except (ValueError, OSError) as e:
            raise ApiError(str(e))
        except Exception as e:
            raise ApiError(tr('Not a valid zip file: {error}', error=e))

    def api_deploy(self, b):
        cfg = b.get('cfg') or {}
        r = self.need_remote()
        site_name = r.site['name']
        return self._job('deploy', tr('Deploy to {host}:{folder}', host=r.site['host'], folder=cfg.get('remote_dir', '')),
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
            raise ApiError(tr('Plugin action not found – try reloading plugins'))
        side = b.get('side', 'local')
        needs_remote = side == 'remote' or action.get('side') == 'remote' or action.get('needs_connection')
        if needs_remote:
            self.need_remote()

        def fn(job, sftp):
            ctx = PluginContext(self, job, side, b.get('cwd'), b.get('paths') or [], b.get('input'), sftp)
            out = action['run'](ctx)
            return {'message': out} if isinstance(out, str) else out

        return self._job('plugin', f'{action["label"]}', fn, [side], remote=bool(self.remote))
