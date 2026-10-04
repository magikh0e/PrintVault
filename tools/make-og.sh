#!/bin/sh
# Render og.svg to og.png, which is what the social card meta actually points at.
#
# og.png went missing from this folder once and nobody noticed, because the copy
# already on the server kept serving fine. The deploy is what broke: scp stats
# every source before sending, so one absent file aborts the whole upload.
#
# Chrome does the rendering because it is the one thing already on every machine
# this site gets deployed from. Do not reach for `convert` here: on Windows that
# name belongs to the filesystem conversion tool, not ImageMagick.
#
# Only run this when the svg has actually changed, or when its png has gone
# missing again. Chrome renders with whatever fonts this machine has, so a
# needless re-render moves the type around slightly and produces a file two and
# a half times the size, for a card that scrapers have already cached.
#
#   tools/make-og.sh              rewrites site/og.png from site/og.svg
#   tools/make-og.sh og-headfit   rewrites site/og-headfit.png likewise
#
# Each page wants its own card. Headfit pointed at the main one for a while and
# invited people to a helmet fit tool with a picture saying their STL folder was
# a landfill.
#
# og-headfit.svg stays here even though Headfit itself moved to its own repo on
# 2026-09-25, because this is what serves that page and what deploys the png.
# The copy that went over with the split was deleted for the same reason. If the
# card is ever redrawn, it is redrawn here.

set -e

# og.svg and og.png live in site/, which is gitignored, so this script is kept
# in the repo instead and reaches across to them. Same arrangement as the other
# scripts here, and for the same reason: a helper stored inside the folder it
# maintains does not survive a fresh clone.
SITEDIR=$(cd "$(dirname "$0")/../site" 2>/dev/null && pwd) ||
  { echo "cannot find the site folder next to $(dirname "$0")" >&2; exit 1; }
NAME=${1:-og}
[ -f "$SITEDIR/$NAME.svg" ] ||
  { echo "$SITEDIR has no $NAME.svg to render" >&2; exit 1; }
cd "$SITEDIR"

# The window has to match the svg or Chrome letterboxes or crops it. Read it
# off the file rather than hardcoding, because the cards are not all one size:
# Open Graph wants 1200x630 and GitHub wants 1280x640.
W=$(sed -n 's/.*<svg[^>]* width="\([0-9]*\)".*/\1/p' "$NAME.svg" | head -1)
H=$(sed -n 's/.*<svg[^>]* height="\([0-9]*\)".*/\1/p' "$NAME.svg" | head -1)
[ -n "$W" ] && [ -n "$H" ] || { echo "$NAME.svg has no width/height on its <svg> tag" >&2; exit 1; }
echo "rendering $NAME.svg at ${W}x${H}"

CHROME="/c/Program Files/Google/Chrome/Application/chrome.exe"
[ -x "$CHROME" ] || CHROME="/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
[ -x "$CHROME" ] || { echo "No Chrome or Edge found, cannot render the card" >&2; exit 1; }

# The size is not a guess: the cards are authored at 1200x630 and the pages
# declare those numbers in og:image:width and og:image:height.
"$CHROME" --headless --disable-gpu --hide-scrollbars \
  --window-size=$W,$H \
  --screenshot="$(pwd -W 2>/dev/null || pwd)/$NAME.png" \
  "file:///$(pwd -W 2>/dev/null || pwd)/$NAME.svg" 2>/dev/null

echo "$NAME.png rewritten from $NAME.svg"
