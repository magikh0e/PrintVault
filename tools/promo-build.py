"""Cut the recorded clips into one vertical reel.

Takes promo/printvault.webm and promo/headfit.webm from tools/promo-record.py
and produces promo/printvault-headfit-reel.mp4: 1080x1920, about 30 seconds, no
audio, because the soundtrack gets added in whatever app it is posted from.

The cards are drawn here rather than kept as files. promo/ is gitignored, so an
asset living only in there is an asset that disappears on a fresh clone; the
script is the source and it renders them with headless Chrome, the same way
tools/make-og.sh renders the social cards.

The app clip sits in the middle of a tall dark frame rather than filling it.
PrintVault is a desktop layout and cropping it to a phone shape would show a
column of one thing, which is not what it is. The caption underneath changes
with what is on screen.

    py tools/promo-build.py

Needs ffmpeg and Chrome on PATH.
"""
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "promo"
W, H = 1080, 1920
FPS = 30
FONT = "C\\:/Windows/Fonts/segoeui.ttf"
FONTB = "C\\:/Windows/Fonts/segoeuib.ttf"

CHROME = next((p for p in [
    Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
    Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
] if p.exists()), None)

SHELL = """<defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#12161e"/><stop offset="1" stop-color="#0a0c10"/>
    </linearGradient>
    <radialGradient id="glow" cx="50%" cy="22%" r="60%">
      <stop offset="0" stop-color="#ff7a2f" stop-opacity=".22"/><stop offset="1" stop-color="#ff7a2f" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="hot" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#ff7a2f"/><stop offset="1" stop-color="#ffb057"/>
    </linearGradient>
    <pattern id="grid" width="60" height="60" patternUnits="userSpaceOnUse">
      <path d="M60 0H0V60" fill="none" stroke="#677184" stroke-opacity=".14" stroke-width="1"/>
    </pattern>
  </defs>
  <rect width="1080" height="1920" fill="url(#bg)"/>
  <rect width="1080" height="1920" fill="url(#grid)"/>
  <rect width="1080" height="1920" fill="url(#glow)"/>
  <g stroke="#ff7a2f" stroke-opacity=".5" stroke-width="3" fill="none">
    <path d="M56 86V56h30"/><path d="M994 56h30v30"/><path d="M1024 1834v30h-30"/><path d="M86 1864H56v-30"/>
  </g>"""

FOOT = """<g font-size="26" font-weight="600" letter-spacing="2">
    <rect x="150" y="1606" width="300" height="66" rx="4" fill="none" stroke="#313d4e"/>
    <text x="300" y="1648" fill="#e9edf4" text-anchor="middle">NO ACCOUNT</text>
    <rect x="486" y="1606" width="444" height="66" rx="4" fill="none" stroke="#313d4e"/>
    <text x="708" y="1648" fill="#e9edf4" text-anchor="middle">NOTHING UPLOADED</text>
  </g>
  <text x="540" y="1762" font-size="32" fill="#8f9aac" text-anchor="middle" letter-spacing="1">printvault.magikh0e.pl</text>
  <text x="540" y="1822" font-size="26" fill="#67718a" text-anchor="middle" letter-spacing="1.6">FREE AND OPEN SOURCE  ·  GPL-3.0</text>"""

MARK = """<g transform="translate(%d,%d) scale(%s)">
    <path d="M16 2 3 9v14l13 7 13-7V9z" fill="none" stroke="#e9edf4" stroke-opacity=".38" stroke-width="1.6" stroke-linejoin="round"/>
    <path d="M3 9l13 6.6L29 9M16 15.6V30" fill="none" stroke="#e9edf4" stroke-opacity=".38" stroke-width="1.6" stroke-linejoin="round"/>
    <path d="M16 2 3 9l13 6.6L29 9z" fill="#ff7a2f"/>
  </g>"""

CARDS = {
    "title": SHELL + MARK % (398, 560, "4.2") + """
  <text x="540" y="820" font-size="78" font-weight="800" fill="#e9edf4" text-anchor="middle" letter-spacing="-2">Print<tspan fill="#ff7a2f">Vault</tspan></text>
  <text x="540" y="952" font-size="54" font-weight="700" fill="#e9edf4" text-anchor="middle" letter-spacing="-1">A local-first manager</text>
  <text x="540" y="1024" font-size="54" font-weight="700" fill="url(#hot)" text-anchor="middle" letter-spacing="-1">for 3D print files.</text>
  <text x="540" y="1128" font-size="32" fill="#8f9aac" text-anchor="middle">Free, open source, nothing uploaded</text>""",

    "handoff": SHELL + """
  <text x="540" y="820" font-size="62" font-weight="800" fill="#e9edf4" text-anchor="middle" letter-spacing="-1.5">Eight hours of printing.</text>
  <text x="540" y="906" font-size="62" font-weight="800" fill="url(#hot)" text-anchor="middle" letter-spacing="-1.5">Sometimes three days.</text>
  <text x="540" y="1016" font-size="38" fill="#8f9aac" text-anchor="middle">Will it actually fit your head?</text>
  <text x="540" y="1164" font-size="46" font-weight="700" fill="#e9edf4" text-anchor="middle" letter-spacing="-1">Head<tspan fill="#ff7a2f">fit</tspan></text>""",

    "end": SHELL + MARK % (430, 520, "3.4") + """
  <text x="540" y="790" font-size="52" font-weight="800" fill="#e9edf4" text-anchor="middle" letter-spacing="-1">Print<tspan fill="#ff7a2f">Vault</tspan>  ·  Head<tspan fill="#ff7a2f">fit</tspan></text>
  <text x="540" y="900" font-size="34" fill="#8f9aac" text-anchor="middle">printvault.magikh0e.pl</text>
  <text x="540" y="958" font-size="34" fill="#8f9aac" text-anchor="middle">printvault.magikh0e.pl/headfit.html</text>
  <g font-size="26" font-weight="600" letter-spacing="2">
    <rect x="258" y="1066" width="258" height="64" rx="4" fill="none" stroke="#313d4e"/>
    <text x="387" y="1107" fill="#e9edf4" text-anchor="middle">BROWSER</text>
    <rect x="564" y="1066" width="258" height="64" rx="4" fill="none" stroke="#313d4e"/>
    <text x="693" y="1107" fill="#e9edf4" text-anchor="middle">DESKTOP</text>
  </g>
  <text x="540" y="1252" font-size="30" fill="#67718a" text-anchor="middle">GPL-3.0  ·  no account  ·  nothing uploaded</text>""",

    "frame": SHELL + FOOT,
}

