# Installing and using FileBridge

FileBridge is free and open source. The apps are **not signed** with a paid Apple or Microsoft certificate.
That is why macOS and Windows warn you the first time you open FileBridge. This is expected: the system doesn't
know who made the app, not because something is wrong with it. Below you'll find, for each system, how to open
FileBridge safely anyway.

Only download FileBridge from the official places: the GitHub releases page
(<https://github.com/wernervorstman/filebridge/releases/latest>) or the links on datalore.wernervorstman.nl.
If you got the file from someone else, don't bypass the warnings this way.

| System | File | Runs on |
|---|---|---|
| macOS | `FileBridge-macOS.dmg` | Macs with Apple silicon (M1 or newer) |
| Windows | `FileBridge.exe` | Windows 10 and 11, 64-bit |
| Linux | `FileBridge-Linux.tar.gz` | 64-bit Linux (x86_64), e.g. Ubuntu 22.04 or newer, Debian 12, Fedora 36+ |

---

## macOS

### Install

1. Download `FileBridge-macOS.dmg` and double-click it.
2. Drag **FileBridge** into the **Applications** folder.
3. Eject the *FileBridge* disk (right-click → Eject).

Always start FileBridge from **Applications**, not from the disk image or the Downloads folder.

### Opening it the first time

Double-click FileBridge in Applications. macOS says:

> "FileBridge.app" Not Opened — Apple could not verify "FileBridge.app" is free of malware…

1. Click **Done**. Do **not** click *Move to Bin*.
2. Open **System Settings → Privacy & Security**.
3. Scroll down to **Security**. You'll see *"FileBridge.app" was blocked…*. Click **Open Anyway**.
4. Confirm with your password or Touch ID, then click **Open** once more.

You only need to do this once per version. On macOS 14 Sonoma and earlier you can also right-click the app →
**Open** → **Open**.

<details>
<summary>Advanced: using Terminal</summary>

You can also remove the "downloaded from the internet" flag in Terminal. Only do this for a FileBridge you
downloaded from the official places:

```bash
xattr -dr com.apple.quarantine /Applications/FileBridge.app
```
</details>

### Keychain prompts

When you save a password in the Site Manager, FileBridge stores it in the **macOS Keychain**. The first time
it's used, macOS asks once or twice:

> FileBridge wants to use your confidential information stored in "FileBridge" in your keychain.

These are two separate prompts for two keychain items; both belong to FileBridge. Enter your **Mac password**
(the one you log in with) and click **Always Allow**, not *Allow*. Then macOS won't ask again on every
connection.

After a **new version** of FileBridge, macOS asks once more: without a certificate, macOS can't tell that the new
version comes from the same developer. Choose **Always Allow** again.

### Folder access

When you open a folder such as Desktop, Documents or an external drive in FileBridge, macOS asks whether
FileBridge may access it. Click **Allow**. If you clicked *Don't Allow* earlier, switch it on under
**System Settings → Privacy & Security → Files and Folders → FileBridge**.

---

## Windows

### Install

FileBridge is a single file; there is no installer.

1. Download `FileBridge.exe`.
2. Put it in a permanent place, e.g. a new folder `C:\Users\<your name>\Apps\FileBridge`.
3. For a desktop shortcut: right-click → **Show more options → Create shortcut** and drag the shortcut to the
   desktop.

FileBridge uses **Microsoft Edge WebView2** for its window. It comes with Windows 10 and 11. If the window stays
blank, install the *WebView2 Runtime* from Microsoft's website.

### Opening it the first time

Double-click `FileBridge.exe`. Windows shows a blue window:

> Windows protected your PC — Microsoft Defender SmartScreen prevented an unrecognized app from starting.

1. Click **More info**.
2. Click **Run anyway**.

You only need to do this once per version.

Does your antivirus (for example Windows Defender) flag FileBridge? Apps built with PyInstaller that aren't
signed are sometimes flagged by mistake. Check that you downloaded the file from the official places, then choose
**Allow on device** for the alert in Windows Security.

### Passwords

Saved passwords are stored in **Windows Credential Manager**, under *FileBridge*. Windows doesn't ask for an
extra password.

---

## Linux

### Install

```bash
tar -xzf FileBridge-Linux.tar.gz
chmod +x FileBridge
mkdir -p ~/.local/bin && mv FileBridge ~/.local/bin/
```

Start it by typing `FileBridge` in a terminal (or `~/.local/bin/FileBridge` if that folder isn't on your `PATH`).
Linux doesn't warn about a missing certificate.

### Window or browser

The Linux build has no window of its own. FileBridge therefore opens in your **default browser** (an address
starting with `http://127.0.0.1:`). It only runs on your own computer and can't be reached from the internet.
Keep the terminal open while you use FileBridge; stop it with **Ctrl+C**.

Everything works in the browser, with one difference: the **Browse…** buttons can't open a folder picker. Type or
paste the folder path instead.

### Passwords

FileBridge stores passwords in your desktop's keyring through *Secret Service*: **GNOME Keyring** (GNOME, Ubuntu)
or **KWallet** (KDE). Most desktops already have one. Without it, FileBridge only remembers a password while it's
running. In that case install, for example, `gnome-keyring`.

### Deleting to the Trash

Local files you delete go to your desktop's Trash, so you can restore them.

---

## Getting started (all systems)

1. Open the **Site Manager** and click **New site**.
2. Choose the **Protocol**: **SFTP** if your server has SSH (recommended), otherwise **FTP** with
   *Use explicit FTP over TLS if available*.
3. Fill in **Host**, **Port** (SFTP usually 22, FTP 21), **User** and **Password**. Your hosting provider gives
   you these details.
4. Click **OK** and double-click the site to connect.
5. On the first SFTP connection, FileBridge remembers the server's key (in `~/.filebridge/known_hosts`). If that
   key changes later, FileBridge refuses to connect and shows a warning. This happens when the server has been
   reinstalled, but it can also mean someone is intercepting the connection. If in doubt, check with your
   hosting provider before removing the old key from that file.

Your own computer is on the left, the server on the right. Drag files between the two sides, or use the
**Upload** and **Download** buttons. By default **Skip if exists** is selected (bottom right): files that are
already on the server are not overwritten.

The [README](../README.md) explains all features.

## Updating to a new version

- **macOS:** drag the new FileBridge into Applications and choose **Replace**. Then open it again via
  *Privacy & Security → Open Anyway*, and choose **Always Allow** again at the keychain prompt.
- **Windows:** replace `FileBridge.exe` with the new version and choose **Run anyway** again at SmartScreen.
- **Linux:** replace the file in `~/.local/bin`.

Your sites and passwords are kept; they are not stored inside the app.

## Removing everything

1. Delete the app (macOS: drag it from Applications to the Bin; Windows and Linux: delete the file).
2. Delete the `.filebridge` folder in your home folder. It contains your sites.
3. Delete the folder with settings and plugins:
   - macOS: `~/Library/Application Support/FileBridge`
   - Windows: `%APPDATA%\FileBridge`
   - Linux: `~/.local/share/FileBridge`
4. Delete the saved passwords named **FileBridge** from Keychain Access (macOS), Credential Manager (Windows), or
   Passwords and Keys / KWallet (Linux).

## Troubleshooting

| Problem | Solution |
|---|---|
| macOS: *"is damaged and can't be opened"* | The download is incomplete or the app still has the download flag. Download again, or use the Terminal command above. |
| macOS: keeps asking for the keychain password | Click **Always Allow** instead of *Allow*. If it keeps happening, delete the FileBridge items in Keychain Access and save the password again. |
| macOS: doesn't run on an Intel Mac | The app is built for Apple silicon. Run FileBridge from the source code instead (see the README). |
| Windows: blank window | Install the Microsoft Edge WebView2 Runtime. |
| Linux: *"GLIBC … not found"* | Your Linux version is too old. Use Ubuntu 22.04 or newer, or run from the source code. |
| Can't connect | Check host, port and protocol. For FTP over TLS on shared hosting, use the hosting server's name as Host; FileBridge tells you the right name if it doesn't match. |
