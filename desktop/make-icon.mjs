// Generates the PrintVault app icon as a real PNG, no image libraries needed.
// Draws the isometric cube from the favicon: dark rounded square, bright orange
// top face, two darker side faces. Node's zlib does the PNG compression.
import { deflateSync } from 'node:zlib';
import { writeFileSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const S = 1024;
const BG = [14, 16, 20];
const TOP = [255, 154, 92];
const LEFT = [200, 95, 34];
const RIGHT = [229, 113, 44];

// Signed area test, so a point can be tested against a convex polygon.
function inPoly(px, py, pts) {
  let sign = 0;
  for (let i = 0; i < pts.length; i++) {
    const [ax, ay] = pts[i];
    const [bx, by] = pts[(i + 1) % pts.length];
    const cross = (bx - ax) * (py - ay) - (by - ay) * (px - ax);
    if (cross === 0) continue;
    const s = cross > 0 ? 1 : -1;
    if (sign === 0) sign = s;
    else if (s !== sign) return false;
  }
  return true;
}

function build(size) {
  const px = Buffer.alloc(size * size * 4);
  const k = size / 1024;
  const cx = size / 2;
  const r = size * 0.30;          // cube half-width
  const h = size * 0.17;          // vertical offset of the top face
  const top = size * 0.20;
  const bot = size * 0.80;
  const mid = (top + bot) / 2 + h * 0.15;

  // cube vertices
  const T = [[cx, top], [cx + r, top + h], [cx, top + 2 * h], [cx - r, top + h]];
  const L = [[cx - r, top + h], [cx, top + 2 * h], [cx, bot], [cx - r, mid]];
  const R = [[cx + r, top + h], [cx, top + 2 * h], [cx, bot], [cx + r, mid]];

  const radius = size * 0.22;
  const inRounded = (x, y) => {
    const m = size * 0.045;
    const x0 = m, y0 = m, x1 = size - m, y1 = size - m;
    if (x < x0 || x > x1 || y < y0 || y > y1) return false;
    const rx = Math.min(Math.max(x, x0 + radius), x1 - radius);
    const ry = Math.min(Math.max(y, y0 + radius), y1 - radius);
    const dx = x - rx, dy = y - ry;
    return dx * dx + dy * dy <= radius * radius || (x >= x0 + radius && x <= x1 - radius) || (y >= y0 + radius && y <= y1 - radius);
  };

  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const i = (y * size + x) * 4;
      // 2x2 supersample for tolerable edges without a rasteriser
      let rr = 0, gg = 0, bb = 0, aa = 0;
      for (const [ox, oy] of [[0.25, 0.25], [0.75, 0.25], [0.25, 0.75], [0.75, 0.75]]) {
        const sx = x + ox, sy = y + oy;
        let col = null, alpha = 0;
        if (inRounded(sx, sy)) { col = BG; alpha = 255; }
        if (col) {
          if (inPoly(sx, sy, T)) col = TOP;
          else if (inPoly(sx, sy, L)) col = LEFT;
          else if (inPoly(sx, sy, R)) col = RIGHT;
        }
        if (col) { rr += col[0]; gg += col[1]; bb += col[2]; aa += alpha; }
      }
      px[i] = Math.round(rr / 4); px[i + 1] = Math.round(gg / 4);
      px[i + 2] = Math.round(bb / 4); px[i + 3] = Math.round(aa / 4);
    }
  }
  return px;
}

function crc32(buf) {
  let c, table = [];
  for (let n = 0; n < 256; n++) {
    c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1;
    table[n] = c >>> 0;
  }
  let crc = 0xFFFFFFFF;
  for (const b of buf) crc = table[(crc ^ b) & 0xFF] ^ (crc >>> 8);
  return (crc ^ 0xFFFFFFFF) >>> 0;
}

function chunk(type, data) {
  const len = Buffer.alloc(4); len.writeUInt32BE(data.length);
  const td = Buffer.concat([Buffer.from(type, 'ascii'), data]);
  const crc = Buffer.alloc(4); crc.writeUInt32BE(crc32(td));
  return Buffer.concat([len, td, crc]);
}

