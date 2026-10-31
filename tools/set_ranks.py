#!/usr/bin/env python3
"""Replace the rank <text> indices on every card with outlined font paths.

Every rank is top-aligned at the same margin from the card edge and centred
over its corner suit; ranks that would hit nearby artwork are shifted left,
then condensed, to fit. The bottom-right index is the top-left one rotated
180 degrees about the card centre. Glyphs are converted to paths so the cards
render the same everywhere without the font installed.

Requires fontTools (pip install fonttools). Safe to re-run.

Usage:
  python3 tools/set_ranks.py                    # Abril Fatface, cards in repo root
  python3 tools/set_ranks.py --font arial --out arial
                                                # copy all cards to arial/ first
  python3 tools/set_ranks.py --font roboto --out roboto
"""
import argparse
import glob
import os
import re
import shutil

from fontTools.pens.basePen import BasePen
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CARD_W, CARD_H = 167.0869141, 242.6669922
MARGIN_TOP = 4.0
MIN_LEFT = 1.5
# Least distance from the rank's ink to the card's rounded edge, a rounded
# rectangle of radius CORNER (where the apps draw the card's outline), so a
# serif doesn't reach into the curve of the corner.
CLEARANCE = 3.0
CORNER = 7.11
# Ranks that need more white space from the card edge.
LEFT_LIMIT = {'Q': 2.75}
# Cap height in card units (the original Arial sizes). K and Q are smaller so
# they fit between the card edge and the face-card art; the queens' corner
# suits are nudged down to clear the Q tail.
CAP = {'K': 20.6, 'Q': 20.6}
CAP_DEFAULT = 22.9

# Centre x of the top-left corner suit (measured from the artwork).
SUIT_CENTER = {
    'pip': {'clubs': 17.49, 'diamonds': 16.97, 'hearts': 17.18, 'spades': 16.93},
    'face': {'clubs': 11.2, 'diamonds': 11.15, 'hearts': 11.3, 'spades': 11.2},
}
# Rightmost x the rank ink may reach: 1 unit short of the nearest artwork
# beside it (face art at x ~21.9, ~22.1 on the queens; the high pips on the 7-10).
RIGHT_LIMIT = {'J': 20.9, 'Q': 21.1, 'K': 20.9, '9': 26.8, '10': 26.8, '7': 31, '8': 31}
RIGHT_DEFAULT = 32

# condense: horizontal scale for every rank. track_10: tracking for "10" in
# 1/700ths of the cap height. left: per-font additions to LEFT_LIMIT.
FONTS = {
    'abril': dict(path=os.path.join(ROOT, 'tools', 'fonts', 'AbrilFatface-Regular.ttf'),
                  condense=0.94, track_10=0, left={'K': 2.75}),
    # Arial is not redistributable, so it is read from the macOS system fonts.
    # Its digits are tabular, so "10" is tightened before any condensing.
    'arial': dict(path='/System/Library/Fonts/Supplemental/Arial.ttf',
                  condense=1.0, track_10=-150),
    # Roboto (SIL Open Font License) is close to Arial and set the same way, for
    # where Arial can't be used, such as Android
    'roboto': dict(path=os.path.join(ROOT, 'tools', 'fonts', 'Roboto-Regular.ttf'),
                   condense=1.0, track_10=-150),
}

RANKS = {'ace': 'A', 'jack': 'J', 'queen': 'Q', 'king': 'K'}
COLORS = {'clubs': '#000000', 'spades': '#000000',
          'diamonds': '#df0000', 'hearts': '#df0000'}


def draw_run(glyphs, names, pen, left, sx, scale, cap_height, track):
    """Draw names into pen, origin at x=left, cap line at MARGIN_TOP."""
    x = 0
    for name in names:
        # Flip y (font units are y-up) and place the cap line at MARGIN_TOP.
        glyphs[name].draw(TransformPen(pen, (sx, 0, 0, -scale,
                                             left + x * sx,
                                             MARGIN_TOP + cap_height * scale)))
        x += glyphs[name].width + track


