#!/usr/bin/env bash
# Move the marketing site onto a new release.
#
# The version sits in fourteen places in site/index.html: the JSON-LD
# softwareVersion, the FAQ answer twice, body copy, the footer, six download
# filenames and the two source archive URLs. Six of those are links that carry
# the version in the filename, so the moment a release goes out they all 404
# until this runs.
#
# This used to live inside mirror-release.sh, which found the current version
# by grepping href="/dl/<version>/ out of the page. Those links went back to
# GitHub when the account was restored on 2026-09-25, so that anchor no longer
# exists and the step needed a home of its own.
#
#   tools/site-version.sh            move the site to whatever index.html says
#   tools/site-version.sh 0.2.29     move it to that version
#   tools/site-version.sh --deploy   rewrite, verify, then upload the page
#
# It refuses to leave the site pointing at a download that is not there, which
# is the whole point. A blind replace is how the site served 0.2.19 for six
# versions: every link was well formed and every one of them was wrong.

set -euo pipefail

REPO=magikh0e/PrintVault
HOST=u959320219@217.196.54.195
PORT=65002
KEY=~/.ssh/id_ed25519
ROOT=/home/u959320219/domains/printvault.magikh0e.pl/public_html
SITE=https://printvault.magikh0e.pl

cd "$(dirname "$0")/.."
REAL=site/index.html
# Everything below edits a copy. The real page is only replaced once every
# link on it has been proven to resolve, so a run against a release that is
# not out yet leaves the site exactly as it found it rather than leaving a
# rewritten page on disk for a later deploy to pick up.
PAGE=$(mktemp)
trap 'rm -f "$PAGE"' EXIT
cp "$REAL" "$PAGE"

say(){ printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
die(){ printf '\n\033[1;31m!! %s\033[0m\n' "$*" >&2; exit 1; }

DEPLOY=0
VER=""
for a in "$@"; do
  case "$a" in
    --deploy) DEPLOY=1 ;;
    -*) die "unknown option $a" ;;
    *)  VER=$a ;;
  esac
done

# index.html is the single source of truth for the version: build.mjs stamps it
# into package.json, tauri.conf.json and Cargo.toml, and the release tag comes
# from there. Asking it beats being told.
if [ -z "$VER" ]; then
  VER=$(grep -oE "APP_VERSION = '[0-9.]+'" index.html | head -1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+')
  [ -n "$VER" ] || die "could not read APP_VERSION out of index.html"
fi

# Anchored on a download filename rather than the JSON-LD, which carries two
# softwareVersion entries, one for PrintVault and one for Headfit. Taking the
# first match got Headfit's, and the replace that followed wrote PrintVault's
# version straight over it. A download filename is unambiguous, and it is also
# the exact thing that breaks when this is not run.
OLD=$(grep -oE 'PrintVault_[0-9.]+_x64_en-US\.msi' "$PAGE" | head -1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+')
[ -n "${OLD:-}" ] || die "could not find a versioned download filename in $PAGE"

# Headfit ships on its own schedule and has its own entry in the same JSON-LD.
# It was reading 0.3.0 against an actual 0.8.1, so it rots exactly the same way
# and is worth carrying here rather than leaving for someone to spot.
#
# It lives in its own repo now and site/headfit.html is a fetched copy, so it
# can legitimately be absent. Absent has to mean fetch it, not skip the check:
# skipping is how it got to 0.3.0 in the first place.
if [ ! -f site/headfit.html ]; then
  say "No site/headfit.html yet, fetching it"
  tools/headfit.sh >/dev/null || die "could not get headfit.html; run tools/headfit.sh to see why"
fi
HF=$(grep -oE "APP_VERSION = '[0-9.]+'" site/headfit.html | head -1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' || true)
[ -n "$HF" ] || die "could not read a version out of site/headfit.html"
HF_OLD=$(grep -oE 'headfit\.html","softwareVersion":"[0-9.]+' "$PAGE" | grep -oE '[0-9.]+$' || true)

say "Site is on $OLD, app is $VER"

if [ "$OLD" = "$VER" ]; then
  echo "   Already there. Checking the links anyway, since a release can be"
  echo "   retagged or an asset renamed without the version moving."
else
  n=$(grep -o "$OLD" "$PAGE" | wc -l)
  sed -i "s/$(printf '%s' "$OLD" | sed 's/\./\\./g')/$VER/g" "$PAGE"
  echo "   Rewrote $n occurrences"
  # A global replace is fine right up until the two products share a version
  # number, at which point it quietly rewrites the other one as well.
  now=$(grep -oE 'headfit\.html","softwareVersion":"[0-9.]+' "$PAGE" | grep -oE '[0-9.]+$' || true)
  [ "$now" = "$HF_OLD" ] || die "that replace moved Headfit from $HF_OLD to $now; $PAGE needs a look by hand"
fi

if [ -n "$HF" ] && [ "$HF" != "$HF_OLD" ]; then
  say "Headfit is $HF and the page said $HF_OLD"
  sed -i "s|\(headfit\.html\",\"softwareVersion\":\"\)[0-9.]*|\1$HF|" "$PAGE"
  echo "   Corrected"
fi

# The AppImage size is printed on the button and is the one number a version
# replace cannot fix. Decimal MB, not MiB: it is what someone compares against
# what their browser shows while it downloads, and browsers count in millions.
# Dividing by 1048576 would quietly relabel an 82 MB file as 78 MB.
say "Sizing the AppImage"
AP=$(gh release view "desktop-v$VER" --repo "$REPO" --json assets \
       --jq '.assets[] | select(.name | endswith(".AppImage")) | "\(.name) \(.size)"' 2>/dev/null || true)
if [ -n "${AP:-}" ]; then
  MB=$(( ( ${AP##* } + 500000 ) / 1000000 ))
  sed -i "s/\.AppImage, [0-9]\{1,4\} MB/.AppImage, $MB MB/" "$PAGE"
  echo "   ${AP%% *} is $MB MB"
else
  echo "   No AppImage on desktop-v$VER yet, leaving the size alone"
fi

# The part that matters. Every link the page offers has to be a file that
# exists, checked against the release rather than against the shape of the URL.
say "Checking every download the page offers"
bad=0
urls=$(grep -oE 'https://github\.com/[^"]+/(releases/latest/download|archive/refs/tags)/[^"]+' "$PAGE" | sort -u)
[ -n "$urls" ] || die "no download links found in $PAGE, which cannot be right"
while read -r u; do
  code=$(curl -s -o /dev/null -w '%{http_code}' -IL "$u" || echo 000)
  printf '   %s  %s\n' "$code" "${u##*/}"
  [ "$code" = "200" ] || bad=$((bad + 1))
done <<< "$urls"
[ "$bad" -eq 0 ] || die "$bad link(s) do not resolve. $REAL is untouched and nothing was deployed."

say "All $(wc -l <<< "$urls") links resolve"

cp "$PAGE" "$REAL"
echo "   $REAL updated"

if [ "$DEPLOY" = 1 ]; then
  say "Deploying $REAL"
  scp -i "$KEY" -P "$PORT" "$REAL" "$HOST:$ROOT/index.html" || die "upload failed"
  live=$(curl -s "$SITE/?cb=$$" | grep -c "PrintVault_${VER}_" || true)
  [ "${live:-0}" -gt 0 ] || die "the live page is not serving $VER links yet"
  echo "   Live page carries $live filenames for $VER"
  tools/indexnow.sh / || true
else
  echo
  echo "   Not deployed. Re-run with --deploy, or deploy the site the usual way."
fi
