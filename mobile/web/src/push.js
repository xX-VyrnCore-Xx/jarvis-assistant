// Notifiche push (Firebase) per Android: arrivano anche con l'app chiusa.
// Si attivano solo se l'APK è stato compilato con google-services.json (VITE_PUSH=1); altrimenti restano le notifiche in-app.
import { Capacitor } from "@capacitor/core";
import { PushNotifications } from "@capacitor/push-notifications";

const KEY = "jarvis.fcm";
let wired = false;

const CHANNELS = [
  { id: "alerts", name: "Avvisi importanti", description: "Conferme richieste, token in esaurimento", importance: 5 },
  { id: "reminders", name: "Promemoria", description: "Promemoria all'ora giusta", importance: 5 },
  { id: "updates", name: "Aggiornamenti", description: "Nuove versioni di JARVIS", importance: 3 },
  { id: "general", name: "Generale", description: "Secondo cervello e informazioni", importance: 3 },
];

/** `onOpen(route)` viene chiamato quando si tocca una notifica: apre la sezione giusta. */
export async function initPush(api, onOpen = () => {}) {
  if (import.meta.env.VITE_PUSH !== "1" || Capacitor.getPlatform() !== "android") return;
  let perm = await PushNotifications.checkPermissions();
  if (perm.receive === "prompt" || perm.receive === "prompt-with-rationale") perm = await PushNotifications.requestPermissions();
  if (perm.receive !== "granted") return;
  if (!wired) {
    wired = true;
    for (const c of CHANNELS) await PushNotifications.createChannel({ ...c, visibility: 1, vibration: true }).catch(() => {});
    await PushNotifications.addListener("pushNotificationActionPerformed", (a) => onOpen(a.notification?.data?.route || ""));
    await PushNotifications.addListener("registration", (t) => {
      try { localStorage.setItem(KEY, t.value); } catch { /* memoria non disponibile */ }
      api.registerDevice("android", t.value, "Telefono").catch(() => {});
    });
    await PushNotifications.addListener("registrationError", () => {});
  }
  await PushNotifications.register();
}

export async function teardownPush(api) {
  let token = "";
  try { token = localStorage.getItem(KEY) || ""; localStorage.removeItem(KEY); } catch { /* ignora */ }
  const done = token ? api.unregisterDevice(token).catch(() => {}) : Promise.resolve();
  await done;
  if (import.meta.env.VITE_PUSH === "1" && Capacitor.getPlatform() === "android") await PushNotifications.unregister().catch(() => {});
}
