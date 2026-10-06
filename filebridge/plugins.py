"""Plugin loader. Every .py file in the plugins/ folder can add actions.

See plugins/README.md for how to write one.
"""
import importlib.util
import os
import traceback

from . import transfer
from .i18n import tr


class PluginContext:
    """What a plugin action gets to work with."""

    def __init__(self, app, job, side, cwd, paths, value, sftp):
        self.app = app
        self.job = job
        self.side = side          # 'local' or 'remote' – the pane it was started from
        self.cwd = cwd            # current folder of that pane
        self.paths = paths        # selected paths (full paths)
        self.input = value        # answer to the plugin's `ask` question, if any
        self.sftp = sftp          # paramiko SFTPClient (None when not connected)
        self.remote = app.remote  # filebridge.remote.Remote (None when not connected)
        self.site = app.remote.site if app.remote else None

    def log(self, msg, level='info'):
        self.app.log(f'[plugin] {msg}', level)

    def progress(self, done, total=None, current=None):
        self.job.done = done
        if total is not None:
            self.job.total = total
        if current is not None:
            self.job.current = current

    def check_cancelled(self):
        self.job.check()

    def exec(self, cmd, timeout=120):
        """Run a shell command on the server. Returns (exit_code, stdout, stderr)."""
        if not self.remote:
            raise RuntimeError('Not connected')
        return self.remote.exec(cmd, timeout)

    def upload(self, local_paths, remote_dir, policy='overwrite'):
        return transfer.upload_paths(self.job, self.sftp, local_paths, remote_dir, policy)

    def download(self, remote_paths, local_dir, policy='overwrite'):
        return transfer.download_paths(self.job, self.sftp, remote_paths, local_dir, policy)


class PluginManager:
    def __init__(self, folder, log):
        self.folder = folder
        self.log = log
        self.actions = {}
        self.errors = []

    def load(self):
        self.actions, self.errors = {}, []
        os.makedirs(self.folder, exist_ok=True)
        for fn in sorted(os.listdir(self.folder)):
            if not fn.endswith('.py') or fn.startswith('_'):
                continue
            mod_name = fn[:-3]
            try:
                spec = importlib.util.spec_from_file_location(f'fb_plugin_{mod_name}',
                                                              os.path.join(self.folder, fn))
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                for a in getattr(mod, 'ACTIONS', []):
                    aid = f'{mod_name}.{a["id"]}'
                    self.actions[aid] = {**a, 'id': aid, 'plugin': getattr(mod, 'NAME', mod_name)}
            except Exception as e:
                self.errors.append(f'{fn}: {e}')
                self.log(tr('Plugin {file} failed to load: {error}', file=fn, error=e) + f'\n{traceback.format_exc(limit=2)}', 'error')
        self.log(tr('Loaded {n} plugin action(s)', n=len(self.actions)))

    def list(self):
        out = []
        for a in self.actions.values():
            out.append({
                'id': a['id'], 'label': a['label'], 'plugin': a['plugin'],
                'side': a.get('side', 'any'), 'ask': a.get('ask'), 'default': a.get('default', ''),
                'confirm': a.get('confirm'), 'needs_selection': bool(a.get('needs_selection')),
                'description': a.get('description', ''),
            })
        return sorted(out, key=lambda a: (a['plugin'].lower(), a['label'].lower()))

    def get(self, aid):
        return self.actions.get(aid)
