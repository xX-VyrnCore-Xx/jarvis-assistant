//! Aggiornamento dell'app dentro l'app: scarica l'installer dalla Release del progetto con avanzamento, ne verifica l'SHA-256 e lo avvia.
use std::io::{BufRead, BufReader};
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::sync::Mutex;
use tauri::{AppHandle, Emitter, Manager, State};

#[cfg(windows)]
use std::os::windows::process::CommandExt;
#[cfg(windows)]
const NO_WINDOW: u32 = 0x0800_0000;

#[derive(Default)]
pub struct Updater {
    busy: Mutex<bool>,
    ready: Mutex<Option<PathBuf>>, // installer scaricato e verificato
}

/// Solo file .exe delle Release GitHub: mai un indirizzo qualsiasi.
fn allowed(url: &str) -> bool {
    url.starts_with("https://github.com/")
        && url.contains("/releases/download/")
        && url.ends_with(".exe")
        && url.len() < 300
        && url.chars().all(|c| c.is_ascii_alphanumeric() || "/:._-%+".contains(c))
}

fn folder() -> PathBuf {
    std::env::temp_dir().join("jarvis-update")
}

const SCRIPT: &str = r#"
param([string]$Url, [string]$Out)
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$req = [System.Net.HttpWebRequest]::Create($Url); $req.UserAgent = 'jarvis-assistant'; $req.Timeout = 30000; $req.ReadWriteTimeout = 30000
$res = $req.GetResponse(); $len = $res.ContentLength; $in = $res.GetResponseStream(); $fs = [IO.File]::Create($Out)
$buf = New-Object byte[] 262144; $got = 0; $last = -1
while (($n = $in.Read($buf, 0, $buf.Length)) -gt 0) {
  $fs.Write($buf, 0, $n); $got += $n
  if ($len -gt 0) { $p = [int](100 * $got / $len); if ($p -ne $last) { $last = $p; [Console]::Out.WriteLine("PROGRESS $p"); [Console]::Out.Flush() } }
}
$fs.Close(); $in.Close(); $res.Close()
[Console]::Out.WriteLine("HASH " + (Get-FileHash -Algorithm SHA256 -LiteralPath $Out).Hash.ToLower())
"#;

#[tauri::command]
pub fn update_download(app: AppHandle, state: State<'_, Updater>, url: String, sha256: String) -> Result<(), String> {
    if !allowed(&url) {
        return Err("Indirizzo di download non attendibile".into());
    }
    {
        let mut busy = state.busy.lock().unwrap();
        if *busy {
            return Err("Download già in corso".into());
        }
        *busy = true;
    }
    *state.ready.lock().unwrap() = None;
    let dir = folder();
    let _ = std::fs::remove_dir_all(&dir); // niente vecchi installer che occupano spazio
    if let Err(e) = std::fs::create_dir_all(&dir) {
        *state.busy.lock().unwrap() = false;
        return Err(format!("Cartella temporanea non disponibile: {e}"));
    }
    let script = dir.join("download.ps1");
    let out = dir.join("JARVIS-update.exe");
    if let Err(e) = std::fs::write(&script, SCRIPT) {
        *state.busy.lock().unwrap() = false;
        return Err(format!("Script non scrivibile: {e}"));
    }
    let want = sha256.to_lowercase();
    std::thread::spawn(move || {
        let mut cmd = Command::new("powershell");
        cmd.args(["-NoProfile", "-ExecutionPolicy", "Bypass", "-File"])
            .arg(&script)
            .arg("-Url")
            .arg(&url)
            .arg("-Out")
            .arg(&out)
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());
        #[cfg(windows)]
        cmd.creation_flags(NO_WINDOW);
        let mut hash = String::new();
        let mut error = String::new();
        match cmd.spawn() {
            Ok(mut child) => {
                if let Some(o) = child.stdout.take() {
                    for line in BufReader::new(o).lines().map_while(Result::ok) {
                        if let Some(p) = line.strip_prefix("PROGRESS ") {
                            let _ = app.emit("update-progress", p.trim().parse::<u32>().unwrap_or(0));
                        } else if let Some(h) = line.strip_prefix("HASH ") {
                            hash = h.trim().to_string();
                        }
                    }
                }
                let ok = child.wait().map(|s| s.success()).unwrap_or(false);
                if !ok || hash.is_empty() {
                    error = "Download non riuscito: controlla la connessione e riprova.".into();
                }
            }
            Err(e) => error = format!("PowerShell non avviabile: {e}"),
        }
        if error.is_empty() && want.len() == 64 && hash != want {
            let _ = std::fs::remove_file(&out);
            error = "Il file scaricato non corrisponde all'impronta SHA-256: non lo installo.".into();
        }
        let st = app.state::<Updater>();
        if error.is_empty() {
            *st.ready.lock().unwrap() = Some(out);
        }
        *st.busy.lock().unwrap() = false;
        let _ = app.emit("update-done", serde_json::json!({ "ok": error.is_empty(), "error": error }));
    });
    Ok(())
}

/// Avvia l'installer scaricato e verificato (la procedura guidata in italiano) e chiude JARVIS: i file in uso si possono così sostituire.
#[tauri::command]
pub fn update_install(app: AppHandle, state: State<'_, Updater>) -> Result<(), String> {
    let path = state.ready.lock().unwrap().clone().ok_or("Nessun aggiornamento scaricato")?;
    if !path.starts_with(folder()) || !path.exists() {
        return Err("Installer non trovato: scaricalo di nuovo".into());
    }
    let mut cmd = Command::new(&path);
    cmd.stdin(Stdio::null()).stdout(Stdio::null()).stderr(Stdio::null());
    cmd.spawn().map_err(|e| format!("Installer non avviabile: {e}"))?;
    crate::exit_all(&app);
    Ok(())
}
