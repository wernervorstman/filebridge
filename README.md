# FileBridge

A FileZilla-style SFTP and FTP client that runs on your Mac and opens in your browser.
You can add your own options through plugins.

## Start

**App (recommended):** open `FileBridge.app` (macOS), `FileBridge.exe` (Windows) or `FileBridge` (Linux).
FileBridge opens in its own window. See [BUILD.md](BUILD.md) for how the apps are built.
Installing without signing certificates, first-launch warnings and Linux: see
[docs/INSTALL.md](docs/INSTALL.md).

**From the source code:**
- Double-click **`start-app.command`** to open FileBridge in its own window.
- Double-click **`start.command`** to open it in your browser (`http://127.0.0.1:8765`).

The first time, setup takes about 20 seconds. If macOS says it can't open the file, right-click it,
choose **Open**, then click **Open** again.

## Your data

FileBridge stores your sites in `~/.filebridge/` and your passwords in the system keychain
(macOS Keychain, Windows Credential Manager, Linux Secret Service). Nothing personal is stored inside
the app. To wipe everything, delete `~/.filebridge/` and remove the **FileBridge** entries from the
keychain. BUILD.md lists all locations.

## What it can do

| | |
|---|---|
| **Two panes** | Local on the left, server on the right, with a queue and log at the bottom. |
| **Transfer** | Use the Upload/Download buttons, double-click a file, or drag between the panes. Drop onto a folder to put the files inside it. When a transfer finishes you get a summary, e.g. *3 uploaded, 5 skipped (already on the server)*. |
| **Opening folders** | **One click** opens a folder (and `..` goes up). To *select* a folder, use its checkbox, ⌘-click, shift-click or right-click. Double-clicking out of habit is safe: the second click is ignored. |
| **Speed** | Several files are sent at the same time over separate connections (default 3, set per site in **Site Manager → Transfer Settings → Simultaneous transfers**, 1–10). FileBridge also avoids unnecessary round trips to the server: one listing per folder instead of a check per file, and no check at all when overwriting. This matters most with many small files on a connection with a lot of latency; on a test server with 200 ms per answer, 27 small files went from 35 s to 12 s. |
| **Tabs** | Every connection opens in its own tab above the panes, so you can be connected to several servers at once. Click a tab to switch (each tab remembers its folders), **×** disconnects it, **＋** opens the Site Manager. **Connect ＋** opens the selected site in a new tab. |
| **Quickconnect** | Connect without saving a site: host, username, password, port. Start the host with `sftp://`, `ftp://`, `ftps://` (implicit TLS) or `ftpes://` (explicit TLS). |
| **Import from FileZilla** | Site Manager → **Import from FileZilla…** reads FileZilla's `sitemanager.xml` and takes over the sites and their folders, protocol, encryption, logon type, colour, transfer mode, charset and default folders. Passwords go straight into the system keychain. Passwords protected with a FileZilla master password can't be read; you type them once when connecting. |
| **View/Edit** | Right-click a server file → **View/Edit** opens it in your editor (Settings → View/Edit; default: the system's text editor). When you save it, FileBridge asks whether to upload it, or does so automatically if you choose *Always*. The **Edited files** tab lists the files being watched. For local files: **Open** (default app) and **Edit** (editor). |
| **Drag from Finder / Explorer** | In the app window, drag files or folders from Finder or Explorer onto the server list to upload them (onto a folder row: into that folder). |
| **Synchronized browsing** | **⇄ Sync browsing** links both sides: open a subfolder on one side and the same subfolder opens on the other. It switches off when a folder doesn't exist on the other side. |
| **Folder tree** | The tree button in each pane shows a folder tree next to the list. It opens to the current folder, and subfolders load when you expand them. |
| **Filters** | Settings → **Filename filters**: names like `.DS_Store`, `.git` and `node_modules` (wildcards allowed) are hidden in the lists and never uploaded or downloaded. The footer shows how many items were filtered. |
| **Speed limits** | Settings → **Speed limits**: maximum upload and download speed in KB/s (0 = unlimited). |
| **Failed files** | If some files fail, the others are still transferred. The queue shows **Retry N** to try just the failed files again. |
| **Public web folders** | When you upload to a public web folder (`public_html`, `www`, `htdocs`, … or a folder with a web address, see below), FileBridge checks for files that shouldn't be downloadable by anyone: archives (`.zip`, `.tar.gz`, …), database dumps (`.sql`), backups (`.bak`, `.old`), `.env` files and keys. You choose **Skip these files**, **Upload anyway** or **Cancel**. Such files already on the server get a red **⚠ public** label, and **Extract here** in a public folder deletes the zip afterwards by default. |
| **Web addresses** | Site Manager → Advanced → **Web addresses**, one per line: `/public_html = https://example.com`. Right-click a server file or folder → **Open in browser** or **Copy URL**. Subfolders follow automatically; add a line for a subfolder with its own address. |
| **Updates** | At startup FileBridge checks GitHub for a newer version and shows **Update available** in the footer (click to open the download page). Turn it off in Settings → Updates. The footer also shows your version. |
| **Quit** | The **power button** (⏻) at the far right of the top bar closes FileBridge: the app window closes, or in browser mode the server stops. If transfers are still running or edited files have changes that are not uploaded yet, FileBridge asks first. |
| **If a file exists** | Bottom right. **Skip if exists** (default) never touches files that are already there, including inside subfolders, so only new files are uploaded. **Overwrite if newer** replaces a file only when yours is newer or a different size. **Overwrite** always replaces. **Skip if same size** and **Resume** are also available. |
| **Select new ▾** | Compares the current folder with the folder open on the other side. *Not on the server* selects what is missing there, *Not on the server + changed here* also selects files that differ, and *Changed here only* selects just the changed files. Then click Upload (or Download on the server side). **Highlight differences** colors the lists: green = not on the other side, orange = changed. Folders that exist on both sides are compared by name only; *Skip if exists* takes care of what's inside them. |
| **Column widths & panel height** | Drag the right edge of a column header to make a column wider or narrower (double-click the edge to reset). When the columns are wider than the pane, the list scrolls sideways. Drag the bar between the file lists and the queue / log up or down (double-click to reset). Both are remembered per pane. |
| **Sort** | Click a column header: Name, Type, Size, Modified or Permissions. Folders always stay on top. |
| **Multi-select** | Click to select one item. ⌘-click toggles an item. Shift-click selects a range. You can also use the checkboxes, ⌘A, or the arrow keys. |
| **Select by type** | **Select type ▾** adds all `.php`, `.jpg` and so on to the selection, and a second click removes them. It also has Select all, Invert selection and Clear. |
| **Delete / Move** | Works on any selection. Local deletes go to the **Trash**. Server deletes are permanent and ask for confirmation first. You can also move by dragging onto a folder or onto `..`. |
| **Right-click** | Opens a menu with every action, plus Copy path, Show in Finder and the plugins. |
| **Permissions** | **Permissions** button or right-click → *Permissions…* opens a FileZilla-style *Change file attributes* window. It has Read/Write/Execute boxes for Owner, Group and Public, plus Set-user-ID, Set-group-ID and Sticky bit. The **Chmod** field stays in sync with the boxes and accepts octal (`755`, `0644`) or text changes (`u+x,go-w`, `a=rx`). When the selected items differ, a box shows *mixed* (–) and the number shows `x`: those bits are left as they are on each item. **Recurse into subdirectories** can apply to all items, files only or folders only. **Only change items that currently have permissions `0777`** limits the change to matching items, including those in subfolders. Works on the server (SFTP and FTP) and on local files. |
| **Permissions after upload** | Set per site in **Site Manager → Transfer Settings**: tick *Give everything I upload to this site fixed permissions* and choose one permission for folders (e.g. `0755`) and one for files (e.g. `0644`). It applies to everything that goes to that site: uploads, drag & drop, sync, deploy (also when the zip is unpacked on the server) and plugins. Leave a field empty to leave that type alone. |
| **Select permission ▾** | Lists every permission in the current folder with a count (e.g. `0777 rwxrwxrwx – 3 files`). Click one to add all those items to the selection, click again to remove them. The **Permissions** column shows `rwxr-xr-x 0755` and sorts by permission. |
| **Choosing folders** | **Browse…** buttons open the system's own dialog (Finder on macOS, Explorer on Windows) to pick a folder or file. The folder button in the local pane does the same. **Use current** next to a server field fills in the folder that is open in the server pane. |
| **Site Manager** | Works like FileZilla's. Sites sit in a tree with folders, with **New site**, **New folder**, **Rename**, **Duplicate** and **Delete** buttons (drag a site onto a folder to move it). Four tabs: **General** (protocol, host, port, encryption, logon type, user, password, background color, comments), **Advanced** (default local and server folder), **Transfer Settings** (FTP active/passive, accepting a certificate that can't be verified) and **Charset** (for FTP file names). **OK** saves everything and **Cancel** discards all changes. Double-click a site to connect. Passwords are stored in the **system keychain** (macOS Keychain, Windows Credential Manager, Linux Secret Service). |
| **Protocols** | **SFTP** (SSH) and **FTP**. FTP offers the same encryption choices as FileZilla: *explicit FTP over TLS if available*, *require explicit TLS*, *require implicit TLS* (port 990) or *plain FTP (insecure)*. |
| **Logon types** | Normal (password saved), Ask for password (never saved), Anonymous (FTP), Key file or SSH agent (SFTP). |
| **Background color** | A site with a color tints the file lists while you're connected, so you can see at a glance which server you're on. |
| **Bookmarks (★)** | Save a local + server folder pair per site and jump to both at once. |
| **Compare & sync** | Compares two folders, including subfolders, by size and date. Shows which files are only local, only on the server, newer or identical. Choose a direction (up, down or both) and optionally *Mirror* to delete extra files. You can change the action for each file before running. |
| **Extract zips** | Right-click a `.zip`: **Upload & extract…** on your Mac, or **Extract here…** on the server. Choose the server folder, *directly into this folder* or *into a new folder named after the zip*, and whether to leave out the zip's top folder (off by default). A **Result** preview shows exactly where the files will end up, e.g. `assets/css/style.css → /public_html/site/assets/css/style.css`, and warns you when leaving out the top folder would miss an existing folder with the same name, whether existing files are overwritten or kept, and the **permissions** for folders and files (default: your site's upload permissions, otherwise 0755/0644). For a zip on the server you can delete it afterwards. Over SFTP with SSH commands the zip is unpacked on the server; over FTP it is unpacked on your Mac and the files are uploaded. The permissions of the target folder itself are never changed. |
| **Deploy** | Uploads a zip, either a fixed file or *the newest zip in a folder* such as `site-update_*.zip`, and unpacks it into a server folder. It can back up the server folder first (a `.tar.gz` on the server, or a download to `~/FileBridge backups`). It unpacks on the server when SSH + unzip is available, otherwise it unpacks locally and uploads the files. **Save to site** remembers the settings, so the next deploy is one click. |