class PointsPen(BasePen):
    """Collects points along the outline, curves sampled every few percent."""
    def __init__(self, glyphs):
        super().__init__(glyphs)
        self.points = []

    def _moveTo(self, p):
        self.points.append(p)

    def _lineTo(self, p):
        self.points.append(p)

    def _curveToOne(self, p1, p2, p3):
        p0 = self._getCurrentPoint()
        for i in range(1, 21):
            t = i / 20
            self.points.append(tuple((1 - t) ** 3 * a + 3 * (1 - t) ** 2 * t * b
                                     + 3 * (1 - t) * t ** 2 * c + t ** 3 * d
                                     for a, b, c, d in zip(p0, p1, p2, p3)))

    def _qCurveToOne(self, p1, p2):
        p0 = self._getCurrentPoint()
        for i in range(1, 21):
            t = i / 20
            self.points.append(tuple((1 - t) ** 2 * a + 2 * (1 - t) * t * b + t ** 2 * c
                                     for a, b, c in zip(p0, p1, p2)))


def edge_distance(x, y):
    """How far a point in the top-left of the card is from its rounded edge."""
    if x < CORNER and y < CORNER:
        return CORNER - ((CORNER - x) ** 2 + (CORNER - y) ** 2) ** 0.5
    return min(x, y)


def rank_path(font, cfg, label, center, left, right):
    """SVG path data for label centred on center, ink kept within [left, right]
    and CLEARANCE from the rounded edge."""
    glyphs = font.getGlyphSet()
    cmap = font.getBestCmap()
    cap_height = font['OS/2'].sCapHeight
    scale = CAP.get(label, CAP_DEFAULT) / cap_height
    names = [cmap[ord(ch)] for ch in label]
    track = cfg['track_10'] * cap_height / 700 if label == '10' else 0
    sx = scale * cfg['condense']

    while True:
        bp = BoundsPen(glyphs)
        draw_run(glyphs, names, bp, 0, sx, scale, cap_height, track)
        x0, _, x1, _ = bp.bounds
        if x1 - x0 > right - left:
            sx *= (right - left) / (x1 - x0)
            continue
        width = x1 - x0
        ink_left = min(max(center - width / 2, left), right - width)
        # Move right, in hundredths, while any of the ink is too near the corner
        pp = PointsPen(glyphs)
        draw_run(glyphs, names, pp, -x0, sx, scale, cap_height, track)
        def clear(at):
            return min(edge_distance(x + at, y) for x, y in pp.points) >= CLEARANCE
        while not clear(ink_left) and ink_left + width <= right:
            ink_left += 0.01
        if ink_left + width <= right:
            break
        # No room to the right: condense and try again
        sx *= 0.99

    pen = SVGPathPen(glyphs, ntos=lambda v: ('%.3f' % v).rstrip('0').rstrip('.'))
    draw_run(glyphs, names, pen, ink_left - x0, sx, scale, cap_height, track)
    return pen.getCommands()


def rank_block(font, cfg, rank, suit, color):
    label = RANKS.get(rank, rank)
    kind = 'face' if rank in ('jack', 'queen', 'king') else 'pip'
    d = rank_path(font, cfg, label, SUIT_CENTER[kind][suit],
                  {**LEFT_LIMIT, **cfg.get('left', {})}.get(label, MIN_LEFT),
                  RIGHT_LIMIT.get(label, RIGHT_DEFAULT))
    return ('<g id="rank-index" style="fill:%s;stroke:none">'
            '<path id="rank-index-top" d="%s" />'
            '<path id="rank-index-bottom" d="%s" transform="rotate(180,%s,%s)" />'
            '</g>' % (color, d, d, CARD_W / 2, CARD_H / 2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--font', choices=sorted(FONTS), default='abril')
    ap.add_argument('--out', help='directory (relative to the repo) to write a '
                    'separate set into; all cards are copied there first')
    args = ap.parse_args()
    cfg = FONTS[args.font]
    font = TTFont(cfg['path'])

    deck = ROOT
    if args.out:
        deck = os.path.join(ROOT, args.out)
        os.makedirs(deck, exist_ok=True)
        for src in glob.glob(os.path.join(ROOT, '*.svg')):
            shutil.copy(src, deck)

    for path in sorted(glob.glob(os.path.join(deck, '*_of_*.svg'))):
        rank, suit = os.path.basename(path)[:-4].split('_of_')
        src = open(path, encoding='utf-8').read()
        block = rank_block(font, cfg, rank, suit, COLORS[suit])
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
            print('updated', os.path.relpath(path, ROOT))


if __name__ == '__main__':
    main()
