"""Connection test (Site Manager → Test connection) and hosting panel detection.

The test runs the same steps as connecting, one at a time, so it can say exactly where it goes wrong:
name lookup, port, server greeting, encryption + login. The panel detection looks at the usual login
pages of Plesk, DirectAdmin and cPanel to suggest the right FTP username format.
"""
import concurrent.futures
import socket
import ssl
import time
import urllib.request

from .common import ApiError
from .sites import default_port

# login page of each hosting panel: (port, words that give it away in the address or the page)
PANELS = {'plesk': (8443, ('plesk',)), 'directadmin': (2222, ('directadmin', '/evo/', 'cmd_login')),
          'cpanel': (2083, ('cpanel',))}
PANEL_NAMES = {'plesk': 'Plesk', 'directadmin': 'DirectAdmin', 'cpanel': 'cPanel'}
USERNAME_HINT = {
    'plesk': 'Plesk: FTP usernames are the account name from the panel, without "@domain" (e.g. ftp1).',
    'directadmin': 'DirectAdmin: extra FTP accounts log in as name@domain (e.g. ftp@example.com); '
                   'the main account uses its plain username.',
    'cpanel': 'cPanel: extra FTP accounts log in as name@domain (e.g. ftp@example.com); '
              'the main account uses its plain username.',
}
_panel_cache = {}  # host -> (time, panel)


def _port_open(host, port, timeout=4):
    try:
        with socket.create_connection((host, port), timeout):
            return True
    except OSError:
        return False


