"""흐름 JSON 을 검사하고 템플릿에 넣어 개발자용 안내 화면과 사용자 설명서 HTML 을 함께 만든다.

    python render.py <flow.json> --out-dir <docs/code-flow 폴더>
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
        "prereq": "공고 현황에서 먼저 새로고침해야 카드가 채워집니다.",
        "nodes": [
            {"id": "pc", "name": "내 PC", "kind": "screen", "zone": "office", "x": 110, "y": 170},
            {"id": "data", "name": "샘플 데이터", "kind": "code", "zone": "app", "x": 360, "y": 80},
            {"id": "mail", "name": "아웃룩", "kind": "server", "zone": "office", "x": 110, "y": 400, "launch": True},
        ],
        "scenes": [
            {"title": "홈을 열면 카드가 그려집니다",
             "tips": [{"text": "금액 단위는 억원입니다.", "level": "core"},
                      {"text": "저장하면 이전 값이 남지 않습니다.", "level": "core", "irreversible": True},
                      {"text": "조회가 실패해도 예시 값이 경고 없이 남습니다.", "level": "core", "defect": True},
                      {"text": "30초마다 자동 갱신됩니다.", "level": "ref"}],
             "screen": {"startName": "검색창에 「견적」 입력", "endName": "카드 표시", "start": [12, 77, 185, 40], "typed": "견적"},
             "actions": [{"from": "pc", "to": "data", "icon": "ask", "text": "카드 요청", "say": "화면이 샘플 데이터를 읽습니다."}]},
            {"title": "공고 목록", "tips": [], "auto": True,
             "screen": {"startName": "「공고」 탭 클릭", "endName": "목록 표시",
                        "unavailable": "실행에 필요한 데이터가 없어 화면을 만들 수 없습니다."},
             "actions": [{"from": "mail", "to": "pc", "icon": "list", "text": "목록", "say": "아웃룩에서 읽은 목록이 화면으로 갑니다."}]},
        ],
    }],
    "tour": [{"key": "home", "name": "홈 화면", "img": "screens/home.png",
              "areas": [{"name": "검색창", "meaning": "제목과 본문에서 찾습니다.", "rect": [12, 77, 185, 40]},
                        {"name": "결과 표", "meaning": "검색 결과입니다.", "rect": [12, 140, 800, 300]},
                        {"name": "보라 테두리", "meaning": "지난달과 등급이 다른 행입니다."}]}],
}


# 노드 상자는 폭 172 · 높이 약 60(줄바꿈하면 더 높다)이다. 무대 좌표(높이 520 기준)로 이보다 가까우면 겹친다
NODE_GAP_X, NODE_GAP_Y = 180, 80
# 구역 상자는 노드 중심에서 좌우 100, 위로 70(구역 이름 칸), 아래로 60 을 감싼다고 보고 겹침을 판정한다
ZONE_PAD = (100, 70, 60)


def overlaps(nodes: list[dict], where: str) -> list[str]:
    errs = []
    pts = [n for n in nodes if isinstance(n.get("x"), (int, float)) and isinstance(n.get("y"), (int, float))]
    for i, a in enumerate(pts):
        for b in pts[i + 1:]:
            if abs(a["x"] - b["x"]) < NODE_GAP_X and abs(a["y"] - b["y"]) < NODE_GAP_Y:
                errs.append(f"{where} 노드 {a.get('id')!r} 와 {b.get('id')!r} 가 겹칩니다(가로 {NODE_GAP_X}, 세로 {NODE_GAP_Y} 이상 띄워야 합니다)")
    boxes = {}
    for n in pts:
        if n.get("zone"):
            boxes.setdefault(n["zone"], []).append(n)
    px, top, bottom = ZONE_PAD
    rect = {z: (min(n["x"] for n in ns) - px, min(n["y"] for n in ns) - top, max(n["x"] for n in ns) + px, max(n["y"] for n in ns) + bottom)
            for z, ns in boxes.items()}
    zs = list(rect)
    for i, a in enumerate(zs):
        for b in zs[i + 1:]:
            A, B = rect[a], rect[b]
            if A[0] < B[2] and B[0] < A[2] and A[1] < B[3] and B[1] < A[3]:
                errs.append(f"{where} 구역 {a!r} 와 {b!r} 의 상자가 겹칩니다(노드 좌표를 옮겨 구역 사이를 띄워야 합니다)")
    return errs


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
    for fi, f in enumerate(data.get("features") or []):
        fw = f"features[{fi}]"
        need(f, ["key", "name", "summary", "nodes", "scenes"], fw)
        if "prereq" in f and not (isinstance(f["prereq"], str) and f["prereq"]):
            errs.append(f"{fw}.prereq 는 비어 있지 않은 글자여야 합니다")
        if "chatbot" in f and not isinstance(f["chatbot"], bool):
            errs.append(f"{fw}.chatbot 은 true · false 여야 합니다")
        if f.get("chatbot") and f.get("scenes"):
            errs.append(f"{fw} 는 챗봇 기능이라 장면을 두지 않습니다(안내 개발 중)")
        ids = set()
        for ni, n in enumerate(f.get("nodes") or []):
            nw = f"{fw}.nodes[{ni}]"
            need(n, ["id", "name", "kind", "x", "y"], nw)
            ids.add(n.get("id"))
            if n.get("kind") not in KINDS:
                errs.append(f"{nw}.kind 값 {n.get('kind')!r} 는 명칭표에 없습니다")
            if "launch" in n and not isinstance(n["launch"], bool):
                errs.append(f"{nw}.launch 는 true · false 여야 합니다")
            if "zone" in n and n["zone"] not in ZONES:
                errs.append(f"{nw}.zone 값 {n['zone']!r} 는 구역 목록에 없습니다")
            x, y = n.get("x"), n.get("y")
            if isinstance(x, (int, float)) and isinstance(y, (int, float)) and not (0 <= x <= STAGE_W and 0 <= y <= STAGE_H):
                errs.append(f"{nw} 좌표 ({x}, {y}) 가 960×520 무대 밖입니다")
        errs += overlaps(f.get("nodes") or [], fw)
        for si, s in enumerate(f.get("scenes") or []):
            sw = f"{fw}.scenes[{si}]"
            need(s, ["title", "actions"], sw)
            if not isinstance(s.get("tips"), list):
                errs.append(f"{sw}.tips 목록이 없습니다")
            for ti, t in enumerate(s.get("tips") or []):
                tw = f"{sw}.tips[{ti}]"
                need(t, ["text", "level"], tw)
                if isinstance(t, dict) and t.get("level") not in (None, "", "core", "ref"):
                    errs.append(f"{tw}.level 은 core 또는 ref 여야 합니다")
                for flag in ("irreversible", "defect"):
                    if isinstance(t, dict) and flag in t and not isinstance(t[flag], bool):
                        errs.append(f"{tw}.{flag} 는 true · false 여야 합니다")
            if "auto" in s and not isinstance(s["auto"], bool):
                errs.append(f"{sw}.auto 는 true · false 여야 합니다")
            scr = s.get("screen") or {}
            need(scr, ["startName", "endName"], f"{sw}.screen")
            shot = bool(scr.get("startImg") or f.get("screenImg"))
            if scr.get("unavailable") and (scr.get("start") or scr.get("startImg")):
                errs.append(f"{sw}.screen 에 캡처와 실패 문구가 함께 있습니다")
            if not shot and not scr.get("unavailable"):
                errs.append(f"{sw}.screen 에 캡처도 실패 문구도 없습니다")
            if "typed" in scr and (not isinstance(scr["typed"], str) or not scr.get("start")):
                errs.append(f"{sw}.screen.typed 는 글자이고, 글자를 칠 칸의 screen.start 가 함께 있어야 합니다")
            for key in ("start", "end"):
                if key in scr and not rect_ok(scr[key]):
                    errs.append(f"{sw}.screen.{key} 는 1440×1000 안의 [x, y, 폭, 높이] 여야 합니다")
            frames = scr.get("frames") or []
            for fi, fm in enumerate(frames):
                if not isinstance(fm, dict) or not fm.get("img"):
                    errs.append(f"{sw}.screen.frames[{fi}] 에 img 가 없습니다")
                elif "rect" in fm and not rect_ok(fm["rect"]):
                    errs.append(f"{sw}.screen.frames[{fi}].rect 는 1440×1000 안의 [x, y, 폭, 높이] 여야 합니다")
            # step 은 사람 동작 번호다. 동작 이미지 수 + 1(마지막 사람 동작 = 결과 화면)까지이고 흐름 동작 순서대로 커진다
            steps = [a["step"] for a in s.get("actions") or [] if isinstance(a, dict) and "step" in a]
            if any(not isinstance(n, int) or not 1 <= n <= len(frames) + 1 for n in steps):
                errs.append(f"{sw} 의 step 은 1 부터 동작 이미지 수 + 1({len(frames) + 1}) 사이여야 합니다")
            elif steps != sorted(steps):
                errs.append(f"{sw} 의 step 이 흐름 동작 순서대로 커지지 않습니다")
            for ai, a in enumerate(s.get("actions") or []):
                aw = f"{sw}.actions[{ai}]"
                need(a, ["from", "to", "icon", "text", "say"], aw)
                for end in ("from", "to"):
                    if a.get(end) and a[end] not in ids:
                        errs.append(f"{aw}.{end} 값 {a[end]!r} 인 노드가 없습니다")
                if a.get("icon") and a["icon"] not in ICONS:
                    errs.append(f"{aw}.icon 값 {a['icon']!r} 는 아이콘 목록에 없습니다")
    return errs


def page_title(data: dict, template: str) -> str:
    """설명서는 개발자용 안내 화면과 브라우저 탭에서 구분되도록 「<레포> 사용 설명서」로 부른다."""
    if template == "manual_template.html":
        return data["title"].removesuffix(", 움직이며 보기") + " 사용 설명서"
    return data["title"]


def render(data: dict, template: str = "movie_template.html") -> str:
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    page = (HERE / template).read_text(encoding="utf-8")
    return page.replace("__TITLE__", html.escape(page_title(data, template))).replace("__DATA__", payload)


ROW_GAP = 24  # 1440×1000 캡처에서 같은 줄로 볼 세로 차이(픽셀)


def number_tour(data: dict) -> dict:
    """위치를 찾은 항목에만 위에서 아래, 왼쪽에서 오른쪽 순서로 번호를 매긴 사본을 돌려준다.
    한 줄에 놓인 칸도 세로 위치가 몇 픽셀씩 다르므로, 앞 칸과 세로 차이가 ROW_GAP 이내면 같은 줄로 보고 왼쪽부터 센다."""
    out = copy.deepcopy(data)
    for sc in out.get("tour") or []:
        areas = sc.get("areas") or []
        for a in areas:
            a.pop("no", None)
        rows: list[list[dict]] = []
        for a in sorted((a for a in areas if a.get("rect")), key=lambda a: a["rect"][1]):
            if rows and a["rect"][1] - rows[-1][0]["rect"][1] <= ROW_GAP:
                rows[-1].append(a)
            else:
                rows.append([a])
        located = [a for r in rows for a in sorted(r, key=lambda a: a["rect"][0])]
        for i, a in enumerate(located, 1):
            a["no"] = i
    return out


def render_all(data: dict, out_dir: Path) -> list[Path]:
    """같은 흐름 JSON 으로 개발자용 안내 화면(index.html)과 사용자 설명서(manual.html)를 함께 쓴다."""
    out_dir.mkdir(parents=True, exist_ok=True)
    outs = []
    for name, tpl in (("index.html", "movie_template.html"), ("manual.html", "manual_template.html")):
        p = out_dir / name
        p.write_text(render(data, tpl), encoding="utf-8")
        outs.append(p)
    return outs


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
    tpl = (HERE / "movie_template.html").read_text(encoding="utf-8")
    expect("템플릿에 자리표시 문자열이 한 번씩만 있다", tpl.count("__TITLE__") == 1 and tpl.count("__DATA__") == 1)

    bad = copy.deepcopy(SAMPLE)
    f = bad["features"][0]
    f["nodes"][0]["kind"] = "browser"
    f["scenes"][0]["actions"][0]["to"] = "nowhere"
    del f["scenes"][1]["screen"]["unavailable"]
    del f["screenImg"]
    errs = validate(bad)
    expect("명칭표에 없는 kind 를 잡는다", any("kind" in e and "browser" in e for e in errs))
    expect("없는 노드로 가는 동작을 잡는다", any("nowhere" in e for e in errs))
    expect("캡처도 실패 문구도 없는 장면을 잡는다", any("features[0].scenes[1]" in e and "캡처" in e for e in errs))

    typo = copy.deepcopy(SAMPLE)
    typo["features"][0]["nodes"][2]["launch"] = "yes"
    del typo["features"][0]["scenes"][0]["screen"]["start"]
    errs = validate(typo)
    expect("launch 가 참 · 거짓이 아니면 잡는다", any("launch" in e for e in errs))
    expect("글자를 칠 칸 없이 typed 만 있으면 잡는다", any("typed" in e for e in errs))

    fr = copy.deepcopy(SAMPLE); sc = fr["features"][0]["scenes"][0]
    sc["screen"]["frames"] = [{"img": "screens/x_f1.png", "rect": [0, 0, 10, 10]}]
    sc["actions"].append(dict(sc["actions"][0]))
    sc["actions"][0]["step"], sc["actions"][1]["step"] = 1, 2
    expect("frames 와 step 이 맞으면 통과한다", validate(fr) == [])
    sc["actions"][1]["step"] = 3
    expect("step 이 frames 수 + 1 을 넘으면 잡는다", any("step" in e for e in validate(fr)))
    sc["actions"][0]["step"], sc["actions"][1]["step"] = 2, 1
    expect("step 이 흐름 동작 순서대로 커지지 않으면 잡는다", any("step" in e for e in validate(fr)))
    sc["actions"][0]["step"], sc["actions"][1]["step"] = 1, 2
    sc["screen"]["frames"][0]["rect"] = [0, 0, 2000, 10]
    expect("frames 의 rect 가 화면 밖이면 잡는다", any("frames" in e for e in validate(fr)))
    del sc["screen"]["frames"][0]["img"]
    expect("frames 항목에 img 가 없으면 잡는다", any("frames" in e and "img" in e for e in validate(fr)))

    tipbad = copy.deepcopy(SAMPLE)
    tips = tipbad["features"][0]["scenes"][0]["tips"]
    tips[0] = "글자만 적은 옛 형식"
    tips[1]["level"] = "info"
    tips[2]["defect"] = "yes"
    tipbad["features"][0]["scenes"][1]["auto"] = 1
    tipbad["features"][0]["prereq"] = ""
    errs = validate(tipbad)
    expect("알아 둘 점이 글자만 있으면 잡는다", any("tips[0].text" in e for e in errs))
    expect("level 이 core · ref 가 아니면 잡는다", any("tips[1].level" in e for e in errs))
    expect("defect 가 참 · 거짓이 아니면 잡는다", any("tips[2].defect" in e for e in errs))
    expect("auto 가 참 · 거짓이 아니면 잡는다", any("scenes[1].auto" in e for e in errs))
    expect("빈 prereq 를 잡는다", any("prereq" in e for e in errs))

    near = copy.deepcopy(SAMPLE)
    near["features"][0]["nodes"][2].update({"x": 150, "y": 200})
    errs = validate(near)
    expect("겹치는 노드를 잡는다", any("'pc'" in e and "'mail'" in e for e in errs))
    zone = copy.deepcopy(SAMPLE)
    zone["features"][0]["nodes"][1].update({"x": 300, "y": 200})
    expect("겹치는 구역 상자를 잡는다", any("구역" in e and "겹칩니다" in e for e in validate(zone)))

    chat = copy.deepcopy(SAMPLE)
    chat["features"].append({"key": "etf", "name": "ETF 챗봇", "summary": "대화로 묻는 기능", "chatbot": True, "nodes": [], "scenes": []})
    expect("장면 없는 챗봇 기능은 통과한다", validate(chat) == [])
    chat["features"][1]["scenes"] = copy.deepcopy(SAMPLE["features"][0]["scenes"])
    expect("챗봇 기능에 장면이 있으면 잡는다", any("챗봇" in e for e in validate(chat)))

    norect = copy.deepcopy(SAMPLE)
    del norect["features"][0]["scenes"][0]["screen"]["start"]
    del norect["features"][0]["scenes"][0]["screen"]["typed"]
    expect("버튼 사각형이 없는 장면도 통과한다", validate(norect) == [])

    numbered = number_tour(SAMPLE)["tour"][0]["areas"]
    expect("위치를 찾은 항목에만 위에서 아래 순서로 번호를 매긴다",
           [a.get("no") for a in numbered] == [1, 2, None])
    expect("tour 가 있는 예제도 검사를 통과한다", validate(number_tour(SAMPLE)) == [])
    row = {"tour": [{"key": "r", "name": "r", "img": "x.png", "areas": [
        {"name": "오른쪽", "meaning": "m", "rect": [900, 10, 50, 20]}, {"name": "왼쪽", "meaning": "m", "rect": [100, 22, 50, 20]},
        {"name": "아래", "meaning": "m", "rect": [50, 200, 50, 20]}]}]}
    expect("같은 줄(세로 차이가 작은 칸)은 왼쪽부터 번호를 매긴다",
           [a["no"] for a in number_tour(row)["tour"][0]["areas"]] == [2, 1, 3])
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
        expect("설명서 제목은 「<레포> 사용 설명서」다", "<title>예제 대시보드 사용 설명서</title>" in man)
    mtpl = (HERE / "manual_template.html").read_text(encoding="utf-8")
    expect("설명서 템플릿에 자리표시 문자열이 한 번씩만 있다", mtpl.count("__TITLE__") == 1 and mtpl.count("__DATA__") == 1)
    return 0 if ok else 1


def main() -> int:
    # PYTHONUTF8=1 을 준 것과 같은 결과다. 그 값이 없는 윈도우 PC 에서도 한국어 출력이 깨지지 않는다
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("flow", nargs="?")
    ap.add_argument("--out-dir")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if a.check:
        return _check()
    if not a.flow or not a.out_dir:
        ap.error("흐름 JSON 경로와 --out-dir 이 필요합니다")
    data = number_tour(json.loads(Path(a.flow).read_text(encoding="utf-8")))
    errs = validate(data)
    if errs:
        print("흐름 JSON 을 고쳐야 합니다:")
        for e in errs:
            print("  - " + e)
        return 1
    for p in render_all(data, Path(a.out_dir)):
        print(p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
