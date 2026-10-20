// Rigenera le icone (Android: mobile/assets, PC: desktop/src-tauri/app-icon.png) da due SVG.
// Uso: node mobile/scripts/gen-icons.mjs   (serve Playwright con Chromium; poi `npx tauri icon` nella cartella desktop)
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import path from "node:path";
const require = createRequire(process.env.PW_MODULES || "/opt/node22/lib/node_modules/");
const { chromium } = require("playwright");
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");

/** Reattore: anello esterno a segmenti, anello pieno, arco interno e nucleo luminoso. */
const reactor = (c1, c2, hot, scale, cx, cy, ticks = false) => `
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${c1}"/><stop offset="1" stop-color="${c2}"/></linearGradient>
    <radialGradient id="core"><stop offset="0" stop-color="${hot}"/><stop offset=".45" stop-color="${c1}"/><stop offset="1" stop-color="${c2}"/></radialGradient>
    <filter id="b" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="26"/></filter>
  </defs>
  <g transform="translate(${cx} ${cy}) scale(${scale})">
    <circle r="130" fill="${c2}" opacity=".55" filter="url(#b)"/>
    <g fill="none" stroke="url(#g)" stroke-linecap="round">
      <circle r="410" stroke-width="36" stroke-dasharray="560 142" transform="rotate(-70)"/>
      <circle r="300" stroke-width="22" opacity=".9"/>
      <circle r="205" stroke-width="30" stroke-dasharray="720 567" transform="rotate(130)"/>
      ${ticks ? Array.from({ length: 36 }, (_, i) => `<line stroke="${c1}" x1="0" y1="-352" x2="0" y2="${i % 3 ? -336 : -326}" stroke-width="${i % 3 ? 5 : 8}" opacity=".7" transform="rotate(${i * 10})"/>`).join("") : ""}
    </g>
    <circle r="86" fill="url(#core)"/>
    <circle r="86" fill="none" stroke="${hot}" stroke-opacity=".5" stroke-width="3"/>
    <circle cx="-26" cy="-28" r="20" fill="#fff" opacity=".55"/>
  </g>`;
const wrap = (size, body, bg = "") => `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">${bg}${body}</svg>`;
const bgAmber = (s) => `<defs><radialGradient id="r" cx=".82" cy=".05" r=".95"><stop offset="0" stop-color="#4a2540"/><stop offset=".55" stop-color="#17121f"/><stop offset="1" stop-color="#0b0911"/></radialGradient></defs><rect width="${s}" height="${s}" fill="url(#r)"/>`;
const bgCyan = (s) => `<defs><radialGradient id="r" cx=".5" cy=".45" r=".75"><stop offset="0" stop-color="#0f2638"/><stop offset="1" stop-color="#050c14"/></radialGradient></defs><rect width="${s}" height="${s}" rx="${s * 0.22}" fill="url(#r)"/>`;
const A = ["#ffc15e", "#ff6a4a", "#fff3d6"], C = ["#4fe3ff", "#1d8bff", "#e6fbff"];

const jobs = [
  [path.join(root, "mobile/assets/icon-only.png"), 1024, wrap(1024, reactor(...A, 0.95, 512, 512), bgAmber(1024)), false],
  [path.join(root, "mobile/assets/icon-foreground.png"), 1024, wrap(1024, reactor(...A, 0.64, 512, 512)), true],
  [path.join(root, "mobile/assets/icon-background.png"), 1024, wrap(1024, "", bgAmber(1024)), false],
  [path.join(root, "mobile/assets/splash.png"), 2732, wrap(2732, reactor(...A, 0.34, 1366, 1366), bgAmber(2732)), false],
  [path.join(root, "mobile/assets/splash-dark.png"), 2732, wrap(2732, reactor(...A, 0.34, 1366, 1366), bgAmber(2732)), false],
  [path.join(root, "desktop/src-tauri/app-icon.png"), 1024, wrap(1024, reactor(...C, 0.9, 512, 512, true), bgCyan(1024)), true],
];
const b = await chromium.launch();
for (const [file, size, markup, transparent] of jobs) {
  const p = await b.newPage({ viewport: { width: size, height: size } });
  await p.setContent(`<body style="margin:0;background:transparent">${markup}</body>`);
  await p.screenshot({ path: file, omitBackground: transparent });
  await p.close();
}
await b.close();
