"""공유 대시보드 트리에서 해석되지 않는 import 를 찾는다.

트리는 {경로: 내용} 이다. 프런트엔드는 `src/frontend/src/` 아래 .ts·.tsx·.js·.jsx, 백엔드는 `src/backend/` 아래 .py 만 본다.
별칭은 `@/` 하나이고, 패키지 import 는 보지 않는다. 결과는 (파일, 대상, 이름) 집합이며 파일 자체가 없으면 이름은 "" 다.
"""
import posixpath
import re

import gitcmd

FRONT = "src/frontend/src/"
BACK = "src/backend/"
JS_EXTS = (".ts", ".tsx", ".js", ".jsx")
ALIAS = "@/"

_JS_STRIP = re.compile(r"""("(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*'|`(?:\\.|[^`\\])*`)|(//[^\n]*|/\*[\s\S]*?\*/)""")
_PY_STRIP = re.compile(r"""(\"\"\"[\s\S]*?\"\"\"|'''[\s\S]*?''')|("(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*')|(#[^\n]*)""")

_JS_IMPORT = re.compile(r"""^[ \t]*import\s+(?!\()(?P<clause>[^'";]*?)\s*\bfrom\s*['"](?P<target>[^'"]+)['"]""", re.M)
_JS_SIDE = re.compile(r"""^[ \t]*import\s*['"](?P<target>[^'"]+)['"]""", re.M)
_JS_REEXPORT = re.compile(r"""^[ \t]*export\s+(?:type\s+)?(?P<clause>\{[^}]*\}|\*(?:\s+as\s+\w+)?)\s*from\s*['"](?P<target>[^'"]+)['"]""", re.M)
_JS_DYNAMIC = re.compile(r"""\bimport\(\s*['"](?P<target>[^'"]+)['"]\s*\)""")
_JS_DECL = re.compile(r"""^[ \t]*export\s+(?:default\s+)?(?:async\s+)?(?:declare\s+)?(?:abstract\s+)?"""
                      r"""(?:const\s+enum|const|let|var|function\s*\*?|class|type|interface|enum|namespace)\s+([A-Za-z_$][\w$]*)""", re.M)
_JS_DEFAULT = re.compile(r"""^[ \t]*export\s+default\b""", re.M)
_JS_BRACE = re.compile(r"""^[ \t]*export\s+(?:type\s+)?\{(?P<names>[^}]*)\}""", re.M)
_JS_STAR = re.compile(r"""^[ \t]*export\s+\*\s*from\b""", re.M)
_JS_STAR_AS = re.compile(r"""^[ \t]*export\s+\*\s+as\s+([A-Za-z_$][\w$]*)""", re.M)

_PY_FROM = re.compile(r"""^[ \t]*from\s+(?P<module>\.+[\w.]*|src\.backend(?:\.[\w]+)*)\s+import\s+(?P<names>\([^)]*\)|[^\n]+)""", re.M)
_PY_IMPORT = re.compile(r"""^[ \t]*import\s+(?P<modules>[^\n]+)""", re.M)
_PY_DEF = re.compile(r"""^(?:async\s+def|def|class)\s+(\w+)""", re.M)
_PY_ASSIGN = re.compile(r"""^(\w+)\s*[:=]""", re.M)
_PY_TOP_IMPORT = re.compile(r"""^(?:from\s+\S+\s+)?import\s+(\([^)]*\)|[^\n]+)""", re.M)


def _blank(match):
    """지운 글자 대신 줄바꿈만 남겨 줄 번호를 지킨다."""
    return "\n" * match.group(0).count("\n")


def _strip_js(text):
    return _JS_STRIP.sub(lambda m: m.group(1) if m.group(1) else _blank(m), text)


def _strip_py(text):
    return _PY_STRIP.sub(lambda m: m.group(2) if m.group(2) else _blank(m), text)


def _text(files, path):
    return files[path].decode("utf-8", "replace")


def _local(target):
    return target.startswith(".") or target.startswith(ALIAS)


def _js_base(path, target):
    if target.startswith(ALIAS):
        return FRONT + target[len(ALIAS):]
    return posixpath.normpath(posixpath.join(posixpath.dirname(path), target))


def _js_resolve(files, path, target):
    base = _js_base(path, target)
    for candidate in [base] + [base + ext for ext in JS_EXTS] + [f"{base}/index{ext}" for ext in JS_EXTS]:
        if candidate in files:
            return candidate
    return None


def _skipped_ext(target):
    """.css·.svg 처럼 읽지 않는 확장자의 대상이면 확인하지 않는다."""
    ext = posixpath.splitext(target)[1]
    return bool(ext) and ext not in JS_EXTS


def _split_names(inner):
    """`a, type B, c as d` 에서 대상 파일이 내보내야 하는 원래 이름(a, B, c)을 돌려준다."""
    names = []
    for part in inner.split(","):
        part = re.sub(r"^\s*type\s+", "", part).strip()
        if part:
            names.append(part.split()[0])
    return names


def _clause_names(clause):
    """import 절에서 확인할 이름. default import 는 "default" 다. `* as ns` 는 이름을 보지 않는다."""
    clause = re.sub(r"^type\s+", "", clause.strip())
    names = []
    brace = re.search(r"\{([^}]*)\}", clause)
    if brace:
        names += _split_names(brace.group(1))
        clause = clause[:brace.start()] + clause[brace.end():]
    head = clause.strip().strip(",").strip()
    if head and not head.startswith("*"):
        names.append("default")
    return names


