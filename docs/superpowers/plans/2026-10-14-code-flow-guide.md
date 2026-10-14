# explaining-code-flow 스킬 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 레포 이름을 받아 기능별 동작 흐름을 움직이는 안내 화면(`docs/code-flow/index.html`)으로 만드는 스킬 `explaining-code-flow` 를 kw-dashboard 플러그인에 추가한다.

**Architecture:** 주 세션이 `SKILL.md` 절차를 따라 분석 서브에이전트로 기능별 흐름 JSON 을 받는다. 파이썬 스크립트 세 개가 레포 실행(`run_repo.py`), 화면 캡처(`capture.py`), HTML 렌더(`render.py`)를 나눠 맡는다. 템플릿은 시제품 `movie_template.html` 에서 레포별 표를 지운 사본이다.

**Tech Stack:** Python 3.12 표준 라이브러리, PyJWT[crypto](토큰), Playwright(`channel="chrome"`), `uv run --no-project --with`, PowerShell 7 계약 테스트, 헤드리스 Chrome.

**Spec:** `docs/superpowers/specs/2026-10-14-code-flow-guide-design.md`

## Global Constraints

- 실행 환경은 윈도우 PowerShell 5 · 7 이다. 스크립트는 하위 명령을 `subprocess` 인자 목록으로 실행한다.
- 스킬 파일에서 파이썬은 `python "${CLAUDE_SKILL_DIR}/scripts/<이름>.py"` 로 호출하고 `python3` 를 쓰지 않는다(기존 `tests/test_devops.ps1` 계약과 같다).
- 스크립트 의존성은 `uv run --no-project --with` 로만 설치하고 PC 전역 파이썬에 설치하지 않는다. `--no-project` 가 없으면 분석 대상 레포의 `pyproject.toml` 을 프로젝트로 잡아 설치를 시도한다.
- Docker 를 쓰지 않고, 사용자에게 보이는 문장에 Docker 라는 말을 쓰지 않는다.
- 서버는 레포 종류와 상관없이 `127.0.0.1` 에만 연결한다.
- 레포의 추적 파일을 고치지 않는다. 설치는 `npm ci` · `npm install --no-save` · `uv sync --frozen` · `uv pip install` 만 쓴다.
- `.env` 를 읽거나 만들지 않는다.
- 토큰은 화면 출력 · 파일 · 명령줄 인자에 남기지 않고, 하위 프로세스 환경변수(`GIT_CONFIG_COUNT` · `GIT_CONFIG_KEY_0` · `GIT_CONFIG_VALUE_0`)로만 넘긴다. App ID `2826312`, 설치 ID `108948292`.
- 캡처는 기본으로 버튼을 누르지 않고, 사용자가 한 번 승인한 때만 목록의 버튼을 모두 누른다.
- 뷰포트 1440×1000, 노드 좌표 960×520 무대 기준.
- 화면 칸 문구는 spec 의 다섯 문장을 글자 그대로 쓴다.
- 결과물은 `<레포>/docs/code-flow/` 에 `index.html` · `screens/` · `flow.json` · `.gitignore`(`*`) 로 둔다.
- 새 파일 이름은 영문만 쓰고, 문서와 주석에 긴 줄표를 쓰지 않는다.

## Review Focus

- 레포의 `dev` 스크립트가 `-H 0.0.0.0` 이나 고정 포트를 박아 둔 조건: 스킬은 스크립트를 거치지 않고 `npm exec -- next dev -H 127.0.0.1 -p <포트>` 로 실행해 루프백에 연결해야 한다. Task 3 의 `--check` 가 검사한다.
- 사설 패키지 설치가 실패해 git 오류문에 토큰 URL 이 찍히는 조건: 로그와 화면 출력에서 토큰이 `***` 로 바뀌어야 한다. Task 3 의 `mask` 검사가 검사한다.
- 백엔드가 선호하는 포트(Dockerfile 의 `--port`)를 사용자가 이미 쓰는 조건: 다른 빈 포트를 고르고 그 사실을 알려야 한다. Task 3 의 검사가 검사한다.
- 화면이 데이터 API 를 아예 부르지 않거나 시간 안에 응답이 없는 조건: 「설정 없음」 문구가 나와야 한다. Task 5 의 `judge` 검사가 검사한다.
- 분석이 준 버튼 글자를 화면에서 찾지 못하는 조건: 캡처는 계속되고 사각형 없이 전체 화면으로 줌해야 하며, `render.py` 가 사각형 없는 장면을 받아야 한다. Task 1 의 검사가 검사한다.

---

## 파일 구조

| 파일 | 책임 |
|---|---|
| `plugins/kw-dashboard/skills/explaining-code-flow/SKILL.md` | 절차, 고정 명칭표, 문장 규칙, 스크립트 호출 |
| `.../explaining-code-flow/analysis-prompt.md` | 분석 서브에이전트 지침과 출력 JSON |
| `.../explaining-code-flow/tips-prompt.md` | 「알아 둘 점」 지침 |
| `.../explaining-code-flow/scripts/render.py` | 흐름 JSON 검사와 HTML 렌더 |
| `.../explaining-code-flow/scripts/movie_template.html` | 안내 화면 템플릿 |
| `.../explaining-code-flow/scripts/run_repo.py` | 인증서 묶음, 실행 계획, 설치, 토큰, 서버 시작 · 종료 |
| `.../explaining-code-flow/scripts/capture.py` | 캡처와 실패 판정 |
| `plugins/kw-dashboard/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` | 플러그인 설명 |
| `tests/test_dashboard.ps1` | 계약 테스트 |

아래에서 `S` 는 `plugins/kw-dashboard/skills/explaining-code-flow` 를 가리킨다.

검사 명령은 WSL 에서 `python3 S/scripts/<이름>.py --check` 로 실행하고, 같은 검사를 윈도우 `python.exe` 로도 한 번 실행한다. 스킬 파일 안에는 `python3` 를 적지 않는다.

---

### Task 1: render.py 의 검사와 렌더

**Files:**
- Create: `S/scripts/render.py`

**Interfaces:**
- Produces: `validate(data: dict) -> list[str]`(빈 목록이면 통과), `render(data: dict, template: str = "movie_template.html") -> str`, CLI `python render.py <flow.json> --out <html>` · `python render.py --check`

- [ ] **Step 1: 검사 예제와 `--check` 를 먼저 쓴다**

```python
"""흐름 JSON 을 검사하고 템플릿에 넣어 안내 화면 HTML 한 장을 만든다.

    python render.py <flow.json> --out <index.html>
    python render.py --check     # 붙박이 예제로 자체 검사
"""
from __future__ import annotations

import argparse
import copy
import html
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
KINDS = {"screen", "server", "db", "ai", "web", "local", "officepc", "code", "clock"}
ZONES = {"office", "app", "ax", "winus", "fund", "external"}
ICONS = {"file", "path", "ask", "card", "list", "stack", "bundle", "answer", "check", "table"}
STAGE_W, STAGE_H, SHOT_W, SHOT_H = 960, 520, 1440, 1000

SAMPLE = {
    "title": "예제 대시보드, 움직이며 보기", "repo": "example (main abc1234)", "appZone": "예제 서비스",
    "features": [{
        "key": "home", "name": "홈", "summary": "고정 카드", "screenImg": "screens/home.png",
        "nodes": [
            {"id": "pc", "name": "내 PC", "kind": "screen", "zone": "office", "x": 110, "y": 170},
            {"id": "data", "name": "샘플 데이터", "kind": "code", "zone": "app", "x": 360, "y": 80},
        ],
        "scenes": [
            {"title": "홈을 열면 카드가 그려집니다", "tips": ["금액 단위는 억원입니다."],
             "screen": {"startName": "「홈」 메뉴 클릭", "endName": "카드 표시", "start": [12, 77, 185, 40]},
             "actions": [{"from": "pc", "to": "data", "icon": "ask", "text": "카드 요청", "say": "화면이 샘플 데이터를 읽습니다."}]},
            {"title": "공고 목록", "tips": [],
             "screen": {"startName": "「공고」 탭 클릭", "endName": "목록 표시",
                        "unavailable": "실행에 필요한 데이터가 없어 화면을 만들 수 없습니다."},
             "actions": [{"from": "data", "to": "pc", "icon": "list", "text": "목록", "say": "목록이 화면으로 갑니다."}]},
        ],
    }],
}


def _check() -> int:
    ok = True

    def expect(label, cond):
        nonlocal ok
        print(("PASS  " if cond else "FAIL  ") + label)
        ok = ok and cond

    expect("예제가 검사를 통과한다", validate(SAMPLE) == [])
    page = render(SAMPLE)
    expect("렌더 결과에 자리표시 문자열이 남지 않는다", "__DATA__" not in page and "__TITLE__" not in page)
    expect("렌더 결과에 제목이 들어간다", "<title>예제 대시보드, 움직이며 보기</title>" in page)

    bad = copy.deepcopy(SAMPLE)
    f = bad["features"][0]
    f["nodes"][0]["kind"] = "browser"
    f["scenes"][0]["actions"][0]["to"] = "nowhere"
    del f["scenes"][1]["screen"]["unavailable"]
    del f["screenImg"]  # 기능 캡처가 있으면 장면은 그 캡처를 쓰므로, 캡처 없음을 시험하려면 함께 지운다
    errs = validate(bad)
    expect("명칭표에 없는 kind 를 잡는다", any("kind" in e and "browser" in e for e in errs))
    expect("없는 노드로 가는 동작을 잡는다", any("nowhere" in e for e in errs))
    expect("캡처도 실패 문구도 없는 장면을 잡는다", any("features[0].scenes[1]" in e and "캡처" in e for e in errs))

    norect = copy.deepcopy(SAMPLE)
    del norect["features"][0]["scenes"][0]["screen"]["start"]
    expect("버튼 사각형이 없는 장면도 통과한다", validate(norect) == [])
    return 0 if ok else 1
```

