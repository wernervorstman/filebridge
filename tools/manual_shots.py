#!/usr/bin/env python3
"""Make the pictures of the user manual (static/manual/img/<lang>/<name>.jpg).

    .venv/bin/python tools/manual_shots.py               # all languages and all scenes
    .venv/bin/python tools/manual_shots.py nl compare    # one language, one scene

Runs FileBridge against a local test SFTP server (tests/fake_sftp.py) with a throwaway home folder and
made-up example files, so the pictures never show real servers or your own sites. WebKit (the engine of
Safari) draws the pages off screen: nothing appears on your screen and your own FileBridge is not touched.
Run it again after every change to the interface, and add a scene when you add a feature (macOS only).
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOME = tempfile.mkdtemp(prefix='fb-shots-')
os.environ['HOME'] = HOME  # before importing filebridge: its settings folder follows HOME
os.environ['PYTHON_KEYRING_BACKEND'] = 'keyring.backends.fail.Keyring'  # passwords only in memory
sys.path[:0] = [ROOT, os.path.join(ROOT, 'tests')]

import fake_sftp  # noqa: E402
import server  # noqa: E402

OUT = os.path.join(ROOT, 'static', 'manual', 'img')
LANGS = ['en', 'nl', 'es']
WIDTH, HEIGHT = 1440, 900  # the size the FileBridge window opens with
MAX_PX = 1440  # pictures are scaled down to at most this width and saved as JPEG (quality 80)
LOCAL = os.path.join(HOME, 'Websites', 'example-site')
REMOTE = os.path.join(HOME, 'server')
SFTP_PORT = 2299

# A scene: JavaScript run in the freshly loaded and connected app, then FileBridge waits until `until` is
# true (if given) plus `wait` seconds. `crop` cuts out one part of the window (a CSS selector, with a margin).
CONNECTED = "S.status.connected && PR.entries.length > 0"
SCENES = {
    'overview': dict(js="PL.sel = new Set(['index.html', 'about.html']); PL.render()", wait=1),
    'sitemanager': dict(js="openSiteManager()", wait=1.2, crop='#modalRoot .modal'),
    'testconn': dict(js="openSiteManager(); setTimeout(() => document.querySelector('#smTest')?.click(), 600)",
                     until="!!document.querySelector('.ctest')", wait=0.8, crop='#modalRoot .overlay:last-child .modal'),
    'fallback': dict(js="openSiteManager(); setTimeout(() => { const f = document.querySelector('#smForm');"
                        " f.elements.protocol.value = 'ftp'; f.elements.protocol.dispatchEvent(new Event('change'));"
                        " f.elements.fallback_sftp.checked = true; f.elements.fallback_port.value = '26';"
                        " document.querySelector('.sm-tab[data-tab=advanced]').click(); }, 500)",
                     wait=1.5, crop='#modalRoot .modal'),
    'queue': dict(js="PL.sel = new Set(['css', 'images', 'index.html', 'about.html']); PL.render(); PL.transfer()",
                  until="document.querySelectorAll('#queue .job.done').length > 0", wait=1, crop='.bottom', max_h=300),
    'selecttype': dict(js="PR.load('/public_html/images').then(() => { const b = PR.el.querySelector('[data-a=types]');"
                          " const r = b.getBoundingClientRect(); PR.typeFilter.add('.jpg');"
                          " PR.sel = new Set(PR.entries.filter(e => e.ext === 'jpg').map(e => e.name)); PR.render();"
                          " PR.typesMenu(r.left, r.bottom + 4); })", wait=1.5, crop='#paneRemote'),
    'permissions': dict(js="PR.load('/public_html').then(() => { PR.sel = new Set(['css', 'index.html']); PR.render(); PR.chmod(); })",
                        wait=1.5, crop='#modalRoot .modal'),
    'compare': dict(js="PR.load('/public_html').then(() => { openCompare(); setTimeout(() => document.querySelector('#cmpRun').click(), 400); })",
                    until="!!document.querySelector('.chip[data-st=remote_only]')",
                    then="document.querySelector('.chip[data-st=local_newer]').click(); document.querySelector('.chip[data-st=local_only]').click()",
                    wait=1, crop='#modalRoot .modal'),
    'extract': dict(js="PR.load('/public_html').then(() => { PL.sel = new Set(['site-update.zip']); PL.render(); openExtract(PL); })",
                    wait=2, crop='#modalRoot .modal'),
    'deploy': dict(js="PR.load('/public_html').then(() => openDeploy())", wait=1.5, crop='#modalRoot .modal'),
    'settings': dict(js="openSettings()", wait=1.2, crop='#modalRoot .modal'),
}


def make_example_files():
    """A made-up website on 'this computer' and an older copy of it on the test server (made fresh every time)."""
    import shutil
    for d in (LOCAL, REMOTE):
        shutil.rmtree(d, ignore_errors=True)

    def write(path, text, mtime=None):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            f.write(text)
        if mtime:
            os.utime(path, (mtime, mtime))
    old = time.time() - 30 * 86400
    pages = {'index.html': '<h1>Example</h1>', 'about.html': '<h1>About us</h1>', 'contact.html': '<h1>Contact</h1>',
             'css/style.css': 'body { font: 16px sans-serif; }', 'css/print.css': '@media print {}',
             'js/site.js': 'console.log("hi");', '.htaccess': 'Options -Indexes'}
    for name, text in pages.items():
        write(os.path.join(LOCAL, name), text)
    for i, name in enumerate(['beach', 'forest', 'harbour', 'mountain', 'sunset', 'team']):
        write(os.path.join(LOCAL, 'images', f'{name}.jpg'), 'x' * (40000 + i * 9000))
    write(os.path.join(LOCAL, 'images', 'logo.png'), 'x' * 5000)
    write(os.path.join(LOCAL, 'news.html'), '<h1>News</h1>')          # only on this computer
    import zipfile
    with zipfile.ZipFile(os.path.join(LOCAL, 'site-update.zip'), 'w') as z:
        for name in ('index.html', 'css/style.css', 'js/site.js'):
            z.write(os.path.join(LOCAL, name), 'site-update/' + name)
    # the server: an older copy, plus a few files that are only there
    pub = os.path.join(REMOTE, 'public_html')
    for name, text in pages.items():
        write(os.path.join(pub, name), text if name != 'index.html' else '<h1>Old</h1>', old)
    for i, name in enumerate(['beach', 'forest', 'harbour', 'mountain', 'sunset', 'team']):
        write(os.path.join(pub, 'images', f'{name}.jpg'), 'x' * (40000 + i * 9000), old)
    for name in ('banner.webp', 'icon.svg'):
        write(os.path.join(pub, 'images', name), 'x' * 3000, old)
    write(os.path.join(pub, 'old-page.html'), '<h1>Old page</h1>', old)  # only on the server
    write(os.path.join(REMOTE, 'logs', 'access.log'), 'GET /\n', old)
    os.chmod(os.path.join(pub, 'css'), 0o777)


def start_app():
    make_example_files()
    fake_sftp.serve(REMOTE, SFTP_PORT)
    httpd, url = server.create_server(47950)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    site = server.APP.sites.save({
        'name': 'Example website', 'protocol': 'sftp', 'host': '127.0.0.1', 'port': SFTP_PORT, 'username': 'demo',
        'auth': 'password', 'color': 'green', 'local_dir': LOCAL, 'remote_dir': '/public_html',
        'web_map': [{'dir': '/public_html', 'url': 'https://www.example.com'}]}, password='demo')
    server.APP.sites.save({'name': 'Shop', 'folder': 'Customers', 'protocol': 'ftp', 'host': 'ftp.example.org',
                           'username': 'ftp1', 'auth': 'ask'})
    server.APP.sites.save({'name': 'Blog', 'folder': 'Customers', 'protocol': 'sftp', 'host': 'blog.example.net',
                           'username': 'blog', 'auth': 'ask'})
    return site, url


def main():
    langs = [a for a in sys.argv[1:] if a in LANGS] or LANGS
    names = [a for a in sys.argv[1:] if a in SCENES] or list(SCENES)
    site, url = start_app()

    from AppKit import (NSAppearance, NSApplication, NSApplicationActivationPolicyProhibited, NSBackingStoreBuffered,
                        NSBitmapImageFileTypePNG, NSBitmapImageRep, NSWindow)
    from Foundation import NSDate, NSMakeRect, NSRunLoop, NSURL, NSURLRequest
    from WebKit import WKSnapshotConfiguration, WKWebView, WKWebViewConfiguration, WKWebsiteDataStore

    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyProhibited)
    conf = WKWebViewConfiguration.alloc().init()
    conf.setWebsiteDataStore_(WKWebsiteDataStore.nonPersistentDataStore())  # nothing is kept afterwards
    win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(-20000, -20000, WIDTH, HEIGHT), 0, NSBackingStoreBuffered, False)
    view = WKWebView.alloc().initWithFrame_configuration_(NSMakeRect(0, 0, WIDTH, HEIGHT), conf)
    view.setAppearance_(NSAppearance.appearanceNamed_('NSAppearanceNameAqua'))  # always the light look
    win.setContentView_(view)
    win.orderBack_(None)

    def spin(seconds):
        end = time.time() + seconds
        while time.time() < end:
            NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.05))

    def js(code, wait=0.0):
        box = {}
        view.evaluateJavaScript_completionHandler_(code, lambda v, e: box.update(v=v, e=e, done=True))
        end = time.time() + 10
        while not box.get('done') and time.time() < end:
            spin(0.05)
        if wait:
            spin(wait)
        if box.get('e'):
            print('    js error:', box['e'].userInfo().get('WKJavaScriptExceptionMessage') or box['e'])
        return box.get('v')

    def wait_for(cond, seconds=15):
        end = time.time() + seconds
        while time.time() < end:
            if js(cond) is True:
                return True
            spin(0.2)
        print(f'    (gave up waiting for: {cond})')
        return False

    def load(lang):
        """Open FileBridge in `lang`, connected to the example site, local pane on the example website."""
        for tab in list(server.APP.conns):
            server.APP._close_tab(tab)
        server.APP.jobs.clear_finished()  # every picture starts with an empty queue
        server.APP.settings.update({'language': lang})  # FileBridge takes its language from its settings
        view.loadRequest_(NSURLRequest.requestWithURL_(NSURL.URLWithString_(url)))
        # the app switches to the language in its settings, which can mean one extra reload
        wait_for(f"typeof PL !== 'undefined' && !!PL.path && LANG === '{lang}'", 20)
        spin(0.8)
        for _ in range(2):
            js(f"document.querySelector('#siteSelect').value = {json.dumps(site['id'])};"
               " PL.load(" + json.dumps(LOCAL) + "); connect(); 0")
            if wait_for(CONNECTED, 10):
                break
        js("PR.load('/public_html'); 0", 0.8)
        spin(0.5)

    def snapshot(path, selector, max_h=None):
        cfg = WKSnapshotConfiguration.alloc().init()
        if selector:
            raw = js(f"JSON.stringify((() => {{ const b = document.querySelector({selector!r})?.getBoundingClientRect();"
                     " return b ? [b.x, b.y, b.width, b.height] : null; })())")
            r = json.loads(raw) if isinstance(raw, str) else None
            if r:
                x, y, w, h = r
                m = 12
                x, y = max(0, x - m), max(0, y - m)
                w, h = min(WIDTH - x, w + 2 * m), min(HEIGHT - y, h + 2 * m, max_h or HEIGHT)
                cfg.setRect_(NSMakeRect(x, y, w, h))
        box = {}
        view.takeSnapshotWithConfiguration_completionHandler_(cfg, lambda img, e: box.update(img=img, e=e, done=True))
        end = time.time() + 15
        while not box.get('done') and time.time() < end:
            spin(0.05)
        if not box.get('img'):
            print(f'  ! no picture for {path}: {box.get("e")}')
            return
        rep = NSBitmapImageRep.imageRepWithData_(box['img'].TIFFRepresentation())
        png = os.path.join(HOME, 'shot.png')
        rep.representationUsingType_properties_(NSBitmapImageFileTypePNG, None).writeToFile_atomically_(png, True)
        subprocess.run(['sips', '-s', 'format', 'jpeg', '-s', 'formatOptions', '80', '-Z', str(MAX_PX), png, '--out', path],
                       capture_output=True, check=True)

    try:
        for lang in langs:
            os.makedirs(os.path.join(OUT, lang), exist_ok=True)
            for name in names:
                load(lang)
                sc = SCENES[name]
                js(sc['js'] + '; 0')
                if sc.get('until'):
                    wait_for(sc['until'])
                if sc.get('then'):
                    js(sc['then'] + '; 0')
                spin(sc.get('wait', 1))
                # the throwaway home folder shows as ~ (like on a real computer), and no passing notifications
                homes = json.dumps(sorted({HOME, os.path.realpath(HOME)}, key=len, reverse=True))
                js("(() => { const homes = " + homes + "; const tidy = s => homes.reduce((x, h) => x.split(h).join('~'), s);"
                   " document.querySelectorAll('input').forEach(i => { i.value = tidy(i.value); });"
                   " const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);"
                   " while (w.nextNode()) { const n = w.currentNode; if (homes.some(h => n.nodeValue.includes(h))) n.nodeValue = tidy(n.nodeValue); }"
                   " document.querySelector('#toasts').style.display = 'none'; })(); 0", 0.3)
                path = os.path.join(OUT, lang, name + '.jpg')
                snapshot(path, sc.get('crop'), sc.get('max_h'))
                print(f'  {lang}/{name}.jpg')
                make_example_files()  # undo what the scene changed (uploads), for the next one
    finally:
        server.APP.shutdown()


if __name__ == '__main__':
    main()