def _exports(text):
    """파일이 내보내는 이름 집합과 `export *` 여부."""
    names = set(_JS_DECL.findall(text)) | set(_JS_STAR_AS.findall(text))
    if _JS_DEFAULT.search(text):
        names.add("default")
    for match in _JS_BRACE.finditer(text):
        for part in match.group("names").split(","):
            part = re.sub(r"^\s*type\s+", "", part).strip()
            if part:
                names.add(part.split()[-1])
    return names, bool(_JS_STAR.search(text))


def _js_items(files, path, cache):
    text = _strip_js(_text(files, path))
    uses = [(m.group("target"), _clause_names(m.group("clause"))) for m in _JS_IMPORT.finditer(text)]
    for match in _JS_REEXPORT.finditer(text):
        clause = match.group("clause")
        uses.append((match.group("target"), _split_names(clause[1:-1]) if clause.startswith("{") else []))
    uses += [(m.group("target"), []) for m in _JS_SIDE.finditer(text)]
    uses += [(m.group("target"), []) for m in _JS_DYNAMIC.finditer(text)]
    found = set()
    for target, names in uses:
        if not _local(target) or _skipped_ext(target):
            continue
        resolved = _js_resolve(files, path, target)
        if resolved is None:
            found.add((path, target, ""))
            continue
        if resolved not in cache:
            cache[resolved] = _exports(_strip_js(_text(files, resolved)))
        exported, star = cache[resolved]
        if star:
            continue
        found |= {(path, target, name) for name in names if name not in exported}
    return found


def _py_module_path(path, module):
    if module.startswith("."):
        dots = len(module) - len(module.lstrip("."))
        base = posixpath.dirname(path)
        for _ in range(dots - 1):
            base = posixpath.dirname(base)
        rest = module.lstrip(".")
        return posixpath.join(base, *rest.split(".")) if rest else base
    return "/".join(module.split("."))


def _is_dir(files, base):
    prefix = base + "/"
    return any(key.startswith(prefix) for key in files)


def _py_names_of(text):
    """모듈 최상위 이름과 `import *` 여부."""
    names = set(_PY_DEF.findall(text)) | set(_PY_ASSIGN.findall(text))
    star = False
    for match in _PY_TOP_IMPORT.finditer(text):
        for part in match.group(1).strip("()").split(","):
            words = part.split()
            if not words:
                continue
            if words[0] == "*":
                star = True
            names.add(words[-1].split(".")[0] if len(words) == 1 else words[-1])
    return names, star


def _py_items(files, path, cache):
    text = _strip_py(_text(files, path))
    found = set()
    for match in _PY_FROM.finditer(text):
        module = match.group("module")
        base = _py_module_path(path, module)
        module_file = next((c for c in (base + ".py", base + "/__init__.py") if c in files), None)
        if module_file is None and not _is_dir(files, base):
            found.add((path, module, ""))
            continue
        if module_file is not None and module_file not in cache:
            cache[module_file] = _py_names_of(_strip_py(_text(files, module_file)))
        defined, star = cache.get(module_file, (set(), False))
        if star:
            continue
        for name in _split_names(match.group("names").strip("()")):
            if name == "*" or name in defined:
                continue
            sub = f"{base}/{name}"
            if sub + ".py" in files or _is_dir(files, sub):
                continue
            found.add((path, module, name))
    for match in _PY_IMPORT.finditer(text):
        for part in match.group("modules").split(","):
            words = part.split()
            if not words or not words[0].startswith("src.backend"):
                continue
            base = _py_module_path(path, words[0])
            if base + ".py" not in files and not _is_dir(files, base):
                found.add((path, words[0], ""))
    return found


def unresolved(files):
    """트리의 {경로: 내용} 에서 해석되지 않는 (파일, 대상, 이름) 집합을 돌려준다."""
    found, js_cache, py_cache = set(), {}, {}
    for path in files:
        if path.startswith(FRONT) and path.endswith(JS_EXTS):
            found |= _js_items(files, path, js_cache)
        elif path.startswith(BACK) and path.endswith(".py"):
            found |= _py_items(files, path, py_cache)
    return found


def locate(files, items):
    """항목마다 {"file", "line", "target", "name"} 을 (file, line) 순서로 돌려준다. line 은 대상이 처음 나오는 줄이다."""
    located = []
    for path, target, name in items:
        text = _text(files, path)
        index = text.find(target)
        line = text.count("\n", 0, index) + 1 if index >= 0 else 1
        located.append({"file": path, "line": line, "target": target, "name": name})
    return sorted(located, key=lambda item: (item["file"], item["line"], item["target"], item["name"]))


def tree_files(top, ref, deadline=None):
    """ref 트리에서 확인 대상 파일의 {경로: 내용} 을 git 프로세스 두 개로 읽는다."""
    entries = gitcmd.git_z(top, "ls-tree", "-r", "-z", ref, deadline=deadline)
    blobs = {}
    for entry in entries:
        if "\t" not in entry:
            continue
        meta, path = entry.split("\t", 1)
        if (path.startswith(FRONT) and path.endswith(JS_EXTS)) or (path.startswith(BACK) and path.endswith(".py")):
            blobs[path] = meta.split()[2]
    contents = gitcmd.blob_contents(top, blobs.values(), deadline=deadline)
    return {path: contents.get(blob, b"") for path, blob in blobs.items()}