function png(size, rgba) {
  const raw = Buffer.alloc((size * 4 + 1) * size);
  for (let y = 0; y < size; y++) {
    raw[y * (size * 4 + 1)] = 0; // filter: none
    rgba.copy(raw, y * (size * 4 + 1) + 1, y * size * 4, (y + 1) * size * 4);
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(size, 0); ihdr.writeUInt32BE(size, 4);
  ihdr[8] = 8; ihdr[9] = 6; ihdr[10] = 0; ihdr[11] = 0; ihdr[12] = 0;
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]),
    chunk('IHDR', ihdr),
    chunk('IDAT', deflateSync(raw, { level: 9 })),
    chunk('IEND', Buffer.alloc(0))
  ]);
}

// Nearest-neighbour downscale from the 1024 master, good enough for icons.
function scale(src, from, to) {
  const out = Buffer.alloc(to * to * 4);
  for (let y = 0; y < to; y++) {
    for (let x = 0; x < to; x++) {
      const step = from / to;
      let r = 0, g = 0, b = 0, a = 0, n = 0;
      for (let sy = Math.floor(y * step); sy < Math.floor((y + 1) * step); sy++) {
        for (let sx = Math.floor(x * step); sx < Math.floor((x + 1) * step); sx++) {
          const i = (sy * from + sx) * 4;
          r += src[i]; g += src[i + 1]; b += src[i + 2]; a += src[i + 3]; n++;
        }
      }
      const o = (y * to + x) * 4;
      out[o] = r / n; out[o + 1] = g / n; out[o + 2] = b / n; out[o + 3] = a / n;
    }
  }
  return out;
}

const here = dirname(fileURLToPath(import.meta.url));
const dir = join(here, 'src-tauri', 'icons');
mkdirSync(dir, { recursive: true });

const master = build(S);
const sizes = {
  'icon.png': 1024, '128x128@2x.png': 256, '128x128.png': 128,
  '64x64.png': 64, '32x32.png': 32,
  'Square30x30Logo.png': 30, 'Square44x44Logo.png': 44, 'Square71x71Logo.png': 71,
  'Square89x89Logo.png': 89, 'Square107x107Logo.png': 107, 'Square142x142Logo.png': 142,
  'Square150x150Logo.png': 150, 'Square284x284Logo.png': 284, 'Square310x310Logo.png': 310,
  'StoreLogo.png': 50
};
for (const [name, n] of Object.entries(sizes)) {
  const data = n === S ? master : scale(master, S, n);
  writeFileSync(join(dir, name), png(n, data));
}

// Windows .ico. Vista and later accept PNG data inside an ICO, so each entry is
// just the PNG we already know how to make.
function ico(entries) {
  const dirEntries = [], blobs = [];
  let offset = 6 + entries.length * 16;
  for (const [n, data] of entries) {
    const e = Buffer.alloc(16);
    e[0] = n >= 256 ? 0 : n;      // 0 means 256
    e[1] = n >= 256 ? 0 : n;
    e[2] = 0; e[3] = 0;
    e.writeUInt16LE(1, 4);        // planes
    e.writeUInt16LE(32, 6);       // bits per pixel
    e.writeUInt32LE(data.length, 8);
    e.writeUInt32LE(offset, 12);
    offset += data.length;
    dirEntries.push(e); blobs.push(data);
  }
  const head = Buffer.alloc(6);
  head.writeUInt16LE(0, 0); head.writeUInt16LE(1, 2); head.writeUInt16LE(entries.length, 4);
  return Buffer.concat([head, ...dirEntries, ...blobs]);
}
const icoSizes = [16, 32, 48, 64, 128, 256];
writeFileSync(join(dir, 'icon.ico'),
  ico(icoSizes.map(n => [n, png(n, scale(master, S, n))])));

// macOS .icns. Modern types take PNG payloads directly.
function icns(entries) {
  const chunks = [];
  for (const [type, data] of entries) {
    const h = Buffer.alloc(8);
    h.write(type, 0, 4, 'ascii');
    h.writeUInt32BE(data.length + 8, 4);
    chunks.push(Buffer.concat([h, data]));
  }
  const body = Buffer.concat(chunks);
  const head = Buffer.alloc(8);
  head.write('icns', 0, 4, 'ascii');
  head.writeUInt32BE(body.length + 8, 4);
  return Buffer.concat([head, body]);
}
writeFileSync(join(dir, 'icon.icns'), icns([
  ['ic07', png(128, scale(master, S, 128))],
  ['ic08', png(256, scale(master, S, 256))],
  ['ic09', png(512, scale(master, S, 512))],
  ['ic10', png(1024, master)]
]));

console.log('wrote ' + Object.keys(sizes).length + ' PNGs + icon.ico + icon.icns to src-tauri/icons/');
