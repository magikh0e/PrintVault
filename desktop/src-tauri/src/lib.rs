// PrintVault desktop shell
// Copyright (C) 2026 magikh0e - GPL-3.0-or-later
//
// The whole app is one HTML file that also runs in a browser. Everything the
// browser build does through the File System Access API is done here through
// these commands instead, which is why they map one-to-one onto the `FS`
// module in index.html rather than being a general-purpose filesystem API.

use std::fs;
use std::io::{Read, Seek, SeekFrom};
use std::path::{Path, PathBuf};

use serde::Serialize;
use tauri::ipc::Response;
use tauri::{WebviewUrl, WebviewWindowBuilder};
use tauri_plugin_dialog::{DialogExt, MessageDialogButtons};
use tauri_plugin_updater::UpdaterExt;
use walkdir::WalkDir;

#[derive(Serialize)]
pub struct Entry {
    path: String, // relative to the root, forward slashes, matching the browser build
    name: String,
    size: u64,
    mtime: u64, // epoch ms
}

#[derive(Serialize)]
pub struct WalkResult {
    files: Vec<Entry>,
    skipped_dirs: Vec<String>,
    truncated: bool,
}

/// Native folder picker.
///
/// Must be `async`, and must not use the plugin's `blocking_` variant. A sync
/// command runs on the main thread, and on GTK that is the same thread the
/// dialog needs in order to pump its own events, so blocking there deadlocks
/// the whole window the moment you click Add Folder. Windows and macOS survive
/// it because their native dialogs run their own message loop, which is why
/// this only ever showed up on Linux.
///
/// As an async command this runs on a worker thread, the dialog is opened
/// without blocking, and the result comes back over a channel.
#[tauri::command]
async fn pv_pick_folder(app: tauri::AppHandle) -> Option<String> {
    let (tx, rx) = std::sync::mpsc::channel();
    app.dialog().file().pick_folder(move |picked| {
        let _ = tx.send(picked);
    });
    rx.recv()
        .ok()
        .flatten()
        .and_then(|p| p.into_path().ok())
        .map(|p| p.to_string_lossy().to_string())
}

fn to_ms(t: std::time::SystemTime) -> u64 {
    t.duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .unwrap_or(0)
}

/// Walk a root and return every file in one call. `skip` is a list of
/// lowercase directory names to prune, matching the browser build's skip list.
/// `max` guards against a mistakenly selected drive root.
#[tauri::command]
async fn pv_walk(root: String, skip: Vec<String>, max: Option<usize>) -> Result<WalkResult, String> {
    let base = PathBuf::from(&root);
    if !base.is_dir() {
        return Err(format!("Not a folder: {}", root));
    }
    let cap = max.unwrap_or(2_000_000);
    let mut files = Vec::new();
    let mut skipped_dirs = Vec::new();
    let mut truncated = false;

    let walker = WalkDir::new(&base).follow_links(false).into_iter();
    let mut it = walker.filter_entry(|e| {
        if e.depth() == 0 {
            return true;
        }
        let name = e.file_name().to_string_lossy().to_lowercase();
        if name.starts_with('.') {
            return false;
        }
        if e.file_type().is_dir() && skip.contains(&name) {
            return false;
        }
        true
    });

    while let Some(next) = it.next() {
        match next {
            Ok(e) => {
                if !e.file_type().is_file() {
                    continue;
                }
                if files.len() >= cap {
                    truncated = true;
                    break;
                }
                let md = match e.metadata() {
                    Ok(m) => m,
                    Err(_) => continue,
                };
                // Join the real path components rather than replacing every
                // backslash with a slash. On Windows the separator is a
                // backslash so the two look the same, but on Linux a backslash
                // is an ordinary character in a filename, and rewriting it
                // split one file into a folder plus a file that does not
                // exist. `a\b.zip` became `a/b.zip`, which then indexed as a
                // model folder named `a` holding `b.zip`.
                let rel = match e.path().strip_prefix(&base) {
                    Ok(r) => r
                        .components()
                        .map(|c| c.as_os_str().to_string_lossy().into_owned())
                        .collect::<Vec<_>>()
                        .join("/"),
                    Err(_) => continue,
                };
                files.push(Entry {
                    name: e.file_name().to_string_lossy().to_string(),
                    path: rel,
                    size: md.len(),
                    mtime: md.modified().map(to_ms).unwrap_or(0),
                });
            }
            // An unreadable folder is reported rather than silently swallowed,
            // the same way the browser build now reports them.
            Err(err) => {
                let p = err
                    .path()
                    .map(|p| p.to_string_lossy().to_string())
                    .unwrap_or_else(|| "(unknown)".into());
                skipped_dirs.push(format!("{}: {}", p, err));
            }
        }
    }

    Ok(WalkResult {
        files,
        skipped_dirs,
        truncated,
    })
}

