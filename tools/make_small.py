#!/usr/bin/env python3
"""Build the small-size deck: cards meant to be read at a glance on a phone,
where the full deck's corner indices are too small to make out.

Each card has a big rank in the top-left corner and its suit beside it, with
one big pip below (aces and number cards) or the top half of the face-card
art (jacks, queens and kings). The pips come from the 2s and the art from the
face cards in the main deck, so both decks share their artwork; the ranks are
outlined from a font, as in set_ranks.py.

The face cards keep only the parts of the art that show: each shape of the
art's paths that lies wholly outside the crop is left out, and coordinates are
rounded, which takes a face card from about 600 KB to a fraction of that.

Requires fontTools and svgpathtools (pip install fonttools svgpathtools).
Safe to re-run.

Usage:
  python3 tools/make_small.py                       # Abril Fatface, into small/
  python3 tools/make_small.py --font arial --out arial/small
  python3 tools/make_small.py --font roboto --out roboto/small
"""
import argparse
import math
import os
import re
import xml.etree.ElementTree as ET

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from svgpathtools import Arc, CubicBezier, Line, QuadraticBezier, parse_path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CARD_W, CARD_H = 167.0869141, 242.6669922
CORNER_RADIUS = 10
RED, BLACK = '#df0000', '#000000'
SUITS = ['clubs', 'diamonds', 'hearts', 'spades']
RANKS = ['ace', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'jack', 'queen', 'king']
LABEL = {'ace': 'A', 'jack': 'J', 'queen': 'Q', 'king': 'K'}

FONTS = {
    'abril': os.path.join(ROOT, 'tools', 'fonts', 'AbrilFatface-Regular.ttf'),
    'arial': '/System/Library/Fonts/Supplemental/Arial.ttf',
    'roboto': os.path.join(ROOT, 'tools', 'fonts', 'Roboto-Regular.ttf'),
}

# The rank: top-left, its cap height a third of the card, squeezed to fit beside the suit
RANK_LEFT, RANK_TOP, RANK_CAP, RANK_MAX_W = 9, 10, 80, 80
# The space between the 1 and the 0 of a 10, closer than the font sets them so the 10 needs less squeezing
RANK_GAP = 5
# The thickest outline added to make up a squeezed rank's weight
MAX_OUTLINE = 1.5
# The suit beside it, and the big pip below
SUIT_BOX = (92, 9, 70, 84)            # x, y, width, height
PIP_BOX = (31, 110, 105, 124)
# The top half of the face art, cut off at the bottom of the card
ART_BOX = (9, 104, 149, 134)

# The upper pip on each 2 in the main deck (measured from the artwork), in card units
PIP_SOURCE = {
    'clubs': (60.3, 33.8, 47.7, 47.8),
    'diamonds': (62.2, 28.5, 41.4, 54.3),
    'hearts': (61.5, 33.4, 44.5, 46.8),
    'spades': (62.2, 32.0, 42.4, 50.8),
}
# The part of the main deck's face art to show: its left, top and width, starting right of the big pip in the art's
# top-left corner, since the suit is already beside the rank
ART_SOURCE = (64.0, 22.0, 82.5)
# The art stays this far below the rank's ink, such as a Q's tail
ART_GAP = 4
# How far outside the crop a shape of the art may reach and still be kept, in card units, for its outline's width
TRIM_MARGIN = 2
# Decimal places kept in the trimmed art's coordinates, which are scaled down to a sixth or so on the card, so a
# tenth of a unit is under a fiftieth of a pixel even on an iPad
TRIM_DECIMALS = 1

NAMESPACES = {
    '': 'http://www.w3.org/2000/svg',
    'xlink': 'http://www.w3.org/1999/xlink',
    'inkscape': 'http://www.inkscape.org/namespaces/inkscape',
    'sodipodi': 'http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd',
    'rdf': 'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
    'cc': 'http://creativecommons.org/ns#',
    'dc': 'http://purl.org/dc/elements/1.1/',
}
for name, uri in NAMESPACES.items():
    ET.register_namespace(name, uri)


