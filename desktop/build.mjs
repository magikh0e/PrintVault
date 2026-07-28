// Copies the single-file app into dist/ so Tauri has a frontend to bundle.
// There is deliberately no build step: the same index.html runs in a browser
// and in the desktop shell, choosing its filesystem layer at runtime.
import { copyFileSync, mkdirSync, statSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const src = join(here, '..', 'index.html');
const outDir = join(here, 'dist');
mkdirSync(outDir, { recursive: true });
copyFileSync(src, join(outDir, 'index.html'));
const kb = (statSync(src).size / 1024).toFixed(0);
console.log(`copied index.html (${kb} KB) -> desktop/dist/`);

// The app is the single source of truth for the version. The shell used to
// carry its own, which meant the window title and the in-app chip could
// disagree and look like a stale build was running.
const app = readFileSync(src, 'utf8');
const v = (app.match(/const APP_VERSION = '([\d.]+)'/) || [])[1];
if (!v) { console.warn('could not read APP_VERSION, leaving shell versions alone'); }
else {
  const targets = [
    [join(here, 'package.json'), /("version"\s*:\s*)"[\d.]+"/],
    [join(here, 'src-tauri', 'tauri.conf.json'), /("version"\s*:\s*)"[\d.]+"/],
    [join(here, 'src-tauri', 'Cargo.toml'), /(^version\s*=\s*)"[\d.]+"/m]
  ];
  const changed = [];
  for (const [file, re] of targets) {
    const before = readFileSync(file, 'utf8');
    const after = before.replace(re, (_, p) => `${p}"${v}"`);
    if (after !== before) { writeFileSync(file, after, 'utf8'); changed.push(file.split(/[\\/]/).pop()); }
  }
  console.log(changed.length ? `version -> ${v} (updated ${changed.join(', ')})` : `version ${v} already in sync`);
}
