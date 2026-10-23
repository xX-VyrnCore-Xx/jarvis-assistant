// Telefono e WhatsApp (solo Android): chiamare, cercare nei contatti, risposta automatica ai numeri autorizzati.
// Il lavoro è nel plugin nativo JarvisPhone (mobile/native/android). Nel browser di prova e su altre piattaforme non c'è nulla.
import { registerPlugin } from "@capacitor/core";
import { isNative, platform } from "./native.js";

const Phone = isNative && platform === "android" ? registerPlugin("JarvisPhone") : null;
export const phoneAvailable = !!Phone;

export const NUMBER_RE = /^[+0-9 ()./-]{3,24}$/;
export const phone = {
  status: () => Phone.status(),
  requestPermissions: () => Phone.requestPermissions(),
  dial: (number) => Phone.dial({ number }),
  whatsapp: ({ number = "", name = "", video = false }) => Phone.whatsapp({ number, name, video }),
  findContacts: async (query) => (await Phone.findContacts({ query })).contacts || [],
  setAuto: (cfg) => Phone.setAuto(cfg),
  log: async (clear = false) => (await Phone.log({ clear })).log || [],
};