- [ ] **Step 2: 검사가 실패하는지 확인한다**

Run: `python3 S/scripts/render.py --check`
Expected: `NameError: name 'validate' is not defined` 로 종료

- [ ] **Step 3: `validate` · `render` · CLI 를 쓴다**

```python
def validate(data: dict) -> list[str]:
    errs: list[str] = []

    def need(obj, keys, where):
        for k in keys:
            if not isinstance(obj, dict) or obj.get(k) in (None, ""):
                errs.append(f"{where}.{k} 가 없습니다")

    def rect_ok(r):
        return (isinstance(r, list) and len(r) == 4 and all(isinstance(v, (int, float)) for v in r)
                and 0 <= r[0] <= SHOT_W and 0 <= r[1] <= SHOT_H)

    need(data, ["title", "repo", "appZone", "features"], "flow")
    for fi, f in enumerate(data.get("features") or []):
        fw = f"features[{fi}]"
        need(f, ["key", "name", "summary", "nodes", "scenes"], fw)
        ids = set()
        for ni, n in enumerate(f.get("nodes") or []):
            nw = f"{fw}.nodes[{ni}]"
            need(n, ["id", "name", "kind", "x", "y"], nw)
            ids.add(n.get("id"))
            if n.get("kind") not in KINDS:
                errs.append(f"{nw}.kind 값 {n.get('kind')!r} 는 명칭표에 없습니다")
            if "zone" in n and n["zone"] not in ZONES:
                errs.append(f"{nw}.zone 값 {n['zone']!r} 는 구역 목록에 없습니다")
            x, y = n.get("x"), n.get("y")
            if isinstance(x, (int, float)) and isinstance(y, (int, float)) and not (0 <= x <= STAGE_W and 0 <= y <= STAGE_H):
                errs.append(f"{nw} 좌표 ({x}, {y}) 가 960×520 무대 밖입니다")
        for si, s in enumerate(f.get("scenes") or []):
            sw = f"{fw}.scenes[{si}]"
            need(s, ["title", "actions"], sw)
            if not isinstance(s.get("tips"), list):
                errs.append(f"{sw}.tips 목록이 없습니다")
            scr = s.get("screen") or {}
            need(scr, ["startName", "endName"], f"{sw}.screen")
            shot = bool(scr.get("startImg") or f.get("screenImg"))
            if scr.get("unavailable") and (scr.get("start") or scr.get("startImg")):
                errs.append(f"{sw}.screen 에 캡처와 실패 문구가 함께 있습니다")
            if not shot and not scr.get("unavailable"):
                errs.append(f"{sw}.screen 에 캡처도 실패 문구도 없습니다")
            for key in ("start", "end"):
                if key in scr and not rect_ok(scr[key]):
                    errs.append(f"{sw}.screen.{key} 는 1440×1000 안의 [x, y, 폭, 높이] 여야 합니다")
            for ai, a in enumerate(s.get("actions") or []):
                aw = f"{sw}.actions[{ai}]"
                need(a, ["from", "to", "icon", "text", "say"], aw)
                for end in ("from", "to"):
                    if a.get(end) and a[end] not in ids:
                        errs.append(f"{aw}.{end} 값 {a[end]!r} 인 노드가 없습니다")
                if a.get("icon") and a["icon"] not in ICONS:
                    errs.append(f"{aw}.icon 값 {a['icon']!r} 는 아이콘 목록에 없습니다")
    return errs


def render(data: dict, template: str = "movie_template.html") -> str:
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    page = (HERE / template).read_text(encoding="utf-8")
    return page.replace("__TITLE__", html.escape(data["title"])).replace("__DATA__", payload)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("flow", nargs="?")
    ap.add_argument("--out")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if a.check:
        return _check()
    if not a.flow or not a.out:
        ap.error("흐름 JSON 경로와 --out 이 필요합니다")
    data = json.loads(Path(a.flow).read_text(encoding="utf-8"))
    errs = validate(data)
    if errs:
        print("흐름 JSON 을 고쳐야 합니다:")
        for e in errs:
            print("  - " + e)
        return 1
    Path(a.out).write_text(render(data), encoding="utf-8")
    print(a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

`_check` 는 `validate` 정의 뒤에 두어도 되고, 파일 끝의 `main` 앞이면 순서는 상관없다. 이 단계에서는 템플릿이 아직 없으므로 Step 4 전에 시제품 템플릿을 임시로 복사한다: `cp ~/02.github/flow_guide/movie_template.html S/scripts/movie_template.html`(Task 2 가 이 사본을 고친다).

- [ ] **Step 4: 검사를 통과하는지 확인한다**

Run: `python3 S/scripts/render.py --check` 와 `powershell.exe -c "python <S 의 윈도우 경로>\scripts\render.py --check"`
Expected: `PASS` 줄 7개, 종료 코드 0

- [ ] **Step 5: 커밋한다**

```bash
git add S/scripts/render.py S/scripts/movie_template.html
git commit -m "feat(kw-dashboard): explaining-code-flow 렌더러와 흐름 JSON 검사"
```

---

### Task 2: 템플릿에서 레포별 표를 지우고 실패 문구를 표시한다

**Files:**
- Modify: `S/scripts/movie_template.html`

**Interfaces:**
- Consumes: Task 1 의 `render.py` 와 `SAMPLE`
- Produces: `n.kind` · `n.zone` · `n.x` · `n.y` 만 읽는 템플릿, `screen.unavailable` 표시

- [ ] **Step 1: 지울 표를 찾는 검사를 먼저 실행해 실패를 본다**

Run: `grep -nE 'SPOT|ZONE_BY_ID|KIND_BY_ID|DOCK_BY_ID|dockOf|영역' S/scripts/movie_template.html`
Expected: 여러 줄이 나온다(지운 뒤에는 0줄이어야 한다)

- [ ] **Step 2: 표와 대체 경로를 지운다**

Edit 도구로 아래를 바꾼다.

- `// 기본 위치는 같은 영역의 노드가 …` 주석과 `const SPOT = {…};` 두 줄을 지운다.
- `useFeature` 의 좌표 처리 두 줄을 아래 한 줄로 바꾼다.

```js
    F.nodes = F.nodes.map(n => ({...n, y: Math.round(30 + (n.y - 30) * 0.86)}));
```

