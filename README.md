# PrintVault

I had about 460 files in a folder called "3d print files". Half a dozen
subfolders named "files". No idea which settings I'd used on anything I'd
already printed. When I finally got a proper index of it there were 78 zips
I'd never extracted, holding 414 printable models that nothing had ever shown
me.

This is what I built to dig myself out. It's free, GPL-3.0, and runs either in
your browser or as a desktop app.

Live at https://printvault.magikh0e.pl/

## What it does

Point it at a folder and it reads what's already there. Nothing gets moved,
renamed, or reorganised into somebody else's idea of a good structure.

It renders a 3D preview for every model, so you're looking at pictures instead
of filenames, and reuses the plate render your slicer already embedded when
there is one.

It pulls settings out of your sliced gcode: time, grams, layer height, nozzle,
infill, material, profile name. Works with PrusaSlicer, OrcaSlicer,
BambuStudio, Creality Print and Cura. Creality Print and Bambu bury the gcode
inside their `.3mf` project files, so it digs that back out. Log a print when
it comes off the bed and the form is already filled in, which means six months
later you can still see what you ran and whether it worked.

It reads inside zips you never extracted, listing and previewing what's in
them without unpacking anything. It'll extract them too, and checksums every
file it writes.

It finds duplicate downloads and proves they're identical with SHA-256 before
touching anything. By default it moves the copies to a quarantine folder
rather than deleting them, because a browser can't use the Recycle Bin and I
didn't want that on my conscience.

There's filament tracking by what's actually left on the spool, and a print
queue that adds up grams and hours so you know whether you can finish
something before you start it.

No account, nothing uploaded, no server involved.

## How it's put together

```
index.html            the whole app, one self-contained file
desktop/              Tauri shell
  build.mjs           copies index.html into dist/, syncs version numbers
  serve.mjs           dev-only static server with correct MIME types
  make-icon.mjs       generates every app icon from raw pixels
  src-tauri/          Rust backend
```

The same `index.html` runs in a browser and inside the desktop shell. It picks
its filesystem layer when it loads, either the File System Access API or
native calls through Tauri, and the other 96% of the code doesn't know or care
which. No build step, no bundler, no dependencies.

## Running it

In a browser, serve the folder over `https` or `http://localhost` and open
`index.html`. It won't work from a `file://` path, because browsers only hand
out folder access in a secure context. Chromium only for the folder part
(Chrome, Edge, Brave, Opera), since Firefox and Safari don't implement the API.

For the desktop app you need Rust and Node:

```bash
cd desktop
npm install
npm run tauri:dev      # with frontend hot reload
npm run tauri:build    # installers for the current platform
```

The desktop build drops most of the browser's restrictions. Drive roots and
mapped network drives work, there's no permission prompt every session, and
scanning is a lot quicker because one call returns the whole directory listing
instead of a round trip per file.

## Releases

Push a tag matching `desktop-v*` and the workflow builds installers for
Windows, macOS and Linux, then opens a draft release. Tauri can't
cross-compile, so each one is built on its own runner.

## Licence

GPL-3.0-or-later, see [LICENSE](LICENSE).
