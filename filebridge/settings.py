"""App-wide settings (not per site): filename filters, speed limits, editing."""
import fnmatch
import json
import os

from .common import CONF_DIR, ApiError

DEFAULTS = {
    # Filename filters (like FileZilla's Directory listing filters)
    'filters_enabled': True,
    'filters': ['.DS_Store', 'Thumbs.db', 'desktop.ini', '__MACOSX', '.git', '.svn', 'node_modules', '__pycache__'],
    'filters_hide': True,        # hide matching items in the file lists
    'filters_transfer': True,    # never upload/download matching items
    # Speed limits in KB/s, 0 = unlimited
    'limit_up': 0,
    'limit_down': 0,
    # View/Edit
    'editor': '',                # empty = the system's default text editor
    'edit_auto_upload': False,   # upload edited files without asking
    # Updates
    'check_updates': True,       # look on GitHub for a newer FileBridge at startup
}


class Settings:
    def __init__(self):
        os.makedirs(CONF_DIR, mode=0o700, exist_ok=True)
        self.path = os.path.join(CONF_DIR, 'settings.json')
        self.data = dict(DEFAULTS)
        try:
            with open(self.path) as f:
                self.data.update({k: v for k, v in json.load(f).items() if k in DEFAULTS})
        except (FileNotFoundError, ValueError):
            pass

    def get(self, key):
        return self.data.get(key, DEFAULTS.get(key))

    def all(self):
        return dict(self.data)

    def update(self, patch):
        clean = {}
        for k, v in (patch or {}).items():
            if k not in DEFAULTS:
                continue
            if k == 'filters':
                v = [p.strip() for p in (v if isinstance(v, list) else str(v).split(',')) if p and p.strip()]
            elif k in ('limit_up', 'limit_down'):
                try:
                    v = max(0, int(v or 0))
                except (TypeError, ValueError):
                    raise ApiError('Speed limits must be a number of KB/s (0 = unlimited)')
            elif isinstance(DEFAULTS[k], bool):
                v = bool(v)
            else:
                v = str(v or '').strip()
            clean[k] = v
        self.data.update(clean)
        tmp = self.path + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(self.data, f, indent=2)
        os.replace(tmp, self.path)
        return self.all()

    # --- filters ---
    def _matches(self, name):
        return any(fnmatch.fnmatch(name, p) for p in self.get('filters'))

    def hidden(self, name):
        """True when a name should be hidden in the file lists."""
        return bool(self.get('filters_enabled') and self.get('filters_hide') and self._matches(name))

    def excluded(self, name):
        """True when a name should never be transferred."""
        return bool(self.get('filters_enabled') and self.get('filters_transfer') and self._matches(name))
