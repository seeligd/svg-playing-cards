# SVG Playing Cards

A full 54-card deck (52 cards + 2 jokers) as standalone SVGs, based on Byron
Knoll's public-domain [Vector Playing Cards 1.3](https://code.google.com/archive/p/vector-playing-cards/),
restyled for use in games and apps.

![All cards](all_cards.png)

## What's here

| Path | Contents |
|---|---|
| `*.svg` | The main deck, with ranks in **Abril Fatface** |
| `arial/*.svg` | The same deck with ranks in **Arial** (see [Licensing](#licensing)) |
| `all_cards.png`, `arial/all_cards.png` | Contact sheets of each deck |
| `all_cards_baseline.png` | The deck before the rank font change, for comparison |
| `tools/` | Scripts that generate the ranks and the contact sheets |

Files are named `<rank>_of_<suit>.svg`, where rank is `ace`, `2`–`10`, `jack`,
`queen` or `king` and suit is `clubs`, `diamonds`, `hearts` or `spades`, plus
`black_joker.svg` and `red_joker.svg`. Every card uses the same
`viewBox="0 0 167.0869141 242.6669922"`.

## Changes from the original

- Uses the original set's alternate (`*2.svg`) designs for the ace of spades
  and all jacks, queens and kings.
- No black rounded-rect border around the card, or around the face-card art.
- The aces' large suit symbols are solid black or red, with no gradient shine.
- Rank indices are vector outlines, not `<text>`, so they render the same
  everywhere without any font installed. They're top-aligned at the same
  margin on every card and centred over the corner suit.
  - A, 2–10 and J have a cap height of 22.9 units; K and Q have 20.6, the
    sizes the original deck used. The 10 is narrowed to fit beside its pips.
- The queens' small corner suits are moved down slightly to clear the Q's tail.

The jokers are unchanged apart from the border. Their "Joker" lettering is
still `<text>` that relies on locally installed fonts.

## Using the cards

Reference them straight from GitHub through jsDelivr:

```html
<img src="https://cdn.jsdelivr.net/gh/seeligd/svg-playing-cards@main/queen_of_hearts.svg" alt="Queen of hearts">
```

Or vendor them into your project with a git submodule:

```sh
git submodule add https://github.com/seeligd/svg-playing-cards.git assets/cards
```

## Regenerating

```sh
pip install fonttools
python3 tools/set_ranks.py                          # main deck (Abril Fatface)
python3 tools/set_ranks.py --font arial --out arial # Arial deck (macOS)
tools/render_all.sh                                 # all_cards.png (needs Google Chrome)
tools/render_all.sh arial/all_cards.png arial
```

Sizes, margins and per-rank limits are constants at the top of
`tools/set_ranks.py`. The Arial deck reads Arial from the macOS system fonts.

## Licensing

- **Card artwork:** Byron Knoll released Vector Playing Cards into the public
  domain ("attribution is appreciated but not required"). Thanks, Byron!
- **Modifications and `tools/` scripts:** MIT. See [LICENSE](LICENSE) and
  [NOTICE](NOTICE).
- **Abril Fatface** (by TypeTogether): SIL Open Font License 1.1. See
  [tools/fonts/OFL.txt](tools/fonts/OFL.txt). The main deck's rank outlines are
  derived from it.
- **Arial:** the rank outlines in `arial/` are derived from Arial, a
  commercial Monotype font. They aren't covered by the MIT license or the
  public-domain dedication. If that's a concern for your project, use the main
  (Abril) deck.