fn joined(root: &str, rel: &str) -> Result<PathBuf, String> {
    // Reject anything that would climb out of the chosen root.
    if rel.split(['/', '\\']).any(|s| s == "..") {
        return Err("Path traversal rejected".into());
    }
    let mut p = PathBuf::from(root);
    for seg in rel.split('/').filter(|s| !s.is_empty()) {
        p.push(seg);
    }
    Ok(p)
}

/// Whole file as raw bytes. Returned as an ArrayBuffer, not a JSON number array.
#[tauri::command]
async fn pv_read(root: String, rel: String) -> Result<Response, String> {
    let p = joined(&root, &rel)?;
    fs::read(&p).map(Response::new).map_err(|e| e.to_string())
}

/// A byte range, so a 200 MB archive can be indexed by reading only its tail.
#[tauri::command]
async fn pv_read_range(root: String, rel: String, start: u64, len: u64) -> Result<Response, String> {
    let p = joined(&root, &rel)?;
    let mut f = fs::File::open(&p).map_err(|e| e.to_string())?;
    let total = f.metadata().map_err(|e| e.to_string())?.len();
    if start >= total {
        return Ok(Response::new(Vec::new()));
    }
    let want = len.min(total - start) as usize;
    f.seek(SeekFrom::Start(start)).map_err(|e| e.to_string())?;
    let mut buf = vec![0u8; want];
    let mut read = 0usize;
    while read < want {
        match f.read(&mut buf[read..]) {
            Ok(0) => break,
            Ok(n) => read += n,
            Err(e) => return Err(e.to_string()),
        }
    }
    buf.truncate(read);
    Ok(Response::new(buf))
}

#[tauri::command]
async fn pv_stat(root: String, rel: String) -> Result<Option<Entry>, String> {
    let p = joined(&root, &rel)?;
    match fs::metadata(&p) {
        Ok(md) if md.is_file() => Ok(Some(Entry {
            name: p
                .file_name()
                .map(|s| s.to_string_lossy().to_string())
                .unwrap_or_default(),
            path: rel,
            size: md.len(),
            mtime: md.modified().map(to_ms).unwrap_or(0),
        })),
        _ => Ok(None),
    }
}

