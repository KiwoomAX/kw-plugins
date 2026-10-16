# 사용자 설명서 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `explaining-code-flow` 스킬이 같은 `flow.json` 으로 개발자용 안내 화면(`index.html`)과 사용자 설명서(`manual.html`)를 함께 만들고, 화면 항목 목록으로 빠진 설명을 채운다.

**Architecture:** 분석 · 캡처 · 합치기는 지금 절차를 그대로 쓰고, `flow.json` 에 최상위 `tour`(설명서 맨 위 「0. 화면 둘러보기」)를 더한다. `capture.py` 는 둘러보기 화면으로 고른 장면의 결과 화면에서 항목 위치를 측정하고, `render.py` 는 번호를 매긴 뒤 두 템플릿으로 HTML 두 개를 쓴다. 항목 목록은 새 지침 `areas-prompt.md` 를 받는 항목 서브에이전트가 기능 분석과 동시에 낸다.

**Tech Stack:** Python 3(표준 라이브러리), Playwright(`uv run --no-project --with playwright`, PC 의 Chrome), 바닐라 HTML · JS 템플릿, PowerShell 7 계약 테스트(`tests/test_dashboard.ps1`).

**Spec:** `docs/superpowers/specs/2026-10-14-code-flow-guide-design.md` (커밋 `e0d4926`). 시안: `C:\Users\Public\claude-etax\tracecheck\cf-manual-mock\manual-play.src.html`(https://claude.ai/artifact/XMKjr2vfuNaCMw5CRkx3kb).

## Global Constraints

- 두 HTML 은 언제나 함께, 같은 `flow.json` 에서 만든다. 설명서만 만드는 옵션은 두지 않는다.
- 설명서는 흐름 그림 · 동작 설명 · 결함(`defect`) 표시를 그리지 않는다. 참고 알아 둘 점은 접지 않고 펼친다.
- 둘러보기는 설명서에만 있고, 개발자용 안내 화면(`movie_template.html`)은 바꾸지 않는다.
- 배율 식 `Math.max(0.6, Math.min(1, innerWidth / 2400))`, 재생 속도 0.5~2배, 구분선 30~80% · 기본 3 : 2 는 개발자용 템플릿과 같은 값이다.
- 둘러보기 화면은 움직이지 않고, 전체 재생 중 6초 보여 준 뒤 넘어간다.
- 항목 위치 측정에서 화면에 보이는 후보가 없거나 둘 이상이면 「찾지 못함」이다(`first: true` 항목만 첫 번째 후보를 쓴다).
- `flow.json` 에는 항목의 `target` · `evidence` 를 넣지 않는다. 항목 필수 필드는 `name` · `meaning` 이다.
- 화면 코드가 다른 레포에 있는 레포는 지원하지 않는다.
- 스크립트는 윈도우 PowerShell 에서 `python` 으로 실행된다. 스킬 문서에 `python3` 와 날짜를 쓰지 않는다(계약 테스트가 검사한다).
- 커밋 메시지에 Co-Authored-By · Generated 줄을 넣지 않는다.

## Review Focus

- 둘러보기 화면으로 고른 장면의 캡처가 실패한 때: 그 화면은 `unavailable` 문구로 보이고 설명서는 그대로 만들어져야 한다 → Task 2 `capture_tour_result` 테스트, Task 1 검사 테스트.
- 항목 위치를 하나도 찾지 못한 화면: 번호 없이 표만 보이고 렌더가 멈추지 않아야 한다 → Task 1 번호 매기기 테스트.
- 번호 표시가 서로 겹치는 칸(배지가 테두리 안): 렌더가 멈추지 않고 템플릿이 뒤 번호를 비켜 놓아야 한다 → Task 3 `nudge` 확인.
- 챗봇 기능만 있거나 `tour` 가 빈 목록인 레포: 설명서가 빈 0번 없이 만들어져야 한다 → Task 1 빈 `tour` 테스트, Task 3 확인.
- 같은 글자가 여럿인 화면의 항목(예: 「초기화」가 두 곳): 엉뚱한 칸을 성공으로 잡지 않아야 한다 → Task 2 `pick_unique` 테스트.

---

### Task 1: `render.py` 가 `tour` 를 검사하고 번호를 매겨 HTML 두 개를 쓴다

**Files:**
- Modify: `plugins/kw-dashboard/skills/explaining-code-flow/scripts/render.py`
- Modify: `docs/superpowers/specs/2026-10-14-code-flow-guide-design.md`(절차 표 「JSON 합치기」 줄, JSON 형식 표 `no` · `rect` 줄)

**Interfaces:**
- Produces: `validate(data) -> list[str]`(tour 검사 추가), `number_tour(data) -> dict`(항목에 `no` 를 매긴 사본), `render(data, template) -> str`(그대로), `render_all(data, out_dir: Path) -> list[Path]`(`index.html` · `manual.html`). CLI `python render.py <flow.json> --out-dir <폴더>`.

- [ ] **Step 1: 실패하는 검사를 `_check()` 에 추가한다**

`SAMPLE` 최상위에 아래 `tour` 를 더한다.

```python
    "tour": [{"key": "home", "name": "홈 화면", "img": "screens/home.png",
              "areas": [{"name": "검색창", "meaning": "제목과 본문에서 찾습니다.", "rect": [12, 77, 185, 40]},
                        {"name": "결과 표", "meaning": "검색 결과입니다.", "rect": [12, 140, 800, 300]},
                        {"name": "보라 테두리", "meaning": "지난달과 등급이 다른 행입니다."}]}],
```

`_check()` 의 `return` 앞에 넣는다.

```python
    numbered = number_tour(SAMPLE)["tour"][0]["areas"]
    expect("위치를 찾은 항목에만 위에서 아래 순서로 번호를 매긴다",
           [a.get("no") for a in numbered] == [1, 2, None])
    expect("tour 가 있는 예제도 검사를 통과한다", validate(number_tour(SAMPLE)) == [])
    nr = copy.deepcopy(number_tour(SAMPLE)); del nr["tour"][0]["areas"][0]["rect"]
    expect("위치 없이 번호만 있는 항목을 잡는다", any("areas[0]" in e and "번호" in e for e in validate(nr)))
    tb = copy.deepcopy(number_tour(SAMPLE))
    tb["tour"][0]["unavailable"] = "화면을 만들 수 없습니다."
    tb["tour"][0]["areas"][0]["rect"] = [99999, 0, 1, 1]
    del tb["tour"][0]["areas"][1]["meaning"]
    errs = validate(tb)
    expect("둘러보기 화면에 캡처와 실패 문구가 함께 있으면 잡는다", any("tour[0]" in e and "실패 문구" in e for e in errs))
    expect("1440×1000 밖의 항목 위치를 잡는다", any("areas[0].rect" in e for e in errs))
    expect("뜻 없는 항목을 잡는다", any("areas[1].meaning" in e for e in errs))
    dup = copy.deepcopy(number_tour(SAMPLE)); dup["tour"][0]["areas"][1]["no"] = 1
    expect("같은 화면의 번호 중복을 잡는다", any("번호" in e and "중복" in e for e in validate(dup)))
    empty = copy.deepcopy(SAMPLE); empty["tour"] = []
    expect("tour 가 빈 목록이어도 통과한다", validate(number_tour(empty)) == [])
    notour = copy.deepcopy(SAMPLE); del notour["tour"]
    expect("tour 가 없으면 잡는다", any("flow.tour" in e for e in validate(notour)))
    import tempfile
    with tempfile.TemporaryDirectory() as t:
        outs = render_all(number_tour(SAMPLE), Path(t))
        expect("index.html 과 manual.html 을 함께 쓴다", sorted(p.name for p in outs) == ["index.html", "manual.html"])
        man = (Path(t) / "manual.html").read_text(encoding="utf-8")
        expect("설명서에 자리표시 문자열이 남지 않는다", "__DATA__" not in man and "__TITLE__" not in man)
    mtpl = (HERE / "manual_template.html").read_text(encoding="utf-8")
    expect("설명서 템플릿에 자리표시 문자열이 한 번씩만 있다", mtpl.count("__TITLE__") == 1 and mtpl.count("__DATA__") == 1)
```

- [ ] **Step 2: 실패를 확인한다**

Run: `cd plugins/kw-dashboard/skills/explaining-code-flow/scripts && python3 render.py --check`
Expected: `NameError: name 'number_tour' is not defined` 로 멈춘다.

- [ ] **Step 3: 구현한다**

`validate()` 의 `need(data, [...], "flow")` 를 `need(data, ["title", "repo", "appZone", "features"], "flow")` 그대로 두고, 바로 아래에 넣는다.

```python
    if not isinstance(data.get("tour"), list):
        errs.append("flow.tour 목록이 없습니다(둘러보기 화면이 없으면 빈 목록 [] 을 둡니다)")
    for ti, sc in enumerate(data.get("tour") or []):
        tw = f"tour[{ti}]"
        need(sc, ["key", "name"], tw)
        if not isinstance(sc.get("areas"), list):
            errs.append(f"{tw}.areas 목록이 없습니다")
        if sc.get("img") and sc.get("unavailable"):
            errs.append(f"{tw} 에 캡처와 실패 문구가 함께 있습니다")
        if not sc.get("img") and not sc.get("unavailable"):
            errs.append(f"{tw} 에 캡처도 실패 문구도 없습니다")
        seen = set()
        for ai, a in enumerate(sc.get("areas") or []):
            aw = f"{tw}.areas[{ai}]"
            need(a, ["name", "meaning"], aw)
            if "rect" in a and not rect_ok(a["rect"]):
                errs.append(f"{aw}.rect 는 1440×1000 안의 [x, y, 폭, 높이] 여야 합니다")
            if "no" in a and "rect" not in a:
                errs.append(f"{aw} 는 위치(rect) 없이 번호(no)만 있습니다")
            if "no" in a:
                if a["no"] in seen:
                    errs.append(f"{tw} 의 번호 {a['no']} 가 중복입니다")
                seen.add(a["no"])
```

`rect_ok` 는 지금 `validate` 안에 정의되어 있으므로 위 코드는 `rect_ok` 정의 뒤에 둔다. `render()` 아래에 넣는다.

```python
def number_tour(data: dict) -> dict:
    """위치를 찾은 항목에만 위에서 아래, 왼쪽에서 오른쪽 순서로 번호를 매긴 사본을 돌려준다."""
    out = copy.deepcopy(data)
    for sc in out.get("tour") or []:
        located = sorted((a for a in sc.get("areas") or [] if a.get("rect")), key=lambda a: (a["rect"][1], a["rect"][0]))
        for a in sc.get("areas") or []:
            a.pop("no", None)
        for i, a in enumerate(located, 1):
            a["no"] = i
    return out


def render_all(data: dict, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    outs = []
    for name, tpl in (("index.html", "movie_template.html"), ("manual.html", "manual_template.html")):
        p = out_dir / name
        p.write_text(render(data, tpl), encoding="utf-8")
        outs.append(p)
    return outs
```

`main()` 을 바꾼다: `--out` 대신 `--out-dir` 를 받고, 읽은 직후 `data = number_tour(data)` 를 한 뒤 `validate`, 통과하면 `for p in render_all(data, Path(a.out_dir)): print(p)`. 오류 문구 `"흐름 JSON 경로와 --out 이 필요합니다"` 를 `"흐름 JSON 경로와 --out-dir 이 필요합니다"` 로 바꾼다. 문서 첫 줄 docstring 을 `"""흐름 JSON 을 검사하고 템플릿에 넣어 개발자용 안내 화면과 사용자 설명서 HTML 을 함께 만든다.` 와 사용법 `python render.py <flow.json> --out-dir <docs/code-flow 폴더>` 로 바꾼다.

이 단계에서는 `manual_template.html` 이 아직 없으므로, Task 3 의 Step 1 이 만들 때까지 빈 틀을 둔다.

```bash
printf '<!doctype html><title>__TITLE__</title><script id="data" type="application/json">__DATA__</script>\n' > manual_template.html
```

spec 의 절차 표 「JSON 합치기」 줄에서 「위치를 찾은 항목에만 위에서 아래, 왼쪽에서 오른쪽 순서로 번호를 매긴다」를 「번호는 `render.py` 가 렌더할 때 위치를 찾은 항목에만 위에서 아래, 왼쪽에서 오른쪽 순서로 매긴다」로, JSON 형식 표의 `no` · `rect` 줄 괄호 안 「주 세션이 합치기 단계에서 번호를 매기고」를 「`render.py` 가 번호를 매기고」로 고친다.

- [ ] **Step 4: 통과를 확인한다**

Run: `python3 render.py --check`
Expected: 모든 줄 PASS, 종료 코드 0.

- [ ] **Step 5: 커밋한다**

```bash
git add plugins/kw-dashboard/skills/explaining-code-flow/scripts/render.py plugins/kw-dashboard/skills/explaining-code-flow/scripts/manual_template.html docs/superpowers/specs/2026-10-14-code-flow-guide-design.md
git commit -m "feat(kw-dashboard): render.py 가 둘러보기(tour)를 검사하고 번호를 매겨 index.html 과 manual.html 을 함께 쓴다"
```

### Task 2: `capture.py` 가 둘러보기 화면의 항목 위치를 측정한다

**Files:**
- Modify: `plugins/kw-dashboard/skills/explaining-code-flow/scripts/capture.py`

**Interfaces:**
- Consumes: 캡처 계획의 최상위 `tour`: `[{"key", "scene": "<장면 id>", "areas": [{"name", "target": {...}, "first": bool?}]}]`.
- Produces: `pick_unique(seen: list[bool], first: bool = False) -> int | None`, `capture_tour_result(tour_plan, scene_results, rects) -> list[dict]`, 결과 JSON 최상위 `tour`: `[{"key", "img" | "unavailable", "rects": {"<항목 순번>": [x, y, w, h]}}]`.

- [ ] **Step 1: 실패하는 검사를 `_check()` 에 추가한다**

```python
    expect("보이는 후보가 하나면 그 후보를 고른다", pick_unique([False, True, False]) == 1)
    expect("보이는 후보가 둘 이상이면 찾지 못함이다", pick_unique([True, True]) is None)
    expect("보이는 후보가 없으면 찾지 못함이다", pick_unique([False]) is None)
    expect("first 항목은 보이는 첫 후보를 고른다", pick_unique([False, True, True], first=True) == 1)
    tp = [{"key": "result", "scene": "result-1", "areas": [{"name": "a"}, {"name": "b"}]},
          {"key": "input", "scene": "input-4", "areas": [{"name": "c"}]}]
    sr = {"result-1": {"endImg": "screens/result-1_end.png"}, "input-4": {"unavailable": MSG_STEP}}
    got = capture_tour_result(tp, sr, {"result-1": {0: [1, 2, 3, 4]}})
    expect("둘러보기 화면은 그 장면의 결과 화면과 찾은 위치를 쓴다",
           got[0] == {"key": "result", "img": "screens/result-1_end.png", "rects": {"0": [1, 2, 3, 4]}})
    expect("장면 캡처가 실패한 둘러보기 화면은 실패 문구를 적는다",
           got[1] == {"key": "input", "unavailable": "둘러보기 화면을 캡처하지 못했습니다."})
    terr = plan_errors({"features": [{"scenes": [{"id": "a-0"}]}], "tour": [{"key": "x", "scene": "a-9", "areas": [{"name": "n"}]}]})
    expect("둘러보기가 없는 장면을 가리키면 잡는다", any("a-9" in e for e in terr))
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 capture.py --check`
Expected: `NameError: name 'pick_unique' is not defined`.

- [ ] **Step 3: 구현한다**

`_locate` 아래에 넣는다.

```python
MSG_TOUR = "둘러보기 화면을 캡처하지 못했습니다."


def pick_unique(seen: list[bool], first: bool = False) -> int | None:
    """보이는 후보 중 하나를 고른다. 둘러보기 번호가 엉뚱한 칸에 찍히지 않도록 후보가 둘 이상이면 고르지 않는다."""
    idx = [i for i, v in enumerate(seen) if v]
    if not idx:
        return None
    if first:
        return idx[0]
    return idx[0] if len(idx) == 1 else None


def _locate_area(page, area):
    """둘러보기 항목의 위치. 정확히 같은 글자(또는 선택자) 후보만 보고, 하나로 정해질 때만 사각형을 돌려준다."""
    loc = _candidates(page, area["target"])[0]
    els = loc.all()[:20]
    seen = []
    for el in els:
        try:
            seen.append(bool(el.evaluate(_SEEN)))
        except Exception:
            seen.append(False)
    i = pick_unique(seen, area.get("first", False))
    if i is None:
        return None
    box = els[i].bounding_box()
    return [round(box["x"]), round(box["y"]), round(box["width"]), round(box["height"])] if box else None


def capture_tour_result(tour_plan: list[dict], scene_results: dict, rects: dict) -> list[dict]:
    out = []
    for t in tour_plan:
        sr = scene_results.get(t["scene"], {})
        if not sr.get("endImg"):
            out.append({"key": t["key"], "unavailable": MSG_TOUR})
            continue
        out.append({"key": t["key"], "img": sr["endImg"],
                    "rects": {str(i): r for i, r in (rects.get(t["scene"]) or {}).items() if r}})
    return out
```

`plan_errors` 끝(`return errs` 앞)에 넣는다.

```python
    ids = {s.get("id") for f in plan_doc.get("features", []) for s in f.get("scenes", [])}
    for t in plan_doc.get("tour", []):
        if t.get("scene") not in ids:
            errs.append(f"둘러보기 {t.get('key')}: 장면 {t.get('scene')!r} 가 계획에 없습니다")
        for i, a in enumerate(t.get("areas", [])):
            if not isinstance(a.get("target"), dict):
                errs.append(f"둘러보기 {t.get('key')} 항목 {i}: target 이 없습니다")
```

`capture()` 에서 `result = {"features": {}}` 아래에 `tour_rects = {}` 와 `tours_by_scene = {}` 를 두고, `for t in plan_doc.get("tour", []): tours_by_scene.setdefault(t["scene"], []).append(t)` 를 넣는다. 장면 루프의 `sr["endImg"] = ...` 와 `end = _locate(...)` 사이에 넣는다.

```python
                        for t in tours_by_scene.get(s["id"], []):
                            tour_rects[s["id"]] = {i: _locate_area(cp, a) for i, a in enumerate(t["areas"])}
```

`browser.close()` 다음, `return result` 앞에 `result["tour"] = capture_tour_result(plan_doc.get("tour", []), {sid: r for fr in result["features"].values() for sid, r in fr["scenes"].items()}, tour_rects)` 를 넣는다. `fail_result()` 의 반환값에도 `"tour": [{"key": t["key"], "unavailable": msg} for t in plan_doc.get("tour", [])]` 를 더한다.

- [ ] **Step 4: 통과를 확인한다**

Run: `python3 capture.py --check`
Expected: 모든 줄 PASS. 기존 「띄우지 못한 화면은 모든 장면에 같은 문구를 적는다」 기대값에 `"tour": []` 가 더해졌으므로 그 줄의 기대값을 `{"features": {...}, "tour": []}` 로 고친다.

- [ ] **Step 5: 커밋한다**

```bash
git add plugins/kw-dashboard/skills/explaining-code-flow/scripts/capture.py
git commit -m "feat(kw-dashboard): capture.py 가 둘러보기 화면의 항목 위치를 하나로 정해질 때만 측정한다"
```

### Task 3: 설명서 템플릿 `manual_template.html`

**Files:**
- Create: `plugins/kw-dashboard/skills/explaining-code-flow/scripts/manual_template.html`(Task 1 의 빈 틀을 덮어쓴다)

**Interfaces:**
- Consumes: `flow.json` 그대로(`features[]` · `tour[]`, Task 1 이 매긴 `no`).
- Produces: `__TITLE__` · `__DATA__` 를 한 번씩 가진 템플릿.

- [ ] **Step 1: 시안을 복사한다**

```bash
cp /mnt/c/Users/Public/claude-etax/tracecheck/cf-manual-mock/manual-play.src.html plugins/kw-dashboard/skills/explaining-code-flow/scripts/manual_template.html
```

- [ ] **Step 2: 시안 전용 부분을 고친다**

1. 첫 줄 `<title>RM 사용 설명서 예시</title>` 를 `<title>__TITLE__</title>` 로, 목록 머리 `<h1>Kiwoom-RM 사용 설명서</h1>` 를 `<h1 id="manualTitle"></h1>` 로 바꾸고, 그 아래 「시안: …」 `<p class="note">` 줄을 지운다.
2. `.areas em` · `.trace` CSS 와, `side()` 안의 `<em class=…>코드 확인…</em>` · `<details class="trace">…</details>` 를 지운다(시안 확인용).
3. `const D = JSON.parse(...)` 줄 바로 아래에 `flow.json` 을 시안 형식으로 바꾸는 코드를 넣는다.

```js
const RAW = D, SRC_ZONES = ['winus', 'fund', 'external'];
document.getElementById('manualTitle').textContent = RAW.title.replace(/, 움직이며 보기$/, '') + ' 사용 설명서';
const tour = (RAW.tour || []).map(t => ({title: t.name, overview: true, auto: false, tips: [], img: t.img, unavailable: t.unavailable,
  areas: t.areas.map(a => ({name: a.name, m: a.meaning, no: a.no, r: a.rect}))}));
D.features = [
  ...(tour.length ? [{name: '화면 둘러보기', overviewGroup: true, summary: '화면의 각 칸이 무엇을 뜻하는지 보입니다.', prereq: null, sources: [], scenes: tour}] : []),
  ...RAW.features.map(f => ({name: f.name, summary: f.summary, prereq: f.prereq || null, chatbot: !!f.chatbot,
    sources: [...new Set((f.nodes || []).filter(n => SRC_ZONES.includes(n.zone)).map(n => n.name))],
    scenes: (f.scenes || []).map(s => ({title: s.title, auto: !!s.auto, tips: s.tips || [], screen: s.screen || {},
      img0: (s.screen || {}).startImg || f.screenImg}))})),
];
```

4. `play()` 의 둘러보기 분기에서 번호는 `ar.no` 가 있는 항목만 찍고(`s.areas.filter(ar => ar.no)`), 번호 글자는 `ar.no` 를 쓴다. 표의 번호 칸도 `a.no || '–'` 로 바꾼다. `s.unavailable` 이면 `camera` 대신 `view` 에 `<div class="wait">${esc(s.unavailable)}</div>` 를 보이고 6초 뒤 넘어간다.
5. 번호 표시가 겹치면 비켜 놓는다. 둘러보기 분기에서 번호를 그린 뒤 부른다.

```js
function nudge() {  // 앞 번호와 44px 안으로 붙은 번호는 오른쪽 아래로 옮긴다(배지가 테두리 안에 있는 칸)
  const pins = [...document.querySelectorAll('#pins .pinx')], placed = [];
  pins.forEach(p => {
    let x = parseFloat(p.style.left), y = parseFloat(p.style.top);
    while (placed.some(q => Math.abs(q[0] - x) < 44 && Math.abs(q[1] - y) < 44)) { x += 36; y += 36; }
    p.style.left = x + 'px'; p.style.top = y + 'px'; placed.push([x, y]);
  });
}
```

6. 챗봇 기능(`f.chatbot`)이면 `play()` 첫머리에서 장면 제목 자리에 「챗봇 기능 안내는 개발 중입니다」를 보이고 캡처를 숨긴 채 끝낸다. 왼쪽 목록에는 기능 제목만 보인다.

- [ ] **Step 3: 렌더해 정지 화면을 확인한다**

Run:
```bash
cd plugins/kw-dashboard/skills/explaining-code-flow/scripts && python3 render.py --check && python3 -c "import json,render;json.dump(render.number_tour(render.SAMPLE),open('/tmp/claude-1000/sample_flow.json','w'),ensure_ascii=False)" && python3 render.py /tmp/claude-1000/sample_flow.json --out-dir /mnt/c/Users/Public/claude-etax/tracecheck/cf-manual-mock/sample_out
"/mnt/c/Program Files/Google/Chrome/Application/chrome.exe" --headless=new --disable-gpu --window-size=1920,1000 --virtual-time-budget=1500 --screenshot='C:\Users\Public\claude-etax\tracecheck\cf-manual-mock\sample_out\m.png' 'C:\Users\Public\claude-etax\tracecheck\cf-manual-mock\sample_out\manual.html'
```
Expected: `render.py --check` 모두 PASS. `m.png` 에 「0. 화면 둘러보기」 목록, 번호 두 개, 「화면 항목」 표(셋째 항목은 번호 「–」)가 보이고, 결함 항목(「조회가 실패해도 예시 값이…」)은 「1. 홈」 장면 알아 둘 점에 보이지 않는다.

- [ ] **Step 4: 커밋한다**

```bash
git add plugins/kw-dashboard/skills/explaining-code-flow/scripts/manual_template.html
git commit -m "feat(kw-dashboard): 사용자 설명서 템플릿을 시안에서 옮겨 flow.json 을 그대로 읽게 한다"
```

### Task 4: 항목 서브에이전트 지침과 분석 · 알아 둘 점 지침

**Files:**
- Create: `plugins/kw-dashboard/skills/explaining-code-flow/areas-prompt.md`
- Modify: `plugins/kw-dashboard/skills/explaining-code-flow/analysis-prompt.md`(「문장 규칙」 표)
- Modify: `plugins/kw-dashboard/skills/explaining-code-flow/tips-prompt.md`(「등급」 표의 「싣지 않음」 줄, 「항목 표시」 절)

**Interfaces:**
- Produces: 항목 서브에이전트 출력 JSON `{"screen": {"key", "name", "scene": "<장면 id>"}, "areas": [{"name", "meaning", "target", "first"?, "evidence": ["레포 상대 경로:줄"]}], "excluded": [{"line": "파일:줄", "reason"}], "unresolved": ["항목 이름"]}`.

- [ ] **Step 1: `areas-prompt.md` 를 만든다**

````markdown
# 화면 항목 지침

이 지침은 항목 서브에이전트가 화면 하나에서 사람이 보는 항목을 모두 나열하고, 항목마다 뜻을 코드에서 찾는 방법을 정한다. 결과는 사용자 설명서 맨 위 「0. 화면 둘러보기」의 「화면 항목」 표가 되고, 주 세션은 이 목록으로 장면과 알아 둘 점에서 빠진 설명을 찾는다. 파일은 읽기만 하고 고치지 않는다.

## 나열

주 세션이 맡긴 화면(장면 id 와 그 장면의 결과 화면)을 그리는 렌더 코드를 읽고, 사람이 보는 항목을 모두 낸다.

| 대상 | 예 |
|---|---|
| 입력 칸 · 고르는 칸 | 기준 연도, 펀드코드 칸 |
| 버튼 · 탭 · 거르기 버튼 | 위너스 저장, 「변경 factor」, 「변동 펀드」 |
| 배지 · 색 · 테두리 · 아이콘으로 상태를 보이는 규칙 | 보라 테두리와 「변경」 배지, G · Y · A · R 배지 |
| 툴팁 · 빈 상태 · 오류 표시 | 「Operating Info가 없습니다」 |

- 조건부로 그려지는 줄, 조건부 class · style, 이벤트 처리(`onClick` · `onChange` 등) 줄마다 항목을 내거나 `excluded` 에 제외 사유를 적는다.
- 반복해서 그려지는 카드 · 행은 종류마다 한 항목으로 센다. 행마다 그려지는 표시 규칙은 `"first": true` 를 붙여 첫 번째 해당 요소를 위치 대상으로 삼게 한다.
- 화면에서 도달할 수 없는 항목(쓰이지 않는 prop, import 되지 않는 부품)은 내지 않는다.

## 뜻

- 항목마다 값의 출처를 코드에서 거꾸로 따라간다. 순서는 화면 상태 → 상위 화면이 넘기는 값 → API 응답 필드 → 백엔드 계산 · 조회 → 테이블이다. 테이블, 외부 응답, LLM 출력에 닿으면 멈춘다.
- 뜻은 닿은 데까지만 사용자 말로 한두 문장에 적는다. 서버 · 함수 이름은 쓰지 않는다. 뜻을 정하지 못한 항목도 렌더 줄을 근거로 내고, 이름을 `unresolved` 에 적는다.
- 「테두리가 보라색이다」 같은 묘사는 뜻이 아니다. 「보라 테두리는 지난달과 등급이 다르거나 지난달 기록이 없는 요인이다」처럼 그 상태가 무엇을 뜻하는지 적는다.
- 업무 용어(예: 공실률, DSCR)의 정의는 레포의 프롬프트 · 문서에 정의가 있을 때만 적는다.
- 값이 없거나 조회에 실패할 때 화면이 무엇을 보이는지도 확인해 뜻에 넣는다. 예: 「이력 조회에 실패하면 일반 펀드는 G 로, 블라인드 펀드는 현재 종합등급과 같은 등급으로 보입니다」.

## 찾는 방법

`target` 은 캡처가 결과 화면에서 그 칸의 위치를 찾는 방법이다. 화면에 보이는 글자는 `{"text": "펀드 종합등급"}`, 글자가 없거나 같은 글자가 여럿이면 `{"selector": "CSS 선택자"}` 로 적는다. 캡처는 후보가 하나로 정해질 때만 번호를 찍는다.

## 출력

JSON 하나만 돌려준다. 근거 경로는 레포 상대 경로다.

```json
{"screen": {"key": "result", "name": "위험등급 산정 결과 화면", "scene": "result-1"},
 "areas": [
  {"name": "펀드 종합등급", "meaning": "왼쪽 「이전」은 직전 월까지 WINUS 에 저장된 가장 최근 위험등급이고, 오른쪽 「현재」는 이번 산정 등급입니다.",
   "target": {"text": "펀드 종합등급"}, "evidence": ["src/components/GradeSummary.tsx:36-39", "src/repositories/risk/loader.py:252-272"]},
  {"name": "보라 테두리 · 「변경」 배지", "meaning": "지난달과 등급이 다르거나 지난달 기록이 없는 요인입니다.",
   "target": {"selector": ".factor-card.changed"}, "first": true, "evidence": ["src/components/FactorCardList.tsx:56-67"]}],
 "excluded": [{"line": "src/components/RiskGradeResultView.tsx:520", "reason": "개발 중 디버그 표시로 화면에서 도달할 수 없음"}],
 "unresolved": []}
```
````

- [ ] **Step 2: `analysis-prompt.md` 「문장 규칙」 표에 줄을 더한다**

```markdown
| 기능 `summary` 는 서버 · 함수 이름 없이 화면을 쓰는 사람의 시각으로 쓴다. 예: 「기준 보고월과 대상을 고르면 펀드마다 위험등급을 매깁니다」 | 사용자 설명서의 「이 기능으로 하는 일」에 그대로 보인다 |
```

- [ ] **Step 3: `tips-prompt.md` 를 고친다**

「등급」 표의 「싣지 않음」 줄 판정 칸을 「화면에 이미 글자로 보이는 안내를 다시 말하는 규칙, 눈에 보이는 상태(테두리, 바탕색, 흐려짐)를 묘사만 하는 규칙. 그 상태가 무엇을 뜻하는지는 화면에 적혀 있지 않으면 핵심이다」로, 예 칸에 「「테두리가 보라색이다」(묘사) · 「보라 테두리는 등급이 바뀐 요인이다」(뜻, 핵심)」를 더한다. 「항목 표시」 절의 `defect: true` 설명 뒤에 한 문장을 넣는다: 「사용자 설명서는 결함 표시를 숨기므로, 사용자 행동에 영향을 주는 결함은 같은 사실을 사용자 시각의 `core` 항목으로도 따로 낸다. 예: 「완료 알림이 떠도 저장이 실패했을 수 있습니다.」」

- [ ] **Step 4: 문서 검사를 실행한다**

Run: `cd /mnt/c && pwsh.exe -NoProfile -File '\\wsl.localhost\Ubuntu\home\rladustn1227\02.github\Kiwoom-dashboard\kw-plugins-code-flow\tests\test_dashboard.ps1' 2>&1 | grep -aE "FAIL|PASS="`
Expected: `FAIL` 줄이 없고(새 문서에 날짜 · `python3` 없음), `PASS=` 줄이 나온다.

- [ ] **Step 5: 커밋한다**

```bash
git add plugins/kw-dashboard/skills/explaining-code-flow/areas-prompt.md plugins/kw-dashboard/skills/explaining-code-flow/analysis-prompt.md plugins/kw-dashboard/skills/explaining-code-flow/tips-prompt.md
git commit -m "docs(kw-dashboard): 화면 항목 지침을 만들고 요약 · 결함 · 상태 묘사 규칙을 지침에 적는다"
```

### Task 5: `SKILL.md` 절차 · 플러그인 설명 · 계약 테스트

**Files:**
- Modify: `plugins/kw-dashboard/skills/explaining-code-flow/SKILL.md`
- Modify: `plugins/kw-dashboard/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`(kw-dashboard 항목)
- Modify: `tests/test_dashboard.ps1`

**Interfaces:**
- Consumes: Task 1 의 `--out-dir`, Task 2 의 계획 `tour` · 결과 `tour`, Task 4 의 항목 출력 형식.

- [ ] **Step 1: 계약 테스트에 실패할 검사를 더한다**

`tests/test_dashboard.ps1` 의 `foreach ($ref in @('analysis-prompt.md', 'tips-prompt.md'))` 를 `@('analysis-prompt.md', 'tips-prompt.md', 'areas-prompt.md')` 로 바꾸고, `movie_template.html ships` 줄 아래에 넣는다.

```powershell
Assert 'manual_template.html ships' (Test-Path (Join-Path $FlowDir 'scripts/manual_template.html'))
Assert 'SKILL.md renders both pages into the output folder' ($flowText -match [regex]::Escape('render.py" <레포>/docs/code-flow/flow.json --out-dir <레포>/docs/code-flow'))
Assert 'the flow skill matches items against scenes and tips' ($flowText -match '\| 설명 대조 검토 \|')
Assert 'its description names the user manual' ($flowDesc -match '사용자 설명서')
Assert 'the plugin description names the user manual' ($pluginJson.description -match '사용자 설명서')
```

Run: `cd /mnt/c && pwsh.exe -NoProfile -File '\\wsl.localhost\Ubuntu\home\rladustn1227\02.github\Kiwoom-dashboard\kw-plugins-code-flow\tests\test_dashboard.ps1' 2>&1 | grep -aE "FAIL|PASS="`
Expected: 위 새 검사 중 `manual_template.html ships` 를 뺀 넷과 `SKILL.md links areas-prompt.md` 가 FAIL.

- [ ] **Step 2: `SKILL.md` 를 고친다**

- frontmatter description 끝 문장을 「Builds a moving developer guide page and a user manual (사용자 설명서) from the same analysis, with screen captures (front end only, fed with example data), in the repo's docs/code-flow folder. Triggers on 코드 흐름·동작 흐름·어떻게 동작하는지·기능별 흐름·흐름 시각화·사용자 설명서·사용 설명서·code flow.」로 바꾼다.
- 첫 문단을 「이 스킬은 레포의 기능마다 「버튼을 누르면 자료가 어디로 오가는지」를 움직이는 그림과 화면 캡처로 보여 주는 개발자용 안내 화면(`index.html`)과, 같은 분석으로 화면의 항목과 버튼의 뜻을 보여 주는 사용자 설명서(`manual.html`)를 함께 만든다.」로 바꾼다. 개발자용 안내 화면의 독자(바이브 코더)와 설명서의 독자(화면을 쓰는 사람)를 한 문장씩 적는다.
- 절차 표: 「레포 찾기」 줄 끝에 「화면 코드가 다른 레포에 있으면 지원하지 않는다고 알리고 멈춘다」. 「기능별 분석」 줄 끝에 「같은 때에 화면마다 항목 서브에이전트를 실행한다. 프롬프트에 [areas-prompt.md](areas-prompt.md) 경로, 레포 경로, 맡을 화면(둘러보기에 넣을 장면 id 와 그 장면 이름)을 넣는다. 둘러보기 화면은 순서표의 장면 중 서로 다른 결과 화면에서 고른다」. 「근거 대조」 줄에 「항목 서브에이전트의 `evidence` 도 같은 방법으로 대조한다」. 「알아 둘 점 검토」 다음 줄로 넣는다:

```markdown
| 설명 대조 검토 | 항목마다 장면 · 알아 둘 점 중 어디에서 설명되는지 대조한다. 장면이 없는 버튼이 있으면 그 기능의 분석 서브에이전트를 빠진 버튼 목록과 함께 다시 실행해 장면을 받고, 근거 대조 · 알아 둘 점 검토를 다시 거친다. 모르면 결과를 잘못 읽는 표시 규칙이 알아 둘 점에 없으면 그 화면이 처음 나오는 장면의 알아 둘 점에 핵심으로 싣는다. 빠진 항목 수와 채운 방법, `unresolved` 항목을 답에 적는다 |
```

  「렌더」 줄을 「`render.py` 로 `docs/code-flow/index.html` 과 `manual.html` 을 함께 만들고 두 파일을 브라우저로 연다」로 바꾼다.
- 「스크립트」 절의 render 명령을 `python "${CLAUDE_SKILL_DIR}/scripts/render.py" <레포>/docs/code-flow/flow.json --out-dir <레포>/docs/code-flow` 로 바꾼다.
- 「캡처 계획」 절 JSON 예시의 마지막 `}` 앞에 `,\n "tour": [{"key": "search", "scene": "search-0", "areas": [{"name": "검색창", "target": {"selector": "#q"}}]}]` 를 넣고, 아래 문장을 더한다: 「`tour` 는 항목 서브에이전트 결과에서 만든다. `capture.py` 는 그 장면의 결과 화면에서 항목 위치를 측정하고, 후보가 하나로 정해지지 않은 항목은 위치 없이 남긴다.」
- 「JSON 합치기」 절: 최상위에 `tour` 를 더하고, 대응표에 줄을 더한다.

```markdown
| `tour[].img` · `unavailable` | `tour[]` 화면의 `img` · `unavailable`(이름과 `areas` 는 항목 서브에이전트 결과의 `screen.name` 과 `areas` 에서 `name` · `meaning` 만 옮긴다) |
| `tour[].rects.<순번>` | 그 순번 항목의 `rect`(번호 `no` 는 `render.py` 가 매긴다) |
```

  둘러보기 화면이 없으면 `"tour": []` 를 둔다고 적는다.
- 「결과물」 절에 `manual.html` 을 더한다. 「결과 알리기」에 `manual.html` 경로, 캡처하지 못한 둘러보기 화면, `unresolved` 항목을 더하고, 마지막 줄을 「다른 사람에게 줄 때는 `index.html` · `manual.html` 과 `screens/` 폴더를 함께 줘야 한다는 점」으로 바꾼다.
- 「화면과 문장 규칙」 표에 Task 4 Step 2 의 요약 규칙 한 줄을 더한다.

- [ ] **Step 3: 플러그인 설명을 고친다**

`plugin.json` 과 `marketplace.json` 의 kw-dashboard `description` 끝 문장 「explaining-code-flow 는 레포의 기능별 동작 흐름을 실제 화면 캡처와 함께 움직이는 안내 화면으로 만든다.」를 두 파일 모두 「explaining-code-flow 는 레포의 기능별 동작 흐름을 실제 화면 캡처와 함께 움직이는 개발자용 안내 화면과 사용자 설명서로 만든다.」로 바꾼다.

- [ ] **Step 4: 통과를 확인한다**

Run: `cd /mnt/c && pwsh.exe -NoProfile -File '\\wsl.localhost\Ubuntu\home\rladustn1227\02.github\Kiwoom-dashboard\kw-plugins-code-flow\tests\test_dashboard.ps1' 2>&1 | grep -aE "FAIL|PASS="`
Expected: `FAIL` 줄 없음, `PASS=` 가 이전(45)보다 다섯 많다.

- [ ] **Step 5: 커밋한다**

```bash
git add plugins/kw-dashboard/skills/explaining-code-flow/SKILL.md plugins/kw-dashboard/.claude-plugin/plugin.json .claude-plugin/marketplace.json tests/test_dashboard.ps1
git commit -m "docs(kw-dashboard): 스킬 절차에 화면 항목 목록 · 설명 대조 · 사용자 설명서 렌더를 넣는다"
```

### Task 6: RM 로 끝까지 실행해 확인한다

**Files:**
- 작업 폴더만 쓴다: `/mnt/c/Users/Public/claude-etax/tracecheck/cf-rm2/`(기존 분석 결과 `analysis_*.json`, `capture_plan.json`, `merge.py`)
- 결과: `~/02.github/Kiwoom-RM/docs/code-flow/`(git 제외 폴더)

**Interfaces:**
- Consumes: Task 1~5 전부.

- [ ] **Step 1: 항목 서브에이전트 세 개를 동시에 실행한다**

화면은 입력 창(`input-4`), 코멘트 생성 결과 창(`comment-3`), 위험등급 산정 결과 화면(`result-1`)이다. 프롬프트에 `areas-prompt.md` 경로, 화면 레포 `~/02.github/Kiwoom-Rag/src/frontend/src`, 백엔드 레포 `~/02.github/Kiwoom-RM`(이번 시험만 손으로 두 경로를 준다), 장면 id 를 넣고 결과를 `cf-rm2/areas_<key>.json` 에 저장하게 한다.
Expected: 결과 화면의 `areas` 에 「보라 테두리 · 「변경」 배지」, 「변경 factor」, 「변동 펀드」가 들어 있다.

- [ ] **Step 2: 근거 대조와 설명 대조를 한다**

`areas_*.json` 의 `evidence` 를 `build.py` 의 근거 검사와 같은 방법으로 확인하고, 항목마다 `flow.json` 장면 · 알아 둘 점에서 설명된 곳을 찾는다. 장면이 없는 버튼(예: 「변경 factor」)이 나오면 결과 기능 분석 서브에이전트를 그 목록과 함께 다시 실행한다.
Expected: 빠진 항목 수와 채운 방법을 표로 정리할 수 있다.

- [ ] **Step 3: 캡처 계획에 `tour` 를 넣어 다시 캡처하고 합친다**

`capture_plan.json` 에 `tour` 세 개를 넣고 `run_repo.py start` → `capture.py` → `run_repo.py stop` 을 실행한다. `merge.py` 에 `tour` 합치기를 더해 `flow.json` 을 만든다.
Expected: 결과 `tour` 세 화면 모두 `img` 가 있고, 결과 화면에서 보라 테두리 항목에 `rect` 가 있다.

- [ ] **Step 4: 렌더하고 확인한다**

Run: `python3 <스킬>/scripts/render.py flow.json --out-dir ~/02.github/Kiwoom-RM/docs/code-flow`, 1920 폭 헤드리스 캡처, `git -C ~/02.github/Kiwoom-RM status --short docs/code-flow`
Expected: 두 HTML 이 만들어지고, 설명서 정지 화면이 시안과 같은 배치이며, git 상태가 빈 출력이다.

- [ ] **Step 5: 설명서를 올려 사용자에게 확인받는다**

시안 주소(https://claude.ai/artifact/XMKjr2vfuNaCMw5CRkx3kb)에 `manual.html` 과 `screens/` 를 새 버전으로 올린다. 코드 커밋은 없다.

<!-- spec-review: passed (사용자가 렌즈 리뷰를 건너뜀) -->
