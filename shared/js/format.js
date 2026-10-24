// Utilità di visualizzazione condivise. Nessun innerHTML: il testo arriva da un modello e da pagine esterne.

export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === false || v == null) continue;
    if (k === "class") node.className = v;
    else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
    else if (k === "dataset") Object.assign(node.dataset, v);
    else node.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return node;
}

export function fmtTokens(n) {
  if (n == null) return "n/d";
  n = Number(n);
  if (n >= 1e9) return `${(n / 1e9).toFixed(1)} G`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)} M`;
  if (n >= 1e3) return `${Math.round(n / 1e3)} k`;
  return String(Math.round(n));
}

export function fmtDate(iso) {
  const d = new Date(iso);
  if (isNaN(d)) return String(iso);
  return d.toLocaleString("it-IT", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

export function fmtUptime(s) {
  if (s < 3600) return `${Math.floor(s / 60)} min`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ${Math.floor((s % 3600) / 60)} min`;
  return `${Math.floor(s / 86400)} g ${Math.floor((s % 86400) / 3600)} h`;
}

/** Percentuale di token rimasti, limitata a 0-100. */
export function pct(remaining, total) {
  if (!total) return 0;
  return Math.max(0, Math.min(100, (remaining / total) * 100));
}

export function nowLocalInput(plusMinutes = 0) {
  const d = new Date(Date.now() + plusMinutes * 60_000);
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
}

// ---- testo con un po' di formattazione (grassetto, corsivo, codice, elenchi, link http/https)
const INLINE = /(`[^`\n]+`)|(\*\*[^*\n]+\*\*)|(\*[^*\n]+\*)|(\[[^\]\n]+\]\(https?:\/\/[^\s)]+\))|(https?:\/\/[^\s<>()]+)/g;

function link(href, label) {
  return el("a", { href, target: "_blank", rel: "noopener noreferrer" }, label);
}

function inline(text) {
  const out = [];
  let last = 0;
  for (const m of text.matchAll(INLINE)) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const t = m[0];
    if (m[1]) out.push(el("code", {}, t.slice(1, -1)));
    else if (m[2]) out.push(el("strong", {}, t.slice(2, -2)));
    else if (m[3]) out.push(el("em", {}, t.slice(1, -1)));
    else if (m[4]) { const i = t.indexOf("]("); out.push(link(t.slice(i + 2, -1), t.slice(1, i))); }
    else out.push(link(t, t));
    last = m.index + t.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

export function markdown(text) {
  const root = el("div", { class: "md" });
  const lines = String(text).replace(/\r/g, "").split("\n");
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (line.startsWith("```")) {
      const lang = line.slice(3).trim().split(/\s/)[0].toLowerCase().replace(/[^a-z0-9+#-]/g, "");
      const code = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) code.push(lines[i++]);
      i++;
      root.append(el("pre", lang ? { "data-lang": lang } : {}, el("code", {}, code.join("\n"))));
    } else if (/^\s*([-*•]|\d+[.)])\s+/.test(line)) {
      const ordered = /^\s*\d+[.)]/.test(line);
      const list = el(ordered ? "ol" : "ul");
      while (i < lines.length && /^\s*([-*•]|\d+[.)])\s+/.test(lines[i])) {
        list.append(el("li", {}, inline(lines[i].replace(/^\s*([-*•]|\d+[.)])\s+/, ""))));
        i++;
      }
      root.append(list);
    } else if (line.trim() === "") {
      i++;
    } else {
      const para = [];
      while (i < lines.length && lines[i].trim() !== "" && !lines[i].startsWith("```") && !/^\s*([-*•]|\d+[.)])\s+/.test(lines[i])) para.push(lines[i++]);
      const p = el("p");
      para.forEach((l, k) => { if (k) p.append(el("br")); p.append(...inline(l)); });
      root.append(p);
    }
  }
  return root;
}
