"""SFTP connection and remote file operations (paramiko)."""
import os
import posixpath
import stat
import threading

import paramiko

from .common import CONF_DIR, ApiError, make_entry


KNOWN_HOSTS = os.path.join(CONF_DIR, 'known_hosts')


# --- helpers that work on any SFTPClient (jobs use their own channel) --------

def is_dir(sftp, path):
    try:
        return stat.S_ISDIR(sftp.stat(path).st_mode)
    except IOError:
        return False


def exists(sftp, path):
    try:
        sftp.lstat(path)
        return True
    except IOError:
        return False


def makedirs(sftp, path, on_create=None):
    """Create path and missing parents; on_create(path) is called for every folder created."""
    if not path or path in ('/', '.'):
        return
    if is_dir(sftp, path):
        return
    makedirs(sftp, posixpath.dirname(path.rstrip('/')), on_create)
    try:
        sftp.mkdir(path)
    except IOError:
        if not is_dir(sftp, path):
            raise
        return
    if on_create:
        on_create(path)


def rmtree(sftp, path, check=None):
    for a in sftp.listdir_attr(path):
        if check:
            check()
        full = posixpath.join(path, a.filename)
        if stat.S_ISDIR(a.st_mode or 0):
            rmtree(sftp, full, check)
        else:
            sftp.remove(full)
    sftp.rmdir(path)


def walk(sftp, root):
    """Yield (full_path, attr) for every file and folder below root."""
    stack = [root]
    while stack:
        d = stack.pop()
        for a in sftp.listdir_attr(d):
            full = posixpath.join(d, a.filename)
            mode = a.st_mode or 0
            if stat.S_ISLNK(mode):
                try:
                    a = sftp.stat(full)
                    mode = a.st_mode
                except IOError:
                    continue
                if stat.S_ISDIR(mode):
                    continue  # don't follow directory links (loops)
            yield full, a
            if stat.S_ISDIR(mode):
                stack.append(full)


# --- connection ---------------------------------------------------------------

