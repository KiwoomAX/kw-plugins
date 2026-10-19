# 동작마다 화면과 장면 · 화면 대조 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 캡처가 사람 동작마다 캡처 이미지를 남기고, 두 템플릿이 흐름 동작과 같은 순간에 그 이미지를 보이며, 끝 대상은 결과 범위 전체를 유일하게 가리키고, 주 세션이 사각형을 그린 사본으로 장면을 대조하게 한다.

**Architecture:** `capture.py` 가 사람 동작마다 `frames`(`img`, `rect`)를 남기고 `--scenes` 로 장면 일부만 다시 캡처한다. 분석 서브에이전트가 흐름 동작에 `step` 을 적고, 주 세션이 `frames` 를 `flow.json` 의 `screen.frames` 로 옮긴다. `render.py` 가 두 필드를 검사하고 두 템플릿이 재생한다. `draw_boxes.py` 는 대조용 사본만 만든다.

**Tech Stack:** Python 3(표준 라이브러리), Playwright(`uv run --no-project --with playwright`), Pillow(`draw_boxes.py` 만, `uv run --no-project --with pillow`), 템플릿 HTML · JS, PowerShell 계약 테스트.

**Spec:** `docs/superpowers/specs/2026-10-14-code-flow-guide-design.md` 의 「동작마다 화면」 절, 「화면과 문장 규칙」의 끝 대상 줄, 절차 표의 「장면 · 화면 대조」 줄.

## Global Constraints

- 사람 동작은 장면 동작 중 `setup` 과 `wait` 를 뺀 동작이고, 장면마다 1부터 센다. `frames` 와 `step` 은 모두 이 번호를 쓴다.
- 마지막 사람 동작 뒤 화면은 `endImg` 이고 `frames` 에 넣지 않는다.
- 캡처 이미지는 1440×1000 전체 화면이며 자르거나 확대해 찍지 않는다. `rect` 는 1440×1000 기준 `[x, y, 폭, 높이]` 다.
- `frames` 의 `rect` 는 동작 뒤에 측정하고, 대상이 보이지 않으면 비운다.
- 끝 대상 후보가 둘 이상 보이면 찾지 못함이다.
- 다시 캡처는 장면마다 한 번이다.
- `draw_boxes.py` 의 사본은 결과물 폴더 밖 임시 폴더에 둔다.
- 서버는 `127.0.0.1` 에만 연다. `.env` 는 열지 않는다. 대상 레포의 추적 파일은 고치지 않는다.
- 문서 · 주석 · 템플릿 문구에 긴 줄표를 쓰지 않는다.

## Review Focus

- 기다리기가 사람 동작 사이에 낀 장면(`[select, wait, select, click]`)에서 `frames` 가 두 장이고 `step` 2 가 두 번째 이미지를 가리켜야 한다. Task 1 의 `frame_points` 검사가 맡는다.
- 사람 동작이 하나뿐인 장면(`[click, wait]`)은 `frames` 가 비고 예전처럼 보여야 한다. Task 1 과 Task 3 의 검사가 맡는다.
- 누르기로 창이 열려 누른 단추가 가려지면 그 동작 이미지는 `rect` 없이 전체 화면이어야 한다. Task 1 의 `_locate_one(first=True)` 사용과 Task 6 의 RM 확인이 맡는다.
- 중간 동작에서 멈춘 장면은 그때까지의 `frames` 를 남겨야 한다. Task 1 의 실패 처리와 Task 6 확인이 맡는다.
- `step` 이 범위를 넘거나 거꾸로 가면 렌더 전에 오류여야 한다. Task 3 검사가 맡는다.

---

### Task 1: capture.py 동작 이미지 · 끝 대상 유일 · 장면 고르기

**Files:**
- Modify: `plugins/kw-dashboard/skills/explaining-code-flow/scripts/capture.py` (`_run` 134행, `capture()` 304~387행, `_check`, `main`)

**Interfaces:**
- Produces: `frame_points(own: list[dict]) -> list[int]`(사진을 찍을 `own` 의 위치), `select_scenes(plan_doc: dict, ids: list[str]) -> dict`, 캡처 결과 장면의 `frames: [{"img": "screens/<id>_f<n>.png", "rect"?: [x,y,w,h]}]`, CLI `--scenes id1,id2`.

