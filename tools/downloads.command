#!/bin/zsh
# Double-click: fetch the FileBridge download counts from GitHub, add them to the history and show them in the browser.
tools="${0:A:h}"
folder="$HOME/Documents/FileBridge Downloads"
python3 "$tools/download_counts.py" --history > /dev/null || echo "GitHub is nu niet bereikbaar; de pagina toont de laatst bekende cijfers."
open "$folder/FileBridge Downloads.html"
