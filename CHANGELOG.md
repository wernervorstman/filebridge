# Changelog

What changed in each FileBridge version. The section of a version is also the text of its GitHub release
and of the update notice in the app, so keep it short and written for users.

## 1.3.0
- FileBridge is now available in **English, Dutch and Spanish**: switch with the flags at the top right.
- A **user manual** with pictures in all three languages: **Manual** at the bottom of the window, or Settings → User manual.
- **Settings** has a new look with tabs (General, Filters, Transfers, View/Edit, User manual), behind the gear at the top right.
- The synchronized browsing button is now the **⇄** icon, so the top bar fits on one line.
- A file that times out or loses its connection is tried again automatically on a fresh connection (up to 3 times).
- Extract zip shows the whole contents of the zip (scroll through it), and dialogs never get taller than the window.
- **What went wrong?** in the queue shows every file that failed, with the server's reply and a plain explanation.
- FileBridge keeps a log file (`~/.filebridge/filebridge.log`), so a problem can be looked up after closing.

## 1.2.8
- The update notice now also checks while FileBridge stays open, and tells you once what is new in a version.
- Compare & sync: click a label such as "Only on server" to tick all those files, then **Upload checked** or
  **Download checked** transfers them right away.
- Select type: shows only the files of the chosen types ("show all" at the bottom brings the rest back).
- Only the checkbox selects a file; clicking a name no longer changes the selection.
- Scrollbars are always visible when a list is longer than the window.

## 1.2.7
- Footer shows "by DataLore".

## 1.2.6
- Fixed: "Update available" never appeared in the packaged app. Versions up to 1.2.5 can't see updates;
  download the new version once by hand.

## 1.2.5
- Site Manager: **Test connection** checks server name, port, encryption and login step by step.
- Hint for the right FTP username on Plesk, DirectAdmin and cPanel hosting.
- Optional switch to SFTP when FTP is blocked on your network (Site Manager → Advanced).
- Clearer messages when FTP times out or a login is refused.

## 1.2.4
- macOS app is signed with a Developer ID and notarized by Apple.
- The power button stays top right in a narrow window.

## 1.2.3
- Windows app is signed by DataLore.
- Power button to close FileBridge, and the server's own reply when a login fails.