- `// 영역: 누가 운영하는 곳인가. …` 주석을 `// 구역: 누가 운영하는 곳인가. 구역 상자는 속한 노드를 감싸도록 계산한다.` 로 바꾼다.
- `const ZONE_BY_ID = {…};` 두 줄을 지우고 `const zoneOf = n => n.zone;` 로 바꾼다.
- `const KIND_BY_ID = {…};` 두 줄과 그 위 주석의 「노드에 kind 가 없으면 id 로 정한다 …」 문장을 지우고 `const kindOf = n => n.kind;` 로 바꾼다.
- `// 붙여 그리는 노드: …` 주석 두 줄, `const DOCK_BY_ID = {};`, `const dockOf = …;` 를 지운다. `drawStage` 안의 `F.nodes.forEach(n => { const host = NODE.get(dockOf(n)) … });` 블록 전체를 지운다. CSS 의 `.node.docked` · `.node.host` 규칙이 있으면 함께 지운다.
- 나머지 주석의 「영역」을 「구역」으로 바꾼다.

- [ ] **Step 3: `setupShot` 이 실패 문구를 표시하게 바꾼다**

```js
function setupShot(sc) {
  const box = document.getElementById('shot');
  // 캡처하지 못한 장면은 빈 화면 대신 이유 문구를 회색 면에 표시하고 줌하지 않는다
  if (sc.screen && sc.screen.unavailable) {
    box.hidden = false;
    box.innerHTML = `<div class="view"><div class="wait">${esc(sc.screen.unavailable)}</div></div>`;
    return false;
  }
  if (!sc.screen || !(sc.screen.startImg || F.screenImg)) { box.hidden = true; return false; }
  box.hidden = false;
  // 장면마다 화면 상태가 다르면 startImg · endImg 로 그 상태의 캡처를 쓴다(예: 기관을 고른 뒤의 화면)
  box.innerHTML = `<div class="cap"><i></i><span></span></div><div class="view"><img src="${esc(sc.screen.startImg || F.screenImg)}" alt=""><div class="mark"></div></div>`;
  camera(null, '대시보드 전체 화면', '#5B6C8C', true);
  return true;
}
```

`.shot .wait` 규칙의 글자를 `font-size:15px;color:var(--text-secondary)` 로 바꿔 문구가 읽히게 한다.

- [ ] **Step 4: 문법과 표시를 확인한다**

