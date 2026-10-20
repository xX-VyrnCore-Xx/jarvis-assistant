//! Voce di JARVIS (XTTS v2) in locale: installazione guidata e processo Python figlio, chiuso insieme all'app.
use serde::Serialize;
use std::io::{BufRead, BufReader};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use tauri::{AppHandle, Emitter, Manager, State};

#[cfg(windows)]
use std::os::windows::process::CommandExt;
#[cfg(windows)]
const NO_WINDOW: u32 = 0x0800_0000; // CREATE_NO_WINDOW: nessuna finestra nera

#[derive(Default)]
pub struct Voice {
    child: Mutex<Option<Child>>,
    run: Mutex<Option<(u16, String)>>,
    installing: Mutex<bool>,
}

#[derive(Serialize)]
pub struct VoiceStatus {
    installed: bool,
    installing: bool,
    running: bool,
    port: u16,
    token: String,
}

fn dir(app: &AppHandle) -> Result<PathBuf, String> {
    let base = app.path().local_data_dir().map_err(|e| e.to_string())?;
    Ok(base.join("JARVIS").join("voice"))
}

fn resource(app: &AppHandle, name: &str) -> Result<PathBuf, String> {
    app.path().resource_dir().map(|d| d.join("resources").join(name)).map_err(|e| e.to_string())
}

fn hidden(cmd: &mut Command) -> &mut Command {
    #[cfg(windows)]
    cmd.creation_flags(NO_WINDOW);
    cmd
}

fn random_token() -> String {
    use std::collections::hash_map::RandomState;
    use std::hash::{BuildHasher, Hasher};
    (0..4).map(|_| format!("{:016x}", RandomState::new().build_hasher().finish())).collect()
}

fn free_port() -> Result<u16, String> {
    let l = std::net::TcpListener::bind("127.0.0.1:0").map_err(|e| e.to_string())?;
    l.local_addr().map(|a| a.port()).map_err(|e| e.to_string())
}

pub fn stop(state: &Voice) {
    if let Some(mut child) = state.child.lock().unwrap().take() {
        let _ = child.kill();
        let _ = child.wait();
    }
    *state.run.lock().unwrap() = None;
}

#[tauri::command]
pub fn voice_status(app: AppHandle, state: State<'_, Voice>) -> Result<VoiceStatus, String> {
    let installed = dir(&app)?.join("ready").exists();
    // se il processo è morto da solo, lo segnala come non attivo
    let mut child = state.child.lock().unwrap();
    if let Some(c) = child.as_mut() {
        if matches!(c.try_wait(), Ok(Some(_))) {
            *child = None;
            *state.run.lock().unwrap() = None;
        }
    }
    let run = state.run.lock().unwrap().clone();
    Ok(VoiceStatus {
        installed,
        installing: *state.installing.lock().unwrap(),
        running: run.is_some(),
        port: run.as_ref().map(|r| r.0).unwrap_or(0),
        token: run.map(|r| r.1).unwrap_or_default(),
    })
}

#[tauri::command]
pub fn voice_install(app: AppHandle, state: State<'_, Voice>) -> Result<(), String> {
    {
        let mut busy = state.installing.lock().unwrap();
        if *busy {
            return Err("Installazione già in corso".into());
        }
        *busy = true;
    }
    let script = resource(&app, "install_voice.ps1")?;
    let target = dir(&app)?;
    std::thread::spawn(move || {
        let mut cmd = Command::new("powershell");
        cmd.args(["-NoProfile", "-ExecutionPolicy", "Bypass", "-File"])
            .arg(&script)
            .arg("-Dir")
            .arg(&target)
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());
        let ok = match hidden(&mut cmd).spawn() {
            Ok(mut child) => {
                let err = child.stderr.take();
                let app2 = app.clone();
                let t = std::thread::spawn(move || {
                    if let Some(e) = err {
                        for line in BufReader::new(e).lines().map_while(Result::ok) {
                            let _ = app2.emit("voice-progress", line);
                        }
                    }
                });
                if let Some(out) = child.stdout.take() {
                    for line in BufReader::new(out).lines().map_while(Result::ok) {
                        let _ = app.emit("voice-progress", line);
                    }
                }
                let _ = t.join();
                child.wait().map(|s| s.success()).unwrap_or(false)
            }
            Err(e) => {
                let _ = app.emit("voice-progress", format!("PowerShell non avviabile: {e}"));
                false
            }
        };
        *app.state::<Voice>().installing.lock().unwrap() = false;
        let _ = app.emit("voice-done", ok);
    });
    Ok(())
}

#[tauri::command]
pub fn voice_start(app: AppHandle, state: State<'_, Voice>) -> Result<(u16, String), String> {
    if let Some(r) = state.run.lock().unwrap().clone() {
        return Ok(r);
    }
    let root = dir(&app)?;
    if !root.join("ready").exists() {
        return Err("La voce non è installata".into());
    }
    let (port, token) = (free_port()?, random_token());
    let mut cmd = Command::new(root.join("python").join("python.exe"));
    cmd.arg(resource(&app, "tts_server.py")?)
        .args(["--port", &port.to_string(), "--voice"])
        .arg(resource(&app, "jarvis.wav")?)
        .env("JARVIS_TTS_TOKEN", &token)
        .env("COQUI_TOS_AGREED", "1")
        .env("TTS_HOME", root.join("models"))
        .env("PYTHONIOENCODING", "utf-8")
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    let child = hidden(&mut cmd).spawn().map_err(|e| format!("Avvio della voce non riuscito: {e}"))?;
    *state.child.lock().unwrap() = Some(child);
    *state.run.lock().unwrap() = Some((port, token.clone()));
    Ok((port, token))
}

#[tauri::command]
pub fn voice_stop(state: State<'_, Voice>) {
    stop(&state);
}

#[tauri::command]
pub fn voice_uninstall(app: AppHandle, state: State<'_, Voice>) -> Result<(), String> {
    stop(&state);
    let d = dir(&app)?;
    if d.exists() {
        std::fs::remove_dir_all(d).map_err(|e| e.to_string())?;
    }
    Ok(())
}
