"""Web-related helpers: which server folders are public, web addresses for files,
risky files in public folders, and checking GitHub for a newer FileBridge."""
import fnmatch
import json
import os
import posixpath
import threading
import time
import urllib.request

from . import __version__
from .common import ApiError

# Folder names that are usually served to the whole internet
PUBLIC_DIRS = {'public_html', 'www', 'htdocs', 'httpdocs', 'html', 'web', 'wwwroot', 'public'}
# Files that shouldn't be downloadable by anyone
RISKY = ['*.zip', '*.tar', '*.tar.gz', '*.tgz', '*.gz', '*.bz2', '*.7z', '*.rar',
         '*.sql', '*.sql.gz', '*.dump', '*.bak', '*.backup', '*.old', '*.orig', '*.swp',
         '.env', '*.env', '.env.*', '*.pem', '*.key']

RELEASES_API = 'https://api.github.com/repos/wernervorstman/filebridge/releases/latest'


def is_risky(name):
    n = name.lower()
    return any(fnmatch.fnmatch(n, p) for p in RISKY)


def web_url(site, remote_path):
    """The web address of a server path, using the site's web address mapping (longest match)."""
    best = None
    for m in (site or {}).get('web_map') or []:
        d = '/' + m['dir'].strip('/') if m['dir'].strip('/') else '/'
        if remote_path == d or remote_path.startswith(d.rstrip('/') + '/'):
            if best is None or len(d) > len(best[0]):
                best = (d, m['url'].rstrip('/'))
    if not best:
        return None
    rest = remote_path[len(best[0]):].lstrip('/')
    from urllib.parse import quote
    return best[1] + ('/' + quote(rest) if rest else '/')


def is_public(site, remote_path):
    """True when files in this server folder can probably be downloaded by anyone."""
    if web_url(site, remote_path):
        return True
    return any(part.lower() in PUBLIC_DIRS for part in remote_path.split('/'))


def risky_local(paths, exclude=None, limit=5000):
    """Risky files among local paths (folders are searched too)."""
    found, seen = [], 0
    for p in paths:
        name = os.path.basename(p.rstrip(os.sep))
        if exclude and exclude(name):
            continue
        if os.path.isdir(p):
            for d, dirs, files in os.walk(p):
                dirs[:] = [x for x in dirs if not (exclude and exclude(x))]
                for f in files:
                    seen += 1
                    if seen > limit:
                        return found
                    if is_risky(f) and not (exclude and exclude(f)):
                        full = os.path.join(d, f)
                        found.append({'path': full, 'name': os.path.relpath(full, os.path.dirname(p)),
                                      'size': os.path.getsize(full)})
        elif is_risky(name):
            found.append({'path': p, 'name': name, 'size': os.path.getsize(p)})
    return found


def clean_web_map(value):
    """Validate the Site Manager's 'Web addresses' lines: '/public_html = https://example.com'."""
    lines = value if isinstance(value, list) else str(value or '').splitlines()
    out = []
    for line in lines:
        if isinstance(line, dict):
            d, u = line.get('dir', ''), line.get('url', '')
        else:
            line = line.strip()
            if not line:
                continue
            if '=' not in line:
                raise ApiError(f'Web addresses: use "server folder = web address", not "{line}"')
            d, u = (x.strip() for x in line.split('=', 1))
        if not u.lower().startswith(('http://', 'https://')):
            raise ApiError(f'Web addresses: "{u}" must start with https:// or http://')
        out.append({'dir': '/' + d.strip().strip('/'), 'url': u.rstrip('/')})
    return out


# --- update check ---
_cache = {'at': 0, 'data': None}
_lock = threading.Lock()


def _version_tuple(v):
    parts = []
    for x in v.lstrip('vV').split('.'):
        num = ''.join(ch for ch in x if ch.isdigit())
        parts.append(int(num) if num else 0)
    return tuple(parts)


def check_update(force=False):
    """{'current', 'latest', 'newer', 'url'} from GitHub, cached for 6 hours. Never raises."""
    with _lock:
        if not force and _cache['data'] and time.time() - _cache['at'] < 6 * 3600:
            return _cache['data']
    data = {'current': __version__, 'latest': None, 'newer': False, 'url': None}
    try:
        req = urllib.request.Request(RELEASES_API, headers={'User-Agent': f'FileBridge/{__version__}',
                                                            'Accept': 'application/vnd.github+json'})
        with urllib.request.urlopen(req, timeout=8) as r:
            rel = json.load(r)
        tag = rel.get('tag_name') or ''
        data.update(latest=tag.lstrip('vV'), url=rel.get('html_url'),
                    newer=_version_tuple(tag) > _version_tuple(__version__))
    except Exception:
        pass  # offline or GitHub unreachable: just no update notice
    with _lock:
        _cache.update(at=time.time(), data=data)
    return data
