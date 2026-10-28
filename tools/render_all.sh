#!/bin/sh
# Render every card into one PNG contact sheet using headless Chrome.
# Usage: tools/render_all.sh [output.png] [deck_dir]
set -e
cd "$(dirname "$0")/.."
out="${1:-all_cards.png}"; case "$out" in /*) ;; *) out="$PWD/$out";; esac
deck="$PWD/${2:-.}"
html="$(mktemp -t cards).html"
{
  echo '<!doctype html><html><body style="margin:0;padding:20px;background:#2e7d32;display:grid;grid-template-columns:repeat(13,167px);gap:12px">'
  for s in clubs diamonds hearts spades; do
    for r in ace 2 3 4 5 6 7 8 9 10 jack queen king; do
      echo "<img src=\"file://$deck/${r}_of_${s}.svg\" width=167 height=243>"
    done
  done
  echo "<img src=\"file://$deck/black_joker.svg\" width=167 height=243>"
  echo "<img src=\"file://$deck/red_joker.svg\" width=167 height=243>"
  echo '</body></html>'
} > "$html"
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --disable-gpu \
  --allow-file-access-from-files --hide-scrollbars --force-device-scale-factor=2 \
  --window-size=2371,1328 --screenshot="$out" "file://$html" 2>/dev/null
rm -f "$html"
echo "wrote $out"