Run:
```bash
grep -cE 'SPOT|ZONE_BY_ID|KIND_BY_ID|DOCK_BY_ID|dockOf|영역' S/scripts/movie_template.html   # 0
python3 - <<'EOF'
import re,sys; sys.path.insert(0,"S/scripts"); import render
open("/tmp/claude-1000/sample.html","w",encoding="utf8").write(render.render(render.SAMPLE))
js=re.findall(r"<script>([\s\S]*?)</script>", open("/tmp/claude-1000/sample.html",encoding="utf8").read())[-1]
open("/tmp/claude-1000/sample.js","w").write(js)
EOF
node --check /tmp/claude-1000/sample.js
```
그다음 `sample.html` 을 `C:\Users\Public\claude-etax\tracecheck\fg_ws\` 로 복사하고, `play(1)` 로 시작하게 바꾼 사본을 헤드리스 Chrome(`--user-data-dir='C:\Users\Public\claude-etax\tracecheck\prof'`, `--window-size=1600,1000`)으로 캡처한다.
Expected: grep 0, `node --check` 오류 없음, 캡처의 오른쪽 화면 칸 회색 면에 「실행에 필요한 데이터가 없어 화면을 만들 수 없습니다.」가 보인다.

- [ ] **Step 5: 커밋한다**

```bash
git add S/scripts/movie_template.html
git commit -m "feat(kw-dashboard): 안내 화면 템플릿에서 레포별 표를 지우고 실패 문구 표시"
```

---

### Task 3: run_repo.py 의 인증서 묶음과 실행 계획

**Files:**
- Create: `S/scripts/run_repo.py`

**Interfaces:**
- Produces:
  - `ca_bundle(repo: Path, out_dir: Path) -> Path | None`
  - `plan(repo: Path) -> dict` 반환 형태 `{"services": [{"name": str, "cwd": str, "install": [[str]], "run": [str], "port": int, "preferred": int | None}], "private": [str], "notes": [str]}`
  - `mask(text: str, secret: str) -> str`
  - `git_token_env(token: str) -> dict[str, str]`
  - `free_port(preferred: int | None = None) -> int`
  - CLI `python run_repo.py exec <repo> -- <명령…>`, `python run_repo.py plan <repo>`, `python run_repo.py --check`

- [ ] **Step 1: `--check` 를 먼저 쓴다**

```python
def _check() -> int:
    import tempfile
    ok = True

    def expect(label, cond):
        nonlocal ok
        print(("PASS  " if cond else "FAIL  ") + label)
        ok = ok and cond

    with tempfile.TemporaryDirectory() as t:
        root = Path(t)
        nxt = root / "nextrepo"; nxt.mkdir()
        (nxt / "package.json").write_text(json.dumps({"scripts": {"dev": "next dev -H 0.0.0.0 -p 3000"}, "dependencies": {"next": "14"}}), encoding="utf-8")
        (nxt / "package-lock.json").write_text("{}", encoding="utf-8")
        p = plan(nxt)
        run = p["services"][0]["run"]
        expect("Next 레포는 npm ci 로 설치한다", p["services"][0]["install"] == [["npm", "ci"]])
        expect("dev 스크립트를 거치지 않고 루프백으로 실행한다", run[:5] == ["npm", "exec", "--", "next", "dev"] and "127.0.0.1" in run and "0.0.0.0" not in run)

        py = root / "pyrepo"; (py / "backend").mkdir(parents=True)
        (py / "backend" / "requirements.txt").write_text("fastapi\n", encoding="utf-8")
        (py / "backend" / "Dockerfile").write_text(
            'RUN uv pip install "git+https://github.com/KiwoomAM/Kiwoom-Manager.git@main#subdirectory=llm-manager"\n'
            'CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]\n', encoding="utf-8")
        p = plan(py)
        svc = p["services"][0]
        expect("Dockerfile 에서 uvicorn 진입점을 찾는다", "main:app" in svc["run"] and "127.0.0.1" in svc["run"])
        expect("Dockerfile 의 포트를 선호 포트로 쓴다", svc["preferred"] == 8002)
        expect("Dockerfile 의 사설 패키지를 찾는다", p["private"] == ["git+https://github.com/KiwoomAM/Kiwoom-Manager.git@main#subdirectory=llm-manager"])
        expect("requirements 레포는 uv venv 뒤 uv pip install 로 설치한다", svc["install"][:2] == [["uv", "venv"], ["uv", "pip", "install", "-r", "requirements.txt"]])

        empty = root / "empty"; empty.mkdir()
        try:
            plan(empty); expect("실행 방법이 없는 레포는 오류를 낸다", False)
        except RepoError as e:
            expect("실행 방법이 없는 레포는 오류를 낸다", "실행 방법" in str(e))

        crt = root / "certs"; crt.mkdir()
        (crt / "ePrism.crt").write_text("-----BEGIN CERTIFICATE-----\nAAAA\n-----END CERTIFICATE-----\n", encoding="utf-8")
        b = ca_bundle(root, root)
        expect("인증서 묶음 끝에 ePrism 이 붙는다", b is not None and b.read_text(encoding="utf-8").rstrip().endswith("-----END CERTIFICATE-----") and "AAAA" in b.read_text(encoding="utf-8"))
        expect("ePrism 이 없으면 묶음을 만들지 않는다", ca_bundle(nxt, root) is None)

    secret = "ghs_abcdef123456"
    expect("토큰을 *** 로 가린다", mask(f"fatal: https://x-access-token:{secret}@github.com/x", secret) == "fatal: https://x-access-token:***@github.com/x")
    env = git_token_env(secret)
    expect("git 설정은 환경변수 세 개로 넘긴다", env["GIT_CONFIG_COUNT"] == "1" and env["GIT_CONFIG_VALUE_0"] == "https://github.com/" and secret in env["GIT_CONFIG_KEY_0"])

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); s.listen(); busy = s.getsockname()[1]
        expect("선호 포트가 쓰이고 있으면 다른 포트를 고른다", free_port(busy) != busy)
    return 0 if ok else 1
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 S/scripts/run_repo.py --check`
Expected: `NameError` 로 종료

- [ ] **Step 3: 구현한다**

```python
"""레포를 이 PC 에서 실행하고 끈다. 캡처 단계가 쓴다.

    python run_repo.py exec <레포> -- <명령…>        # 사내 인증서 묶음을 SSL_CERT_FILE 로 주고 명령을 실행
    python run_repo.py plan <레포>                   # 설치 · 실행 계획만 출력
    python run_repo.py doctor <레포>                 # 도구와 토큰 발급이 되는지 확인(토큰은 출력하지 않음)
    python run_repo.py start <레포> --state <파일>   # 설치하고 서버를 실행한 뒤 주소를 출력
    python run_repo.py stop --state <파일>           # 서버를 끄고 레포의 추적 파일이 바뀌었는지 알림
    python run_repo.py --check                       # 붙박이 예제로 자체 검사

토큰은 화면 · 파일 · 명령줄에 남기지 않고 하위 프로세스 환경변수로만 넘긴다.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
from pathlib import Path

APP_ID = "2826312"            # Kiwoom-ESG gen_token.sh · backend/Dockerfile 에 적힌 공개 식별자
INSTALLATION_ID = "108948292"
GIT_URL = re.compile(r"git\+https://github\.com/[^\s\"'\\]+")
UVICORN_APP = re.compile(r"[\w.]+:[\w]+")


class RepoError(Exception):
    pass


def ca_bundle(repo: Path, out_dir: Path) -> Path | None:
    crt = repo / "certs" / "ePrism.crt"
    if not crt.exists():
        return None
    pems = []
    if hasattr(ssl, "enum_certificates"):  # 윈도우 인증서 저장소
        for der, enc, _ in ssl.enum_certificates("ROOT"):
            if enc == "x509_asn":
                pems.append(ssl.DER_cert_to_PEM_cert(der))
    else:
        cafile = ssl.get_default_verify_paths().cafile
        if cafile and Path(cafile).exists():
            pems.append(Path(cafile).read_text(encoding="utf-8"))
    out = out_dir / "ca-bundle.pem"
    out.write_text("".join(pems) + "\n" + crt.read_text(encoding="utf-8"), encoding="utf-8")
    return out


def mask(text: str, secret: str) -> str:
    return text.replace(secret, "***") if secret else text


def git_token_env(token: str) -> dict[str, str]:
    return {"GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": f"url.https://x-access-token:{token}@github.com/.insteadOf",
            "GIT_CONFIG_VALUE_0": "https://github.com/"}


def free_port(preferred: int | None = None) -> int:
    if preferred:
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", preferred))
                return preferred
            except OSError:
                pass
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _dirs(repo: Path):
    yield repo
    for d in sorted(repo.iterdir()):
        if d.is_dir() and not d.name.startswith(".") and d.name not in ("node_modules", "docs"):
            yield d


def _node_service(d: Path) -> dict | None:
    pj = d / "package.json"
    if not pj.exists():
        return None
    pkg = json.loads(pj.read_text(encoding="utf-8"))
    if "dev" not in (pkg.get("scripts") or {}):
        return None
    deps = {**(pkg.get("dependencies") or {}), **(pkg.get("devDependencies") or {})}
    if "next" in deps:
        run = ["npm", "exec", "--", "next", "dev", "-H", "127.0.0.1", "-p", "{port}"]
    elif "vite" in deps:
        run = ["npm", "exec", "--", "vite", "--host", "127.0.0.1", "--port", "{port}", "--strictPort"]
    else:
        raise RepoError(f"{d.name}: Next.js · Vite 가 아닌 dev 스크립트는 아직 실행 방법을 모릅니다")
    install = [] if (d / "node_modules").exists() else [["npm", "ci"] if (d / "package-lock.json").exists() else ["npm", "install", "--no-save"]]
    return {"name": "frontend", "cwd": str(d), "install": install, "run": run, "preferred": None}


def _py_service(d: Path, private: list[str]) -> dict | None:
    pyproject, req = d / "pyproject.toml", d / "requirements.txt"
    if not (pyproject.exists() or req.exists()):
        return None
    docker = d / "Dockerfile"
    text = docker.read_text(encoding="utf-8") if docker.exists() else ""
    for url in GIT_URL.findall(text):
        if url not in private:
            private.append(url)
    app, preferred = None, None
    for line in text.splitlines():
        if "uvicorn" in line:
            m = [t for t in re.findall(r"[\w.:-]+", line) if UVICORN_APP.fullmatch(t)]
            app = app or (m[0] if m else None)
            pm = re.search(r"--port[\"',\s]+(\d+)", line)
            preferred = preferred or (int(pm.group(1)) if pm else None)
    if not app:
        raise RepoError(f"{d.name}: 백엔드 시작 명령(uvicorn 모듈:앱)을 찾지 못했습니다")
    if pyproject.exists() and (d / "uv.lock").exists():
        install = [["uv", "sync", "--frozen"]]
    else:
        install = [["uv", "venv"], ["uv", "pip", "install", "-r", "requirements.txt" if req.exists() else "pyproject.toml"]]
    run = ["uv", "run", "--no-sync", "uvicorn", app, "--host", "127.0.0.1", "--port", "{port}"]
    return {"name": "backend", "cwd": str(d), "install": install, "run": run, "preferred": preferred}


def plan(repo: Path) -> dict:
    services, private, notes = [], [], []
    back = front = None
    for d in _dirs(repo):
        back = back or _py_service(d, private)
        front = front or _node_service(d)
    for svc in (back, front):  # 백엔드를 먼저 실행한다
        if svc:
            svc["port"] = free_port(svc["preferred"])
            if svc["preferred"] and svc["port"] != svc["preferred"]:
                notes.append(f"{svc['name']} 포트 {svc['preferred']} 이 쓰이고 있어 {svc['port']} 로 실행합니다")
            svc["run"] = [str(svc["port"]) if t == "{port}" else t for t in svc["run"]]
            services.append(svc)
    if not services:
        raise RepoError("이 레포의 실행 방법을 찾지 못했습니다(package.json 의 dev 스크립트나 파이썬 백엔드가 없습니다)")
    return {"services": services, "private": private, "notes": notes}


def _exec(repo: Path, cmd: list[str]) -> int:
    tmp = Path(tempfile.mkdtemp(prefix="code-flow-"))
    env = dict(os.environ)
    bundle = ca_bundle(repo, tmp)
    if bundle:
        env["SSL_CERT_FILE"] = str(bundle)
    return subprocess.call([shutil.which(cmd[0]) or cmd[0], *cmd[1:]], env=env)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    p_exec = sub.add_parser("exec"); p_exec.add_argument("repo"); p_exec.add_argument("rest", nargs=argparse.REMAINDER)
    p_plan = sub.add_parser("plan"); p_plan.add_argument("repo")
    a = ap.parse_args()
    if a.check:
        return _check()
    try:
        if a.cmd == "exec":
            rest = a.rest[1:] if a.rest[:1] == ["--"] else a.rest
            return _exec(Path(a.repo).resolve(), rest)
        if a.cmd == "plan":
            print(json.dumps(plan(Path(a.repo).resolve()), ensure_ascii=False, indent=2))
            return 0
    except RepoError as e:
        print(str(e))
        return 2
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 통과를 확인한다**

Run: `python3 S/scripts/run_repo.py --check` 와 윈도우 `python.exe` 로 같은 검사, 그리고 `python3 S/scripts/run_repo.py plan ~/02.github/Kiwoom-dashboard/wholesale-dashboard`
Expected: `PASS` 줄 12개, wholesale 계획의 `run` 이 `["npm","exec","--","next","dev","-H","127.0.0.1","-p","<포트>"]` 이다.

- [ ] **Step 5: 커밋한다**

```bash
git add S/scripts/run_repo.py
git commit -m "feat(kw-dashboard): 레포 실행 계획과 사내 인증서 묶음"
```

---

### Task 4: run_repo.py 의 설치 · 토큰 · 시작 · 종료

**Files:**
- Modify: `S/scripts/run_repo.py`

**Interfaces:**
- Consumes: Task 3 의 `plan` · `ca_bundle` · `mask` · `git_token_env`
- Produces: CLI `doctor <레포>`, `start <레포> --state <파일>`(출력 `{"url": "http://127.0.0.1:<포트>", "notes": [...]}`), `stop --state <파일>`(추적 파일 변경 목록 출력, 이미 꺼진 프로세스여도 오류 없이 끝남)

- [ ] **Step 1: 함수를 추가한다**

```python
import time
import urllib.error
import urllib.request


def github_token(repo: Path, bundle: Path | None) -> str:
    import jwt  # uv run --no-project --with "pyjwt[crypto]" 로 들어온다
    pem = repo / "certs" / "kiwoom.pem"
    if not pem.exists():
        raise RepoError("certs/kiwoom.pem 이 없어 사내 패키지를 설치할 수 없습니다")
    now = int(time.time())
    tok = jwt.encode({"iat": now - 60, "exp": now + 600, "iss": APP_ID}, pem.read_text(encoding="utf-8"), algorithm="RS256")
    req = urllib.request.Request(f"https://api.github.com/app/installations/{INSTALLATION_ID}/access_tokens", method="POST",
                                 headers={"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"})
    ctx = ssl.create_default_context(cafile=str(bundle)) if bundle else ssl.create_default_context()
    with urllib.request.urlopen(req, context=ctx, timeout=30) as r:
        return json.load(r)["token"]


def _run_logged(cmd, cwd, env, log: Path, secret: str) -> None:
    r = subprocess.run([shutil.which(cmd[0]) or cmd[0], *cmd[1:]], cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    with log.open("a", encoding="utf-8") as f:
        f.write(mask(f"$ {' '.join(cmd)}\n{r.stdout}{r.stderr}\n", secret))
    if r.returncode != 0:
        raise RepoError(f"설치 명령 {' '.join(cmd)} 가 실패했습니다. 기록: {log}")


def _git_status(repo: Path) -> list[str]:
    r = subprocess.run(["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=no"], capture_output=True, text=True)
    return sorted(r.stdout.splitlines())


def _wait_http(port: int, proc: subprocess.Popen, seconds: int = 180) -> bool:
    end = time.time() + seconds
    while time.time() < end:
        if proc.poll() is not None:
            return False
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=3)
            return True
        except urllib.error.HTTPError:
            return True  # 응답이 오면 서버는 떠 있다
        except Exception:
            time.sleep(1)
    return False


def _kill_tree(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True)
    else:
        import signal
        try:
            os.killpg(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass


def start(repo: Path, state_path: Path) -> dict:
    p = plan(repo)
    tmp = state_path.parent
    log = tmp / "run_repo.log"
    env = dict(os.environ)
    bundle = ca_bundle(repo, tmp)
    if bundle:
        env["SSL_CERT_FILE"] = str(bundle)
    token = ""
    if p["private"] or any("git+https" in (Path(s["cwd"]) / f).read_text(encoding="utf-8", errors="ignore")
                           for s in p["services"] for f in ("requirements.txt", "pyproject.toml") if (Path(s["cwd"]) / f).exists()):
        token = github_token(repo, bundle)
    inst_env = {**env, **(git_token_env(token) if token else {})}
    state = {"repo": str(repo), "git_before": _git_status(repo), "pids": [], "notes": p["notes"]}
    try:
        for svc in p["services"]:
            for cmd in svc["install"]:
                _run_logged(cmd, svc["cwd"], inst_env, log, token)
            if svc["name"] == "backend" and p["private"]:
                _run_logged(["uv", "pip", "install", *p["private"]], svc["cwd"], inst_env, log, token)
            out = (tmp / f"{svc['name']}.log").open("w", encoding="utf-8")
            kw = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
            proc = subprocess.Popen([shutil.which(svc["run"][0]) or svc["run"][0], *svc["run"][1:]], cwd=svc["cwd"], env=env,
                                    stdout=out, stderr=subprocess.STDOUT, **kw)
            state["pids"].append(proc.pid)
            state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
            if not _wait_http(svc["port"], proc):
                raise RepoError(f"{svc['name']} 서버가 응답하지 않습니다. 기록: {tmp / (svc['name'] + '.log')}")
            state["url"] = f"http://127.0.0.1:{svc['port']}"
    except Exception:
        stop(state_path)
        raise
    state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    return {"url": state["url"], "notes": state["notes"]}


def stop(state_path: Path) -> list[str]:
    if not state_path.exists():
        return []
    state = json.loads(state_path.read_text(encoding="utf-8"))
    for pid in reversed(state.get("pids", [])):
        _kill_tree(pid)
    after = _git_status(Path(state["repo"]))
    return [l for l in after if l not in state.get("git_before", [])]


def doctor(repo: Path) -> int:
    ok = True
    for tool in ("git", "node", "npm", "uv"):
        found = shutil.which(tool) is not None
        print(("있음  " if found else "없음  ") + tool)
        ok = ok and (found or tool in ("node", "npm"))
    chrome = [Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Google/Chrome/Application/chrome.exe"]
    print(("있음  " if any(c.exists() for c in chrome) or shutil.which("google-chrome") else "없음  ") + "Chrome")
    if (repo / "certs" / "kiwoom.pem").exists():
        tmp = Path(tempfile.mkdtemp(prefix="code-flow-"))
        try:
            github_token(repo, ca_bundle(repo, tmp))
            print("있음  사내 패키지 토큰 발급")
        except Exception as e:
            ok = False
            print(f"없음  사내 패키지 토큰 발급 ({type(e).__name__})")
    return 0 if ok else 1
```

`main` 에 하위 명령을 추가한다.

```python
    p_doc = sub.add_parser("doctor"); p_doc.add_argument("repo")
    p_start = sub.add_parser("start"); p_start.add_argument("repo"); p_start.add_argument("--state", required=True)
    p_stop = sub.add_parser("stop"); p_stop.add_argument("--state", required=True)
    # … try 블록 안에
        if a.cmd == "doctor":
            return doctor(Path(a.repo).resolve())
        if a.cmd == "start":
            print(json.dumps(start(Path(a.repo).resolve(), Path(a.state).resolve()), ensure_ascii=False))
            return 0
        if a.cmd == "stop":
            changed = stop(Path(a.state).resolve())
            print("레포의 추적 파일이 바뀌었습니다:\n" + "\n".join(changed) if changed else "서버를 껐습니다. 레포의 추적 파일은 그대로입니다.")
            return 3 if changed else 0
```

`--check` 에 `stop` 의 멱등 검사를 추가한다.

```python
    with tempfile.TemporaryDirectory() as t:
        st = Path(t) / "state.json"
        st.write_text(json.dumps({"repo": t, "pids": [999999], "git_before": []}), encoding="utf-8")
        try:
            stop(st); stop(st); expect("이미 꺼진 프로세스를 두 번 꺼도 오류가 없다", True)
        except Exception as e:
            expect(f"이미 꺼진 프로세스를 두 번 꺼도 오류가 없다 ({e})", False)
```

- [ ] **Step 2: 자체 검사를 실행한다**

Run: `python3 S/scripts/run_repo.py --check`
Expected: `PASS` 줄 13개

- [ ] **Step 3: wholesale-dashboard 로 실제 실행을 확인한다**

Run:
```bash
W=~/02.github/Kiwoom-dashboard/wholesale-dashboard; ST=/tmp/claude-1000/cf/state.json; mkdir -p $(dirname $ST)
python3 S/scripts/run_repo.py start $W --state $ST
ss -ltnp | grep node        # 127.0.0.1:<포트> 만 보인다
curl -s -o /dev/null -w '%{http_code}\n' "$(python3 -c "import json;print(json.load(open('$ST'))['url'])")/"
python3 S/scripts/run_repo.py stop --state $ST
ss -ltnp | grep node || echo "남은 서버 없음"
git -C $W status --short
```
Expected: 출력 주소가 `http://127.0.0.1:<포트>`, `ss` 가 `127.0.0.1` 만 보임, HTTP 200, 종료 뒤 「남은 서버 없음」, `git status` 빈 출력.

- [ ] **Step 4: 토큰 발급을 확인한다**

Run: `python3 S/scripts/run_repo.py exec ~/02.github/Kiwoom-ESG -- uv run --no-project --with "pyjwt[crypto]" python S/scripts/run_repo.py doctor ~/02.github/Kiwoom-ESG`
Expected: 「있음  사내 패키지 토큰 발급」 줄이 나오고 토큰 문자열은 어디에도 출력되지 않는다.

- [ ] **Step 5: 커밋한다**

```bash
git add S/scripts/run_repo.py
git commit -m "feat(kw-dashboard): 레포 설치 · 실행 · 종료와 사내 패키지 토큰"
```

---

### Task 5: capture.py 의 실패 판정

**Files:**
- Create: `S/scripts/capture.py`

**Interfaces:**
- Produces:
  - 문구 상수 `MSG_RUN` · `MSG_NOSCREEN` · `MSG_AUTH` · `MSG_CONFIG` · `MSG_DATA`(spec 표의 글자 그대로)
  - `judge(doc_status: int | None, final_path: str, api_status: int | None, api_body, list_field: str | None) -> str | None`
  - `pick(body, dotted: str)`
  - CLI `python capture.py --check`

- [ ] **Step 1: `--check` 를 먼저 쓴다**

```python
def _check() -> int:
    ok = True

    def expect(label, cond):
        nonlocal ok
        print(("PASS  " if cond else "FAIL  ") + label)
        ok = ok and cond

    expect("정상 응답은 문구가 없다", judge(200, "/", 200, {"notices": [1]}, "notices") is None)
    expect("문서 요청 401 은 권한 문구", judge(401, "/", None, None, None) == MSG_AUTH)
    expect("로그인 화면 이동은 권한 문구", judge(200, "/auth/login", None, None, None) == MSG_AUTH)
    expect("데이터 API 403 은 권한 문구", judge(200, "/", 403, None, "notices") == MSG_AUTH)
    expect("로컬 전용 가드의 503 은 설정 문구", judge(200, "/", 503, {"error": "이 기능은 내 PC에서"}, None) == MSG_CONFIG)
    expect("API 를 부르지 않으면(0) 설정 문구", judge(200, "/", 0, None, "notices") == MSG_CONFIG)
    expect("객체 안의 빈 목록은 데이터 문구", judge(200, "/", 200, {"notices": [], "meta": {}}, "notices") == MSG_DATA)
    expect("점으로 이은 경로의 빈 목록도 데이터 문구", judge(200, "/", 200, {"data": {"items": []}}, "data.items") == MSG_DATA)
    expect("데이터 API 를 지정하지 않은 장면은 문구가 없다", judge(200, "/", None, None, None) is None)
    return 0 if ok else 1
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 S/scripts/capture.py --check`
Expected: `NameError` 로 종료

- [ ] **Step 3: 구현한다**

```python
"""레포 화면을 기능마다 캡처하고, 캡처하지 못한 장면에 이유 문구를 정한다.

    python capture.py <capture_plan.json> --out <capture_result.json>
    python capture.py <capture_plan.json> --out <결과> --fail run|noscreen   # 브라우저 없이 모든 장면에 문구만 적는다
    python capture.py --check
