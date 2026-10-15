#!/usr/bin/env python3
"""Draw the FileBridge app icon (two thin green arrows, sunk into a white rounded square with a green frame) and write
build/icon.{png,ico,icns} and static/icon.{png,ico}. Run on a Mac: .venv/bin/python tools/make_icon.py

The arrows are the same mark as in the interface and on datalore.eu (24-unit grid):
  M4 7h13 M13 3l4 4-4 4   (top: to the right)    M20 17H7 M11 13l-4 4 4 4   (bottom: to the left)
"""
import os
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SS = 4                               # drawn four times as large, then scaled down for smooth edges
SIZE = 1024 * SS


def draw():
    """White rounded square with a thin green frame and the two arrows, sunk into the icon (the AccountBridge style)."""
    from PIL import ImageChops, ImageFilter
    S = 1024
    im = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((40, 40, S - 40, S - 40), radius=215, fill='#FFFFFF')
    d.rounded_rectangle((40, 40, S - 40, S - 40), radius=215, outline='#2E9E5B', width=7)
    d.rounded_rectangle((70, 70, S - 70, S - 70), radius=190, outline='#CFE8D8', width=3)
    # the arrows as a mask: thin, slender lines, about 60% of the icon high, drawn large for smooth edges
    big = S * SS
    mask = Image.new('L', (big, big), 0)
    md = ImageDraw.Draw(mask)
    unit = 0.6 * big / 18          # the mark is 18 units high (y 3-21) on its 24-unit grid
    ox, oy = big / 2 - 12 * unit, big / 2 - 12 * unit
    width = round(0.95 * unit)     # a thin line, like Helvetica Neue Light

    def line(points):
        pts = [(ox + x * unit, oy + y * unit) for x, y in points]
        md.line(pts, fill=255, width=width, joint='curve')
        for x, y in pts:           # round caps and joins
            md.ellipse([x - width / 2, y - width / 2, x + width / 2, y + width / 2], fill=255)

    line([(4, 7), (17, 7)])
    line([(13, 3), (17, 7), (13, 11)])
    line([(20, 17), (7, 17)])
    line([(11, 13), (7, 17), (11, 21)])
    mask = mask.resize((S, S), Image.LANCZOS)
    # sunk in: flat green with a soft gradient, a dark green shadow inside along the top edge, a light shine under the bottom edge
    gradient = Image.new('RGBA', (S, S))
    gd = ImageDraw.Draw(gradient)
    for yy in range(S):
        t = yy / S
        gd.line((0, yy, S, yy), fill=(int(70 - 25 * t), int(185 - 45 * t), int(105 - 30 * t), 255))
    im.paste(gradient, (0, 0), mask)
    shine = ImageChops.subtract(ImageChops.offset(mask, 0, 6), mask).filter(ImageFilter.GaussianBlur(2))
    im.paste(Image.new('RGBA', (S, S), (150, 200, 170, 255)), (0, 0), shine.point(lambda v: int(v * 0.8)))
    inner = ImageChops.subtract(mask, ImageChops.offset(mask, 0, 10)).filter(ImageFilter.GaussianBlur(5))
    inner = ImageChops.multiply(inner, mask.filter(ImageFilter.GaussianBlur(1)))
    im.paste(Image.new('RGBA', (S, S), (8, 60, 30, 255)), (0, 0), inner.point(lambda v: min(255, int(v * 1.3))))
    return im


def main():
    icon = draw()
    if '--preview' in sys.argv:  # only show it: write a picture next to the build folder, change nothing
        out = os.path.join(ROOT, 'build', 'icon-preview.png')
        icon.save(out)
        print('preview:', out)
        return
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
