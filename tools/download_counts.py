#!/usr/bin/env python3
"""Download counts of the FileBridge releases on GitHub, as one snapshot (JSON) for the downloads dashboard.

    python3 tools/download_counts.py              # prints the snapshot
    python3 tools/download_counts.py out.json     # also writes it to a file
    python3 tools/download_counts.py --history    # also adds it to the history of the FileBridge Downloads app

Counts only the installers (.dmg, .exe, .tar.gz), not checksums or signatures. Uses the public GitHub API
(no login needed; at most 60 requests per hour per address, this makes one).
"""
import datetime
import json
import os
import sys
import urllib.request

# The history of the FileBridge Downloads app (one snapshot per day), shared with that app
HISTORY = os.path.expanduser('~/Library/Application Support/FileBridge Downloads/history.json')

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