def multiply(a, b):
    """The affine transform a then b, each as (a, b, c, d, e, f) like SVG's matrix()."""
    return (a[0] * b[0] + a[1] * b[2], a[0] * b[1] + a[1] * b[3],
            a[2] * b[0] + a[3] * b[2], a[2] * b[1] + a[3] * b[3],
            a[4] * b[0] + a[5] * b[2] + b[4], a[4] * b[1] + a[5] * b[3] + b[5])


def parse_transform(text):
    """An SVG transform attribute as one (a, b, c, d, e, f) matrix."""
    result = (1, 0, 0, 1, 0, 0)
    for kind, args in re.findall(r'(\w+)\s*\(([^)]*)\)', text or ''):
        n = [float(v) for v in re.split(r'[\s,]+', args.strip()) if v]
        if kind == 'matrix':
            m = tuple(n)
        elif kind == 'translate':
            m = (1, 0, 0, 1, n[0], n[1] if len(n) > 1 else 0)
        elif kind == 'scale':
            m = (n[0], 0, 0, n[1] if len(n) > 1 else n[0], 0, 0)
        elif kind == 'rotate':
            r = math.radians(n[0])
            cx, cy = (n[1], n[2]) if len(n) > 2 else (0, 0)
            m = multiply(multiply((1, 0, 0, 1, -cx, -cy), (math.cos(r), math.sin(r), -math.sin(r), math.cos(r), 0, 0)),
                         (1, 0, 0, 1, cx, cy))
        else:
            raise ValueError(f'unsupported transform {kind}')
        # Each transform in the list applies to what follows it
        result = multiply(m, result)
    return result


def compact(shape):
    """One continuous shape as short path data: relative moves between points rounded to TRIM_DECIMALS, so the
    rounding never adds up along the way, with no separators that a minus sign or decimal point makes unneeded."""
    def r(z):
        return complex(round(z.real, TRIM_DECIMALS), round(z.imag, TRIM_DECIMALS))

    def num(v):
        text = f'{v:.{TRIM_DECIMALS}f}'.rstrip('0').rstrip('.')
        text = '0' if text in ('-0', '') else text
        return text.replace('0.', '.', 1) if text.startswith(('0.', '-0.')) else text

    def nums(values):
        out, last = '', None
        for v in values:
            text = num(v)
            # A space only where the number would otherwise run into the one before: a minus sign starts a new number,
            # and so does a second decimal point
            if last is not None and not text.startswith('-') and not (text.startswith('.') and '.' in last):
                out += ' '
            out += text
            last = text
        return out

    start = r(shape[0].start)
    out = [f'M{nums([start.real, start.imag])}']
    here = start
    for seg in shape:
        end = r(seg.end)
        d = end - here
        if isinstance(seg, Line):
            out.append('l' + nums([d.real, d.imag]))
        elif isinstance(seg, CubicBezier):
            c1, c2 = r(seg.control1) - here, r(seg.control2) - here
            out.append('c' + nums([c1.real, c1.imag, c2.real, c2.imag, d.real, d.imag]))
        elif isinstance(seg, QuadraticBezier):
            c = r(seg.control) - here
            out.append('q' + nums([c.real, c.imag, d.real, d.imag]))
        elif isinstance(seg, Arc):
            out.append('a' + nums([seg.radius.real, seg.radius.imag, seg.rotation]) +
                       f' {int(seg.large_arc)} {int(seg.sweep)} ' + nums([d.real, d.imag]))
        else:
            raise ValueError(f'unsupported segment {type(seg).__name__}')
        here = end
    if shape.isclosed():
        out.append('z')
    return ''.join(out)


def trim(text, crop):
    """An SVG document without the shapes in its paths that lie wholly outside crop, an (x0, y0, x1, y1)
    rectangle in the document's own units, and with its paths' coordinates rounded."""
    root = ET.fromstring(text)
    x0, y0, x1, y1 = crop[0] - TRIM_MARGIN, crop[1] - TRIM_MARGIN, crop[2] + TRIM_MARGIN, crop[3] + TRIM_MARGIN

    def visit(element, ctm):
        ctm = multiply(parse_transform(element.get('transform')), ctm)
        for child in list(element):
            if child.tag == f'{{{NAMESPACES[""]}}}path' and child.get('d'):
                kept = []
                for shape in parse_path(child.get('d')).continuous_subpaths():
                    if not len(shape):
                        continue
                    left, right, top, bottom = shape.bbox()
                    corners = [(ctm[0] * x + ctm[2] * y + ctm[4], ctm[1] * x + ctm[3] * y + ctm[5])
                               for x in (left, right) for y in (top, bottom)]
                    xs, ys = [c[0] for c in corners], [c[1] for c in corners]
                    if max(xs) >= x0 and min(xs) <= x1 and max(ys) >= y0 and min(ys) <= y1:
                        kept.append(shape)
                if kept:
                    child.set('d', ''.join(compact(shape) for shape in kept))
                else:
                    element.remove(child)
            else:
                visit(child, ctm)

    visit(root, (1, 0, 0, 1, 0, 0))
    return ET.tostring(root, encoding='unicode')


