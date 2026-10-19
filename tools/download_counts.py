#!/usr/bin/env python3
"""Download counts of the FileBridge releases on GitHub, as one snapshot (JSON) for the downloads dashboard.

    python3 tools/download_counts.py              # prints the snapshot
    python3 tools/download_counts.py out.json     # also writes it to a file
    python3 tools/download_counts.py --history    # also adds it to the local dashboard in ~/Documents/FileBridge Downloads

Counts only the installers (.dmg, .exe, .tar.gz), not checksums or signatures. Uses the public GitHub API
(no login needed; at most 60 requests per hour per address, this makes one).
"""
import datetime
import json
import os
import shutil
import sys
import urllib.request

# The local dashboard: a page to open in the browser, with its history (one snapshot per day) next to it
DASHBOARD_DIR = os.path.expanduser('~/Documents/FileBridge Downloads')
HISTORY = os.path.join(DASHBOARD_DIR, 'history.json')
PAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'downloads-dashboard-local.html')

API = 'https://api.github.com/repos/wernervorstman/filebridge/releases?per_page=100'
KIND = {'.dmg': 'mac', '.exe': 'win', '.tar.gz': 'linux'}


def snapshot():
    req = urllib.request.Request(API, headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'FileBridge-stats'})
    with urllib.request.urlopen(req, timeout=20) as r:
        releases = json.load(r)
    rels = []
    for rel in releases:
        counts = {'mac': 0, 'win': 0, 'linux': 0}
        for a in rel.get('assets', []):
            kind = next((k for ext, k in KIND.items() if a['name'].endswith(ext)), None)
            if kind:
                counts[kind] += a.get('download_count', 0)
        rels.append({'tag': rel['tag_name'], 'published': rel.get('published_at'), **counts})
    now = datetime.datetime.now().astimezone()
    total = {k: sum(r[k] for r in rels) for k in ('mac', 'win', 'linux')}
    return {'date': now.date().isoformat(), 'taken_at': now.isoformat(timespec='seconds'),
            'total': sum(total.values()), **total, 'releases': rels}


def add_to_history(snap, path=HISTORY):
    """Put the snapshot in the history file, replacing an earlier one of the same day."""
    try:
        with open(path) as f:
            history = json.load(f)
    except (FileNotFoundError, ValueError):
        history = []
    history = [s for s in history if s.get('date') != snap['date']] + [snap]
    history.sort(key=lambda s: s['date'])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(history, f, indent=1)
    os.replace(tmp, path)
    # the page reads the history as a script (a browser may not read a JSON file next to a local page)
    folder = os.path.dirname(path)
    with open(os.path.join(folder, 'history.js'), 'w') as f:
        f.write('window.FB_HISTORY = ' + json.dumps(history) + ';\n')
    shutil.copy(PAGE, os.path.join(folder, 'FileBridge Downloads.html'))


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if a != '--history']
    snap = snapshot()
    text = json.dumps(snap, indent=1)
    if args:
        with open(args[0], 'w') as f:
            f.write(text)
    if '--history' in sys.argv:
        add_to_history(snap)
    print(text)
