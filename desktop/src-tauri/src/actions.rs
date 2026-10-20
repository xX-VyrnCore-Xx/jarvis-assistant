//! Azioni eseguibili sul PC su richiesta del server. Le conferme per le azioni sensibili
//! (spostamenti, spegnimento) sono chieste all'utente dal frontend prima di arrivare qui.
use crate::paths::resolve;
use serde_json::Value;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

const MAX_RESULTS: usize = 30;
const MAX_DEPTH: usize = 6;

fn arg<'a>(args: &'a Value, key: &str) -> Result<&'a str, String> {
    args.get(key).and_then(Value::as_str).ok_or_else(|| format!("parametro mancante: {key}"))
}

fn home() -> Result<PathBuf, String> {
    std::env::var_os(if cfg!(windows) { "USERPROFILE" } else { "HOME" })
        .map(PathBuf::from)
        .ok_or_else(|| "cartella home non trovata".to_string())
}

fn level(args: &Value) -> Result<u32, String> {
    let n = args.get("level").and_then(Value::as_u64).ok_or("parametro mancante: level")?;
    Ok(n.min(100) as u32)
}

#[cfg(windows)]
fn powershell(script: &str) -> Result<String, String> {
    use std::os::windows::process::CommandExt;
    let out = Command::new("powershell")
        .args(["-NoProfile", "-NonInteractive", "-Command", script])
        .creation_flags(0x0800_0000) // CREATE_NO_WINDOW
        .output()
        .map_err(|e| e.to_string())?;
    if out.status.success() {
        Ok(String::from_utf8_lossy(&out.stdout).trim().to_string())
    } else {
        Err(String::from_utf8_lossy(&out.stderr).trim().to_string())
    }
}

#[cfg(not(windows))]
fn powershell(_: &str) -> Result<String, String> {
    Err("azione disponibile solo su Windows".into())
}

fn spawn_hidden(program: &str, args: &[&str]) -> Result<(), String> {
    let mut cmd = Command::new(program);
    cmd.args(args);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x0800_0000);
    }
    cmd.spawn().map(|_| ()).map_err(|e| e.to_string())
}

fn search(dir: &Path, needle: &str, depth: usize, out: &mut Vec<String>) {
    if depth > MAX_DEPTH || out.len() >= MAX_RESULTS {
        return;
    }
    let Ok(entries) = fs::read_dir(dir) else { return };
    for e in entries.flatten() {
        if out.len() >= MAX_RESULTS {
            return;
        }
        let name = e.file_name().to_string_lossy().to_string();
        if name.starts_with('.') {
            continue;
        }
        let Ok(ft) = e.file_type() else { continue };
        if ft.is_symlink() {
            continue;
        }
        if name.to_lowercase().contains(needle) {
            out.push(e.path().display().to_string());
        }
        if ft.is_dir() {
            search(&e.path(), needle, depth + 1, out);
        }
    }
}

pub fn run(app: &tauri::AppHandle, action: &str, args: &Value) -> Result<String, String> {
    let _ = app;
    match action {
        "pc_open_url" => {
            let url = arg(args, "url")?;
            if !(url.starts_with("https://") || url.starts_with("http://")) {
                return Err("sono consentiti solo URL http/https".into());
            }
            tauri_plugin_opener::open_url(url, None::<&str>).map_err(|e| e.to_string())?;
            Ok(format!("Aperto {url}"))
        }
        "pc_open_app" => {
            let name = arg(args, "name")?;
            let ok = !name.is_empty()
                && name.len() <= 40
                && name.chars().all(|c| c.is_ascii_alphanumeric() || " ._-".contains(c));
            if !ok {
                return Err("nome applicazione non valido".into());
            }
            spawn_hidden("cmd", &["/C", "start", "", name])?;
            Ok(format!("Avviata l'applicazione '{name}'"))
        }
        "pc_list_dir" => {
            let dir = resolve(&home()?, arg(args, "path")?)?;
            let mut rows: Vec<String> = fs::read_dir(&dir)
                .map_err(|e| e.to_string())?
                .flatten()
                .take(100)
                .map(|e| {
                    let d = e.file_type().map(|t| t.is_dir()).unwrap_or(false);
                    format!("{}{}", e.file_name().to_string_lossy(), if d { "/" } else { "" })
                })
                .collect();
            rows.sort();
            Ok(if rows.is_empty() { "Cartella vuota.".into() } else { rows.join("\n") })
        }
        "pc_search_files" => {
            let needle = arg(args, "query")?.to_lowercase();
            if needle.len() < 2 {
                return Err("query troppo corta".into());
            }
            let mut out = Vec::new();
            search(&home()?, &needle, 0, &mut out);
            Ok(if out.is_empty() { "Nessun file trovato.".into() } else { out.join("\n") })
        }
        "pc_open_path" => {
            let p = resolve(&home()?, arg(args, "path")?)?;
            if !p.exists() {
                return Err("il percorso non esiste".into());
            }
            tauri_plugin_opener::open_path(p.display().to_string(), None::<&str>).map_err(|e| e.to_string())?;
            Ok(format!("Aperto {}", p.display()))
        }
        "pc_create_folder" => {
            let p = resolve(&home()?, arg(args, "path")?)?;
            fs::create_dir_all(&p).map_err(|e| e.to_string())?;
            Ok(format!("Cartella creata: {}", p.display()))
        }
        "pc_move" => {
            let h = home()?;
            let (src, dst) = (resolve(&h, arg(args, "src")?)?, resolve(&h, arg(args, "dst")?)?);
            if dst.exists() {
                return Err("la destinazione esiste già".into());
            }
            fs::rename(&src, &dst).map_err(|e| e.to_string())?;
            Ok(format!("Spostato in {}", dst.display()))
        }
        "pc_volume" => {
            if let Some(a) = args.get("action").and_then(Value::as_str) {
                let key = match a {
                    "up" => 175,
                    "down" => 174,
                    "mute" => 173,
                    _ => return Err("azione volume non valida".into()),
                };
                powershell(&format!("(New-Object -ComObject WScript.Shell).SendKeys([char]{key})"))?;
                return Ok(format!("Volume: {a}"));
            }
            let l = level(args)?;
            // porta a zero e risale: ogni pressione vale 2 punti percentuali
            powershell(&format!(
                "$w=New-Object -ComObject WScript.Shell; 1..50|%{{$w.SendKeys([char]174)}}; 1..{}|%{{$w.SendKeys([char]175)}}",
                l / 2
            ))?;
            Ok(format!("Volume impostato a circa {l}%"))
        }
        "pc_brightness" => {
            let l = level(args)?;
            powershell(&format!(
                "(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1,{l})"
            ))?;
            Ok(format!("Luminosità impostata al {l}%"))
        }
        "pc_lock" => {
            spawn_hidden("rundll32.exe", &["user32.dll,LockWorkStation"])?;
            Ok("PC bloccato".into())
        }
        "pc_power" => match arg(args, "mode")? {
            "shutdown" => spawn_hidden("shutdown", &["/s", "/t", "30"]).map(|_| "Spegnimento tra 30 secondi".into()),
            "restart" => spawn_hidden("shutdown", &["/r", "/t", "30"]).map(|_| "Riavvio tra 30 secondi".into()),
            "cancel" => spawn_hidden("shutdown", &["/a"]).map(|_| "Operazione annullata".into()),
            _ => Err("modalità non valida".into()),
        },
        other => Err(format!("azione sconosciuta: {other}")),
    }
}
