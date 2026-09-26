#!/usr/bin/env python3
"""Move each sitemap lastmod on the day its page actually changes.

The sitemap said every page was last modified 2026-09-17 while the home page
was being rewritten and redeployed on every release. lastmod is the one recrawl
signal we control and it was telling Google nothing had happened. Stamping all
three with today's date on every deploy would be the same lie pointed the other
way, and a sitemap whose lastmod is always "now" gets discounted, so this only
moves a date when the bytes behind it move.

"Changed" is decided against site/.sitemap-hashes, a cache of what each page
looked like the last time this ran. It is not tracked, because it describes
this working copy rather than the project, and the first run on a fresh clone
seeds it and stamps nothing: with no idea what the previous content was, any
date it wrote would be a guess.

    python tools/sitemap-stamp.py           stamp what changed
    python tools/sitemap-stamp.py --check   say what it would do, write nothing

Exit codes: 0 nothing moved, 10 the sitemap was rewritten and now needs
uploading, 1 something is wrong. Callers deploy on 10.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
SITEMAP = SITE / "sitemap.xml"
CACHE = SITE / ".sitemap-hashes"
HOST = "https://printvault.magikh0e.pl/"

CHECK = "--check" in sys.argv[1:]
for a in sys.argv[1:]:
    if a != "--check":
        sys.exit("unknown option %s" % a)


def local_for(loc: str) -> Path | None:
    """The file on disk behind a <loc>, or None if it is not ours to hash."""
    if not loc.startswith(HOST):
        return None
    rel = loc[len(HOST):] or "index.html"
    if rel.endswith("/"):
        rel += "index.html"
    return SITE / rel


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


if not SITEMAP.is_file():
    sys.exit("no %s" % SITEMAP)

old_cache = {}
if CACHE.is_file():
    for line in CACHE.read_text(encoding="utf-8").splitlines():
        if " " in line:
            h, _, name = line.partition(" ")
            old_cache[name] = h

xml = SITEMAP.read_text(encoding="utf-8")
today = dt.date.today().isoformat()
new_cache = {}
moved = []
seeded = []

# Rewriting the text in place rather than parsing and re-serialising. An
# ElementTree round trip renames the default namespace and reindents the whole
# file, which turns a one line change into a diff nobody will read.
blocks = list(re.finditer(r"<url>.*?</url>", xml, re.S))
if not blocks:
    sys.exit("%s has no <url> blocks" % SITEMAP)

out = []
last = 0
for b in blocks:
    block = b.group(0)
    m = re.search(r"<loc>\s*(.*?)\s*</loc>", block, re.S)
    if not m:
        continue
    loc = m.group(1)
    path = local_for(loc)
    if path is None:
        continue
    name = str(path.relative_to(SITE)).replace("\\", "/")
    if not path.is_file():
        print("   %s is in the sitemap and not on disk, leaving its date alone" % name)
        if name in old_cache:
            new_cache[name] = old_cache[name]
        continue

    digest = sha(path)
    new_cache[name] = digest
    was = old_cache.get(name)
    if was is None:
        seeded.append(name)
        continue
    if was == digest:
        continue

    cur = re.search(r"<lastmod>\s*(.*?)\s*</lastmod>", block, re.S)
    if cur and cur.group(1) == today:
        continue
    if cur:
        block = block[:cur.start(1)] + today + block[cur.end(1):]
    else:
        # No lastmod on this url yet. Put one after the loc, indented to match.
        indent = re.search(r"\n(\s*)<loc>", block)
        pad = indent.group(1) if indent else "    "
        block = block[:m.end()] + "\n%s<lastmod>%s</lastmod>" % (pad, today) + block[m.end():]
    moved.append((name, cur.group(1) if cur else "none", today))
    out.append(xml[last:b.start()])
    out.append(block)
    last = b.end()

out.append(xml[last:])
new_xml = "".join(out)

for name, before, after in moved:
    print("   %s changed, lastmod %s -> %s" % (name, before, after))
if seeded:
    print("   first run for %s, recorded but not stamped" % ", ".join(seeded))
if not moved:
    print("   no page changed, sitemap left alone")

if CHECK:
    sys.exit(10 if moved else 0)

CACHE.write_text("".join("%s %s\n" % (h, n) for n, h in sorted(new_cache.items())),
                 encoding="utf-8")
if not moved:
    sys.exit(0)
SITEMAP.write_text(new_xml, encoding="utf-8")
print("   %s rewritten" % SITEMAP.relative_to(ROOT).as_posix())
sys.exit(10)
