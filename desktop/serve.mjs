// Dev-only static server for the desktop shell.
//
// Tauri's built-in dev server hands index.html back as application/octet-stream,
// which WebView2 will not render as a page, so the window comes up blank. This
// serves the same directory with correct MIME types. It also means editing
// index.html only needs a refresh rather than a Rust rebuild.
import { createServer } from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import { dirname, join, extname, normalize } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, 'dist');
const port = Number(process.env.PV_DEV_PORT || 1421);

const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.webp': 'image/webp',
  '.woff2': 'font/woff2',
  '.ico': 'image/x-icon'
};

createServer(async (req, res) => {
  try {
    let rel = decodeURIComponent((req.url || '/').split('?')[0]);
    if (rel === '/' || rel === '') rel = '/index.html';
    // keep requests inside dist/
    const file = join(root, normalize(rel).replace(/^(\.\.[\\/])+/, ''));
    if (!file.startsWith(root)) { res.writeHead(403).end('forbidden'); return; }
    const s = await stat(file).catch(() => null);
    if (!s || !s.isFile()) { res.writeHead(404).end('not found'); return; }
    const body = await readFile(file);
    res.writeHead(200, {
      'Content-Type': TYPES[extname(file).toLowerCase()] || 'application/octet-stream',
      'Content-Length': body.length,
      'Cache-Control': 'no-store'
    });
    res.end(body);
  } catch (e) {
    res.writeHead(500).end(String(e && e.message || e));
  }
}).listen(port, '127.0.0.1', () => {
  console.log(`dev server on http://localhost:${port} serving desktop/dist`);
});
