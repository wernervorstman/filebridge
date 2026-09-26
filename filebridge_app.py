#!/usr/bin/env python3
"""FileBridge desktop app: the FileBridge server shown in its own native window (pywebview).

Works on macOS (WebKit), Windows (Edge WebView2) and Linux (GTK WebKit or Qt).
This is the entry point for the packaged app (see build/ and BUILD.md).
"""
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


def main():
    httpd, url = server.create_server(APP_PORT)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    webview.settings['OPEN_EXTERNAL_LINKS_IN_BROWSER'] = True  # e.g. the datalore.eu link
    window = webview.create_window(
        'FileBridge', url, width=1440, height=900, min_size=(960, 620),
        text_select=True, background_color='#131410',
    )
    system.WINDOW = window
    icon = os.path.join(system.resource_dir(), 'static', 'icon.png')
    try:
        webview.start(private_mode=False, storage_path=os.path.join(system.user_data_dir(), 'webview'),
                      icon=icon if os.path.exists(icon) else None)
    except Exception as e:  # e.g. Linux without a GTK/Qt web engine: use the default browser instead
        print(f'Could not open the app window ({e}); opening FileBridge in your browser.', flush=True)
        system.WINDOW = None
        webbrowser.open(url)
        try:
            threading.Event().wait()  # keep serving until the process is stopped
        except KeyboardInterrupt:
            pass
    finally:
        server.APP.shutdown()
        httpd.shutdown()


if __name__ == '__main__':
    main()