캡처는 uv run --no-project --with playwright 로 실행하고, PC 에 설치된 Chrome 을 쓴다.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

MSG_RUN = "이 PC 에서 레포를 실행하지 못해 화면을 만들 수 없습니다."
MSG_NOSCREEN = "이 레포에는 화면 코드가 없어 화면을 만들 수 없습니다."
MSG_AUTH = "접근 권한이 없어 화면을 만들 수 없습니다."
MSG_CONFIG = "실행에 필요한 설정이 없어 화면을 만들 수 없습니다."
MSG_DATA = "실행에 필요한 데이터가 없어 화면을 만들 수 없습니다."
LOGIN = re.compile(r"(login|signin|sso)", re.I)


def pick(body, dotted: str):
    for key in dotted.split("."):
        if not isinstance(body, dict):
            return None
        body = body.get(key)
    return body


def judge(doc_status, final_path, api_status, api_body, list_field):
    if doc_status in (401, 403) or LOGIN.search(final_path or ""):
        return MSG_AUTH
    if api_status is None:
        return None
    if api_status in (401, 403):
        return MSG_AUTH
    if api_status == 0 or api_status >= 500:
        return MSG_CONFIG
    if list_field:
        v = pick(api_body, list_field)
        if isinstance(v, list) and not v:
            return MSG_DATA
    return None
