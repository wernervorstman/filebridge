#!/usr/bin/env python3
"""Build the FileBridge Downloads app (a Mac app showing how often FileBridge is downloaded) and put it in /Applications.

    .venv/bin/python tools/make_downloads_app.py

Compiles tools/downloads_app/FileBridgeDownloads.swift (Cocoa + WebKit), adds dashboard.html and an icon in the
FileBridge style (a bar chart), and signs it for this Mac. The app keeps its history in
~/Library/Application Support/FileBridge Downloads/history.json; tools/download_counts.py --history adds to it too.
"""
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'tools', 'downloads_app')
NAME = 'FileBridge Downloads'
TARGET = os.path.join('/Applications', NAME + '.app')

sys.path.insert(0, os.path.join(ROOT, 'tools'))
import make_icon  # noqa: E402


def main():
    with tempfile.TemporaryDirectory() as td:
        app = os.path.join(td, NAME + '.app')
        macos, res = os.path.join(app, 'Contents', 'MacOS'), os.path.join(app, 'Contents', 'Resources')
        os.makedirs(macos)
        os.makedirs(res)
        subprocess.run(['swiftc', '-O', os.path.join(SRC, 'FileBridgeDownloads.swift'), '-o',
                        os.path.join(macos, 'FileBridgeDownloads'), '-framework', 'Cocoa', '-framework', 'WebKit'], check=True)
        shutil.copy(os.path.join(SRC, 'dashboard.html'), res)
        # icon: the FileBridge icon style with a bar chart
        icon = make_icon.draw(make_icon.CHART)
        iconset = os.path.join(td, 'AppIcon.iconset')
        os.makedirs(iconset)
        for px in (16, 32, 128, 256, 512):
            icon.resize((px, px)).save(os.path.join(iconset, f'icon_{px}x{px}.png'))
            icon.resize((px * 2, px * 2)).save(os.path.join(iconset, f'icon_{px}x{px}@2x.png'))
        subprocess.run(['iconutil', '-c', 'icns', iconset, '-o', os.path.join(res, 'AppIcon.icns')], check=True)
        with open(os.path.join(app, 'Contents', 'Info.plist'), 'wb') as f:
            plistlib.dump({'CFBundleName': NAME, 'CFBundleDisplayName': NAME, 'CFBundleIdentifier': 'eu.datalore.filebridge.downloads',
                           'CFBundleExecutable': 'FileBridgeDownloads', 'CFBundleIconFile': 'AppIcon',
                           'CFBundlePackageType': 'APPL', 'CFBundleVersion': '1.0', 'CFBundleShortVersionString': '1.0',
                           'LSMinimumSystemVersion': '13.0', 'NSHighResolutionCapable': True,
                           'NSHumanReadableCopyright': '© DataLore'}, f)
        subprocess.run(['codesign', '--force', '--deep', '-s', '-', app], check=True)
        if os.path.exists(TARGET):
            shutil.rmtree(TARGET)
        shutil.copytree(app, TARGET, symlinks=True)
    print('Built:', TARGET)


if __name__ == '__main__':
    main()
