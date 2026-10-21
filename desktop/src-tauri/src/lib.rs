mod actions;
mod paths;
mod voice;

use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Manager, WindowEvent};
use tauri_plugin_autostart::{MacosLauncher, ManagerExt as _};
use tauri_plugin_global_shortcut::{Code, GlobalShortcutExt, Modifiers, Shortcut, ShortcutState};
use tauri_plugin_notification::NotificationExt;

fn show(app: &AppHandle) {
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.show();
        let _ = w.unminimize();
        let _ = w.set_focus();
    }
}

fn toggle(app: &AppHandle) {
    if let Some(w) = app.get_webview_window("main") {
        if w.is_visible().unwrap_or(false) && w.is_focused().unwrap_or(false) {
            let _ = w.hide();
        } else {
            show(app);
        }
    }
}

/// Uscita definitiva: chiude voce e installazione (con i loro processi figli), toglie l'icona dalla barra, distrugge la finestra e termina il processo.
/// Se l'uscita normale restasse appesa (WebView, thread), dopo 3 secondi il processo viene terminato comunque.
fn exit_all(app: &AppHandle) {
    voice::stop_all(&app.state::<voice::Voice>());
    let _ = app.remove_tray_by_id("main");
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.destroy();
    }
    std::thread::spawn(|| {
        std::thread::sleep(std::time::Duration::from_secs(3));
        std::process::exit(0);
    });
    app.exit(0);
}

#[tauri::command]
fn quit_app(app: AppHandle) {
    exit_all(&app);
}

#[tauri::command]
fn run_action(app: AppHandle, action: String, args: serde_json::Value) -> Result<String, String> {
    actions::run(&app, &action, &args)
}

#[tauri::command]
fn notify(app: AppHandle, title: String, body: String) {
    let _ = app.notification().builder().title(title).body(body).show();
}

#[tauri::command]
fn show_window(app: AppHandle) {
    show(&app);
}

// Il token personale sta nel Gestore credenziali di Windows, non in un file in chiaro.
fn secret_entry() -> Result<keyring::Entry, String> {
    keyring::Entry::new("JARVIS", "api-token").map_err(|e| e.to_string())
}

#[tauri::command]
fn secret_get() -> Result<Option<String>, String> {
    match secret_entry()?.get_password() {
        Ok(v) => Ok(Some(v)),
        Err(keyring::Error::NoEntry) => Ok(None),
        Err(e) => Err(e.to_string()),
    }
}

#[tauri::command]
fn secret_set(value: String) -> Result<(), String> {
    secret_entry()?.set_password(&value).map_err(|e| e.to_string())
}

#[tauri::command]
fn secret_delete() -> Result<(), String> {
    match secret_entry()?.delete_credential() {
        Ok(()) | Err(keyring::Error::NoEntry) => Ok(()),
        Err(e) => Err(e.to_string()),
    }
}

#[tauri::command]
fn autostart_get(app: AppHandle) -> Result<bool, String> {
    app.autolaunch().is_enabled().map_err(|e| e.to_string())
}

#[tauri::command]
fn autostart_set(app: AppHandle, enabled: bool) -> Result<(), String> {
    let launcher = app.autolaunch();
    let result = if enabled { launcher.enable() } else { launcher.disable() };
    result.map_err(|e| e.to_string())
}

pub fn run() {
    tauri::Builder::default()
        // una sola copia di JARVIS: aprire di nuovo il programma (o l'avvio con Windows) riporta davanti quella già attiva,
        // invece di lasciare due processi di cui «Esci» ne chiuderebbe uno solo
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| show(app)))
        .manage(voice::Voice::default())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_autostart::init(MacosLauncher::LaunchAgent, Some(vec!["--hidden"])))
        .plugin(
            tauri_plugin_global_shortcut::Builder::new()
                .with_handler(|app, _shortcut, event| {
                    if event.state() == ShortcutState::Pressed {
                        toggle(app);
                    }
                })
                .build(),
        )
        .setup(|app| {
            // Alt+Spazio mostra/nasconde JARVIS ovunque
            app.global_shortcut().register(Shortcut::new(Some(Modifiers::ALT), Code::Space))?;

            let open = MenuItem::with_id(app, "open", "Apri JARVIS", true, None::<&str>)?;
            let quit = MenuItem::with_id(app, "quit", "Esci definitivamente", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&open, &quit])?;
            TrayIconBuilder::with_id("main")
                .icon(app.default_window_icon().unwrap().clone())
                .tooltip("JARVIS")
                .menu(&menu)
                .show_menu_on_left_click(false)
                .on_menu_event(|app, ev| match ev.id.as_ref() {
                    "open" => show(app),
                    "quit" => exit_all(app),
                    _ => {}
                })
                .on_tray_icon_event(|tray, ev| {
                    if let TrayIconEvent::Click { button: MouseButton::Left, button_state: MouseButtonState::Up, .. } = ev {
                        toggle(tray.app_handle());
                    }
                })
                .build(app)?;

            // all'avvio automatico con Windows resta nella tray
            if !std::env::args().any(|a| a == "--hidden") {
                show(app.handle());
            }
            Ok(())
        })
        .on_window_event(|window, event| {
            // la X nasconde la finestra: JARVIS resta attivo nella tray
            if let WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                let _ = window.hide();
            }
        })
        .invoke_handler(tauri::generate_handler![run_action, notify, show_window, quit_app, secret_get, secret_set, secret_delete, autostart_get, autostart_set,
            voice::voice_status, voice::voice_install, voice::voice_start, voice::voice_stop, voice::voice_uninstall])
        .build(tauri::generate_context!())
        .expect("errore nell'avvio di JARVIS")
        .run(|app, event| {
            // qualunque uscita (anche da Windows) chiude la voce: nessun processo Python rimane in giro
            if let tauri::RunEvent::Exit = event {
                voice::stop_all(&app.state::<voice::Voice>());
            }
        });
}
