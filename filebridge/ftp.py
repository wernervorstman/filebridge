"""FTP and FTPS (FTP over TLS) support.

FtpClient mimics the part of paramiko's SFTPClient that FileBridge uses
(stat, listdir_attr, open, mkdir, rename, …), so transfers, compare & sync,
deploy and plugins work unchanged over FTP.
"""
import calendar
import codecs
import ftplib
import functools
import posixpath
import re
import ssl
import stat
import time

from .common import ApiError

try:  # verify certificates like macOS does (fills in missing intermediate certificates)
    import truststore
except ImportError:  # pragma: no cover
    truststore = None


def tls_context(insecure=False):
    if insecure:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    if truststore:
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    return ssl.create_default_context()
from .remote import Remote

MONTHS = {m: i for i, m in enumerate(
    ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'], 1)}


def charset_of(site):
    """'auto' and 'utf-8' mean UTF-8; otherwise the custom charset (e.g. latin-1)."""
    cs = (site.get('charset') or 'auto').strip()
    if cs in ('auto', 'utf-8', ''):
        return 'utf-8'
    try:
        return codecs.lookup(cs).name
    except LookupError:
        raise ApiError(f'Unknown character set: {cs}')


class Attr:
    """Same fields as paramiko's SFTPAttributes."""

    def __init__(self, filename='', mode=0, size=0, mtime=0):
        self.filename = filename
        self.mode_known = True  # False when the server didn't report permissions
        self.st_mode = mode
        self.st_size = size
        self.st_mtime = mtime
        self.st_atime = mtime


def _ftp_errors(fn):
    """Turn ftplib errors into OSError, which is what the rest of FileBridge expects."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except (ftplib.Error, EOFError) as e:
            raise OSError(str(e) or 'FTP error') from None
    return wrapper


def _parse_time(s):
    try:
        return calendar.timegm(time.strptime(s[:14], '%Y%m%d%H%M%S'))
    except (ValueError, TypeError):
        return 0


def _attr_from_facts(name, facts):
    t = facts.get('type', 'file').lower()
    if t == 'dir':
        kind, default = stat.S_IFDIR, 0o755
    elif 'link' in t:
        kind, default = stat.S_IFLNK, 0o777
    else:
        kind, default = stat.S_IFREG, 0o644
    known = True
    try:
        perms = int(facts['unix.mode'], 8) & 0o7777
    except (KeyError, ValueError):
        perms, known = default, False
    size = facts.get('size') or facts.get('sizd') or '0'
    a = Attr(name, kind | perms, int(size) if size.isdigit() else 0, _parse_time(facts.get('modify', '')))
    a.mode_known = known
    return a


def _parse_list_line(line):
    """Parse one line of a Unix-style LIST reply."""
    parts = line.split(None, 8)
    if len(parts) < 9 or not parts[0] or parts[0][0] not in 'dl-':
        return None
    perms, size, mon, day, when, name = parts[0], parts[4], parts[5], parts[6], parts[7], parts[8]
    if perms[0] == 'l' and ' -> ' in name:
        name = name.split(' -> ', 1)[0]
    kind = {'d': stat.S_IFDIR, 'l': stat.S_IFLNK}.get(perms[0], stat.S_IFREG)
    bits = 0
    for i, ch in enumerate(perms[1:10]):
        if ch not in '-ST':
            bits |= 1 << (8 - i)
    mtime = 0
    try:
        month, d = MONTHS[mon.lower()[:3]], int(day)
        if ':' in when:
            hh, mm = (int(x) for x in when.split(':'))
            now = time.gmtime()
            year = now.tm_year
            mtime = calendar.timegm((year, month, d, hh, mm, 0))
            if mtime > time.time() + 86400:  # "Dec 31 23:00" seen in January = last year
                mtime = calendar.timegm((year - 1, month, d, hh, mm, 0))
        else:
            mtime = calendar.timegm((int(when), month, d, 0, 0, 0))
    except (KeyError, ValueError):
        pass
    return Attr(name, kind | bits, int(size) if size.isdigit() else 0, mtime)


class _FTP_TLS(ftplib.FTP_TLS):
    """FTP_TLS that reuses the TLS session on data connections.

    Many servers (ProFTPD, vsftpd) refuse data connections without session reuse,
    which plain ftplib does not do.
    """

    def ntransfercmd(self, cmd, rest=None):
        conn, size = ftplib.FTP.ntransfercmd(self, cmd, rest)
        if self._prot_p:
            conn = self.context.wrap_socket(conn, server_hostname=self.host, session=self.sock.session)
        return conn, size


class _FTP_TLS_Implicit(_FTP_TLS):
    """Implicit FTPS (usually port 990): TLS from the very first byte."""

    def connect(self, host='', port=0, timeout=-999, source_address=None):
        if host:
            self.host = host
        if port > 0:
            self.port = port
        if timeout != -999:
            self.timeout = timeout
        import socket
        sock = socket.create_connection((self.host, self.port), self.timeout)
        self.af = sock.family
        self.sock = self.context.wrap_socket(sock, server_hostname=self.host)
        self.file = self.sock.makefile('r', encoding=self.encoding)
        self.welcome = self.getresp()
        return self.welcome


class FtpFile:
    """File object for one FTP transfer (RETR, STOR or APPE)."""

    def __init__(self, client, path, mode):
        self.client = client
        self.path = path
        self.writing = any(c in mode for c in 'wa+')
        self.append = 'a' in mode
        self.offset = 0
        self.conn = None
        self.eof = False

    def seek(self, offset):
        if self.conn:
            raise OSError('Cannot seek after the transfer has started')
        self.offset = offset

    def set_pipelined(self, *_):
        pass

    def prefetch(self, *_):
        pass

    @_ftp_errors
    def _start(self):
        ftp = self.client.ftp
        self.client.binary()  # listings switch the connection to ASCII; transfers must be binary
        if self.writing:
            cmd = 'APPE' if (self.offset or self.append) else 'STOR'
            self.conn = ftp.transfercmd(f'{cmd} {self.path}')
        else:
            self.conn = ftp.transfercmd(f'RETR {self.path}', rest=self.offset or None)

    def read(self, n=-1):
        if not self.conn:
            self._start()
        if n is None or n < 0:
            chunks = []
            while True:
                d = self.conn.recv(65536)
                if not d:
                    break
                chunks.append(d)
            self.eof = True
            return b''.join(chunks)
        data = self.conn.recv(n)
        if not data:
            self.eof = True
        return data

    def write(self, data):
        if not self.conn:
            self._start()
        self.conn.sendall(data)

    def close(self):
        if self.conn is None:
            if not self.writing:
                return
            self._start()  # creates an empty file
        conn, self.conn = self.conn, None
        complete = self.writing or self.eof
        try:
            if complete and isinstance(conn, ssl.SSLSocket):
                try:
                    conn.unwrap()
                except (OSError, ValueError):
                    pass
        finally:
            conn.close()
        try:
            self.client.ftp.voidresp()
        except (ftplib.Error, EOFError, OSError) as e:
            if complete:
                raise OSError(str(e)) from None
            # aborted download: the server answers "426 transfer aborted"

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class FtpClient:
    """The subset of paramiko.SFTPClient that FileBridge uses, over FTP/FTPS."""

    def __init__(self, site, password, insecure=False):
        self.site = site
        enc = site.get('encryption') or 'auto'
        host = site['host']
        port = int(site.get('port') or (990 if enc == 'implicit' else 21))
        encoding = charset_of(site)
        ctx = tls_context(insecure)

        if enc == 'implicit':
            ftp = _FTP_TLS_Implicit(context=ctx, timeout=30, encoding=encoding)
            ftp.connect(host, port)
        elif enc in ('auto', 'explicit'):
            ftp = _FTP_TLS(context=ctx, timeout=30, encoding=encoding)
            ftp.connect(host, port)
            try:
                ftp.auth()
            except ftplib.error_perm as e:
                if enc == 'explicit' or str(e)[:3] not in ('500', '502', '504', '534', '530', '431'):
                    raise
                # "Use explicit FTP over TLS if available": the server has no TLS, continue unencrypted
                ftp.close()
                ftp = ftplib.FTP(timeout=30, encoding=encoding)
                ftp.connect(host, port)
        else:
            ftp = ftplib.FTP(timeout=30, encoding=encoding)
            ftp.connect(host, port)

        ftp.login(site['username'], password or '')
        if isinstance(ftp, ftplib.FTP_TLS) and isinstance(ftp.sock, ssl.SSLSocket):
            ftp.prot_p()
        ftp.set_pasv(site.get('transfer_mode') != 'active')
        self.ftp = ftp
        self.features = self._feat()
        if 'UTF8' in self.features and encoding.lower().replace('-', '') == 'utf8':
            try:
                ftp.sendcmd('OPTS UTF8 ON')
            except ftplib.Error:
                pass
        if 'MLST' in self.features:
            try:  # ask for permissions (unix.mode) in every MLST/MLSD reply
                ftp.sendcmd('OPTS MLST type;size;modify;unix.mode;')
            except ftplib.Error:
                pass
        ftp.voidcmd('TYPE I')
        self._binary = True
        self.home = ftp.pwd()

    def binary(self):
        """Switch to binary mode – only when needed, it costs a round trip to the server."""
        if not getattr(self, '_binary', False):
            self.ftp.voidcmd('TYPE I')
            self._binary = True

    def _feat(self):
        try:
            resp = self.ftp.sendcmd('FEAT')
        except ftplib.Error:
            return set()
        return {line.strip().split(' ')[0].upper() for line in resp.splitlines()[1:-1] if line.strip()}

    def normalize(self, path):
        if not path or path == '.':
            return self.home
        if not path.startswith('/'):
            path = posixpath.join(self.home, path)
        p = posixpath.normpath(path)
        return '/' + p.lstrip('/')

    @_ftp_errors
    def listdir_attr(self, path='.'):
        path = self.normalize(path)
        out = []
        if 'MLST' in self.features:
            self._binary = False  # mlsd/retrlines switch the connection to TYPE A
            for name, facts in self.ftp.mlsd(path, ['type', 'size', 'modify', 'unix.mode']):
                if facts.get('type', '').lower() in ('cdir', 'pdir') or name in ('.', '..'):
                    continue
                out.append(_attr_from_facts(name, facts))
            return out
        lines = []
        self._binary = False
        self.ftp.cwd(path)
        try:
            self.ftp.retrlines('LIST -a', lines.append)
        except ftplib.error_perm:
            lines = []
            self.ftp.retrlines('LIST', lines.append)
        for line in lines:
            a = _parse_list_line(line)
            if a and a.filename not in ('.', '..'):
                out.append(a)
        return out

    @_ftp_errors
    def stat(self, path):
        path = self.normalize(path)
        if path == '/':
            return Attr('/', stat.S_IFDIR | 0o755)
        if 'MLST' in self.features:
            resp = self.ftp.sendcmd(f'MLST {path}')
            for line in resp.splitlines()[1:]:
                line = line.strip()
                if '=' in line and ';' in line:
                    facts = {}
                    for part in line.split(' ', 1)[0].split(';'):
                        if '=' in part:
                            k, v = part.split('=', 1)
                            facts[k.lower()] = v
                    return _attr_from_facts(posixpath.basename(path), facts)
        # Without MLST: a folder if we can change into it, otherwise ask for size and date
        try:
            self.ftp.cwd(path)
            a = Attr(posixpath.basename(path), stat.S_IFDIR | 0o755)
            a.mode_known = False
            return a
        except ftplib.error_perm:
            pass
        self.binary()  # SIZE is refused in ASCII mode
        size = self.ftp.size(path)
        if size is None:
            raise OSError(f'Not found: {path}')
        mtime = 0
        try:
            mtime = _parse_time(self.ftp.sendcmd(f'MDTM {path}').split()[-1])
        except ftplib.Error:
            pass
        a = Attr(posixpath.basename(path), stat.S_IFREG | 0o644, size, mtime)
        a.mode_known = False
        return a

    lstat = stat

    def open(self, path, mode='rb'):
        return FtpFile(self, self.normalize(path), mode)

    @_ftp_errors
    def utime(self, path, times):
        if 'MFMT' in self.features and times:
            stamp = time.strftime('%Y%m%d%H%M%S', time.gmtime(times[1]))
            self.ftp.sendcmd(f'MFMT {stamp} {self.normalize(path)}')

    @_ftp_errors
    def mkdir(self, path, mode=None):
        self.ftp.mkd(self.normalize(path))

    @_ftp_errors
    def rmdir(self, path):
        self.ftp.rmd(self.normalize(path))

    @_ftp_errors
    def remove(self, path):
        self.ftp.delete(self.normalize(path))

    @_ftp_errors
    def rename(self, src, dst):
        self.ftp.rename(self.normalize(src), self.normalize(dst))

    @_ftp_errors
    def chmod(self, path, mode):
        self.ftp.sendcmd(f'SITE CHMOD {mode:o} {self.normalize(path)}')

    @_ftp_errors
    def noop(self):
        self.ftp.voidcmd('NOOP')

    def close(self):
        try:
            self.ftp.quit()
        except Exception:
            self.ftp.close()


class FtpRemote(Remote):
    """A Remote that talks FTP/FTPS. Every job gets its own FTP connection."""

    def __init__(self, site, password=None, passphrase=None):
        super().__init__(site, password, passphrase)
        self._can_exec = False
        self._last_ok = 0

    def _client(self):
        return FtpClient(self.site, self._password, bool(self.site.get('ftps_insecure')))

    def connect(self):
        s = self.site
        try:
            self.sftp = self._client()
        except ftplib.error_perm as e:
            msg = str(e)
            if msg.startswith('530'):  # keep the server's own words: it may be a ban or a connection limit
                raise ApiError(f'Login failed: wrong username, password or key. Server: {msg}')
            if s.get('encryption') == 'explicit' and msg[:3] in ('500', '502', '504', '534'):
                raise ApiError(f'This server does not support FTP over TLS ({msg}). Choose '
                               f'"Use explicit FTP over TLS if available" or "Only use plain FTP".')
            raise ApiError(f'FTP error: {msg}')
        except ssl.SSLError as e:
            raise ApiError(self._cert_message(e))
        except ConnectionRefusedError:
            p = s.get('port') or 21
            raise ApiError(f'The server refused the connection on port {p}. FTP normally uses port 21 '
                           f'(990 for implicit TLS). Leave Port empty to use the default.')
        except (OSError, EOFError, ftplib.Error) as e:
            raise ApiError(f'Could not connect to {s["host"]}: {e}')
        sock = self.sftp.ftp.sock
        if isinstance(sock, ssl.SSLSocket):
            self.fingerprint = f'FTP over TLS ({sock.version()})'
        else:
            self.fingerprint = 'FTP – NOT encrypted'
        self._last_ok = time.time()

    def _cert_message(self, e):
        text = str(getattr(e, 'verify_message', '') or e)
        m = re.search(r'[“"]([^”"]+)[”"] certificate name does not match', text)
        if m:
            return (f'The server\'s TLS certificate is for "{m.group(1)}", not "{self.site["host"]}". '
                    f'This is normal on shared hosting. Fix: in Site Manager, set Host to {m.group(1)} '
                    f'(recommended – the connection stays fully verified), or tick "Accept the certificate '
                    f'even if it can\'t be verified" under Transfer Settings.')
        return (f'The server\'s TLS certificate could not be verified ({text}). Use the server host name '
                f'from your hosting provider, or tick "Accept the certificate even if it can\'t be verified" '
                f'in Site Manager → Transfer Settings.')

    def close(self):
        if self.sftp:
            self.sftp.close()
        self.sftp = None

    def alive(self):
        if not self.sftp:
            return False
        if time.time() - self._last_ok < 15:
            return True
        with self.lock:
            try:
                self.sftp.noop()
            except OSError:
                # The server closed the idle connection – reconnect quietly.
                try:
                    self.sftp.close()
                    self.sftp = self._client()
                except Exception:
                    return False
            self._last_ok = time.time()
            return True

    def new_sftp(self):
        return self._client()

    def home(self):
        return self.sftp.home

    def exec(self, cmd, timeout=120):
        raise RuntimeError('Running commands on the server is not possible over FTP (use SFTP for that).')

    def can_exec(self):
        return False
