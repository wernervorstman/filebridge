#!/bin/bash
# Double-click to start FileBridge in its own window (development version).
# start.command does the same but opens FileBridge in your browser.
cd "$(dirname "$0")" || exit 1
if [ ! -x .venv/bin/python ] || ! cmp -s requirements.txt .venv/.requirements; then
  echo "Setting up FileBridge (only needed once)…"
  python3 -m venv .venv \
    && .venv/bin/pip install --quiet --disable-pip-version-check -r requirements.txt \
    && cp requirements.txt .venv/.requirements \
    || { echo "Setup failed. Press a key to close."; read -rn1; exit 1; }
fi
exec .venv/bin/python filebridge_app.py "$@"
