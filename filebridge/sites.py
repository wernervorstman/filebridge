"""Site Manager storage: settings in ~/.filebridge/sites.json, secrets in the system keychain
(macOS Keychain, Windows Credential Manager, or the Secret Service keyring on Linux)."""
import codecs
import json
import os
import uuid

from .common import CONF_DIR, ApiError
from .i18n import tr

try:
    import keyring
except ImportError:  # pragma: no cover
    keyring = None

SERVICE = 'FileBridge'
FIELDS = ('id', 'name', 'folder', 'protocol', 'host', 'port', 'encryption', 'auth', 'username', 'key_path',
          'color', 'comments', 'local_dir', 'remote_dir', 'transfer_mode', 'charset', 'ftps_insecure',
          'upload_perms', 'upload_dir_mode', 'upload_file_mode', 'max_connections', 'web_map',
          'bookmarks', 'deploy', 'has_password', 'has_passphrase', 'fallback_sftp', 'fallback_port',
          'fallback_user')
PROTOCOLS = ('sftp', 'ftp')
ENCRYPTIONS = ('auto', 'explicit', 'implicit', 'plain')
AUTHS = {'sftp': ('password', 'ask', 'key', 'agent'), 'ftp': ('password', 'ask', 'anonymous')}
COLORS = ('', 'red', 'green', 'blue', 'yellow', 'cyan', 'magenta')


def default_port(site):
    if site.get('protocol') == 'ftp':
        return 990 if site.get('encryption') == 'implicit' else 21
    return 22


