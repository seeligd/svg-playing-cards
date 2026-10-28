#!/usr/bin/env python3
"""Replace the rank <text> indices on every card with outlined Abril Fatface paths.

Every rank is drawn at the same cap height with the same top/left margin from
the card edge; the bottom-right index is the top-left one rotated 180 degrees
about the card centre. Glyphs are converted to paths so the cards render the
same everywhere without the font installed.

Requires fontTools (pip install fonttools). Safe to re-run.

Usage: python3 tools/set_ranks.py
"""
import glob
import os
import re

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT = os.path.join(ROOT, 'tools', 'fonts', 'AbrilFatface-Regular.ttf')

CARD_W, CARD_H = 167.0869141, 242.6669922
MARGIN_LEFT = 4.0
MARGIN_TOP = 4.0
# Font units -> card units. Sized so the Q tail clears the queens' corner
# suits (nudged down 2.5 units to make room) and K/Q clear the face-card art
# (x ~21.9).
SCALE = 0.0256
# Horizontal condense for every rank; "10" gets extra so it clears the
# top-left pip on the 10 (x ~27.8).
CONDENSE_ALL = 0.94
CONDENSE = {'10': 0.915}

RANKS = {'ace': 'A', 'jack': 'J', 'queen': 'Q', 'king': 'K'}
COLORS = {'clubs': '#000000', 'spades': '#000000',
          'diamonds': '#df0000', 'hearts': '#df0000'}

font = TTFont(FONT)
glyphs = font.getGlyphSet()
cmap = font.getBestCmap()
cap_height = font['OS/2'].sCapHeight


def rank_path(label):
    """SVG path data for label, ink left edge at MARGIN_LEFT, cap line at MARGIN_TOP."""
    names = [cmap[ord(ch)] for ch in label]
    first = glyphs[names[0]]
    bp = BoundsPen(glyphs)
    first.draw(bp)
    lsb = bp.bounds[0]
    sx = SCALE * CONDENSE_ALL * CONDENSE.get(label, 1.0)
    pen = SVGPathPen(glyphs, ntos=lambda v: ('%.3f' % v).rstrip('0').rstrip('.'))
    x = -lsb
    for name in names:
        # Flip y (font units are y-up) and place the cap line at MARGIN_TOP.
        t = TransformPen(pen, (sx, 0, 0, -SCALE,
                               MARGIN_LEFT + x * sx,
                               MARGIN_TOP + cap_height * SCALE))
        glyphs[name].draw(t)
        x += glyphs[name].width
    return pen.getCommands()


def rank_block(label, color):
    d = rank_path(label)
    return ('<g id="rank-index" style="fill:%s;stroke:none">'
            '<path id="rank-index-top" d="%s" />'
            '<path id="rank-index-bottom" d="%s" transform="rotate(180,%s,%s)" />'
            '</g>' % (color, d, d, CARD_W / 2, CARD_H / 2))


for path in sorted(glob.glob(os.path.join(ROOT, '*_of_*.svg'))):
    rank, suit = os.path.basename(path)[:-4].split('_of_')
    label = RANKS.get(rank, rank)
    src = open(path, encoding='utf-8').read()
    block = rank_block(label, COLORS[suit])
    if 'id="rank-index"' in src:
        out = re.sub(r'<g id="rank-index".*?</g>', lambda m: block, src, count=1, flags=re.S)
    else:
        texts = list(re.finditer(r'<text\b.*?</text>', src, re.S))
        assert texts, path
        # Put the new index where the first rank <text> was; drop the rest.
        out = src[:texts[0].start()] + block
        prev = texts[0].end()
        for m in texts[1:]:
            out += src[prev:m.start()]
            prev = m.end()
        out += src[prev:]
    if out != src:
        open(path, 'w', encoding='utf-8').write(out)
        print('updated', os.path.basename(path))
