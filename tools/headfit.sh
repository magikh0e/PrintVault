#!/usr/bin/env bash
# Put Headfit on the site.
#
# Headfit was site/headfit.html in this repo until 2026-09-25, when it moved to
# github.com/magikh0e/headfit. It is a different tool with its own version
# number, it had reached 0.8.1 while the app was on 0.2.30, and none of that was
# visible to anybody, because a file inside someone else's repo has no releases,
# no issues and no page to land on.
#
# It is still served from this site, so a deploy still has to get the file from
# somewhere. That is what this is.
#
#   tools/headfit.sh             fetch it to site/headfit.html
#   tools/headfit.sh --version   print the version it would install, write nothing
#   tools/headfit.sh --deploy    fetch, upload, then read the version back off the site
#
# site/headfit.html is ignored by git here on purpose. It is a copy, and a copy
# you can edit is a copy that gets edited, which is how a fix ends up live and
# nowhere else. Edit it in the headfit checkout and let this bring it over.

set -euo pipefail

SRC_REPO=magikh0e/headfit
RAW=https://raw.githubusercontent.com/$SRC_REPO/main/headfit.html
HOST=u959320219@217.196.54.195
PORT=65002
KEY=~/.ssh/id_ed25519
ROOT=/home/u959320219/domains/printvault.magikh0e.pl/public_html
SITE=https://printvault.magikh0e.pl

cd "$(dirname "$0")/.."
DEST=site/headfit.html

say(){ printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
die(){ printf '\n\033[1;31m!! %s\033[0m\n' "$*" >&2; exit 1; }

DEPLOY=0
QUIET=0
for a in "$@"; do
  case "$a" in
    --deploy)  DEPLOY=1 ;;
    --version) QUIET=1 ;;
    *) die "unknown option $a" ;;
  esac
done

# A checkout next door wins over the raw URL. That is where you would be editing
# it, and reaching past your own working copy to fetch the pushed version is a
# good way to spend ten minutes wondering why your change did not take.
CHECKOUT=${HEADFIT_REPO:-../headfit}
TMP=$(mktemp)
trap 'rm -f "$TMP"' EXIT

if [ -f "$CHECKOUT/headfit.html" ]; then
  FROM="$CHECKOUT/headfit.html"
  cp "$FROM" "$TMP"
  # Worth saying out loud on a deploy. Anything uncommitted here goes live as a
  # file that exists on one laptop, and the repo is then not what the site runs.
  if git -C "$CHECKOUT" rev-parse --git-dir >/dev/null 2>&1; then
    DIRTY=$(git -C "$CHECKOUT" status --porcelain -- headfit.html)
    AHEAD=$(git -C "$CHECKOUT" log --oneline '@{u}..' -- headfit.html 2>/dev/null || true)
  fi
else
  FROM="$RAW"
  curl -fsSL "$RAW" -o "$TMP" || die "could not fetch $RAW, and there is no checkout at $CHECKOUT"
fi

# What lands here goes straight onto the site, so check it is the thing and not
# a truncated download or an error page wearing a 200.
BYTES=$(wc -c < "$TMP")
[ "$BYTES" -gt 300000 ] || die "$FROM came back as $BYTES bytes, which is too small to be Headfit"
grep -q '<title>Headfit' "$TMP" || die "$FROM does not look like Headfit: no title"
HF=$(grep -oE "APP_VERSION = '[0-9.]+'" "$TMP" | head -1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' || true)
[ -n "$HF" ] || die "could not read an APP_VERSION out of $FROM"

if [ "$QUIET" = 1 ]; then
  echo "$HF"
  exit 0
fi

say "Headfit $HF from $FROM"
printf '   %s KB\n' "$(( BYTES / 1024 ))"
[ -z "${DIRTY:-}" ] || printf '   \033[1;33muncommitted changes in that checkout\033[0m\n'
[ -z "${AHEAD:-}" ] || printf '   \033[1;33mthat checkout has commits it has not pushed\033[0m\n'

cp "$TMP" "$DEST"
echo "   $DEST updated"

if [ "$DEPLOY" = 1 ]; then
  say "Deploying $DEST"
  scp -i "$KEY" -P "$PORT" "$DEST" "$HOST:$ROOT/headfit.html" || die "upload failed"
  # Not a byte comparison: Cloudflare's Rocket Loader rewrites the script tags
  # on the way out, so the served file never matches the one that was sent. The
  # version string is inside the script body and survives that.
  live=$(curl -s "$SITE/headfit.html?cb=$$" | grep -oE "APP_VERSION = '[0-9.]+'" | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 || true)
  [ "$live" = "$HF" ] || die "the site is serving ${live:-nothing} and not $HF"
  echo "   Live page is $HF"

  # Headfit is in the sitemap, so a new version here is a page Google should
  # come back for. Same stamper as the release script: it moves a date only
  # when the file behind it moved, and exits 10 when there is one to upload.
  say "Checking the sitemap dates"
  SM=0
  python tools/sitemap-stamp.py || SM=$?
  [ "$SM" = 0 ] || [ "$SM" = 10 ] || die "tools/sitemap-stamp.py failed"
  if [ "$SM" = 10 ]; then
    scp -i "$KEY" -P "$PORT" site/sitemap.xml "$HOST:$ROOT/sitemap.xml" || die "sitemap upload failed"
    echo "   sitemap.xml uploaded"
  fi
fi
