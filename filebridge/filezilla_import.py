"""Import sites from FileZilla's Site Manager (sitemanager.xml)."""
import base64
import os
import sys
import xml.etree.ElementTree as ET

from .common import ApiError

# FileZilla <Protocol> -> (protocol, encryption)
PROTOCOLS = {
    '0': ('ftp', 'auto'),       # FTP – use explicit FTP over TLS if available
    '1': ('sftp', 'auto'),      # SFTP
    '3': ('ftp', 'implicit'),   # FTPS – implicit TLS
    '4': ('ftp', 'explicit'),   # FTPES – require explicit TLS
    '6': ('ftp', 'plain'),      # insecure plain FTP
}
# FileZilla <Logontype> -> FileBridge logon type
LOGONS = {'0': 'anonymous', '1': 'password', '2': 'ask', '3': 'ask', '4': 'ask', '5': 'key'}
COLOURS = {'1': 'red', '2': 'green', '3': 'blue', '4': 'yellow', '5': 'cyan', '6': 'magenta'}
PASV = {'MODE_ACTIVE': 'active', 'MODE_PASSIVE': 'passive'}


def default_path():
    if sys.platform.startswith('win'):
        base = os.environ.get('APPDATA') or os.path.expanduser('~\\AppData\\Roaming')
        return os.path.join(base, 'FileZilla', 'sitemanager.xml')
    return os.path.expanduser('~/.config/filezilla/sitemanager.xml')


def parse_remote_dir(value):
    """FileZilla stores remote folders as '1 0 11 public_html 4 site' (type, prefix, length-prefixed parts)."""
    s = (value or '').strip()
    if not s:
        return ''
    pos = 0

    def token():
        nonlocal pos
        while pos < len(s) and s[pos] == ' ':
            pos += 1
        start = pos
        while pos < len(s) and s[pos] != ' ':
            pos += 1
        return s[start:pos]

    try:
        token()  # server type
        prefix_len = int(token())
        if prefix_len:
            pos += 1
            pos += prefix_len
        parts = []
        while pos < len(s):
            t = token()
            if not t:
                break
            n = int(t)
            pos += 1
            parts.append(s[pos:pos + n])
            pos += n
        return '/' + '/'.join(parts)
    except (ValueError, IndexError):
        return ''


def _text(el, tag, default=''):
    x = el.find(tag)
    return (x.text or '').strip() if x is not None and x.text else default


def _server(el, folder):
    proto = _text(el, 'Protocol', '0')
    if proto not in PROTOCOLS:
        return None, f'unsupported protocol ({proto}) – only FTP, FTPS and SFTP'
    protocol, encryption = PROTOCOLS[proto]
    name = _text(el, 'Name')
    logon = LOGONS.get(_text(el, 'Logontype', '1'), 'password')
    if protocol == 'ftp' and logon == 'key':
        logon = 'password'
    if protocol == 'sftp' and logon == 'anonymous':
        logon = 'password'
    password = None
    pw = el.find('Pass')
    if pw is not None and pw.text and logon == 'password':
        enc = pw.get('encoding', '')
        if enc == 'base64':
            try:
                password = base64.b64decode(pw.text).decode('utf-8')
            except Exception:
                password = None
        elif enc == 'crypt':
            password = None  # protected with a FileZilla master password – can't be read
        else:
            password = pw.text
    enc_type = _text(el, 'EncodingType', 'Auto')
    charset = 'auto' if enc_type == 'Auto' else 'utf-8' if enc_type == 'UTF-8' else (_text(el, 'CustomEncoding') or 'auto')
    site = {
        'name': name or _text(el, 'Host'),
        'folder': folder,
        'protocol': protocol,
        'encryption': encryption,
        'host': _text(el, 'Host'),
        'port': _text(el, 'Port') or '',
        'auth': logon,
        'username': _text(el, 'User'),
        'key_path': _text(el, 'Keyfile'),
        'color': COLOURS.get(_text(el, 'Colour', '0'), ''),
        'comments': _text(el, 'Comments'),
        'local_dir': _text(el, 'LocalDir'),
        'remote_dir': parse_remote_dir(_text(el, 'RemoteDir')),
        'transfer_mode': PASV.get(_text(el, 'PasvMode'), 'default'),
        'charset': charset,
    }
    return {'site': site, 'password': password,
            'password_note': 'protected by a FileZilla master password – enter it once when connecting'
            if pw is not None and pw.get('encoding') == 'crypt' else ''}, None


def read(path=None):
    """Return {'path', 'sites': [{site, password, password_note}], 'skipped': [..]}."""
    path = os.path.expanduser(path or default_path())
    if not os.path.isfile(path):
        raise ApiError(f'FileZilla site list not found: {path}')
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as e:
        raise ApiError(f'Could not read {path}: {e}')
    servers = root.find('Servers')
    if servers is None:
        return {'path': path, 'sites': [], 'skipped': []}
    found, skipped = [], []

    def walk(node, folder):
        for child in node:
            if child.tag == 'Folder':
                name = (child.text or '').strip()
                sub = f'{folder} / {name}' if folder and name else (name or folder)
                walk(child, sub)
            elif child.tag == 'Server':
                item, why = _server(child, folder)
                if item:
                    found.append(item)
                else:
                    skipped.append({'name': _text(child, 'Name') or _text(child, 'Host'), 'reason': why})

    walk(servers, '')
    return {'path': path, 'sites': found, 'skipped': skipped}