- [ ] **Step 1: `_check` 에 실패하는 검사를 넣는다**

```python
expect("사람 동작마다 마지막을 빼고 찍는다(기다리기는 건너뜀)", frame_points([m, {"action": "wait", "ms": 500}, m, c]) == [0, 2])
expect("사람 동작이 하나면 찍지 않는다", frame_points([c, {"action": "wait", "ms": 3000}]) == [])
expect("누르기 둘 뒤 기다리기면 첫 누르기만 찍는다", frame_points([c, c, {"action": "wait", "ms": 3000}]) == [0])
sp = select_scenes({"features": [{"key": "a", "scenes": [{"id": "a-0"}, {"id": "a-1"}]}, {"key": "b", "scenes": [{"id": "b-0"}]}],
                    "tour": [{"key": "t", "scene": "b-0", "areas": []}]}, ["a-1"])
expect("고른 장면만 남기고 장면 없는 기능과 둘러보기는 뺀다",
       sp["features"] == [{"key": "a", "scenes": [{"id": "a-1"}]}] and sp["tour"] == [])
```

- [ ] **Step 2: 실행해 실패를 확인한다**

Run: `python3 plugins/kw-dashboard/skills/explaining-code-flow/scripts/capture.py --check`
Expected: `NameError: name 'frame_points' is not defined`

- [ ] **Step 3: 구현한다**
  - `frame_points(own)`: `wait` 가 아닌 동작의 위치 목록에서 마지막을 뺀 목록.
  - `select_scenes(plan_doc, ids)`: 사본을 만들어 장면을 거르고, 장면이 없어진 기능과 그 장면을 가리키는 `tour` 를 뺀다.
  - `_run(page, steps, part, after=None)`: 동작 `i` 를 마친 뒤 `after(i, st)` 를 부른다.
  - `capture()` 의 장면 처리: `sr["frames"] = []` 을 두고, `after` 에서 `i in frame_points(own)` 이면 `<id>_f<n>.png`(n 은 1부터)를 찍고 `rect = _locate_one(cp, st["target"], first=True)`(대상이 없으면 `None`)를 붙여 `sr["frames"]` 에 넣는다. 예외가 나도 넣은 항목은 남는다. 빈 `frames` 는 결과에서 뺀다.
  - 끝 대상 측정 두 곳(`("end", _locate(...))` 와 결과 화면 뒤 `end = _locate(...)`)을 `_locate_one(page, target)` 으로 바꾼다. 후보가 둘 이상이면 `None` 이다.
  - `main`: `--scenes` 가 있으면 `plan_errors` 뒤 `select_scenes(plan_doc, a.scenes.split(","))` 로 바꾼다.

- [ ] **Step 4: 통과를 확인한다**

Run: `python3 plugins/kw-dashboard/skills/explaining-code-flow/scripts/capture.py --check`
Expected: 모든 줄 `PASS`, 끝 상태 0

- [ ] **Step 5: 커밋한다**

```bash
git add plugins/kw-dashboard/skills/explaining-code-flow/scripts/capture.py
git commit -m "feat(kw-dashboard): 캡처가 사람 동작마다 이미지를 남기고, 끝 대상은 유일할 때만 쓰며, 장면 일부만 다시 캡처한다"
```

### Task 2: draw_boxes.py

**Files:**
- Create: `plugins/kw-dashboard/skills/explaining-code-flow/scripts/draw_boxes.py`

**Interfaces:**
- Consumes: Task 1 의 캡처 결과 형식(`features.<key>.scenes.<id>` 의 `startImg` · `start` · `frames` · `endImg` · `end`).
- Produces: CLI `draw_boxes.py <capture_result.json> --screens <screens 폴더> --out <임시 폴더>`, 함수 `box_jobs(result: dict) -> list[tuple[str, list | None, str]]`(원본 이미지 상대 경로, 사각형, 사본 이름).

- [ ] **Step 1: `--check` 에 실패하는 검사를 쓴다**