class SiteStore:
    def __init__(self):
        os.makedirs(CONF_DIR, mode=0o700, exist_ok=True)
        self.path = os.path.join(CONF_DIR, 'sites.json')
        self.folders_path = os.path.join(CONF_DIR, 'folders.json')
        self.sites = self._load(self.path)
        self.folders = self._load(self.folders_path)
        self._session_secrets = {}  # used only if the Keychain is unavailable

    @staticmethod
    def _load(path):
        try:
            with open(path) as f:
                return json.load(f)
        except (FileNotFoundError, ValueError):
            return []

    @staticmethod
    def _write(path, data):
        tmp = path + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(data, f, indent=2)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)

    def _save(self):
        self._write(self.path, self.sites)
        used = {s.get('folder') for s in self.sites if s.get('folder')}
        self.folders = sorted(set(self.folders) | used, key=str.lower)
        self._write(self.folders_path, self.folders)

    def list(self):
        return sorted(self.sites, key=lambda s: ((s.get('folder') or '').lower(), s.get('name', '').lower()))

    def get(self, site_id):
        for s in self.sites:
            if s['id'] == site_id:
                return s
        raise ApiError(tr('Site not found'))

    def clean(self, site):
        """Validate a site and return only known fields (raises ApiError)."""
        c = {k: site.get(k) for k in FIELDS if k in site}
        for k in ('name', 'host', 'username', 'folder', 'key_path', 'local_dir', 'remote_dir', 'comments', 'charset'):
            c[k] = (c.get(k) or '').strip() if k != 'comments' else (c.get(k) or '')
        label = f'"{c["name"]}"' if c['name'] else tr('a site')
        if not c['name']:
            raise ApiError(tr('Every site needs a name'))
        c['protocol'] = c.get('protocol') if c.get('protocol') in PROTOCOLS else 'sftp'
        c['encryption'] = c.get('encryption') if c.get('encryption') in ENCRYPTIONS else 'auto'
        if c.get('auth') not in AUTHS[c['protocol']]:
            c['auth'] = 'password'
        if not c['host']:
            raise ApiError(tr('Please fill in the host for {site}', site=label))
        if not c['username'] and c['auth'] != 'anonymous':
            raise ApiError(tr('Please fill in the user for {site}', site=label))
        try:
            c['port'] = int(c.get('port') or default_port(c))
            assert 0 < c['port'] < 65536
        except (ValueError, AssertionError):
            raise ApiError(tr('The port of {site} must be a number between 1 and 65535', site=label))
        if c['auth'] == 'key' and not c['key_path']:
            raise ApiError(tr('Choose a key file for {site}', site=label))
        c['color'] = c.get('color') if c.get('color') in COLORS else ''
        c['transfer_mode'] = c.get('transfer_mode') if c.get('transfer_mode') in ('default', 'active', 'passive') else 'default'
        if c['charset'] not in ('', 'auto', 'utf-8'):
            try:
                codecs.lookup(c['charset'])
            except LookupError:
                raise ApiError(tr('Unknown character set "{charset}" for {site}', charset=c['charset'], site=label))
        c['charset'] = c['charset'] or 'auto'
        c['ftps_insecure'] = bool(c.get('ftps_insecure'))
        c['fallback_sftp'] = bool(c.get('fallback_sftp')) and c['protocol'] == 'ftp'
        c['fallback_user'] = (c.get('fallback_user') or '').strip()
        try:
            c['fallback_port'] = int(c.get('fallback_port') or 22)
            assert 0 < c['fallback_port'] < 65536
        except (ValueError, AssertionError):
            raise ApiError(tr('The SFTP fallback port of {site} must be a number between 1 and 65535', site=label))
        c['upload_perms'] = bool(c.get('upload_perms'))
        from .webinfo import clean_web_map
        c['web_map'] = clean_web_map(c.get('web_map') or [])
        try:
            c['max_connections'] = max(1, min(10, int(c.get('max_connections') or 3)))
        except (TypeError, ValueError):
            raise ApiError(tr('Simultaneous transfers for {site} must be a number from 1 to 10', site=label))
        for k, what in (('upload_dir_mode', 'folders'), ('upload_file_mode', 'files')):
            v = str(c.get(k) or '').strip()
            if v:
                try:
                    n = int(v, 8)
                    assert 0 <= n <= 0o7777
                except (ValueError, AssertionError):
                    raise ApiError(tr('The upload permission for {what} of {site} must be octal, e.g. 755 or 644', what=tr(what), site=label))
                v = f'{n:04o}'
            c[k] = v
        c.setdefault('bookmarks', [])
        c.setdefault('deploy', {})
        if not c.get('bookmarks'):
            c['bookmarks'] = []
        if not c.get('deploy'):
            c['deploy'] = {}
        return c

    def save(self, site, password=None, passphrase=None, copy_secrets_from=None):
        clean = self.clean(site)
        old = None
        if clean.get('id'):
            old = next((s for s in self.sites if s['id'] == clean['id']), None)
        if not old:
            clean['id'] = uuid.uuid4().hex[:12]
        src = old or (next((s for s in self.sites if s['id'] == copy_secrets_from), None) if copy_secrets_from else None)
        clean['has_password'] = bool(src and src.get('has_password'))
        clean['has_passphrase'] = bool(src and src.get('has_passphrase'))
        if src and not old:  # duplicate: copy the saved secrets too
            for kind in ('password', 'passphrase'):
                v = self.get_secret(src['id'], kind)
                if v:
                    self.set_secret(clean['id'], kind, v)
        if clean['auth'] in ('ask', 'anonymous'):
            self.delete_secret(clean['id'], 'password')
            clean['has_password'] = False
        elif password:
            self.set_secret(clean['id'], 'password', password)
            clean['has_password'] = True
        if passphrase:
            self.set_secret(clean['id'], 'passphrase', passphrase)
            clean['has_passphrase'] = True
        if old:
            self.sites[self.sites.index(old)] = clean
        else:
            self.sites.append(clean)
        self._save()
        return clean

    def apply(self, sites, deleted, folders, secrets):
        """Save all Site Manager changes at once (OK / Connect). Returns {temp id: real id}."""
        sites = [s for s in sites if s.get('id') not in deleted]
        cleaned = [self.clean(s) for s in sites]  # validate everything before changing anything
        for sid in deleted:
            if any(s['id'] == sid for s in self.sites):
                self.delete(sid)
        ids = {}
        for raw, c in zip(sites, cleaned):
            sec = secrets.get(raw.get('id') or '', {})
            temp = raw.get('id') or ''
            if temp.startswith('new-'):
                c.pop('id', None)
            saved = self.save(c, sec.get('password'), sec.get('passphrase'), raw.get('copy_from'))
            ids[temp] = saved['id']
        self.folders = sorted({f.strip() for f in folders if f and f.strip()}, key=str.lower)
        self._save()
        return ids

    def update(self, site_id, patch):
        site = self.get(site_id)
        for k in ('bookmarks', 'deploy', 'local_dir', 'remote_dir'):
            if k in patch:
                site[k] = patch[k]
        self._save()
        return site

    def delete(self, site_id):
        self.sites = [s for s in self.sites if s['id'] != site_id]
        self._save()
        for kind in ('password', 'passphrase'):
            self.delete_secret(site_id, kind)

    def forget_password(self, site_id):
        site = self.get(site_id)
        self.delete_secret(site_id, 'password')
        site['has_password'] = False
        self._save()

    # --- secrets ---
    def set_secret(self, site_id, kind, value):
        key = f'{site_id}:{kind}'
        if keyring:
            try:
                keyring.set_password(SERVICE, key, value)
                return
            except Exception:
                pass
        self._session_secrets[key] = value

    def get_secret(self, site_id, kind):
        key = f'{site_id}:{kind}'
        if key in self._session_secrets:
            return self._session_secrets[key]
        if keyring:
            try:
                return keyring.get_password(SERVICE, key)
            except Exception:
                return None
        return None

    def delete_secret(self, site_id, kind):
        key = f'{site_id}:{kind}'
        self._session_secrets.pop(key, None)
        if keyring:
            try:
                keyring.delete_password(SERVICE, key)
            except Exception:
                pass