```

`main` 은 Task 6 에서 캡처와 함께 쓰고, 이 태스크에서는 `--check` 만 연결한다.

```python
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("plan", nargs="?")
    ap.add_argument("--out")
    ap.add_argument("--fail", choices=["run", "noscreen"])
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if a.check:
        return _check()
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 통과를 확인한다**

Run: `python3 S/scripts/capture.py --check` 와 윈도우 `python.exe` 로 같은 검사
Expected: `PASS` 줄 9개

- [ ] **Step 5: 커밋한다**

```bash
git add S/scripts/capture.py
git commit -m "feat(kw-dashboard): 캡처 실패 판정"
```

---

### Task 6: capture.py 의 캡처 실행

**Files:**
- Modify: `S/scripts/capture.py`

**Interfaces:**
- Consumes: Task 5 의 `judge` · 문구 상수, Task 4 의 `start` 출력 `url`
- Produces: 캡처 계획 입력과 결과 출력 형식

캡처 계획(`capture_plan.json`, 주 세션이 분석 결과로 만든다):

```json
{"baseUrl": "http://127.0.0.1:53211", "outDir": "<레포>/docs/code-flow/screens", "allowClick": false,
 "features": [{"key": "notices", "path": "/#notices",
   "scenes": [{"id": "notices-0", "click": false,
               "start": {"text": "공고"}, "end": {"selector": "[data-section=notices]"},
               "dataApi": {"path": "/api/notices", "listField": "notices"}}]}]}
```

캡처 결과(`capture_result.json`):

```json
{"features": {"notices": {"screenImg": "screens/notices.png",
  "scenes": {"notices-0": {"start": [12, 77, 185, 40], "end": [256, 197, 1137, 220]}}}}}
```

실패한 장면은 `{"unavailable": "<문구>"}` 만 포함하고, 클릭한 장면은 `endImg` 도 포함한다.

- [ ] **Step 1: 실패 모드 출력을 먼저 검사에 넣는다**

```python
    plan_doc = {"features": [{"key": "a", "scenes": [{"id": "a-0"}, {"id": "a-1"}]}]}
    res = fail_result(plan_doc, MSG_RUN)
    expect("실행 실패는 모든 장면에 같은 문구를 적는다",
           res == {"features": {"a": {"scenes": {"a-0": {"unavailable": MSG_RUN}, "a-1": {"unavailable": MSG_RUN}}}}})
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 S/scripts/capture.py --check`
Expected: `NameError: name 'fail_result' is not defined`

- [ ] **Step 3: 캡처를 구현한다**

```python
def fail_result(plan_doc: dict, msg: str) -> dict:
    return {"features": {f["key"]: {"scenes": {s["id"]: {"unavailable": msg} for s in f["scenes"]}} for f in plan_doc["features"]}}


def _locate(page, target):
    if not target:
        return None
    loc = page.locator(target["selector"]).first if target.get("selector") else page.get_by_text(target["text"]).first
    try:
        box = loc.bounding_box(timeout=3000)
    except Exception:
        return None
    return [round(box["x"]), round(box["y"]), round(box["width"]), round(box["height"])] if box else None


def capture(plan_doc: dict) -> dict:
    from playwright.sync_api import sync_playwright
    out_dir = Path(plan_doc["outDir"]); out_dir.mkdir(parents=True, exist_ok=True)
    result = {"features": {}}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        for f in plan_doc["features"]:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            seen = {}
            page.on("response", lambda r: seen.__setitem__(urlparse(r.url).path, r))
            try:
                # 대시보드는 주기적으로 요청을 보내 networkidle 에 닿지 않을 수 있어 load 뒤 3초를 기다린다
                doc = page.goto(plan_doc["baseUrl"] + f["path"], wait_until="load", timeout=30000)
                page.wait_for_timeout(3000)
            except Exception:
                doc = None
            doc_status = doc.status if doc else 0
            final_path = urlparse(page.url).path
            img = f"{f['key']}.png"
            page.screenshot(path=str(out_dir / img))
            fr = {"screenImg": f"screens/{img}", "scenes": {}}
            for s in f["scenes"]:
                api = s.get("dataApi") or {}
                status, body = None, None
                if api.get("path"):
                    r = seen.get(api["path"])
                    status = r.status if r else 0
                    try:
                        body = r.json() if r else None
                    except Exception:
                        body = None
                msg = judge(doc_status, final_path, status, body, api.get("listField"))
                if msg:
                    fr["scenes"][s["id"]] = {"unavailable": msg}
                    continue
                sr = {k: v for k, v in (("start", _locate(page, s.get("start"))), ("end", _locate(page, s.get("end")))) if v}
                if s.get("click") and plan_doc.get("allowClick") and s.get("start"):
                    try:
                        (page.locator(s["start"]["selector"]).first if s["start"].get("selector") else page.get_by_text(s["start"]["text"]).first).click(timeout=5000)
                        page.wait_for_timeout(3000)
                        end_img = f"{s['id']}_end.png"
                        page.screenshot(path=str(out_dir / end_img))
                        sr["endImg"] = f"screens/{end_img}"
                        end = _locate(page, s.get("end"))
                        if end:
                            sr["end"] = end
                    except Exception:
                        pass  # 클릭이 실패하면 시작 화면 안의 결과 위치로 줌한다
                fr["scenes"][s["id"]] = sr
            result["features"][f["key"]] = fr
            page.close()
        browser.close()
    return result
```

