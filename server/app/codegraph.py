"""Mappa del codice a grafo (idea di Graphify: interrogare la struttura invece di rileggere i file).

Per ogni file della sandbox si estraggono simboli (classi, funzioni, metodi con riga e firma) e collegamenti (importa, chiama, eredita).
Python si analizza con `ast` (preciso); gli altri linguaggi con espressioni regolari (approssimato ma economico). Nessun codice viene eseguito.
Rispondere a «dove sta X, chi lo usa, da cosa dipende» costa poche centinaia di token invece di decine di migliaia."""
import ast
import re
from collections import defaultdict, deque
from dataclasses import dataclass, field

LANG = {".py": "py", ".js": "js", ".jsx": "js", ".mjs": "js", ".ts": "js", ".tsx": "js", ".java": "jvm", ".kt": "jvm", ".cs": "jvm", ".go": "go", ".rs": "rs",
        ".php": "php", ".rb": "rb", ".c": "c", ".h": "c", ".cpp": "c", ".hpp": "c", ".swift": "jvm"}
DEFS = {
    "js": [(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\*?\s+(\w+)\s*\(([^)]*)", "function"), (r"^\s*(?:export\s+)?(?:abstract\s+)?class\s+(\w+)", "class"),
           (r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*(?::[^=]+)?=\s*(?:async\s*)?(?:\(([^)]*)\)|\w+)\s*(?::[^=]+)?=>", "function"), (r"^\s*(?:export\s+)?interface\s+(\w+)", "class")],
    "jvm": [(r"^\s*(?:public|private|protected|internal|static|final|abstract|open|data|sealed|\s)*\b(?:class|interface|object|enum|struct|record)\s+(\w+)", "class"),
            (r"^\s*(?:public|private|protected|internal|static|final|override|suspend|open|async|\s)*(?:fun|func)\s+(\w+)\s*\(([^)]*)", "function"),
            (r"^\s*(?:public|private|protected|internal|static|final|abstract|\s)+[\w<>\[\],.? ]+\s+(\w+)\s*\(([^)]*)\)\s*(?:throws [\w, .]+)?\s*[{;]", "function")],
    "go": [(r"^func\s+(?:\([^)]*\)\s*)?(\w+)\s*\(([^)]*)", "function"), (r"^type\s+(\w+)\s+(?:struct|interface)", "class")],
    "rs": [(r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?fn\s+(\w+)\s*(?:<[^>]*>)?\s*\(([^)]*)", "function"), (r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:struct|enum|trait)\s+(\w+)", "class")],
    "php": [(r"^\s*(?:public|private|protected|static|\s)*function\s+(\w+)\s*\(([^)]*)", "function"), (r"^\s*(?:abstract\s+|final\s+)?(?:class|interface|trait)\s+(\w+)", "class")],
    "rb": [(r"^\s*def\s+(?:self\.)?(\w+[?!]?)\s*\(?([^)\n]*)", "function"), (r"^\s*(?:class|module)\s+(\w+)", "class")],
    "c": [(r"^[\w:<>*&\s]+?\b(\w+)\s*\(([^;)]*)\)\s*(?:const)?\s*\{", "function"), (r"^\s*(?:class|struct)\s+(\w+)", "class")],
}
IMPORTS = {
    "js": re.compile(r"""(?:import\s+(?:[^'";]+?\s+from\s+)?|require\(\s*|import\(\s*)['"]([^'"]+)['"]"""),
    "jvm": re.compile(r"^\s*(?:import|using)\s+(?:static\s+)?([\w.]+)", re.M), "go": re.compile(r'^\s*(?:import\s+)?"([\w./-]+)"', re.M),
    "rs": re.compile(r"^\s*(?:pub\s+)?(?:use|mod)\s+([\w:]+)", re.M), "php": re.compile(r"^\s*(?:use|require_once|require|include)\s+['\"]?([\w\\/.-]+)", re.M),
    "rb": re.compile(r"^\s*require(?:_relative)?\s+['\"]([^'\"]+)", re.M), "c": re.compile(r'^\s*#\s*include\s+"([^"]+)"', re.M),
}
CALL = re.compile(r"\b([A-Za-z_]\w*)\s*\(")
STOP = {"if", "for", "while", "switch", "catch", "return", "function", "def", "fn", "func", "print", "len", "str", "int", "list", "dict", "set", "range", "isinstance", "super", "self", "this",
        "new", "await", "async", "typeof", "sizeof", "Some", "Ok", "Err", "println", "console", "log", "require", "import", "from", "with", "assert", "raise", "throw", "else", "elif"}
ENTRY = re.compile(r"(^|/)(main|app|index|server|cli|manage|__main__|lib|mod|program)\.\w+$|(^|/)(main|index)\.", re.I)


@dataclass
class Node:
    id: str
    kind: str  # file | class | function
    name: str
    file: str
    line: int = 0
    sig: str = ""
    doc: str = ""
    parent: str = ""  # classe che lo contiene


@dataclass
class CodeGraph:
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: list[tuple[str, str, str]] = field(default_factory=list)  # (da, a, tipo): imports | calls | extends
    skipped: int = 0

    # ------------------------------------------------------------------ costruzione
    @classmethod
    def build(cls, files: dict[str, bytes]) -> "CodeGraph":
        g = cls()
        texts = {}
        for path, raw in files.items():
            ext = "." + path.rsplit(".", 1)[-1].lower() if "." in path.rsplit("/", 1)[-1] else ""
            if ext not in LANG:
                continue
            texts[path] = (LANG[ext], raw.decode("utf-8", errors="ignore"))
            g.nodes[f"f:{path}"] = Node(f"f:{path}", "file", path.rsplit("/", 1)[-1], path)
        bodies: dict[str, set[str]] = {}
        raw_imports: dict[str, list[str]] = {}
        for path, (lang, text) in texts.items():
            try:
                (g._python if lang == "py" else g._generic)(path, text, bodies, raw_imports, lang)
            except (SyntaxError, ValueError, RecursionError):
                g.skipped += 1
        g._resolve(texts, bodies, raw_imports)
        return g

    def _add(self, path: str, kind: str, name: str, line: int, sig: str = "", doc: str = "", parent: str = "") -> Node:
        nid = f"s:{path}:{(parent + '.' if parent else '') + name}:{line}"
        n = self.nodes[nid] = Node(nid, kind, name, path, line, sig[:110], doc[:100], parent)
        self.edges.append((f"f:{path}", nid, "contains"))
        return n

    def _python(self, path, text, bodies, raw_imports, lang):
        tree = ast.parse(text)
        imps = raw_imports.setdefault(path, [])
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imps += [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                imps.append("." * node.level + (node.module or "") if node.level else (node.module or ""))
                imps += [("." * node.level + (node.module or "") + "." + a.name).lstrip(".") if not node.level else "." * node.level + (node.module or "") + "." + a.name for a in node.names]

        def calls(fn) -> set[str]:
            out = set()
            for n in ast.walk(fn):
                if isinstance(n, ast.Call):
                    f = n.func
                    nm = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""
                    if nm and nm not in STOP:
                        out.add(nm)
            return out

        def sig(fn) -> str:
            a = fn.args
            names = [x.arg for x in (*a.posonlyargs, *a.args)] + (["*" + a.vararg.arg] if a.vararg else []) + [x.arg for x in a.kwonlyargs] + (["**" + a.kwarg.arg] if a.kwarg else [])
            return "(" + ", ".join(n for n in names if n not in ("self", "cls")) + ")"

        def visit(body, parent=""):
            for n in body:
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    node = self._add(path, "function", n.name, n.lineno, ("async " if isinstance(n, ast.AsyncFunctionDef) else "") + sig(n), (ast.get_docstring(n) or "").split("\n")[0], parent)
                    bodies[node.id] = calls(n)
                elif isinstance(n, ast.ClassDef):
                    node = self._add(path, "class", n.name, n.lineno, "(" + ", ".join(ast.unparse(b) for b in n.bases)[:80] + ")" if n.bases else "", (ast.get_docstring(n) or "").split("\n")[0], parent)
                    for b in n.bases:
                        bodies.setdefault(node.id, set())
                        self.edges.append((node.id, "?" + (b.id if isinstance(b, ast.Name) else b.attr if isinstance(b, ast.Attribute) else ""), "extends"))
                    visit(n.body, n.name)
        visit(tree.body)

    def _generic(self, path, text, bodies, raw_imports, lang):
        raw_imports[path] = IMPORTS.get(lang, re.compile(r"$^")).findall(text)
        lines = text.splitlines()
        found: list[Node] = []
        for pat, kind in DEFS.get(lang, []):
            rx = re.compile(pat)
            for i, line in enumerate(lines, 1):
                m = rx.match(line)
                if m and m.group(1) not in STOP and len(found) < 400:
                    sig = "(" + " ".join((m.group(2) or "").split())[:80] + ")" if kind == "function" and m.lastindex and m.lastindex >= 2 else ""
                    found.append(self._add(path, kind, m.group(1), i, sig))
        found.sort(key=lambda n: n.line)
        for k, n in enumerate(found):  # il corpo arriva fino alla definizione successiva
            end = found[k + 1].line - 1 if k + 1 < len(found) else len(lines)
            bodies[n.id] = {c for c in CALL.findall("\n".join(lines[n.line:end])) if c not in STOP and c != n.name}

    # ------------------------------------------------------------------ risoluzione dei collegamenti
    def _resolve(self, texts, bodies, raw_imports):
        by_name: dict[str, list[Node]] = defaultdict(list)
        for n in self.nodes.values():
            if n.kind != "file":
                by_name[n.name].append(n)
        paths = set(texts)
        stems = defaultdict(list)
        for p in paths:
            stems[p.rsplit(".", 1)[0]].append(p)
        resolved = []
        for src, dst, kind in self.edges:
            if dst.startswith("?"):
                cands = by_name.get(dst[1:], [])
                if len(cands) == 1:
                    resolved.append((src, cands[0].id, kind))
            else:
                resolved.append((src, dst, kind))
        for sid, names in bodies.items():
            me = self.nodes.get(sid)
            for nm in names:
                cands = [c for c in by_name.get(nm, []) if c.id != sid]
                same = [c for c in cands if me and c.file == me.file]
                use = same or cands
                if 0 < len(use) <= 3:
                    resolved += [(sid, c.id, "calls") for c in use]
        for path, mods in raw_imports.items():
            for mod in mods:
                tgt = self._module_file(path, mod, paths, stems)
                if tgt and tgt != path:
                    resolved.append((f"f:{path}", f"f:{tgt}", "imports"))
        seen, out = set(), []
        for e in resolved:
            if e not in seen and e[0] in self.nodes and e[1] in self.nodes:
                seen.add(e)
                out.append(e)
        self.edges = out

    @staticmethod
    def _module_file(path: str, mod: str, paths: set[str], stems) -> str | None:
        if not mod:
            return None
        base = path.rsplit("/", 1)[0] if "/" in path else ""
        if mod.startswith("."):  # relativo: Python (.pkg.mod) o JS (./x, ../y)
            if "/" in mod:
                import posixpath
                cand = posixpath.normpath(posixpath.join(base, mod))
            else:
                up = len(mod) - len(mod.lstrip("."))
                parts = [p for p in base.split("/") if p][: max(0, len([p for p in base.split("/") if p]) - (up - 1))]
                cand = "/".join(parts + [p for p in mod.lstrip(".").split(".") if p])
        else:
            cand = mod if "/" in mod or ("." + mod.rsplit(".", 1)[-1]) in LANG else mod.replace(".", "/")
        dotted = "/" not in mod
        parts = cand.split("/")
        for k in range(len(parts), 0, -1) if dotted else [len(parts)]:  # «app.util.helper» → app/util/helper, poi app/util…
            c = "/".join(parts[:k])
            for x in (c, c + "/index", c + "/__init__"):
                if x in stems:
                    return stems[x][0]
                if x in paths:
                    return x
        tail = cand.split("/")[-1]
        hits = [p for p in paths if p.rsplit(".", 1)[0].endswith("/" + cand) or p.rsplit(".", 1)[0] == cand]
        return hits[0] if len(hits) == 1 else (stems[tail][0] if len(stems.get(tail, [])) == 1 and "/" not in cand else None)

    # ------------------------------------------------------------------ interrogazione
    def _adj(self):
        out, inn = defaultdict(list), defaultdict(list)
        for a, b, k in self.edges:
            if k != "contains":
                out[a].append((b, k))
                inn[b].append((a, k))
        return out, inn

    def _label(self, nid: str) -> str:
        n = self.nodes[nid]
        if n.kind == "file":
            return n.file
        return f"{(n.parent + '.') if n.parent else ''}{n.name} ({n.file}:{n.line})"

    def overview(self, limit: int = 2600) -> str:
        files = [n for n in self.nodes.values() if n.kind == "file"]
        syms = [n for n in self.nodes.values() if n.kind != "file"]
        if not files:
            return "Nessun file di codice riconosciuto nella sandbox."
        out_, in_ = self._adj()
        areas: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for n in files:
            d = n.file.rsplit("/", 1)[0] if "/" in n.file else "."
            areas[d][0] += 1
        for s in syms:
            d = s.file.rsplit("/", 1)[0] if "/" in s.file else "."
            areas[d][1] += 1
        degree = {n.id: len(out_[n.id]) + len(in_[n.id]) for n in syms}
        top = sorted(syms, key=lambda n: -degree[n.id])[:8]
        entries = [n.file for n in files if ENTRY.search(n.file)][:6]
        edge_kinds = defaultdict(int)
        for _, _, k in self.edges:
            edge_kinds[k] += 1
        lines = [f"Grafo del codice: {len(files)} file, {len(syms)} simboli, " + ", ".join(f"{v} {k}" for k, v in sorted(edge_kinds.items())) + (f"; {self.skipped} file non analizzabili" if self.skipped else ""),
                 "Aree: " + "; ".join(f"{d} ({a} file, {b} simboli)" for d, (a, b) in sorted(areas.items(), key=lambda x: -x[1][1])[:8])]
        if entries:
            lines.append("Punti d'ingresso probabili: " + ", ".join(entries))
        lines.append("Simboli più collegati (da leggere per primi):\n" + "\n".join(f"- {self._label(n.id)} [{n.kind}{n.sig and ' ' + n.sig}] grado {degree[n.id]}" for n in top if degree[n.id]))
        lines.append("Usa code_symbol(nome) per dettagli e chiamanti, code_deps(file) per le dipendenze, code_path(a, b) per il collegamento tra due cose; poi code_read solo sulle righe che servono.")
        return "\n".join(lines)[:limit]

    def find(self, name: str) -> list[Node]:
        q = name.strip()
        exact = [n for n in self.nodes.values() if n.kind != "file" and (n.name == q or f"{n.parent}.{n.name}" == q)]
        if exact:
            return exact
        low = q.lower()
        return [n for n in self.nodes.values() if n.kind != "file" and low in n.name.lower()][:10] or [n for n in self.nodes.values() if n.kind == "file" and (q in n.file or n.name.lower() == low)][:6]

    def symbol(self, name: str, limit: int = 2400) -> str:
        hits = self.find(name)
        if not hits:
            return f"Nessun simbolo o file «{name}» nel grafo."
        out_, in_ = self._adj()
        blocks = []
        for n in hits[:5]:
            callers = [self._label(a) for a, k in in_[n.id] if k in ("calls", "extends")][:8]
            callees = [self._label(b) for b, k in out_[n.id] if k in ("calls", "extends")][:8]
            head = f"{n.kind} {(n.parent + '.') if n.parent else ''}{n.name}{n.sig} — {n.file}" + (f":{n.line}" if n.line else "") + (f"\n  «{n.doc}»" if n.doc else "")
            blocks.append(head + (f"\n  usato da: {'; '.join(callers)}" if callers else "\n  usato da: nessuno trovato") + (f"\n  usa: {'; '.join(callees)}" if callees else ""))
        return ("\n".join(blocks) + (f"\n[…{len(hits) - 5} altri risultati]" if len(hits) > 5 else ""))[:limit]

    def deps(self, path: str, limit: int = 2000) -> str:
        fid = f"f:{path.strip('/')}"
        if fid not in self.nodes:
            cands = [n for n in self.nodes.values() if n.kind == "file" and path.strip("/") in n.file]
            if len(cands) != 1:
                return f"File «{path}» non trovato nel grafo" + (": " + ", ".join(c.file for c in cands[:6]) if cands else ".")
            fid = cands[0].id
        out_, in_ = self._adj()
        imp = sorted({self.nodes[b].file for b, k in out_[fid] if k == "imports"})
        by = sorted({self.nodes[a].file for a, k in in_[fid] if k == "imports"})
        defs = [f"{n.parent + '.' if n.parent else ''}{n.name}:{n.line}" for n in self.nodes.values() if n.file == self.nodes[fid].file and n.kind != "file"][:25]
        return (f"{self.nodes[fid].file}\n  importa: {', '.join(imp) or '—'}\n  importato da: {', '.join(by) or '—'}\n  definisce: {', '.join(defs) or '—'}")[:limit]

    def path(self, a: str, b: str, limit: int = 1800) -> str:
        ha, hb = self.find(a), self.find(b)
        if not ha or not hb:
            return f"Non trovo {'«' + a + '»' if not ha else '«' + b + '»'} nel grafo."
        out_, in_ = self._adj()
        goals = {n.id for n in hb}
        for start in ha[:3]:
            prev, q = {start.id: None}, deque([start.id])
            while q:
                cur = q.popleft()
                if cur in goals:
                    chain, kinds = [], []
                    while cur:
                        chain.append(cur)
                        cur = prev[cur][0] if prev[cur] else None
                    chain.reverse()
                    return " → ".join(self._label(c) for c in chain)[:limit]
                for nxt, k in out_[cur] + in_[cur]:
                    if nxt not in prev:
                        prev[nxt] = (cur, k)
                        q.append(nxt)
        return "Nessun collegamento trovato tra i due."
