#!/usr/bin/env python3
"""Draw the FileBridge app icon (two arrows, one each way, in DataLore green on the DataLore ink square) and write
build/icon.{png,ico,icns} and static/icon.{png,ico}. Run on a Mac: .venv/bin/python tools/make_icon.py

The arrows are the same mark as in the interface and on datalore.eu (24-unit grid):
  M4 7h13 M13 3l4 4-4 4   (top: to the right)    M20 17H7 M11 13l-4 4 4 4   (bottom: to the left)
"""
import os
import subprocess
import tempfile

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INK, GREEN = '#131410', '#7BC94C'   # DataLore ink and bright green
SS = 4                               # drawn four times as large, then scaled down for smooth edges
SIZE = 1024 * SS


def draw():
    img = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # the macOS icon grid: an 824-point rounded square in a 1024 canvas
    m, r = 100 * SS, 185 * SS
    d.rounded_rectangle([m, m, SIZE - m, SIZE - m], radius=r, fill=INK)
    # the arrows, 24-unit grid scaled up and centred (the mark spans x 4–20, y 3–21)
    s = 26 * SS
    ox, oy = SIZE / 2 - 12 * s, SIZE / 2 - 12 * s
    width = round(2.1 * s)
    gap = 0.9  # the two arrows a little further apart than in the small mark, so the heads don't touch

    def line(points):
        pts = [(ox + x * s, oy + y * s) for x, y in points]
        d.line(pts, fill=GREEN, width=width, joint='curve')
        for x, y in (pts[0], pts[-1]):  # round caps
            d.ellipse([x - width / 2, y - width / 2, x + width / 2, y + width / 2], fill=GREEN)
        for x, y in pts[1:-1]:          # round joins
            d.ellipse([x - width / 2, y - width / 2, x + width / 2, y + width / 2], fill=GREEN)

    up = lambda pts: [(x, y - gap) for x, y in pts]
    down = lambda pts: [(x, y + gap) for x, y in pts]
    line(up([(4, 7), (17, 7)]))
    line(up([(13, 3), (17, 7), (13, 11)]))
    line(down([(20, 17), (7, 17)]))
    line(down([(11, 13), (7, 17), (11, 21)]))
    return img.resize((1024, 1024), Image.LANCZOS)


def main():
    icon = draw()
    for path in ('build/icon.png', 'static/icon.png'):
        icon.save(os.path.join(ROOT, path))
    for path in ('build/icon.ico', 'static/icon.ico'):
        icon.save(os.path.join(ROOT, path), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    with tempfile.TemporaryDirectory() as td:  # macOS .icns via iconutil
        iconset = os.path.join(td, 'icon.iconset')
        os.makedirs(iconset)
        for px in (16, 32, 128, 256, 512):
            icon.resize((px, px), Image.LANCZOS).save(os.path.join(iconset, f'icon_{px}x{px}.png'))
            icon.resize((px * 2, px * 2), Image.LANCZOS).save(os.path.join(iconset, f'icon_{px}x{px}@2x.png'))
        subprocess.run(['iconutil', '-c', 'icns', iconset, '-o', os.path.join(ROOT, 'build', 'icon.icns')], check=True)
    print('wrote build/icon.{png,ico,icns} and static/icon.{png,ico}')


if __name__ == '__main__':
    main()