```python
r = {"features": {"a": {"scenes": {"a-1": {"startImg": "screens/a-1_start.png", "start": [1, 2, 3, 4],
     "frames": [{"img": "screens/a-1_f1.png", "rect": [5, 6, 7, 8]}, {"img": "screens/a-1_f2.png"}],
     "endImg": "screens/a-1_end.png", "end": [9, 9, 9, 9]}}}}}
expect("시작 · 동작 · 결과 순서로 사본을 만든다", [j[2] for j in box_jobs(r)] == ["a-1_0_start.png", "a-1_1_f1.png", "a-1_2_f2.png", "a-1_3_end.png"])
expect("사각형이 없는 동작 이미지는 사각형 없이 복사한다", box_jobs(r)[2][1] is None)
```

- [ ] **Step 2: 실패를 확인한다** — Run: `python3 .../draw_boxes.py --check` / Expected: 파일 없음 또는 `NameError`

- [ ] **Step 3: 구현한다** — `box_jobs` 는 표준 라이브러리만 쓴다. 그리기는 `main` 안에서 `from PIL import Image, ImageDraw` 로 불러 3px 빨간 테두리(`#D33`)를 그린다. 원본은 고치지 않는다. 시작 이미지가 없는 장면은 `screenImg` 대신 건너뛴다.

- [ ] **Step 4: 통과를 확인한다** — Run: `python3 .../draw_boxes.py --check` / Expected: 모두 `PASS`

- [ ] **Step 5: 커밋한다** — `git commit -m "feat(kw-dashboard): 장면 · 화면 대조용으로 캡처 이미지 사본에 화면 사각형을 그리는 draw_boxes.py 를 둔다"`

### Task 3: render.py 검사

**Files:**
- Modify: `plugins/kw-dashboard/skills/explaining-code-flow/scripts/render.py` (`validate` 81행 이하, `_check`)

**Interfaces:**
- Produces: `validate` 가 `screen.frames` 와 동작 `step` 오류 문구를 낸다.

- [ ] **Step 1: 실패하는 검사를 쓴다**

```python
fr = copy.deepcopy(SAMPLE); sc = fr["features"][0]["scenes"][0]
sc["screen"]["frames"] = [{"img": "screens/x_f1.png", "rect": [0, 0, 10, 10]}]
sc["actions"][0]["step"] = 1
expect("frames 와 step 이 맞으면 통과한다", validate(fr) == [])
sc["actions"][0]["step"] = 3
expect("step 이 frames 수 + 1 을 넘으면 잡는다", any("step" in e for e in validate(fr)))
sc["actions"][0]["step"] = 1; sc["screen"]["frames"][0]["rect"] = [0, 0, 2000, 10]
expect("frames 의 rect 가 화면 밖이면 잡는다", any("frames" in e for e in validate(fr)))
```

(SAMPLE 첫 장면의 동작이 둘 이상이면 두 번째 동작에 `step: 2` 를 넣고 감소 순서 검사도 한 줄 넣는다: `step` 이 2 다음 1 이면 잡는다.)

- [ ] **Step 2: 실패를 확인한다** — Run: `python3 .../render.py --check` / Expected: 새 줄 `FAIL`
- [ ] **Step 3: 구현한다** — 기존 `rect` 범위 검사 함수를 재사용한다. `frames` 항목마다 `img` 필수, `rect` 는 있으면 범위 안. 장면의 `step` 들은 1 이상 `len(frames)+1` 이하이고 흐름 동작 순서대로 증가.
- [ ] **Step 4: 통과를 확인한다** — Expected: 모두 `PASS`
- [ ] **Step 5: 커밋한다**

### Task 4: 두 템플릿의 동작 이미지 재생

**Files:**
- Modify: `scripts/movie_template.html` (play 루프 489~500행), `scripts/manual_template.html` (RAW→D 어댑터 155행, play 284~297행)

**Interfaces:**
- Consumes: `flow.json` 장면의 `screen.frames`, 동작의 `step`.

