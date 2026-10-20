// Funzioni del telefono (vibrazione, barra di stato, tasto Indietro, dettatura). Nel browser di prova non fanno nulla.
import { App } from "@capacitor/app";
import { Capacitor } from "@capacitor/core";
import { Haptics, ImpactStyle } from "@capacitor/haptics";
import { SplashScreen } from "@capacitor/splash-screen";
import { StatusBar, Style } from "@capacitor/status-bar";
import { SpeechRecognition } from "@capacitor-community/speech-recognition";

export const isNative = Capacitor.isNativePlatform();

export function haptic(kind = "light") {
  if (!isNative) return;
  Haptics.impact({ style: kind === "heavy" ? ImpactStyle.Heavy : kind === "medium" ? ImpactStyle.Medium : ImpactStyle.Light }).catch(() => {});
}

/** Colora la barra di stato come il tema e toglie la schermata di avvio. */
export function paintSystemBars(dark, bg) {
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", bg);
  if (!isNative) return;
  StatusBar.setStyle({ style: dark ? Style.Dark : Style.Light }).catch(() => {});
  StatusBar.setBackgroundColor({ color: bg }).catch(() => {});
}

export function hideSplash() {
  if (isNative) SplashScreen.hide({ fadeOutDuration: 250 }).catch(() => {});
}

/** `handler()` deve restituire true se ha gestito il tasto Indietro; altrimenti l'app va in secondo piano. */
export function onBack(handler) {
  if (!isNative) return;
  App.addListener("backButton", () => {
    if (!handler()) App.minimizeApp().catch(() => {});
  });
}

export async function dictationAvailable() {
  if (!isNative) return false;
  try { return (await SpeechRecognition.available()).available; } catch { return false; }
}

export async function startDictation(onText, onEnd) {
  const perm = await SpeechRecognition.requestPermissions();
  if (perm.speechRecognition !== "granted") throw new Error("Permesso del microfono negato");
  await SpeechRecognition.removeAllListeners();
  await SpeechRecognition.addListener("partialResults", (d) => onText((d.matches && d.matches[0]) || ""));
  await SpeechRecognition.addListener("listeningState", (s) => { if (s.status === "stopped") onEnd(); });
  await SpeechRecognition.start({ language: "it-IT", partialResults: true, popup: false, maxResults: 1 });
}

export function stopDictation() {
  return SpeechRecognition.stop().catch(() => {});
}

/** Versione installata dell'app (nel browser di prova: nessuna). */
export async function appVersion() {
  if (!isNative) return "";
  try { return (await App.getInfo()).version; } catch { return ""; }
}

/** Apre un indirizzo fuori dall'app (per l'APK: lo scarica il browser, poi Android propone l'installazione). */
export async function openExternal(url) {
  if (isNative) {
    try { await App.openUrl({ url }); return; } catch { /* ripiego sotto */ }
  }
  window.open(url, "_blank", "noopener");
}

export const platform = Capacitor.getPlatform();
