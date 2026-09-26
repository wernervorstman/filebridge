# Building FileBridge

FileBridge is packaged with [PyInstaller](https://pyinstaller.org). PyInstaller can only build for the
system it runs on, so each platform is built on that platform. The GitHub Actions workflow does all three.

| Platform | Result | Notes |
|---|---|---|
| macOS   | `FileBridge.app`, `FileBridge-macOS.dmg` | Own window (WebKit). |
| Windows | `FileBridge.exe` (single file) | Own window (Edge WebView2, built into Windows 10/11). |
| Linux   | `FileBridge` (single file, in a `.tar.gz`) | Opens in your default browser unless a GTK/Qt web engine is bundled (see below). |

## Build on this Mac

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-build.txt
.venv/bin/pyinstaller --noconfirm --clean --distpath dist --workpath build/work build/filebridge.spec
hdiutil create -volname FileBridge -srcfolder dist/FileBridge.app -ov -format UDZO dist/FileBridge-macOS.dmg
```

The app is in `dist/FileBridge.app` and the disk image in `dist/FileBridge-macOS.dmg`.

## Build Windows and Linux with GitHub Actions

1. Put this folder in a GitHub repository. `.gitignore` already leaves out `.venv/` and the build output.
2. Push a version tag, e.g. `git tag v1.0.0 && git push --tags`, or start **Build FileBridge**
   under the repository's **Actions** tab.
3. After ~10 minutes the downloads appear under the workflow run (Artifacts). For a tag they also
   appear as a GitHub Release.

## First launch warnings (unsigned builds)

- **macOS:** "FileBridge.app Not Opened – Apple could not verify…". Click **Done**, then
  **System Settings → Privacy & Security → Open Anyway** (macOS 15 and later; on macOS 14 and earlier
  right-click the app → **Open** → **Open**). This is needed once per version. To remove the warning for everyone, sign and notarize the
  app with an Apple Developer ID ($99/year).
- **Windows:** SmartScreen shows "Windows protected your PC". Click **More info** → **Run anyway**.
  Signing with a code-signing certificate removes this.

## Where FileBridge keeps its data

| What | Where |
|---|---|
| Sites (no passwords) | `~/.filebridge/sites.json`, `folders.json` |
| Trusted server keys | `~/.filebridge/known_hosts` |
| Passwords | macOS Keychain / Windows Credential Manager / Linux Secret Service, under the service **FileBridge** |
| Plugins (packaged app) | macOS `~/Library/Application Support/FileBridge/plugins`, Windows `%APPDATA%\FileBridge\plugins`, Linux `~/.local/share/FileBridge/plugins` |
| Window settings | the same FileBridge folder, `webview/` |

None of this is inside the app, so the app itself contains no personal data and can be shared freely.

## Linux: own window instead of the browser

The Linux build falls back to the browser because a web engine is not bundled. For a real window,
add `pywebview[qt]` to `requirements.txt` before building. This makes the download much bigger
(~150 MB).
