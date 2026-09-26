# PyInstaller recipe for FileBridge – build with:  pyinstaller build/filebridge.spec
# macOS  -> dist/FileBridge.app      (and a .dmg, see BUILD.md)
# Windows -> dist/FileBridge.exe     (single file)
# Linux  -> dist/FileBridge          (single file)
import os
import sys

from PyInstaller.utils.hooks import collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, '..'))
sys.path.insert(0, ROOT)
from filebridge import __version__  # noqa: E402

IS_MAC = sys.platform == 'darwin'
IS_WIN = sys.platform.startswith('win')

hidden = collect_submodules('filebridge') + [
    # plugins are loaded at runtime and may use these
    'fnmatch', 'zipfile', 'shlex', 'glob', 'tempfile', 'csv', 'hashlib',
    # password stores for every platform
    'keyring.backends.macOS', 'keyring.backends.Windows', 'keyring.backends.SecretService',
    'keyring.backends.chainer', 'keyring.backends.fail',
]

a = Analysis(
    [os.path.join(ROOT, 'filebridge_app.py')],
    pathex=[ROOT],
    datas=[(os.path.join(ROOT, 'static'), 'static'), (os.path.join(ROOT, 'plugins'), 'plugins')],
    hiddenimports=hidden,
    excludes=['tkinter', 'PIL', 'PyInstaller'],
    noarchive=False,
)
pyz = PYZ(a.pure)

if IS_MAC:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='FileBridge', console=False,
              icon=os.path.join(SPECPATH, 'icon.icns'))
    coll = COLLECT(exe, a.binaries, a.datas, name='FileBridge')
    app = BUNDLE(
        coll, name='FileBridge.app', icon=os.path.join(SPECPATH, 'icon.icns'),
        bundle_identifier='eu.datalore.filebridge', version=__version__,
        info_plist={
            'CFBundleName': 'FileBridge',
            'CFBundleDisplayName': 'FileBridge',
            'CFBundleShortVersionString': __version__,
            'NSHumanReadableCopyright': 'DataLore – datalore.eu',
            'NSHighResolutionCapable': True,
            'LSMinimumSystemVersion': '11.0',
            # Texts macOS shows when FileBridge asks for access to protected folders
            'NSDownloadsFolderUsageDescription': 'FileBridge needs access to your Downloads folder to upload and download files there.',
            'NSDocumentsFolderUsageDescription': 'FileBridge needs access to your Documents folder to upload and download files there.',
            'NSDesktopFolderUsageDescription': 'FileBridge needs access to your Desktop folder to upload and download files there.',
            'NSRemovableVolumesUsageDescription': 'FileBridge needs access to external drives to upload and download files there.',
            'NSNetworkVolumesUsageDescription': 'FileBridge needs access to network drives to upload and download files there.',
        },
    )
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='FileBridge', console=False,
              icon=os.path.join(SPECPATH, 'icon.ico') if IS_WIN else None, upx=False)
