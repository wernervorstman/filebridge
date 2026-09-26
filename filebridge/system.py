"""Everything that differs between macOS, Windows and Linux, in one place.

- where bundled files (static/, example plugins) live – also inside a PyInstaller build
- where the user's plugins live
- file/folder picker, "show in Finder/Explorer", move to Trash / Recycle Bin
"""
import os
import shutil
import subprocess
import sys

from .common import ApiError

IS_MAC = sys.platform == 'darwin'
IS_WIN = sys.platform.startswith('win')
FROZEN = getattr(sys, 'frozen', False)

# Set by the desktop launcher (filebridge_app.py) when running in its own window.
WINDOW = None


def resource_dir():
    """Folder with static/ and the bundled example plugins."""
    if FROZEN:
        return getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def user_data_dir():
    if IS_MAC:
        base = os.path.expanduser('~/Library/Application Support')
    elif IS_WIN:
        base = os.environ.get('APPDATA') or os.path.expanduser('~\\AppData\\Roaming')
    else:
        base = os.environ.get('XDG_DATA_HOME') or os.path.expanduser('~/.local/share')
    path = os.path.join(base, 'FileBridge')
    os.makedirs(path, exist_ok=True)
    return path


def plugins_dir():
    """Plugins folder. In a built app it lives in the user's data folder (the app itself is read-only);
    the first time, the example plugins are copied there."""
    bundled = os.path.join(resource_dir(), 'plugins')
    if not FROZEN:
        return bundled
    target = os.path.join(user_data_dir(), 'plugins')
    if not os.path.isdir(target):
        os.makedirs(target)
        if os.path.isdir(bundled):
            for name in os.listdir(bundled):
                if name.endswith('.py'):
                    shutil.copy2(os.path.join(bundled, name), os.path.join(target, name))
    return target


def keychain_name():
    return 'the macOS Keychain' if IS_MAC else 'Windows Credential Manager' if IS_WIN else 'the system keyring'


def permission_hint(path):
    """A helpful message when the operating system blocks access to a local folder."""
    name = os.path.basename(path.rstrip('/\\')) or path
    if IS_MAC:
        return (f'macOS does not allow FileBridge to open "{name}" yet. Open System Settings → Privacy & Security → '
                f'Files and Folders, find FileBridge and switch on access to this folder (or add FileBridge under '
                f'Full Disk Access). Then click Refresh.')
    return f'You do not have permission to open "{name}".'


def file_manager_name():
    return 'Finder' if IS_MAC else 'Explorer' if IS_WIN else 'file manager'


def reveal(path):
    """Show a file (selected) or open a folder in Finder / Explorer / the file manager."""
    is_file = os.path.isfile(path)
    if IS_MAC:
        subprocess.run(['open', '-R', path] if is_file else ['open', path], check=False)
    elif IS_WIN:
        subprocess.run(['explorer', f'/select,{path}'] if is_file else ['explorer', path], check=False)
    else:
        subprocess.run(['xdg-open', os.path.dirname(path) if is_file else path], check=False)


def trash(path):
    """Move to the Trash / Recycle Bin (recoverable) instead of deleting permanently."""
    try:
        from send2trash import send2trash
    except ImportError:
        send2trash = None
    if send2trash:
        send2trash(path)
        return
    if IS_MAC:  # fallback without send2trash
        script = f'tell application "Finder" to delete (POSIX file {as_applescript(path)} as alias)'
        subprocess.run(['osascript', '-e', script], check=True, capture_output=True)
        return
    raise ApiError('Moving to the Recycle Bin is not available (send2trash is missing)')


def as_applescript(s):
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'


def pick(kind='folder', start='', types=(), invisibles=False, prompt=''):
    """Native file/folder picker. Returns a path, or None when cancelled."""
    if WINDOW is not None:  # desktop app: pywebview's native dialog works on every OS
        import webview
        dialog = webview.FOLDER_DIALOG if kind == 'folder' else webview.OPEN_DIALOG
        file_types = ()
        if kind == 'file' and types:
            file_types = (f'Files ({";".join("*." + t for t in types)})',)
        result = WINDOW.create_file_dialog(dialog, directory=start or '', file_types=file_types)
        if not result:
            return None
        return result[0] if isinstance(result, (list, tuple)) else result
    if IS_MAC:  # browser mode on macOS: Finder dialog through AppleScript
        extra = ''
        if kind == 'file' and types:
            extra += ' of type {' + ', '.join(as_applescript(t) for t in types) + '}'
        if invisibles:
            extra += ' with invisibles'
        script = (f'activate\nPOSIX path of (choose {kind} with prompt {as_applescript(prompt)} '
                  f'default location (POSIX file {as_applescript(start)}){extra})')
        r = subprocess.run(['osascript', '-e', script], capture_output=True, text=True, timeout=900)
        if r.returncode != 0:
            if '-128' in r.stderr:  # Cancel
                return None
            raise ApiError(f'Could not open the Finder dialog: {r.stderr.strip()}')
        return r.stdout.strip()
    raise ApiError('The file picker is available in the FileBridge app window. Type the path instead.')
