"""설명기 ver2 화면이 쓰는 엑셀 캡처 재료를 만든다.

캡처 단위는 시트가 아니라 덩어리다. 엑셀 표가 있으면 그 표(위의 제목 띠 포함)이고,
없으면 빈 열과 빈 행으로 나뉜 범위다. 덩어리의 왼쪽 위부터 캡처가 시작된다.
"""
from explain_cell import a1, show

TITLE_BAND_ROWS = 3  # 표 머리 위에서 제목 띠로 볼 행 수


def detect_blocks(book, sheet):
    """칸이 있는 곳을 빈 열로 먼저, 이어서 빈 행으로 나눈 덩어리(r1, c1, r2, c2)의 목록."""
    pos = set(book.cells[sheet]) | set(book.sheet_values(sheet))
    if not pos:
        return []
    cols = sorted({c for _, c in pos})
    groups = [[cols[0]]]
    for c in cols[1:]:
        (groups.append([c]) if c - groups[-1][-1] > 1 else groups[-1].append(c))
    out = []
    for g in groups:
        rows = sorted({r for r, c in pos if g[0] <= c <= g[-1]})
        rg = [[rows[0]]]
        for r in rows[1:]:
            (rg.append([r]) if r - rg[-1][-1] > 1 else rg[-1].append(r))
        out += [(x[0], g[0], x[-1], g[-1]) for x in rg]
    return out


def _blocks_of_sheet(book, sheet):
    """시트별 덩어리를 한 번만 계산해 book 에 둔다."""
    cache = book.__dict__.setdefault("_capture_blocks", {})
    if sheet not in cache:
        cache[sheet] = detect_blocks(book, sheet)
    return cache[sheet]


def _table_top(book, sheet, area):
    """표 머리 위 3행 안에 글자가 있으면 가장 위의 그 행, 없으면 표 머리 행. 위쪽 다른 표의 행은 제목 띠로 보지 않는다."""
    r1, c1, _, c2 = area
    vals = book.sheet_values(sheet)
    others = [t.area for t in book.tables.values() if t.sheet == sheet and t.area != area and t.area[1] <= c2 and c1 <= t.area[3]]
    for r in range(max(1, r1 - TITLE_BAND_ROWS), r1):
        if any(a[0] <= r <= a[2] for a in others):
            continue
        if any(vals.get((r, c)) is not None for c in range(c1, c2 + 1)):
            return r
    return r1


def block_of(book, sheet, r, c):
    """칸 (r, c) 가 든 덩어리 {"sheet", "rect", "table"}. 어느 덩어리에도 없으면 그 칸 하나."""
    for name, t in book.tables.items():
        if t.sheet == sheet and t.area[0] <= r <= t.area[2] and t.area[1] <= c <= t.area[3]:
            top = _table_top(book, sheet, t.area)
            return {"sheet": sheet, "rect": (top, t.area[1], t.area[2], t.area[3]), "table": name}
    for rect in _blocks_of_sheet(book, sheet):
        if rect[0] <= r <= rect[2] and rect[1] <= c <= rect[3]:
            return {"sheet": sheet, "rect": rect, "table": None}
    return {"sheet": sheet, "rect": (r, c, r, c), "table": None}


def label_of(book, blk):
    """덩어리 이름 글자: 「시트 · 첫 줄의 처음 글자 표(또는 덩어리) 범위」. 오류 글자(`#...`)는 이름으로 쓰지 않는다."""
    r1, c1, r2, c2 = blk["rect"]
    vals = book.sheet_values(blk["sheet"])
    title = next((vals[(r, c1)] for r in range(r1, min(r1 + 4, r2 + 1))
                  if isinstance(vals.get((r, c1)), str) and not vals[(r, c1)].startswith("#")), "")
    kind = "표" if blk["table"] else "덩어리"
    return f"{blk['sheet']} · {title + ' ' if title else ''}{kind} {a1(r1, c1)}:{a1(r2, c2)}"


HEAD_ROWS, HEAD_COLS = 24, 20  # 덩어리 왼쪽 위에서 후보로 싣는 행 · 열 수. 실제로 몇 개를 보일지는 창 크기를 아는 화면이 정한다
AROUND = 6                     # 가리키는 칸과 입력 칸 둘레에서 후보로 싣는 행 · 열 수
EARLIER_MAX = 20               # 앞 단계에서 본 칸은 가장 최근 20개까지만 싣는다(반복 사슬에서 데이터가 제곱으로 커지지 않게)


def _candidates(lo, hi, head, focus):
    keep = set(range(lo, min(hi, lo + head - 1) + 1))
    for f in focus:
        keep |= set(range(max(lo, f - AROUND), min(hi, f + AROUND) + 1))
    return sorted(keep)


def _clip(span, rect):
    """값 칸 범위 span 을 덩어리 rect 안으로 자른다. 겹치지 않으면 None."""
    a, b, c, d = max(span[0], rect[0]), max(span[1], rect[1]), min(span[2], rect[2]), min(span[3], rect[3])
    return [a, b, c, d] if a <= c and b <= d else None


