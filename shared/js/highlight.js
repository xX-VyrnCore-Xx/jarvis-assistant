// Evidenziazione della sintassi leggera (nessuna libreria): commenti, stringhe, numeri, parole chiave e chiamate di funzione.
// Una sola passata con un'espressione regolare, valida per i linguaggi più comuni; testo sconosciuto resta com'è.

const KW = new Set(("abstract and as assert async await break case catch class const continue def default defer del delete do elif else enum except export extends false final finally fn for from func function " +
  "go goto if impl implements import in instanceof interface is lambda let match mod mut new nil none not null of or package pass private protected pub public raise return self static struct super switch " +
  "this throw trait true try type typeof undefined use var void while with yield select insert update from where join group order by limit create table alter drop index values set into then end echo fi done").split(" "));

const TOKEN = /(\/\*[\s\S]*?\*\/|\/\/[^\n]*|#[^\n]*|--[^\n]*)|("(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*'|`(?:\\.|[^`\\])*`)|\b(0x[\da-fA-F]+|\d+(?:\.\d+)?)\b|\b([A-Za-z_]\w*)(?=\()|\b([A-Za-z_]\w*)\b/g;
const HASH_OK = /^(python|py|bash|sh|shell|zsh|yaml|yml|toml|ruby|rb|dockerfile|makefile|ini|conf|r|perl|)$/i;
const SLASH_OK = /^(js|javascript|jsx|ts|typescript|tsx|java|c|cpp|cs|csharp|go|rust|rs|kotlin|kt|swift|php|css|scss|json|jsonc|dart|scala|)$/i;
const DASH_OK = /^(sql|lua|haskell|)$/i;

/** @param {HTMLElement} codeEl elemento <code>: se la lingua è nota (data-lang sul <pre>) restringe cosa conta come commento. */
export function highlight(codeEl, lang = "") {
  const src = codeEl.textContent || "";
  if (!src || src.length > 20000 || codeEl.dataset.hl === String(src.length)) return;
  const frag = document.createDocumentFragment();
  let last = 0;
  const span = (cls, text) => { const s = document.createElement("span"); s.className = cls; s.textContent = text; return s; };
  for (const m of src.matchAll(TOKEN)) {
    if (m.index > last) frag.append(src.slice(last, m.index));
    const [txt, com, str, num, fn, word] = m;
    if (com) {
      const ok = com.startsWith("#") ? HASH_OK.test(lang) : com.startsWith("--") ? DASH_OK.test(lang) : SLASH_OK.test(lang) || /^(php|css|scss)$/i.test(lang) || !lang;
      frag.append(ok ? span("tk-c", txt) : txt);
    } else if (str) frag.append(span("tk-s", txt));
    else if (num) frag.append(span("tk-n", txt));
    else if (fn) frag.append(KW.has(fn.toLowerCase()) ? span("tk-k", txt) : span("tk-f", txt));
    else if (word) frag.append(KW.has(word.toLowerCase()) ? span("tk-k", txt) : txt);
    else frag.append(txt);
    last = m.index + txt.length;
  }
  if (last < src.length) frag.append(src.slice(last));
  codeEl.replaceChildren(frag);
  codeEl.dataset.hl = String(src.length);
}
