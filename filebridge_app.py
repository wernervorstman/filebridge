#!/usr/bin/env python3
"""FileBridge desktop app: the FileBridge server shown in its own native window (pywebview).

Works on macOS (WebKit), Windows (Edge WebView2) and Linux (GTK WebKit or Qt).
This is the entry point for the packaged app (see build/ and BUILD.md).
"""
import json
import os
import sys
import threading
import webbrowser

BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

import webview  # noqa: E402

import server  # noqa: E402
from filebridge import system  # noqa: E402

APP_PORT = 47655  # fixed, so the window keeps its settings (sort order, etc.) between runs


def enable_os_drop(window):
    """Files dragged from Finder / Explorer: pass their full paths to the page (window.fbOsDrop)."""
    from webview.dom import DOMEventHandler

    def on_drop(event):
        files = (event.get('dataTransfer') or {}).get('files') or []
        paths = [f['pywebviewFullPath'] for f in files if f.get('pywebviewFullPath')]
        if paths:
            window.evaluate_js(f'window.fbOsDrop && window.fbOsDrop({json.dumps(paths)})')

    def register():
        try:
            window.dom.document.events.drop += DOMEventHandler(on_drop, prevent_default=True)
        except Exception as e:  # dropping from Finder is a convenience; never block the app
            print(f'File drop from the system is not available: {e}', flush=True)

    window.events.loaded += register  # again after every page load


def main():
    httpd, url = server.create_server(APP_PORT)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    webview.settings['OPEN_EXTERNAL_LINKS_IN_BROWSER'] = True  # e.g. the datalore.eu link
    window = webview.create_window(
        'FileBridge', url, width=1440, height=900, min_size=(960, 620),
        text_select=True, background_color='#131410',
    )
    system.WINDOW = window
    server.APP.quit_hook = window.destroy  # Quit button: webview.start() returns, then we clean up
    enable_os_drop(window)
    # Window icon: Windows needs an .ico (a .png crashes WinForms), Linux uses the .png,
    # macOS takes the icon from the app bundle.
    icon = None
    if system.IS_WIN:
        icon = os.path.join(system.resource_dir(), 'static', 'icon.ico')
    elif not system.IS_MAC:
        icon = os.path.join(system.resource_dir(), 'static', 'icon.png')
    if icon and not os.path.exists(icon):
        icon = None
    try:
        webview.start(private_mode=False, storage_path=os.path.join(system.user_data_dir(), 'webview'),
                      icon=icon)
    except Exception as e:  # e.g. Linux without a GTK/Qt web engine: use the default browser instead
        print(f'Could not open the app window ({e}); opening FileBridge in your browser.', flush=True)
        system.WINDOW = None
        webbrowser.open(url)
        stopped = threading.Event()
        server.APP.quit_hook = stopped.set
        try:
            stopped.wait()  # keep serving until Quit or the process is stopped
        except KeyboardInterrupt:
            pass
    finally:
        server.APP.shutdown()
        httpd.shutdown()


if __name__ == '__main__':
    main()