def _view(book, blk, cur, inputs, cur_span=None, input_spans=()):
    """덩어리 blk 에서 cur 칸과 입력 칸 둘레의 후보 행 · 열과 칸 글자를 모은다.

    값 칸 범위 단계는 범위 전체(`cur_span` 이 현재 단계, `input_spans` 가 입력)를 칠하고, 후보에는 범위의 네 모서리를 넣는다.
    """
    r1, c1, r2, c2 = blk["rect"]
    corners = [(sp[i], sp[j]) for sp in ([cur_span] if cur_span else []) + list(input_spans) for i, j in ((0, 1), (2, 3))]
    focus = [cur] + list(inputs) + corners
    rows = _candidates(r1, r2, HEAD_ROWS, [r for r, _ in focus])
    cols = _candidates(c1, c2, HEAD_COLS, [c for _, c in focus])
    vals = book.sheet_values(blk["sheet"])
    return {"label": label_of(book, blk), "rect": list(blk["rect"]), "rows": rows, "cols": cols,
            "cells": {f"{r},{c}": show(vals[(r, c)]) for r in rows for c in cols if (r, c) in vals},
            "cur": list(cur), "inputs": [list(i) for i in inputs], "cur_span": cur_span, "input_spans": [list(x) for x in input_spans],
            "earlier": [], "far": []}


def build_views(book, steps, repeats):
    """단계마다 캡처 후보(`label` · `rect` · `rows` · `cols` · `cells` · `cur` · `inputs` · `earlier` · `far`)를 만든다.

    접힌 구간(repeats 항목)은 구간의 첫 단계 자리에 항목 하나를 두고(`inputs` 는 구간 처음 칸, `cur` 는 구간 끝 칸),
    구간 안의 나머지 단계는 None 이다. `far` 의 `j` 는 단계 번호이며, 접힌 구간 안이면 화면이 그 구간의 첫 단계로 바꾼다.
    """
    folds = {r["first"]: r for r in repeats}
    hidden = {i for r in repeats for i in range(r["first"], r["last"] + 1)}
    where = [block_of(book, s["sheet"], s["row"], s["col"]) for s in steps]
    seen = {}  # 덩어리별로 보통 단계 번호를 쌓아 두고 앞 단계에서 본 칸을 고른다
    views = [None] * len(steps)
    for i, s in enumerate(steps):
        r = folds.get(i)
        if r:
            ra, rb = r["rows"]
            blk = block_of(book, r["sheet"], rb, r["col"])
            first_inside = blk["rect"][0] <= ra <= blk["rect"][2]  # 구간의 처음 칸이 다른 덩어리에 있으면 입력으로 그리지 않는다
            views[i] = _view(book, blk, (rb, r["col"]), [(ra, r["col"])] if first_inside else [])
            continue
        if i in hidden:
            continue
        blk = where[i]
        key = (blk["sheet"], blk["rect"])
        same = lambda j: (where[j]["sheet"], where[j]["rect"]) == key  # noqa: E731
        inputs = [j for j in s["from"] if same(j)]
        spans = [sp for sp in (_clip(steps[j]["span"], blk["rect"]) for j in inputs if steps[j].get("span")) if sp]
        v = _view(book, blk, (s["row"], s["col"]), [(steps[j]["row"], steps[j]["col"]) for j in inputs],
                  _clip(s["span"], blk["rect"]) if s.get("span") else None, spans)
        past = seen.setdefault(key, [])
        v["earlier"] = [[steps[j]["row"], steps[j]["col"]] for j in past[-(EARLIER_MAX + len(inputs)):] if j not in inputs][-EARLIER_MAX:]
        v["far"] = [{"j": j, "addr": steps[j]["addr"], "value": steps[j]["value"], "label": label_of(book, where[j])}
                    for j in s["from"] if not same(j)]
        views[i] = v
        past.append(i)
    return views


SOURCE_KINDS = [("WINUS", "WINUS"), ("WFS", "WFS(우리펀드 서비스)"), ("DB 쿼리 연결", "DB 쿼리 연결"),
                ("외부 연결", "외부 연결"), ("외부 파일", "외부 파일"), ("수기 입력", "수기 입력")]


def build_sources(nodes, steps):
    """「출처 확인」 단계에 보일 출처 종류별 값 이름 목록.

    값이 나오는 단계(`kind == "value"`)만 넣는다. 가져오기 · 계산 · 피벗 · 표 열 제목 단계는 넣지 않는다.
    이름은 그 단계 열의 제목이고, 같은 열은 처음 나온 단계 하나만 넣는다. `j` 는 단계 번호이다. 쓰이지 않은 출처 종류는 뺀다.
    """
    title = {n["id"]: n["title"] for n in nodes}
    groups, seen = {key: [] for key, _ in SOURCE_KINDS}, set()
    for j, s in enumerate(steps):
        if s["kind"] != "value":
            continue
        key = next((k for k, _ in SOURCE_KINDS if (s.get("source") or "").startswith(k)), None)
        if key and (key, s["node"]) not in seen:  # 같은 열은 이름 하나다. 접힌 값도 앞의 보이는 단계로 간다
            seen.add((key, s["node"]))
            groups[key].append({"j": j, "name": title.get(s["node"], s["addr"]), "value": s["value"]})
    return [{"kind": key, "name": name, "items": groups[key]} for key, name in SOURCE_KINDS if groups[key]]
