#!/usr/bin/env python3
"""FileBridge – the local server behind the interface.

Run this file to use FileBridge in your browser (python server.py). The desktop
app (filebridge_app.py) starts the same server and shows it in its own window.

Only listens on 127.0.0.1, and every API call needs a secret token that is
generated at startup, so other websites cannot talk to it.
"""
import argparse
import json
import mimetypes
import os
import secrets
import sys
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

from filebridge import i18n, system  # noqa: E402
from filebridge.app import App  # noqa: E402
from filebridge.common import ApiError  # noqa: E402

STATIC = os.path.join(system.resource_dir(), 'static')
# Windows can map .js to text/plain via the registry; be explicit (nosniff would block it)
for _type, _ext in (('application/javascript', '.js'), ('text/css', '.css'), ('font/woff2', '.woff2'),
                    ('image/svg+xml', '.svg'), ('image/png', '.png')):
    mimetypes.add_type(_type, _ext)
TOKEN = secrets.token_urlsafe(24)
APP = None


class Handler(BaseHTTPRequestHandler):
    server_version = 'FileBridge'

    def log_message(self, *args):
        pass

    def _host_ok(self):
        host = (self.headers.get('Host') or '').rsplit(':', 1)[0]
        return host in ('127.0.0.1', 'localhost')

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self._host_ok():
            return self._send(403, b'Forbidden', 'text/plain')
        path = urlparse(self.path).path
        if path in ('/', '/index.html'):
            with open(os.path.join(STATIC, 'index.html'), encoding='utf-8') as f:
                html = f.read().replace('{{TOKEN}}', TOKEN)
            return self._send(200, html.encode(), 'text/html; charset=utf-8')
        if path.startswith('/static/'):
            rel = os.path.normpath(unquote(path[len('/static/'):]))
            full = os.path.join(STATIC, rel)
            if not rel.startswith('..') and not os.path.isabs(rel) and os.path.isfile(full):
                with open(full, 'rb') as f:
                    ctype = mimetypes.guess_type(full)[0] or 'application/octet-stream'
                    if ctype.startswith('text/') or ctype.endswith('javascript'):
                        ctype += '; charset=utf-8'
                    return self._send(200, f.read(), ctype)
        self._send(404, b'Not found', 'text/plain')

    def do_POST(self):
        if not self._host_ok() or not secrets.compare_digest(self.headers.get('X-Token', ''), TOKEN):
            return self._send(403, b'{"ok":false,"error":"Forbidden"}', 'application/json')
        path = urlparse(self.path).path
        if not path.startswith('/api/'):
            return self._send(404, b'{"ok":false,"error":"Not found"}', 'application/json')
        i18n.set_lang(self.headers.get('X-Lang'))  # answer in the language of the interface
        try:
            length = int(self.headers.get('Content-Length') or 0)
            body = json.loads(self.rfile.read(length) or b'{}')
            payload = {'ok': True, **APP.call(path[5:], body)}
        except ApiError as e:
            payload = {'ok': False, 'error': str(e)}
        except (OSError, ValueError, KeyError) as e:
            payload = {'ok': False, 'error': str(e) or type(e).__name__}
        except Exception as e:
            traceback.print_exc()
            payload = {'ok': False, 'error': f'{type(e).__name__}: {e}'}
        self._send(200, json.dumps(payload).encode(), 'application/json')


DEFAULT_PORT = 8765


def create_server(port=DEFAULT_PORT):
    """Create the app and bind the server to 127.0.0.1 (first free port from `port`)."""
    global APP
    APP = App(system.resource_dir())
    for p in range(port, port + 20):
        try:
            httpd = ThreadingHTTPServer(('127.0.0.1', p), Handler)
            break
        except OSError:
            continue
    else:
        sys.exit('No free port found')
    httpd.daemon_threads = True
    return httpd, f'http://127.0.0.1:{httpd.server_address[1]}/'


def main():
    ap = argparse.ArgumentParser(description='FileBridge SFTP/FTP client (browser mode)')
    ap.add_argument('--port', type=int, default=DEFAULT_PORT)
    ap.add_argument('--no-browser', action='store_true')
    args = ap.parse_args()

    httpd, url = create_server(args.port)
    APP.quit_hook = httpd.shutdown  # Quit button: serve_forever() returns, then we clean up
    print(f'FileBridge is running at {url}\nClose this window (or press Ctrl+C) to stop.', flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        APP.shutdown()
        httpd.server_close()


if __name__ == '__main__':
    main()
