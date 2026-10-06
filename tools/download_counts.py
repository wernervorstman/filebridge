#!/usr/bin/env python3
"""Download counts of the FileBridge releases on GitHub, as one snapshot (JSON) for the downloads dashboard.

    python3 tools/download_counts.py              # prints the snapshot
    python3 tools/download_counts.py out.json     # also writes it to a file

Counts only the installers (.dmg, .exe, .tar.gz), not checksums or signatures. Uses the public GitHub API
(no login needed; at most 60 requests per hour per address, this makes one).
"""
import datetime
import json
import sys
import urllib.request

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


if __name__ == '__main__':
    snap = snapshot()
    text = json.dumps(snap, indent=1)
    if len(sys.argv) > 1:
        with open(sys.argv[1], 'w') as f:
            f.write(text)
    print(text)