## FTP compared with SFTP

Everything works over FTP too: transfers, resume, compare & sync, deploy and plugins. A few differences:

- **Deploy** always unpacks on your Mac and uploads the files, because FTP can't run commands on the server. A backup is downloaded to `~/FileBridge backups`.
- **Compare & sync** relies on the server keeping file dates (the MFMT command). Most servers support it; if yours doesn't, uploaded files show as "Server newer".
- **FTP over TLS on shared hosting:** the certificate usually belongs to the hosting server (e.g. `server12.example-hosting.com`), not to your domain. Use the server name as Host and the connection stays fully verified. FileBridge tells you the right name if they don't match. Certificates are checked with the operating system's own trust store.
- **Plain FTP** sends your password unencrypted. Use SFTP or FTP over TLS where you can.

## Look & feel

FileBridge uses the DataLore house style from [datalore.eu](https://datalore.eu): a dark header and footer (`#131410`), soft background `#EEF0E7`, green accents (`#5FA83D`, `#7BC94C`), pill-shaped buttons, **Archivo** for headings and **Inter** for text. It has a light and a dark mode. The footer links to datalore.eu. The fonts load from Google Fonts; without internet FileBridge falls back to the system font. The colors are CSS variables at the top of `static/style.css`.

## Security

- The server only listens on `127.0.0.1`. Every request needs a secret token
  that is created each time it starts, so other websites can't use it.
- The first time you connect to a server, its host key is remembered in
  `~/.filebridge/known_hosts`. If the key ever changes, the connection is
  refused with a warning.
- Site settings are stored in `~/.filebridge/sites.json` (without passwords).

## Adding your own options (plugins)

Every `.py` file in `plugins/` adds actions to the **Plugins ▾** menu and the
right-click menu. Copy `plugins/_template.py` to, for example,
`plugins/my_tools.py`, edit it, then choose **Plugins ▾ → Reload plugins**.
You don't need to restart.

```python
NAME = 'My tools'

def clear_cache(ctx):
    rc, out, err = ctx.exec(f'rm -rf {ctx.cwd}/cache/*')
    return 'Cache cleared' if rc == 0 else err

ACTIONS = [
    {'id': 'cache', 'label': 'Clear cache folder', 'side': 'remote',
     'run': clear_cache, 'confirm': 'Delete everything in cache/?'},
]
```

The template lists everything `ctx` offers: selected paths, the current folder,
SFTP/FTP, running commands on the server (SFTP only), upload/download, progress and log.
Examples included: *Calculate size*, *Find files by name*, *Show 30 largest
files* and *Zip selected items*.

## Project layout

```
server.py              local web server + API routing
filebridge/app.py      all API actions
filebridge/remote.py   SFTP connection (paramiko)
filebridge/ftp.py      FTP / FTP over TLS connection
filebridge/transfer.py uploads/downloads with resume
filebridge/sync.py     compare & sync
filebridge/deploy.py   zip deploy
filebridge/plugins.py  plugin loader
filebridge/sites.py    site manager + keychain
filebridge/system.py   macOS / Windows / Linux differences (paths, picker, trash)
filebridge_app.py      desktop app: the same interface in its own window (pywebview)
build/filebridge.spec  PyInstaller recipe (see BUILD.md)
static/                interface (HTML/CSS/JS, no build step)
plugins/               your extensions
```

## Verifying a download

Every release has a `SHA256SUMS.txt` with the checksums of the downloads, signed with the
**DataLore FileBridge Releases** GPG key (fingerprint
`4A2E 2EFB D80F 3DEA 3E81 9577 A801 DC3B 7A0B 668F`, public key in
[docs/filebridge-release-key.asc](docs/filebridge-release-key.asc)).

```bash
gpg --import filebridge-release-key.asc
gpg --verify SHA256SUMS.txt.asc SHA256SUMS.txt      # must say "Good signature"
shasum -a 256 -c SHA256SUMS.txt --ignore-missing    # must say "OK" for your download
```

On Windows: `certutil -hashfile FileBridge.exe SHA256` and compare with `SHA256SUMS.txt`.
Once the code-signing certificates are in place, the Windows and macOS apps are also signed by
DataLore (Windows) and notarized by Apple (macOS).

## License

FileBridge is released under the [MIT License](LICENSE) by DataLore ([datalore.eu](https://datalore.eu)).
The bundled fonts Inter and Archivo are licensed under the SIL Open Font License 1.1.