#[tauri::command]
async fn pv_write(root: String, rel: String, data: Vec<u8>) -> Result<(), String> {
    let p = joined(&root, &rel)?;
    if let Some(parent) = p.parent() {
        fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    fs::write(&p, data).map_err(|e| e.to_string())
}

#[tauri::command]
async fn pv_remove(root: String, rel: String) -> Result<(), String> {
    let p = joined(&root, &rel)?;
    fs::remove_file(&p).map_err(|e| e.to_string())
}

/// Move within the same root. Falls back to copy-then-delete when the source
/// and destination are on different filesystems.
#[tauri::command]
async fn pv_move(root: String, from: String, to: String) -> Result<(), String> {
    let src = joined(&root, &from)?;
    let dst = joined(&root, &to)?;
    if let Some(parent) = dst.parent() {
        fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    if fs::rename(&src, &dst).is_ok() {
        return Ok(());
    }
    fs::copy(&src, &dst).map_err(|e| e.to_string())?;
    let a = fs::metadata(&src).map_err(|e| e.to_string())?.len();
    let b = fs::metadata(&dst).map_err(|e| e.to_string())?.len();
    if a != b {
        let _ = fs::remove_file(&dst);
        return Err("Copy verification failed, original left alone".into());
    }
    fs::remove_file(&src).map_err(|e| e.to_string())
}

#[tauri::command]
async fn pv_exists(root: String, rel: String) -> Result<bool, String> {
    Ok(joined(&root, &rel)?.exists())
}

/// Hand a file to whatever the OS uses for it, which is how "open in slicer"
/// works. The browser build cannot do this at all.
#[tauri::command]
fn pv_open(root: String, rel: String, reveal: bool) -> Result<(), String> {
    use tauri_plugin_opener::OpenerExt;
    let p = joined(&root, &rel)?;
    let app = APP.get().ok_or("App handle unavailable")?;
    if reveal {
        app.opener()
            .reveal_item_in_dir(&p)
            .map_err(|e| e.to_string())
    } else {
        app.opener()
            .open_path(p.to_string_lossy().to_string(), None::<&str>)
            .map_err(|e| e.to_string())
    }
}


/// Hand a file to a specific program, typically a slicer.
///
/// `exe` empty means "whatever the OS opens this with", which for a .3mf or
/// .stl is usually the slicer anyway. Pointing at one explicitly matters when
/// several are installed and the file association is not the one you want.
#[tauri::command]
async fn pv_open_with(root: String, rel: String, exe: String) -> Result<(), String> {
    let p = joined(&root, &rel)?;
    if !p.is_file() {
        return Err("That file is no longer there".into());
    }
    if exe.trim().is_empty() {
        return pv_open(root, rel, false);
    }
    let program = PathBuf::from(exe.trim());
    if !program.exists() {
        return Err(format!("No program at {}", program.display()));
    }
    // Spawned, not waited on. A slicer takes seconds to appear and the window
    // should not sit frozen until someone closes it.
    std::process::Command::new(&program)
        .arg(&p)
        .spawn()
        .map(|_| ())
        .map_err(|e| format!("Could not start {}: {}", program.display(), e))
}

/// Pick a program, for choosing a slicer in settings.
#[tauri::command]
async fn pv_pick_exe(app: tauri::AppHandle) -> Option<String> {
    let (tx, rx) = std::sync::mpsc::channel();
    let mut dlg = app.dialog().file();
    if cfg!(windows) {
        dlg = dlg.add_filter("Programs", &["exe"]);
    }
    dlg.pick_file(move |picked| {
        let _ = tx.send(picked);
    });
    rx.recv()
        .ok()
        .flatten()
        .and_then(|p| p.into_path().ok())
        .map(|p| p.to_string_lossy().to_string())
}

#[derive(Serialize)]
pub struct ExtractResult {
    written: usize,
    failed: usize,
    problems: Vec<String>,
}

/// Unpack an archive into a sibling folder. Done here rather than in JS so
/// entry bytes never cross the IPC bridge, which is what made large entries
/// fragile in the browser build. Paths from the archive are sanitised before
/// anything is written.
#[tauri::command]
async fn pv_extract(root: String, archive_rel: String, dest_rel: String) -> Result<ExtractResult, String> {
    let src = joined(&root, &archive_rel)?;
    let dest = joined(&root, &dest_rel)?;
    let file = fs::File::open(&src).map_err(|e| e.to_string())?;
    let mut zip = zip::ZipArchive::new(file).map_err(|e| e.to_string())?;

    let mut written = 0usize;
    let mut failed = 0usize;
    let mut problems: Vec<String> = Vec::new();

    for i in 0..zip.len() {
        let mut entry = match zip.by_index(i) {
            Ok(e) => e,
            Err(e) => {
                failed += 1;
                problems.push(format!("entry {}: {}", i, e));
                continue;
            }
        };
        if entry.is_dir() {
            continue;
        }
        // enclosed_name() rejects absolute paths and any .. traversal
        let rel = match entry.enclosed_name() {
            Some(p) => p,
            None => {
                failed += 1;
                problems.push(format!("{} (unsafe path, refused)", entry.name()));
                continue;
            }
        };
        let out = dest.join(&rel);
        if let Some(parent) = out.parent() {
            if let Err(e) = fs::create_dir_all(parent) {
                failed += 1;
                problems.push(format!("{}: {}", rel.display(), e));
                continue;
            }
        }
        let mut w = match fs::File::create(&out) {
            Ok(w) => w,
            Err(e) => {
                failed += 1;
                problems.push(format!("{}: {}", rel.display(), e));
                continue;
            }
        };
        match std::io::copy(&mut entry, &mut w) {
            Ok(n) => {
                // the zip's own size is the check; a short write is a failure
                if n == entry.size() {
                    written += 1;
                } else {
                    failed += 1;
                    let _ = fs::remove_file(&out);
                    problems.push(format!(
                        "{}: wrote {} of {} bytes",
                        rel.display(),
                        n,
                        entry.size()
                    ));
                }
            }
            Err(e) => {
                failed += 1;
                let _ = fs::remove_file(&out);
                problems.push(format!("{}: {}", rel.display(), e));
            }
        }
    }

    Ok(ExtractResult {
        written,
        failed,
        problems,
    })
}

/// Confirm a stored root still exists, so a disconnected share is reported
/// rather than looking like an empty folder.
#[tauri::command]
async fn pv_root_ok(root: String) -> bool {
    Path::new(&root).is_dir()
}


/* ---------------------------------------------------------------
   Sending a sliced file to a printer

   Moonraker (Klipper, and the Creality K2 among others) and OctoPrint both
   take a multipart upload over plain HTTP on the local network, which is why
   this lives in Rust: the webview will not post to an unencrypted box on your
   LAN, and a browser page never could.
   --------------------------------------------------------------- */

#[derive(Serialize)]
pub struct PrinterInfo {
    flavour: String,
    name: String,
    state: String,
}

fn base_url(addr: &str) -> String {
    let a = addr.trim().trim_end_matches('/');
    if a.starts_with("http://") || a.starts_with("https://") {
        a.to_string()
    } else {
        format!("http://{}", a)
    }
}

fn client() -> Result<reqwest::Client, String> {
    reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(600))
        .connect_timeout(std::time::Duration::from_secs(6))
        .build()
        .map_err(|e| e.to_string())
}

/// Work out what is answering at that address, so a typo says so plainly
/// rather than failing later halfway through an upload.
#[tauri::command]
async fn pv_printer_probe(addr: String, api_key: Option<String>) -> Result<PrinterInfo, String> {
    let base = base_url(&addr);
    let c = client()?;

    if let Ok(r) = c.get(format!("{}/printer/info", base)).send().await {
        if r.status().is_success() {
            let v: serde_json::Value = r.json().await.map_err(|e| e.to_string())?;
            let res = &v["result"];
            return Ok(PrinterInfo {
                flavour: "moonraker".into(),
                name: res["hostname"].as_str().unwrap_or("Klipper").to_string(),
                state: res["state"].as_str().unwrap_or("unknown").to_string(),
            });
        }
    }

    let mut req = c.get(format!("{}/api/version", base));
    if let Some(k) = api_key.as_deref().filter(|k| !k.is_empty()) {
        req = req.header("X-Api-Key", k);
    }
    if let Ok(r) = req.send().await {
        if r.status().is_success() {
            let v: serde_json::Value = r.json().await.map_err(|e| e.to_string())?;
            return Ok(PrinterInfo {
                flavour: "octoprint".into(),
                name: format!("OctoPrint {}", v["server"].as_str().unwrap_or("")),
                state: "ready".into(),
            });
        }
        return Err("Reached it, but it did not answer as Moonraker or OctoPrint. Wrong port, or an API key is needed".into());
    }
    Err("Nothing answered at that address".into())
}

/// Upload a sliced file, optionally starting it.
#[tauri::command]
async fn pv_printer_send(
    root: String,
    rel: String,
    addr: String,
    flavour: String,
    api_key: Option<String>,
    start: bool,
) -> Result<String, String> {
    let p = joined(&root, &rel)?;
    let name = p
        .file_name()
        .map(|s| s.to_string_lossy().to_string())
        .ok_or("Bad file name")?;
    let bytes = tokio::fs::read(&p).await.map_err(|e| e.to_string())?;
    let base = base_url(&addr);
    let c = client()?;

    let part = reqwest::multipart::Part::bytes(bytes)
        .file_name(name.clone())
        .mime_str("application/octet-stream")
        .map_err(|e| e.to_string())?;

    let (url, form) = if flavour == "octoprint" {
        let mut f = reqwest::multipart::Form::new().part("file", part);
        if start {
            f = f.text("print", "true");
        }
        (format!("{}/api/files/local", base), f)
    } else {
        let mut f = reqwest::multipart::Form::new().part("file", part);
        f = f.text("root", "gcodes");
        if start {
            f = f.text("print", "true");
        }
        (format!("{}/server/files/upload", base), f)
    };

    let mut req = c.post(url).multipart(form);
    if let Some(k) = api_key.as_deref().filter(|k| !k.is_empty()) {
        req = req.header("X-Api-Key", k);
    }
    let r = req.send().await.map_err(|e| e.to_string())?;
    let code = r.status();
    let body = r.text().await.unwrap_or_default();
    if !code.is_success() {
        return Err(format!("Printer refused it ({}): {}", code.as_u16(), body.chars().take(200).collect::<String>()));
    }
    Ok(name)
}

static APP: std::sync::OnceLock<tauri::AppHandle> = std::sync::OnceLock::new();

/// Ask the release manifest whether a newer signed build exists, and offer it.
///
/// Every failure is deliberately silent: offline, no release yet, a declined
/// prompt. Someone organising print files should never get an error dialog
/// because their network was flaky at launch.
///
/// Runs on a worker thread, so `blocking_show` is safe here. On the main
/// thread it would deadlock GTK, the same way the folder picker did.
async fn check_for_update(app: tauri::AppHandle) {
    let updater = match app.updater() {
        Ok(u) => u,
        Err(_) => return,
    };
    let update = match updater.check().await {
        Ok(Some(u)) => u,
        _ => return,
    };

    let msg = format!(
        "PrintVault {} is available (you have {}). Install it and restart now?

Your library and index are untouched.",
        update.version, update.current_version
    );
    let accepted = app
        .dialog()
        .message(msg)
        .title("Update available")
        .buttons(MessageDialogButtons::OkCancelCustom(
            "Install".into(),
            "Later".into(),
        ))
        .blocking_show();

    if accepted && update.download_and_install(|_, _| {}, || {}).await.is_ok() {
        app.restart();
    }
}

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![
            pv_pick_folder,
            pv_walk,
            pv_read,
            pv_read_range,
            pv_stat,
            pv_write,
            pv_remove,
            pv_move,
            pv_exists,
            pv_open,
            pv_open_with,
            pv_pick_exe,
            pv_printer_probe,
            pv_printer_send,
            pv_extract,
            pv_root_ok
        ])
        .setup(|app| {
            let _ = APP.set(app.handle().clone());

            // Tells the page it is running in the desktop shell, before any app
            // JS runs, so FS can pick its implementation at load time.
            let init = format!(
                "window.__PV_DESKTOP__ = {};",
                serde_json::to_string(env!("CARGO_PKG_VERSION")).unwrap()
            );

            WebviewWindowBuilder::new(app, "main", WebviewUrl::default())
                .title(concat!("PrintVault ", env!("CARGO_PKG_VERSION")))
                .inner_size(1280.0, 860.0)
                .min_inner_size(720.0, 520.0)
                .initialization_script(init.as_str())
                .build()?;

            let handle = app.handle().clone();
            tauri::async_runtime::spawn(async move { check_for_update(handle).await });

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running the PrintVault desktop app");
}