# clip, where to start, how long, the heading over it, and what the captions say
SEGMENTS = [
    # Timed against a contact sheet of the clip, one frame per second, not
    # against the sleeps in the recorder: page loads and renders push them
    # around and a caption describing the previous screen is worse than none.
    ("printvault", 0.4, 13.0, "PrintVault", [
        (0.0, 4.4, "Point it at the folder you already have"),
        (4.4, 7.2, "Every model, its files and its settings"),
        (7.2, 10.6, "Duplicates, and what they are costing you"),
        (10.6, 13.0, "A record of what you printed, and with what"),
    ]),
    ("headfit", 1.0, 11.5, "Headfit", [
        (0.0, 3.0, "A head built from three tape measurements"),
        (3.0, 5.2, "The helmet sits where you would wear it"),
        (5.2, 8.6, "Clearance painted on. Red is where it bites"),
        (8.6, 11.5, "Check it from any angle before you commit"),
    ]),
]


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"failed: {' '.join(str(c) for c in cmd[:3])}...\n{r.stderr[-900:]}")


def render_cards():
    if not CHROME:
        sys.exit("no Chrome or Edge found to render the cards")
    for name, body in CARDS.items():
        svg = OUT / f"{name}.svg"
        svg.write_text(
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
            f'viewBox="0 0 {W} {H}" font-family="Segoe UI, Helvetica, Arial, sans-serif">{body}</svg>',
            encoding="utf-8")
        run([str(CHROME), "--headless", "--disable-gpu", "--hide-scrollbars",
             f"--window-size={W},{H}", f"--screenshot={OUT / (name + '.png')}",
             f"file:///{svg.as_posix()}"])
        print(f"  card {name}.png")


def esc(text):
    """drawtext eats colons, apostrophes and backslashes."""
    return text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\u2019")


def build_segment(name, start, dur, heading, captions):
    chain = [f"[1:v]scale=1040:-2[c]", f"[0:v][c]overlay=(W-w)/2:618[v0]"]
    label = ("[v0]drawtext=fontfile='%s':text='%s':fontcolor=#e9edf4:fontsize=58:"
             "x=(w-text_w)/2:y=452[v1]" % (FONTB, esc(heading)))
    chain.append(label)
    tag = "v1"
    for i, (a, b, text) in enumerate(captions):
        nxt = f"c{i}"
        chain.append(
            "[%s]drawtext=fontfile='%s':text='%s':fontcolor=#c6cedb:fontsize=36:"
            "x=(w-text_w)/2:y=1372:enable='between(t,%.2f,%.2f)'[%s]"
            % (tag, FONT, esc(text), a, b, nxt))
        tag = nxt
    out = OUT / f"seg-{name}.mp4"
    run(["ffmpeg", "-v", "error", "-loop", "1", "-i", str(OUT / "frame.png"),
         "-ss", str(start), "-t", str(dur), "-i", str(OUT / f"{name}.webm"),
         "-filter_complex", ";".join(chain), "-map", f"[{tag}]",
         "-t", str(dur), "-r", str(FPS), "-pix_fmt", "yuv420p",
         "-c:v", "libx264", "-crf", "19", "-preset", "medium", "-an", "-y", str(out)])
    print(f"  {out.name}")
    return out


def build_card(name, dur):
    out = OUT / f"card-{name}.mp4"
    run(["ffmpeg", "-v", "error", "-loop", "1", "-t", str(dur), "-i", str(OUT / f"{name}.png"),
         "-r", str(FPS), "-pix_fmt", "yuv420p", "-c:v", "libx264", "-crf", "19",
         "-preset", "medium", "-an", "-y", str(out)])
    print(f"  {out.name}")
    return out


if __name__ == "__main__":
    if not shutil.which("ffmpeg"):
        sys.exit("no ffmpeg on PATH")
    for name, *_ in SEGMENTS:
        if not (OUT / f"{name}.webm").exists():
            sys.exit(f"no promo/{name}.webm, run tools/promo-record.py first")

    print("cards")
    render_cards()
    print("segments")
    parts = [build_card("title", 2.6)]
    parts.append(build_segment(*SEGMENTS[0]))
    parts.append(build_card("handoff", 2.8))
    parts.append(build_segment(*SEGMENTS[1]))
    parts.append(build_card("end", 3.0))

    listing = OUT / "parts.txt"
    listing.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
    final = OUT / "printvault-headfit-reel.mp4"
    run(["ffmpeg", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(listing),
         "-c", "copy", "-movflags", "+faststart", "-y", str(final)])
    size = final.stat().st_size / 1_000_000
    dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(final)], capture_output=True, text=True).stdout.strip()
    print(f"\n{final.name}  {float(dur):.1f}s  {size:.1f} MB")
