"""View/Edit: open a server file in your editor and upload it again when you save it.

The file is downloaded to a temporary folder and opened in the editor from the
settings (or the system's text editor). A watcher notices when you save it; then
FileBridge asks whether to upload it (or does so automatically, if chosen in Settings).
"""
import os
import posixpath
import shutil
import threading
import time
import uuid

from . import system, transfer
from .jobs import Job

KEEP_DAYS = 7


class EditManager:
    def __init__(self, app):
        self.app = app
        self.items = {}
        self.lock = threading.Lock()
        self.dir = os.path.join(system.user_data_dir(), 'edit')
        os.makedirs(self.dir, exist_ok=True)
        self._cleanup()
        threading.Thread(target=self._watch, daemon=True).start()

    def _cleanup(self):
        """Remove temporary copies of edits older than a week."""
        limit = time.time() - KEEP_DAYS * 86400
        for name in os.listdir(self.dir):
            p = os.path.join(self.dir, name)
            try:
                if os.path.getmtime(p) < limit:
                    shutil.rmtree(p, ignore_errors=True)
            except OSError:
                pass

    def start(self, remote, remote_path):
        eid = uuid.uuid4().hex[:10]
        folder = os.path.join(self.dir, eid)
        os.makedirs(folder)
        local = os.path.join(folder, posixpath.basename(remote_path))
        job = Job('edit', 'download for editing', self.app.log)
        client = remote.new_sftp()
        try:
            transfer.download_file(job, client, remote_path, local, 'overwrite')
        finally:
            client.close()
        item = {'id': eid, 'name': posixpath.basename(remote_path), 'remote_path': remote_path, 'local': local,
                'remote': remote, 'site': remote.site.get('name', remote.site['host']),
                'mtime': os.path.getmtime(local), 'state': 'watching', 'error': None}
        with self.lock:
            self.items[eid] = item
        system.edit_file(local, self.app.settings.get('editor'))
        self.app.log(f'Editing {remote_path} – save the file in your editor to upload it again')
        return eid

    def _watch(self):
        while True:
            time.sleep(1)
            with self.lock:
                items = list(self.items.values())
            for it in items:
                if it['state'] != 'watching':
                    continue
                try:
                    m = os.path.getmtime(it['local'])
                except OSError:
                    continue
                if m != it['mtime']:
                    it['mtime'] = m
                    if self.app.settings.get('edit_auto_upload'):
                        self.upload(it['id'])
                    else:
                        it['state'] = 'changed'

    def upload(self, eid):
        it = self.items.get(eid)
        if not it:
            raise ValueError('This edit is no longer open')
        if not it['remote'].alive():
            it['state'] = 'changed'
            raise ValueError(f'Not connected to {it["site"]} anymore – reconnect, then upload again')
        it['state'] = 'uploading'
        it['error'] = None

        def fn(job, sftp):
            try:
                transfer.upload_file(job, sftp, it['local'], it['remote_path'], 'overwrite')
                it['mtime'] = os.path.getmtime(it['local'])
                it['state'] = 'watching'
                msg = f'Uploaded your changes to {it["remote_path"]}'
                job.log(msg, 'ok')
                return {'message': msg}
            except Exception as e:
                it['state'] = 'changed'
                it['error'] = str(e)
                raise

        return self.app._job('edit-upload', f'Upload edited {it["name"]} → {posixpath.dirname(it["remote_path"])}',
                             fn, ['remote'], conn=it['remote'])

    def discard(self, eid):
        it = self.items.get(eid)
        if it:
            it['state'] = 'watching'

    def stop(self, eid):
        with self.lock:
            it = self.items.pop(eid, None)
        if it:
            shutil.rmtree(os.path.dirname(it['local']), ignore_errors=True)

    def list(self):
        with self.lock:
            return [{k: it[k] for k in ('id', 'name', 'remote_path', 'site', 'state', 'error')}
                    for it in self.items.values()]