def inline(path, prefix, crop=None):
    """The contents of an SVG file, without its root element, metadata or Inkscape's view
    settings, and with every id prefixed so several files can share one document.  With a
    crop, only what shows inside it."""
    text = open(path, encoding='utf-8').read()
    if crop:
        text = trim(text, crop)
    body = re.search(r'<svg\b[^>]*>(.*)</svg>', text, re.S).group(1)
    body = re.sub(r'<metadata\b.*?</metadata>', '', body, flags=re.S)
    body = re.sub(r'<sodipodi:namedview\b.*?(/>|</sodipodi:namedview>)', '', body, flags=re.S)
    body = re.sub(r'<!--.*?-->', '', body, flags=re.S)
    # Inkscape's own attributes do nothing outside Inkscape
    body = re.sub(r'\s(inkscape|sodipodi):[\w-]+="[^"]*"', '', body)
    body = re.sub(r'\bid="([^"]+)"', lambda m: f'id="{prefix}-{m.group(1)}"', body)
    body = re.sub(r'url\(#([^)]+)\)', lambda m: f'url(#{prefix}-{m.group(1)})', body)
    body = re.sub(r'(xlink:href|href)="#([^"]+)"', lambda m: f'{m.group(1)}="#{prefix}-{m.group(2)}"', body)
    return body


class Font:
    def __init__(self, path):
        self.font = TTFont(path)
        self.glyphs = self.font.getGlyphSet()
        self.cmap = self.font.getBestCmap()
        os2 = self.font['OS/2']
        self.cap = getattr(os2, 'sCapHeight', 0) or self.bounds('H')[3]

    def bounds(self, text, offsets=None):
        pen = BoundsPen(self.glyphs)
        for ch, x in zip(text, offsets or self.offsets(text)):
            self.glyphs[self.cmap[ord(ch)]].draw(TransformPen(pen, (1, 0, 0, 1, x, 0)))
        return pen.bounds

    def offsets(self, text, gap=None):
        """Where each character goes, in font units: spaced as the font sets them, or with gap
        font units between one character's ink and the next's."""
        offsets, x = [], 0
        for i, ch in enumerate(text):
            glyph = self.glyphs[self.cmap[ord(ch)]]
            if gap is not None and i > 0:
                previous = self.bounds(text[i - 1], [0])
                x = offsets[-1] + previous[2] + gap - self.bounds(ch, [0])[0]
            offsets.append(x)
            x += glyph.width
        return offsets

    def path(self, text, left, top, cap, max_width, gap):
        """An SVG path drawing text with its ink's top-left at (left, top), its capitals cap
        units tall, gap units between characters, and narrowed if need be to max_width.
        Also returns the bottom of its ink and how much it was narrowed."""
        scale = cap / self.cap
        offsets = self.offsets(text, gap / scale)
        xmin, ymin, xmax, ymax = self.bounds(text, offsets)
        squeeze = min(1.0, max_width / ((xmax - xmin) * scale))
        sx, sy = scale * squeeze, scale
        # Font units point up from the baseline; the card's point down from the top
        dx = left - xmin * sx
        dy = top + ymax * sy
        pen = SVGPathPen(self.glyphs)
        for ch, x in zip(text, offsets):
            self.glyphs[self.cmap[ord(ch)]].draw(TransformPen(pen, (sx, 0, 0, -sy, dx + x * sx, dy)))
        return pen.getCommands(), dy - ymin * sy, squeeze

    def stem(self, cap):
        """How thick the font's upright strokes are, with capitals cap units tall."""
        xmin, _, xmax, _ = self.bounds('l')
        return (xmax - xmin) * cap / self.cap


