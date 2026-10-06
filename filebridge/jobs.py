"""Background jobs (transfers, compare, deploy, plugins) with progress and cancel."""
import threading
import time
import uuid
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor

from . import i18n
from .i18n import tr


class Cancelled(Exception):
    pass


class Job:
    def __init__(self, kind, title, log):
        self.id = uuid.uuid4().hex[:10]
        self.kind = kind
        self.title = title
        self.status = 'queued'
        self.total = 0
        self.done = 0
        self.current = ''
        self.error = None
        self.result = None
        self.refresh = []
        self.unit = 'bytes'  # or 'items' (progress counts items, not bytes)
        self.created = time.time()
        self.started = None
        self.finished = None
        self._cancel = threading.Event()
        self._log = log
        self._lock = threading.Lock()   # several transfer threads may update progress
        self.new_client = None          # opens an extra connection (for parallel transfers)
        self.parallel = 1               # max simultaneous transfers for this job
        self.exclude = None             # name -> True when filtered (never transferred)
        self.skipped_filtered = 0
        self.failed = []                # files that failed: [{direction, src, dst, error}]
        self.retry_of = None

    def log(self, msg, level='info'):
        self._log(msg, level)

    def add(self, n):
        with self._lock:
            self.done += n

    def check(self):
        if self._cancel.is_set():
            raise Cancelled()

    def to_dict(self):
        end = self.finished or time.time()
        elapsed = (end - self.started) if self.started else 0
        return {
            'id': self.id, 'kind': self.kind, 'title': self.title, 'status': self.status,
            'total': self.total, 'done': self.done, 'current': self.current,
            'error': self.error, 'result': self.result, 'refresh': self.refresh, 'unit': self.unit,
            'failed': len(self.failed),
            'speed': (self.done / elapsed) if elapsed > 0.5 else 0,
        }


class JobManager:
    def __init__(self, log, workers=2):
        self._log = log
        self.jobs = OrderedDict()
        self.pool = ThreadPoolExecutor(max_workers=workers)
        self.lock = threading.Lock()

    def submit(self, kind, title, fn, refresh=()):
        job = Job(kind, title, self._log)
        job.refresh = list(refresh)
        job.lang = i18n.current()  # the job speaks the language of the request that started it
        with self.lock:
            self.jobs[job.id] = job
        self.pool.submit(self._run, job, fn)
        return job

    def _run(self, job, fn):
        i18n.use(getattr(job, 'lang', 'en'))
        if job._cancel.is_set():
            job.status = 'cancelled'
            job.finished = time.time()
            return
        job.status = 'running'
        job.started = time.time()
        self._log(tr('Started: {title}', title=job.title))
        try:
            result = fn(job)
            if result is not None:
                job.result = result
            if job.failed:
                n = len(job.failed)
                job.status = 'error'
                job.error = tr('{n} file(s) failed – the others were transferred. Click Retry to try the failed ones again.', n=n)
                self._log(tr('Finished with errors: {title} – {n} file(s) failed', title=job.title, n=n), 'error')
            else:
                job.status = 'done'
                self._log(tr('Finished: {title}', title=job.title), 'ok')
        except Cancelled:
            job.status = 'cancelled'
            self._log(tr('Cancelled: {title}', title=job.title), 'warn')
        except PermissionError as e:
            from .system import permission_hint  # e.g. macOS blocks Downloads/Documents until allowed
            job.status = 'error'
            job.error = permission_hint(e.filename) if e.filename else str(e)
            self._log(tr('Failed: {title} – {error}', title=job.title, error=job.error), 'error')
        except Exception as e:
            job.status = 'error'
            job.error = str(e) or type(e).__name__
            self._log(tr('Failed: {title} – {error}', title=job.title, error=job.error), 'error')
        finally:
            job.current = ''
            job.finished = time.time()

    def cancel(self, job_id):
        job = self.jobs.get(job_id)
        if job:
            job._cancel.set()
            if job.status == 'queued':
                job.status = 'cancelled'

    def cancel_all(self):
        for j in list(self.jobs.values()):
            j._cancel.set()

    def clear_finished(self):
        with self.lock:
            for k in [k for k, j in self.jobs.items() if j.status in ('done', 'error', 'cancelled')]:
                del self.jobs[k]

    def list(self):
        with self.lock:
            return [j.to_dict() for j in reversed(self.jobs.values())][:200]

    def get(self, job_id):
        return self.jobs.get(job_id)