def _page_mentions(host, port, words):
    """Does the page on https://host:port/ (or where it redirects to) mention one of `words`?
    Only reads a public login page."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE  # panels often have a self-signed certificate; we send nothing secret
    try:
        req = urllib.request.Request(f'https://{host}:{port}/', headers={'User-Agent': 'FileBridge'})
        with urllib.request.urlopen(req, timeout=5, context=ctx) as r:
            text = (r.geturl() + ' ' + r.read(200_000).decode('utf-8', 'replace')).lower()
        return any(w in text for w in words)
    except Exception:
        return False


def detect_panel(host):
    """'plesk', 'directadmin', 'cpanel' or None. Cached for an hour."""
    host = (host or '').strip().lower()
    if not host:
        return None
    hit = _panel_cache.get(host)
    if hit and time.time() - hit[0] < 3600:
        return hit[1]

    def check(item):
        name, (port, words) = item
        return name if _port_open(host, port, 3) and _page_mentions(host, port, words) else None

    with concurrent.futures.ThreadPoolExecutor(len(PANELS)) as pool:
        found = [n for n in pool.map(check, PANELS.items()) if n]
    panel = found[0] if found else None
    _panel_cache[host] = (time.time(), panel)
    return panel


def username_suggestion(panel, username):
    """A better FTP username for this panel, or None."""
    if panel == 'plesk' and '@' in (username or ''):
        return username.split('@')[0]
    return None


def _greeting(host, port, proto):
    """First line the server sends (FTP 220 … / SSH-2.0-…)."""
    with socket.create_connection((host, port), 10) as s:
        s.settimeout(10)
        data = s.recv(512).decode('utf-8', 'replace').strip()
    return data.splitlines()[0] if data else ''


def test_connection(site, password, passphrase, remote_classes):
    """Run the connection step by step. Returns {'steps': [...], 'fixes': [...]}.

    Each step: {'name', 'ok' (True/False/None = skipped or info), 'detail'}.
    Each fix: {'label', 'patch'} – changes the Site Manager can apply with one click.
    """
    Remote, FtpRemote = remote_classes
    host, is_ftp = site['host'], site.get('protocol') == 'ftp'
    port = int(site.get('port') or default_port(site))
    steps, fixes = [], []
    add = lambda name, ok, detail='': steps.append({'name': name, 'ok': ok, 'detail': detail})
    panel_job = concurrent.futures.ThreadPoolExecutor(1).submit(detect_panel, host) if is_ftp else None

    def finish():
        if panel_job:
            try:
                panel = panel_job.result(timeout=15)
            except Exception:
                panel = None
            if panel:
                add('Hosting panel', None, f'{PANEL_NAMES[panel]} detected. {USERNAME_HINT[panel]}')
                better = username_suggestion(panel, site.get('username'))
                if better:
                    fixes.append({'label': f'Use "{better}" as username', 'patch': {'username': better}})
        return {'steps': steps, 'fixes': fixes}

    # 1. name lookup
    try:
        ips = sorted({a[4][0] for a in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)})
        add('Server name', True, f'{host} → {", ".join(ips[:3])}')
    except OSError as e:
        add('Server name', False, f'"{host}" could not be found ({e}). Check the spelling of Host.')
        return finish()

    # 2. port
    try:
        socket.create_connection((host, port), 10).close()
        add('Port', True, f'port {port} is open')
    except TimeoutError:
        detail = f'port {port} does not answer.'
        if is_ftp:
            detail += ' The network you are on may block FTP – public, hotel and work wifi often do.'
            ssh = [p for p in (22, int(site.get('fallback_port') or 0)) if p and p != port and _port_open(host, p)]
            if ssh:
                detail += f' SSH/SFTP port {ssh[0]} is open on this server.'
                fixes.append({'label': f'Switch to SFTP on port {ssh[0]}',
                              'patch': {'protocol': 'sftp', 'port': ssh[0]}})
        add('Port', False, detail)
        return finish()
    except ConnectionRefusedError:
        add('Port', False, f'the server refused port {port}. Check the port (FTP 21, FTPS 990, SFTP 22 or '
                           f'the SSH port of your hosting provider).')
        return finish()
    except OSError as e:
        add('Port', False, f'port {port}: {e}')
        return finish()

    # 3. greeting: is this the right protocol on this port?
    try:
        hello = '' if (is_ftp and site.get('encryption') == 'implicit') else _greeting(host, port, site.get('protocol'))
        if hello:
            if is_ftp and hello.startswith('SSH-'):
                add('Server type', False, f'this port speaks SSH ({hello[:60]}), not FTP. Choose SFTP as protocol.')
                fixes.append({'label': 'Switch to SFTP', 'patch': {'protocol': 'sftp'}})
                return finish()
            if not is_ftp and hello[:3].isdigit():
                add('Server type', False, f'this port speaks FTP ({hello[:60]}), not SFTP. Choose FTP as protocol.')
                fixes.append({'label': 'Switch to FTP', 'patch': {'protocol': 'ftp'}})
                return finish()
            add('Server type', True, hello[:120])
    except OSError as e:
        add('Server type', None, f'no greeting ({e})')

    # 4. encryption + login: the real connection
    auth = site.get('auth', 'password')
    if auth == 'anonymous':
        site, password = {**site, 'username': 'anonymous'}, 'anonymous@'
    elif auth in ('password', 'ask') and not password:
        add('Login', None, 'no password to test with – type one in the Password field or in the prompt.')
        return finish()
    r = (FtpRemote if is_ftp else Remote)(site, password, passphrase)
    try:
        r.connect()
    except ApiError as e:
        msg = str(e)
        if msg.startswith('Login failed'):
            add('Encryption', True, 'OK') if is_ftp else None
            add('Login', False, msg.replace('Login failed: ', ''))
        elif 'certificate' in msg.lower() or 'TLS' in msg:
            add('Encryption', False, msg)
        else:
            add('Connection', False, msg)
        return finish()
    try:
        add('Encryption', True if 'NOT' not in r.fingerprint else None, r.fingerprint) if is_ftp else \
            add('Host key', True, r.fingerprint + (' (new – remembered)' if r.new_host_key else ''))
        add('Login', True, f'logged in as {site.get("username") or "anonymous"}')
        try:
            add('Home folder', True, r.home())
        except Exception as e:
            add('Home folder', None, str(e))
    finally:
        r.close()
    return finish()