def fit(source, box):
    """Where an item of the source's shape goes, as big as fits, centred in box."""
    _, _, sw, sh = source
    x, y, w, h = box
    scale = min(w / sw, h / sh)
    return x + (w - sw * scale) / 2, y + (h - sh * scale) / 2, sw * scale, sh * scale


def placed(path, prefix, source, box, crop=None):
    """The part of an SVG file inside source, an (x, y, width, height) rectangle in its own units, scaled into box
    on the card and clipped to it, as plain groups rather than <symbol> and <use>, which some renderers (Apple's
    CoreSVG, for one) don't scale or clip."""
    sx, sy, sw, sh = source
    x, y, w, h = box
    scale = min(w / sw, h / sh)
    clip = (f'<clipPath id="{prefix}-clip"><rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}"/></clipPath>')
    return clip, (f'<g clip-path="url(#{prefix}-clip)"><g transform="matrix({scale:.5f},0,0,{scale:.5f},'
                  f'{x - sx * scale:.3f},{y - sy * scale:.3f})">{inline(path, prefix, crop)}</g></g>')


def card(rank, suit, font, deck):
    color = RED if suit in ('diamonds', 'hearts') else BLACK
    face = rank in ('jack', 'queen', 'king')
    pip = PIP_SOURCE[suit]
    pip_file = os.path.join(deck, f'2_of_{suit}.svg')
    label, label_bottom, squeeze = font.path(LABEL.get(rank, rank), RANK_LEFT, RANK_TOP, RANK_CAP, RANK_MAX_W, RANK_GAP)
    # A squeezed rank's upright strokes come out thinner, so an outline of the same colour makes up the difference
    # (up to a point: a heavy font's thin strokes would thicken too much)
    lost = min(font.stem(RANK_CAP) * (1 - squeeze), MAX_OUTLINE)
    outline = f' stroke="{color}" stroke-width="{lost:.2f}" stroke-linejoin="round"' if lost > 0.01 else ''
    defs = []
    parts = [f'<rect width="{CARD_W}" height="{CARD_H}" rx="{CORNER_RADIUS}" fill="#fff"/>',
             f'<path fill="{color}"{outline} d="{label}"/>']
    clip, suit_mark = placed(pip_file, 'suit', pip, fit(pip, SUIT_BOX))
    defs.append(clip)
    parts.append(suit_mark)
    if face:
        ax, ay, aw = ART_SOURCE
        bx, by, bw, bh = ART_BOX
        top = max(by, label_bottom + ART_GAP)
        by, bh = top, bh - (top - by)
        ah = aw * bh / bw
        # The art box stays inside the card's rounded corners, so clipping to it is enough
        clip, art = placed(os.path.join(deck, f'{rank}_of_{suit}.svg'), 'art', (ax, ay, aw, ah), (bx, by, bw, bh),
                           crop=(ax, ay, ax + aw, ay + ah))
    else:
        clip, art = placed(pip_file, 'pip', pip, fit(pip, PIP_BOX))
    defs.append(clip)
    parts.append(art)
    return ('<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n'
            '<!-- Small-size card from https://github.com/seeligd/svg-playing-cards, '
            'based on http://code.google.com/p/vector-playing-cards/ -->\n'
            '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'width="{CARD_W}pt" height="{CARD_H}pt" viewBox="0 0 {CARD_W} {CARD_H}">\n'
            f'<defs>{"".join(defs)}</defs>\n' + '\n'.join(parts) + '\n</svg>\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--font', choices=sorted(FONTS), default='abril')
    parser.add_argument('--out', default='small', help='output directory, relative to the repo')
    parser.add_argument('--deck', default='.', help='the main deck to take the artwork from')
    args = parser.parse_args()
    font = Font(FONTS[args.font])
    deck = os.path.join(ROOT, args.deck)
    out = os.path.join(ROOT, args.out)
    os.makedirs(out, exist_ok=True)
    for suit in SUITS:
        for rank in RANKS:
            with open(os.path.join(out, f'{rank}_of_{suit}.svg'), 'w', encoding='utf-8') as f:
                f.write(card(rank, suit, font, deck))
    print(f'wrote 52 cards to {args.out}/')


if __name__ == '__main__':
    main()