`main` 의 `--check` 처리 뒤에 아래를 넣는다.

```python
    if not a.plan or not a.out:
        ap.error("캡처 계획 경로와 --out 이 필요합니다")
    plan_doc = json.loads(Path(a.plan).read_text(encoding="utf-8"))
    res = fail_result(plan_doc, MSG_RUN if a.fail == "run" else MSG_NOSCREEN) if a.fail else capture(plan_doc)
    Path(a.out).write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print(a.out)
    return 0
```

- [ ] **Step 4: wholesale-dashboard 로 캡처를 확인한다**

WSL 에서 Task 4 의 `start` 로 서버를 실행하고, 윈도우에서 캡처한다(WSL2 는 127.0.0.1 에 연결한 포트를 윈도우 localhost 로 넘긴다).

```bash
python3 S/scripts/run_repo.py start $W --state $ST            # url 확인
# plan.json: market(홈) 장면 하나와 notices 장면 하나, dataApi /api/notices listField notices, outDir 은 /mnt/c/Users/Public/claude-etax/tracecheck/cf/screens
cd /mnt/c && powershell.exe -c "uv run --native-tls --with playwright python <capture.py 윈도우 경로> <plan.json 윈도우 경로> --out <result.json 윈도우 경로>"
python3 S/scripts/run_repo.py stop --state $ST
```
Expected: `market.png` 가 1440×1000 이고, 결과의 notices 장면이 `MSG_DATA` 또는 `MSG_CONFIG` 이며, market 장면에 `start` 사각형이 있다. 개발 PC 확인에서만 `--native-tls` 를 쓰고, 스킬은 `run_repo.py exec` 를 거친다.

- [ ] **Step 5: 커밋한다**

```bash
git add S/scripts/capture.py
git commit -m "feat(kw-dashboard): Chrome 으로 기능별 화면 캡처"
```

---

### Task 7: 분석 · 알아 둘 점 지침

**Files:**
- Create: `S/analysis-prompt.md`, `S/tips-prompt.md`

**Interfaces:**
- Consumes: Task 1 의 흐름 JSON 필드, Task 6 의 캡처 계획 필드
- Produces: 분석 서브에이전트가 돌려줄 JSON(`feature`, `capture`, `clickEffects`, `evidence`, `mismatches`)

- [ ] **Step 1: `analysis-prompt.md` 를 쓴다**

내용은 아래 절로 구성한다. 시제품 분석 결과(`~/02.github/flow_guide/wholesale/a.json`)와 `wholesale_movie.json` 의 기능 하나를 예시로 넣는다.

- 맡은 일: 기능 하나의 코드를 읽어 장면과 동작을 낸다. 파일을 고치지 않는다.
- 문장 규칙: spec 「화면과 문장 규칙」 표의 규칙을 그대로 옮긴다.
- 고정 명칭표: spec 의 종류 표와 구역 표를 그대로 옮기고, `kind` · `zone` 은 표의 값만 쓴다고 적는다.
- 좌표: 960×520 무대의 노드 중심, 왼쪽은 `office`, 중간은 `app` · `ax`, 오른쪽은 `external` 에 둔다.
- 출력 JSON:

```json
{"feature": {"key": "notices", "name": "운용사 선정 공고", "summary": "접수 중인 공고 목록",
             "nodes": [{"id": "pc", "name": "내 PC", "sub": "브라우저", "kind": "screen", "zone": "office", "x": 110, "y": 170}],
             "scenes": [{"title": "…", "tips": [], "screen": {"startName": "「공고」 탭 클릭", "endName": "공고 목록 표시"},
                         "actions": [{"from": "pc", "to": "server", "icon": "ask", "text": "공고 목록 요청", "say": "…"}]}]},
 "capture": {"path": "/#notices",
             "scenes": [{"start": {"text": "공고"}, "end": {"selector": "…"}, "click": false,
                         "dataApi": {"path": "/api/notices", "listField": "notices"}}]},
 "clickEffects": [{"scene": 0, "button": "새로고침", "effects": ["Claude API 호출(과금)", "Redis 저장"], "evidence": ["app/api/notices/route.ts:41"]}],
 "evidence": {"0.0": ["components/tabs/NoticeTab.tsx:41"]},
 "mismatches": ["주석은 회색이라 적지만 코드는 #000000 을 쓴다 (lib/delta.ts:12)"]}
```

- `capture.scenes` 는 `feature.scenes` 와 같은 순서이고, 결과를 보려면 버튼을 눌러야 하는 장면만 `click: true` 로 두고 `clickEffects` 에 그 클릭이 일으키는 외부 API 호출 · 저장소 쓰기 · 메일 발송을 근거와 함께 적는다고 적는다.
- `dataApi.listField` 는 응답 본문에서 목록이 들어 있는 필드 경로(점으로 이음)이고, 샘플 데이터만 쓰는 장면은 `dataApi` 를 비우고 노드를 `code` 로 그린다고 적는다.

- [ ] **Step 2: `tips-prompt.md` 를 쓴다**

- 맡은 일: 장면마다 화면을 읽는 사람이 알아야 할 해석 규칙(색 뜻, 표시 조건, 단위, 예시 값 여부)을 코드에서 찾는다.
- 근거: 항목마다 `파일:줄` 을 적고, 근거가 없는 항목은 내지 않는다.
- 문장 규칙: spec 「화면과 문장 규칙」 표를 그대로 옮긴다.
- 예시: 시제품의 「분홍색(마젠타) 숫자는 증가, 파란색 숫자는 감소, 검은색 숫자는 변동 없음을 뜻합니다.」와 그 근거 줄.
- 출력: `{"tips": {"<장면 번호>": ["…"]}, "evidence": {"<장면 번호>.<항목 번호>": ["파일:줄"]}}`

- [ ] **Step 3: 계약을 확인한다**

Run: `grep -c 'clickEffects\|listField\|unavailable\|startName' S/analysis-prompt.md` 와 `grep -nP '\x{2014}' S/*.md`
Expected: 첫 명령 3 이상, 둘째 명령 0줄

- [ ] **Step 4: 커밋한다**

```bash
git add S/analysis-prompt.md S/tips-prompt.md
git commit -m "feat(kw-dashboard): 기능 분석과 알아 둘 점 지침"
```

---

### Task 8: SKILL.md · 플러그인 설명 · 계약 테스트