class Remote:
    def __init__(self, site, password=None, passphrase=None):
        self.site = site
        self._password = password
        self._passphrase = passphrase
        self.client = None
        self.sftp = None
        self.lock = threading.Lock()
        self._can_exec = None
        self.fingerprint = ''
        self.new_host_key = False

    def connect(self):
        os.makedirs(CONF_DIR, mode=0o700, exist_ok=True)
        if not os.path.exists(KNOWN_HOSTS):
            open(KNOWN_HOSTS, 'a').close()
            os.chmod(KNOWN_HOSTS, 0o600)
        c = paramiko.SSHClient()
        try:
            c.load_system_host_keys()
        except Exception:
            pass
        c.load_host_keys(KNOWN_HOSTS)
        before = len(c.get_host_keys().keys())
        # First connection to a host: remember its key (like "Trust" in FileZilla).
        # A changed key later raises BadHostKeyException and the connection is refused.
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        s = self.site
        auth = s.get('auth', 'password')
        kwargs = dict(hostname=s['host'], port=int(s.get('port') or 22), username=s['username'],
                      timeout=20, banner_timeout=20, auth_timeout=30)
        if auth in ('password', 'ask'):
            kwargs.update(password=self._password, allow_agent=False, look_for_keys=False)
        elif auth == 'key':
            kwargs.update(key_filename=os.path.expanduser(s.get('key_path') or ''),
                          passphrase=self._passphrase or None, allow_agent=False, look_for_keys=False)
        else:  # agent / default keys in ~/.ssh
            kwargs.update(allow_agent=True, look_for_keys=True, passphrase=self._passphrase or None)
        try:
            c.connect(**kwargs)
        except paramiko.BadHostKeyException:
            raise ApiError(f'WARNING: the host key of {s["host"]} has CHANGED. This can mean the server was '
                           f'reinstalled, or that someone is intercepting the connection. Connection refused. '
                           f'If you trust the change, remove the host from {KNOWN_HOSTS}.')
        except paramiko.AuthenticationException:
            raise ApiError('Login failed: wrong username, password or key.')
        except ConnectionRefusedError:
            raise ApiError(f'The server refused the connection on port {kwargs["port"]}. SFTP normally uses '
                           f'port 22, but some hosting providers use another port – check their SSH instructions.')
        except (OSError, paramiko.SSHException) as e:
            raise ApiError(f'Could not connect to {s["host"]}: {e}')
        self.new_host_key = len(c.get_host_keys().keys()) > before
        key = c.get_transport().get_remote_server_key()
        self.fingerprint = f'{key.get_name()} {key.fingerprint}'
        c.get_transport().set_keepalive(30)
        self.client = c
        self.sftp = c.open_sftp()
        self._password = None  # don't keep it in memory longer than needed

    def close(self):
        try:
            if self.client:
                self.client.close()
        finally:
            self.client = self.sftp = None

    def alive(self):
        t = self.client and self.client.get_transport()
        return bool(t and t.is_active())

    def new_sftp(self):
        return self.client.open_sftp()

    def home(self):
        with self.lock:
            return self.sftp.normalize('.')

    # --- commands over SSH (not every host allows this) ---
    def exec(self, cmd, timeout=120):
        _, stdout, stderr = self.client.exec_command(cmd, timeout=timeout)
        stdout.channel.shutdown_write()
        out = stdout.read().decode('utf-8', 'replace')
        err = stderr.read().decode('utf-8', 'replace')
        return stdout.channel.recv_exit_status(), out, err

    def can_exec(self):
        if self._can_exec is None:
            try:
                rc, out, _ = self.exec('echo filebridge-ok', timeout=15)
                self._can_exec = rc == 0 and 'filebridge-ok' in out
            except Exception:
                self._can_exec = False
        return self._can_exec

    def has_command(self, name):
        return self.can_exec() and self.exec(f'command -v {name}', timeout=15)[0] == 0

    # --- operations used by the UI ---
    def list(self, path):
        with self.lock:
            path = self.sftp.normalize(path or '.')
            out = []
            for a in self.sftp.listdir_attr(path):
                full = posixpath.join(path, a.filename)
                mode = a.st_mode or 0
                link = stat.S_ISLNK(mode)
                size, mtime = a.st_size, a.st_mtime
                known = getattr(a, 'mode_known', True)
                if link:
                    try:
                        t = self.sftp.stat(full)
                        mode, size, mtime = t.st_mode, t.st_size, t.st_mtime
                    except IOError:
                        pass
                out.append(make_entry(a.filename, full, stat.S_ISDIR(mode), size, mtime,
                                      stat.filemode(a.st_mode or 0) if known else '', link,
                                      mode if known else None))
            return path, out

    def mkdir(self, path):
        with self.lock:
            if exists(self.sftp, path):
                raise ApiError(f'"{posixpath.basename(path)}" already exists')
            self.sftp.mkdir(path)

    def rename(self, src, dst):
        with self.lock:
            if exists(self.sftp, dst):
                raise ApiError(f'"{posixpath.basename(dst)}" already exists')
            self.sftp.rename(src, dst)

    def move(self, paths, dest):
        with self.lock:
            dest = self.sftp.normalize(dest)
            if not is_dir(self.sftp, dest):
                raise ApiError(f'Folder not found: {dest}')
            for p in paths:
                name = posixpath.basename(p.rstrip('/'))
                if dest == p or dest.startswith(p.rstrip('/') + '/'):
                    raise ApiError(f'Cannot move "{name}" into itself')
                target = posixpath.join(dest, name)
                if exists(self.sftp, target):
                    raise ApiError(f'"{name}" already exists in {dest}')
                self.sftp.rename(p, target)

    def delete(self, paths):
        with self.lock:
            for p in paths:
                if stat.S_ISDIR(self.sftp.lstat(p).st_mode):
                    rmtree(self.sftp, p)
                else:
                    self.sftp.remove(p)

    def chmod(self, paths, mode, recursive=False):
        with self.lock:
            for p in paths:
                self.sftp.chmod(p, mode)
                if recursive and is_dir(self.sftp, p):
                    for full, _ in walk(self.sftp, p):
                        self.sftp.chmod(full, mode)
