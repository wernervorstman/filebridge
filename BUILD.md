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

## Signing

The GitHub build signs everything by itself **as soon as the secrets below exist** (repository
**Settings → Secrets and variables → Actions → New repository secret**). Until then it builds
unsigned, as before. Never paste these values anywhere else.

### Windows – Certum Standard Code Signing in the Cloud (SimplySign)

| Secret | Value |
|---|---|
| `CERTUM_USERNAME` | the e-mail address you log in to SimplySign with |
| `CERTUM_TOTP_SECRET` | the TOTP secret of your SimplySign account (Base32). You get it when you set up SimplySign: it is the `secret=` part of the QR code / `otpauth://` link. Keep it as safe as a password. |

The exe is signed with SHA-256 and a Certum timestamp, and then verified. The signing step uses
`jay0lee/certum-cloud-code-sign`, pinned to a reviewed commit (it only downloads SimplySign
Desktop from files.certum.eu and masks the credentials). Review the code again before changing
that commit.

### macOS – Apple Developer ID + notarization

| Secret | Value |
|---|---|
| `MACOS_CERTIFICATE_P12` | your **Developer ID Application** certificate, exported from Keychain Access as `.p12`, then base64: `base64 -i cert.p12 \| pbcopy` |
| `MACOS_CERTIFICATE_PASSWORD` | the password you gave the `.p12` export |
| `MACOS_SIGNING_IDENTITY` | the certificate's name, e.g. `Developer ID Application: Your Name (TEAMID)` (shown by `security find-identity -v -p codesigning`) |
| `APPLE_ID` | your Apple ID e-mail |
| `APPLE_TEAM_ID` | your 10-character Team ID (developer.apple.com → Membership) |
| `APPLE_APP_PASSWORD` | an app-specific password from appleid.apple.com → Sign-In and Security |

The app is signed with the hardened runtime (`build/entitlements.plist`), notarized and stapled;
the `.dmg` is signed, notarized and stapled too.

### Checksums and GPG (all platforms)

Every release gets `SHA256SUMS.txt`. When `GPG_PRIVATE_KEY` is set, `SHA256SUMS.txt.asc` and
`FileBridge-Linux.tar.gz.asc` are added: detached signatures with the **DataLore FileBridge
Releases** key (fingerprint `4A2E 2EFB D80F 3DEA 3E81 9577 A801 DC3B 7A0B 668F`). The public key
is in `docs/filebridge-release-key.asc`. The private key is only kept by the maintainer and in the
GitHub secret.

| Secret | Value |
|---|---|
| `GPG_PRIVATE_KEY` | the complete contents of the private key file (`-----BEGIN PGP PRIVATE KEY BLOCK-----` …) |

## First launch warnings

Official releases (1.2.4 and later) are signed: macOS with a Developer ID and notarized by Apple, Windows by DataLore
(Certum). Builds you make yourself without the signing secrets are unsigned and get the usual warnings:

- **macOS:** "FileBridge.app Not Opened – Apple could not verify…". Click **Done**, then
  **System Settings → Privacy & Security → Open Anyway** (on macOS 14 and earlier: right-click the app → **Open** → **Open**).
- **Windows:** SmartScreen shows "Windows protected your PC". Click **More info** → **Run anyway**.

## Where FileBridge keeps its data

| What | Where |
|---|---|
| Sites (no passwords) | `~/.filebridge/sites.json`, `folders.json` |
| Trusted server keys | `~/.filebridge/known_hosts` |
| Log | `~/.filebridge/filebridge.log` (and `.1`, about 2 MB in total) |
| Passwords | macOS Keychain / Windows Credential Manager / Linux Secret Service, under the service **FileBridge** |
| Plugins (packaged app) | macOS `~/Library/Application Support/FileBridge/plugins`, Windows `%APPDATA%\FileBridge\plugins`, Linux `~/.local/share/FileBridge/plugins` |
| Window settings | the same FileBridge folder, `webview/` |

None of this is inside the app, so the app itself contains no personal data and can be shared freely.

## Linux: own window instead of the browser

The Linux build falls back to the browser because a web engine is not bundled. For a real window,
add `pywebview[qt]` to `requirements.txt` before building. This makes the download much bigger
(~150 MB).