- [ ] **Step 1: 개발자용 템플릿** — 루프에서 `const a = sc.actions[k]` 에 `step` 이 있고 `F = sc.screen.frames || []` 의 `step-1` 번째가 있으면 `camera(fr.rect || null, a.text, '#27457D', false, fr.img)` 를 부르고, 그 동작에는 「뒤에서 처리 중」 두 줄을 건너뛴다. `step === F.length + 1` 이면 끝 대상 호출(지금 `k === last` 분기와 같은 호출)을 그 동작에서 한다.
- [ ] **Step 2: 설명서 템플릿** — 어댑터가 장면에 `frames` 와 `caps`(`step` → 동작 `text`)를 싣는다. play 는 시작(입력 연출 포함) 뒤, 결과 앞에서 `frames` 마다 `camera(fr.rect || null, fr.img)` · `cap(caps[n] || '', '#27457D')` · `wait(1800)` 을 한다.
- [ ] **Step 3: 렌더 자체 검사와 계약 테스트를 실행한다** — Run: `python3 .../render.py --check` 와 `pwsh.exe -NoProfile -ExecutionPolicy Bypass -File <tests/test_dashboard.ps1 의 윈도우 경로>` / Expected: 모두 `PASS`, `FAIL=0`
- [ ] **Step 4: 커밋한다**

### Task 5: 지침 · 절차 문서와 계약 테스트

**Files:**
- Modify: `analysis-prompt.md`(99행 end 규칙, 동작 필드 설명에 `step`), `SKILL.md`(절차 표에 「장면 · 화면 대조」 줄, 대응표에 `scenes.<id>.frames` → `screen.frames` 줄, 결과 알리기), `tests/test_dashboard.ps1`

- [ ] **Step 1: 계약 테스트에 실패하는 확인을 넣는다** — SKILL.md 에 「장면 · 화면 대조」와 `draw_boxes.py` 링크, 대응표의 `frames`, analysis-prompt.md 에 `step` 과 「범위 전체」가 있는지 본다.
- [ ] **Step 2: 실패를 확인한다** — Expected: 새 줄 `FAIL`
- [ ] **Step 3: 문서를 고친다** — analysis-prompt.md 99행의 「결과 제목」 · 「그 단추 · 칸」 문장을 spec 끝 대상 규칙 문장으로 바꾼다. 동작 필드에 `step`(사람 동작 번호, 첫 흐름 동작에만)을 적는다.
- [ ] **Step 4: 통과를 확인한다** — Expected: `FAIL=0`
- [ ] **Step 5: 커밋한다**

### Task 6: RM 재캡처와 대조

- [ ] **Step 1:** RM 분석 결과의 흐름 동작에 `step` 을 넣고, 끝 대상 12장면(input-0 · input-1 · comment-0 · comment-5 · grade-0~4 · result-0 · result-1 · result-7)을 범위 전체 선택자로 고친다. 선택자는 Kiwoom-Rag 화면 코드에서 찾는다.
- [ ] **Step 2:** 개발 서버를 띄워 전체를 캡처하고 서버를 끈다. Expected: 30장면 모두 캡처 또는 실패 문구, 동작 이미지 약 18장.
- [ ] **Step 3:** `draw_boxes.py` 로 사본을 만들어 30장면을 대조한다. 맞지 않는 장면은 고쳐 `--scenes` 로 한 번 다시 캡처한다.
- [ ] **Step 4:** `merge.py` 와 `render.py --out-dir` 로 두 페이지를 만든다. Expected: 「2026년 선택」 순간 연도 칸이 2026년, input-0 끝 화면이 입력 창 전체.
- [ ] **Step 5:** 대조 장면 수 · 고친 장면 · 고치지 못한 장면을 보고한다.

### Task 7: 기존 결과물 정리와 홀세일 · RM 재실행

- [ ] **Step 1:** 지울 대상 목록(claude.ai 페이지: RM 두 페이지와 미리보기, email_db, GM 등. 레포의 `docs/code-flow/` 폴더)을 사용자에게 보이고 확인을 받는다.
- [ ] **Step 2:** 확인받은 대상만 지운다.
- [ ] **Step 3:** wholesale-dashboard 와 Kiwoom-RM 에 스킬 절차 전체를 실행해 두 페이지씩 만들고 게시한다.
- [ ] **Step 4:** 게시 주소와 결과 알리기 목록을 보고한다.

<!-- spec-review: passed (사용자가 렌즈 리뷰를 건너뜀) -->