**Files:**
- Create: `S/SKILL.md`
- Modify: `plugins/kw-dashboard/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `tests/test_dashboard.ps1`

**Interfaces:**
- Consumes: Task 1 · 3 · 4 · 5 · 6 · 7 의 CLI 와 파일 이름

- [ ] **Step 1: 계약 테스트를 먼저 쓴다**

`tests/test_dashboard.ps1` 의 `--- skill ---` 절 뒤, 합계 출력 앞에 추가한다.

```powershell
Write-Host '--- explaining-code-flow ---'
$FlowDir = Join-Path $PluginDir 'skills/explaining-code-flow'
$flowMd  = Join-Path $FlowDir 'SKILL.md'
$flowText = Read-TextOrEmpty $flowMd
Assert 'explaining-code-flow SKILL.md ships' (Test-Path $flowMd)
Assert 'its frontmatter name matches the folder' (([regex]::Match($flowText, '(?m)^name:\s*(\S+)\s*$')).Groups[1].Value -eq 'explaining-code-flow')
$flowDesc = ([regex]::Match($flowText, '(?m)^description:\s*(.+)$')).Groups[1].Value
Assert 'its description says when to open the skill' ($flowDesc -match '^Use when ')
Assert 'its description is a safe plain scalar' (-not ($flowDesc -match ': | #'))
foreach ($ref in @('analysis-prompt.md', 'tips-prompt.md')) {
    Assert "$ref ships" (Test-Path (Join-Path $FlowDir $ref))
    Assert "SKILL.md links $ref" ($flowText -match [regex]::Escape($ref))
}
foreach ($s in @('render.py', 'run_repo.py', 'capture.py')) {
    $py = Join-Path $FlowDir "scripts/$s"
    Assert "$s ships" (Test-Path $py)
    Assert "every $s call goes through CLAUDE_SKILL_DIR" ($flowText -match [regex]::Escape("`${CLAUDE_SKILL_DIR}/scripts/$s"))
    $null = & python $py --check 2>&1 | Out-String
    Assert "$s --check passes" ($LASTEXITCODE -eq 0)
}
Assert 'movie_template.html ships' (Test-Path (Join-Path $FlowDir 'scripts/movie_template.html'))
$flowAll = (Get-ChildItem $FlowDir -Recurse -File -Include *.md | ForEach-Object { [IO.File]::ReadAllText($_.FullName) }) -join "`n"
Assert 'no flow skill file calls python3' (-not ($flowAll -match '\bpython3\b'))
$flowPy = (Get-ChildItem (Join-Path $FlowDir 'scripts') -File -Include *.py -Recurse | ForEach-Object { [IO.File]::ReadAllText($_.FullName) }) -join "`n"
Assert 'no user-facing script message says Docker' (-not ($flowPy -match '(RepoError|print)\(f?"[^"]*[Dd]ocker'))
Assert 'the plugin description names the flow skill' ($pluginJson.description -match 'explaining-code-flow')
```

- [ ] **Step 2: 실패를 확인한다**

Run: `pwsh -NoProfile -ExecutionPolicy Bypass -File .\tests\test_dashboard.ps1`(윈도우에서 레포 경로로)
Expected: `FAIL  explaining-code-flow SKILL.md ships` 와 description 관련 FAIL

- [ ] **Step 3: SKILL.md 를 쓴다**

머리말:

```yaml
---
name: explaining-code-flow
description: Use when someone wants to see how their repo works feature by feature (which button reads which DB, which server and AI it passes through, and what comes back), especially vibe coders who cannot read the code. Builds a moving guide page with real screen captures in the repo's docs/code-flow folder. Triggers on 코드 흐름·동작 흐름·어떻게 동작하는지·기능별 흐름·흐름 시각화·code flow.
---
```

본문은 spec 「절차」 표의 단계를 순서대로 적고, 단계마다 실행할 명령을 아래 형태로 적는다. 사용자에게 보이는 안내 문장에는 Docker 를 쓰지 않는다.

```text
python "${CLAUDE_SKILL_DIR}/scripts/run_repo.py" exec <레포> -- uv run --no-project --with "pyjwt[crypto]" python "${CLAUDE_SKILL_DIR}/scripts/run_repo.py" doctor <레포>
python "${CLAUDE_SKILL_DIR}/scripts/run_repo.py" exec <레포> -- uv run --no-project --with "pyjwt[crypto]" python "${CLAUDE_SKILL_DIR}/scripts/run_repo.py" start <레포> --state <임시 폴더>/state.json
python "${CLAUDE_SKILL_DIR}/scripts/run_repo.py" exec <레포> -- uv run --no-project --with playwright python "${CLAUDE_SKILL_DIR}/scripts/capture.py" <임시 폴더>/capture_plan.json --out <임시 폴더>/capture_result.json
python "${CLAUDE_SKILL_DIR}/scripts/run_repo.py" stop --state <임시 폴더>/state.json
python "${CLAUDE_SKILL_DIR}/scripts/render.py" <레포>/docs/code-flow/flow.json --out <레포>/docs/code-flow/index.html
```

본문에 반드시 넣을 규칙:
- 기능 목록은 사용자 승인 뒤 분석한다. 분석 서브에이전트에는 `analysis-prompt.md` 와 `tips-prompt.md` 경로를 넣는다.
- 클릭 승인은 `clickEffects` 를 모아 한 목록으로 보여 주고 한 번만 묻는다. 승인하면 캡처 계획의 `allowClick` 을 `true` 로 둔다.
- `stop` 은 캡처가 실패해도 반드시 실행한다. `stop` 이 종료 코드 3 이면 바뀐 추적 파일을 사용자에게 알린다.
- `start` 가 실패하면 `capture.py --fail run`, 화면 코드가 없으면 `--fail noscreen` 으로 결과를 만든다.
- JSON 합치기: `capture_result.json` 의 `screenImg` 를 기능에, 장면별 `start` · `end` · `endImg` · `unavailable` 을 `screen` 에 넣는다. 클릭한 장면은 `startImg` 를 기능의 `screenImg` 로 둔다.
- 결과물 폴더에 `.gitignore`(`*`)를 만들고 `git status --short docs/code-flow` 가 빈 출력인지 확인한다.
- 결과를 알릴 때 「다른 사람에게 줄 때는 HTML 과 `screens/` 폴더를 함께 준다」와 「캡처와 HTML 에 실제 데이터가 들어 있으니 받을 사람을 확인한다」를 함께 적는다.
- 고정 명칭표, 화면과 문장 규칙(spec 표 그대로).
- 코드와 다른 점은 고치지 않고 `mismatches` 를 모아 알린다.

- [ ] **Step 4: 플러그인 설명을 고친다**

`plugin.json` 과 `marketplace.json` 의 kw-dashboard `description` 끝에 같은 문장을 붙인다.

```text
 explaining-code-flow 는 레포의 기능별 동작 흐름을 실제 화면 캡처와 함께 움직이는 안내 화면으로 만든다.
```

- [ ] **Step 5: 계약 테스트 통과를 확인한다**

Run: `pwsh -NoProfile -ExecutionPolicy Bypass -File .\tests\test_dashboard.ps1`
Expected: FAIL 0

- [ ] **Step 6: 커밋한다**

```bash
git add S/SKILL.md plugins/kw-dashboard/.claude-plugin/plugin.json .claude-plugin/marketplace.json tests/test_dashboard.ps1
git commit -m "feat(kw-dashboard): explaining-code-flow 스킬 절차와 계약 테스트"
```

---

### Task 9: wholesale-dashboard 로 처음부터 끝까지 확인

**Files:**
- 레포 파일은 바뀌지 않는다. 결과물은 `wholesale-dashboard/docs/code-flow/` 에 생기고 git 에서 제외된다.

- [ ] **Step 1: 스킬 절차대로 실행한다**

이 세션에서 `S/SKILL.md` 를 따라 wholesale-dashboard 를 대상으로 처음부터 실행한다. 기능 목록 승인과 클릭 승인은 사용자에게 묻는다.

- [ ] **Step 2: 결과를 확인한다**

Run:
```bash
W=~/02.github/Kiwoom-dashboard/wholesale-dashboard
ls $W/docs/code-flow $W/docs/code-flow/screens
git -C $W status --short           # 빈 출력
python3 S/scripts/render.py $W/docs/code-flow/flow.json --out /tmp/claude-1000/cf/check.html
```
Expected: `index.html` · `flow.json` · `.gitignore` · `screens/*.png` 가 있고, `git status` 가 빈 출력이며, 공고 장면 화면 칸에 실패 문구가 나온다. 시제품 `wholesale_movie.html` 과 기능 목록 · 장면 수를 대조해 사용자에게 차이를 보고한다.

- [ ] **Step 3: 사용자가 브라우저에서 재생을 확인한다**

`index.html` 을 브라우저로 열어 사용자에게 보여 주고, 재생 · 이전 · 다음 · 번호 클릭이 동작하는지 확인받는다.
