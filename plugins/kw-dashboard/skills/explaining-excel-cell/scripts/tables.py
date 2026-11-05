"""엑셀 전체 분석 모드가 쓰는 표 단위 판단. 표, 머리글 행, 표 묶음, 날짜 시트 군을 찾는다.

표는 엑셀 표가 있으면 그 표이고, 없으면 빈 행과 빈 열로 나뉜 데이터 범위 하나다.
위치는 (r1, c1, r2, c2) 이고, 표 id 는 「시트!A1:C3」 형식이다.
"""
import datetime as dt
import re
from collections import Counter

from openpyxl.formula import Tokenizer

from explain_cell import a1, col_name

HEADER_MIN = 3  # 머리글 행으로 볼 글자 셀 최소 개수(근거 없는 시작 값)
HEADER_SHARE = 0.6  # 그 행 셀 중 글자 셀 비율(근거 없는 시작 값)
OUTSIDE_LIMIT = 200  # 표 밖 셀 목록의 상한(근거 없는 시작 값)
DATED = re.compile(r"(19|20)\d\d|(?<!\d)\d{6}(?!\d)|(?<!\d)\d{8}(?!\d)")
SUMMARY_LABEL = re.compile(r"소\s*계|합\s*계|총\s*계|총\s*합|계|total|sub\s*total|grand\s*total", re.I)
SUMMARY_FUNCS = ("SUM", "AVERAGE", "COUNT")
DATE_TEXT = re.compile(r"(19|20)\d{6}")
SUM_ABOVE = re.compile(r"=SUM\(([A-Z]+)(\d+):([A-Z]+)(\d+)\)", re.I)


def _text(v):
    return str(v).replace("\n", " ").strip() if isinstance(v, str) else None


def _is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _cell_text(book, sheet, pos):
    """셀의 글자. 병합 범위 안의 셀은 그 범위의 왼쪽 위 셀 글자를 쓴다."""
    return _text(book.sheet_values(sheet).get(book.merge_top.get(sheet, {}).get(pos, pos)))


def _row_texts(book, sheet, r, c1, c2):
    """r 행의 글자 셀 목록. 병합 범위의 셀은 왼쪽 위 셀 위치로 적는다.
    같은 행의 가로 병합만 센다. 위 행에서 내려온 세로 병합은 그 행의 머리글이 아니다."""
    tops = book.merge_top.get(sheet, {})
    heads = [tops.get((r, c), (r, c)) for c in range(c1, c2 + 1)]
    return [h for h in heads if h[0] == r and _text(book.sheet_values(sheet).get(h))]


def _looks_header(texts, c1, c2):
    need = HEADER_MIN if c2 == c1 else min(HEADER_MIN, c2 - c1 + 1)
    return len(set(texts)) >= 2 and len(texts) >= need and len(texts) >= HEADER_SHARE * (c2 - c1 + 1)  # 글자가 하나뿐이면 제목이다


def _has_second_row(book, sheet, area, r):
    """r 행에 가로 병합이 있고, 그 아래 셀이 모두 글자이고, 다음 행도 글자가 많으면 True.
    아래 행이 위 병합과 같은 폭으로 병합되어 있으면 나뉜 머리글이 아니라 데이터 행이다."""
    _, c1, r2, c2 = area
    spans = [m for m in book.merged.get(sheet, []) if m[0] == m[2] == r and m[3] > m[1] and c1 <= m[1] and m[3] <= c2]
    tops = book.merge_top.get(sheet, {})

    def split(m):
        cols = range(m[1], m[3] + 1)
        return all(_cell_text(book, sheet, (r + 1, c)) for c in cols) and len({tops.get((r + 1, c), (r + 1, c)) for c in cols}) >= 2

    texts = [c for c in range(c1, c2 + 1) if _cell_text(book, sheet, (r + 1, c))]
    return r < r2 and bool(spans) and all(split(m) for m in spans) and len(texts) >= HEADER_SHARE * (c2 - c1 + 1)


def header_row(book, sheet, area):
    """위쪽 3행 안에서 글자 셀이 3개 이상이고 그 행 셀의 60% 이상인 첫 행 번호. 열이 2개인 표는 글자 셀 2개면 된다.
    병합 제목과 단위 글자뿐인 행은 다음 행이 더 많은 글자로 머리글이면 넘어간다."""
    r1, c1, r2, c2 = area
    for r in range(r1, min(r1 + 3, r2 + 1)):
        texts = _row_texts(book, sheet, r, c1, c2)
        if not _looks_header(texts, c1, c2):
            continue
        below = _row_texts(book, sheet, r + 1, c1, c2)
        title = len(set(texts)) == 2 < len(texts) and _looks_header(below, c1, c2) and len(set(below)) > 2
        if not title or _has_second_row(book, sheet, area, r):
            return r
    return None


def header_rows(book, sheet, area):
    """머리글의 (첫 행, 끝 행). 머리글이 없으면 None."""
    r = header_row(book, sheet, area)
    if r is None:
        return None
    return (r, r + 1) if _has_second_row(book, sheet, area, r) else (r, r)


def column_levels(book, sheet, area, rows):
    """머리글 줄마다의 글자. 병합 범위는 그 범위의 글자로 채운다. rows 가 None 이면 빈 tuple."""
    if rows is None:
        return ()
    return tuple(tuple(_cell_text(book, sheet, (r, c)) or "" for c in range(area[1], area[3] + 1))
                 for r in range(rows[0], rows[1] + 1))


def join_levels(levels):
    """열마다 위아래 머리글을 「_」로 잇는다. 세로 병합으로 같은 글자가 이어지면 한 번만 쓴다."""
    out = []
    for parts in zip(*levels):
        kept = [p for i, p in enumerate(parts) if p and (i == 0 or p != parts[i - 1])]
        out.append("_".join(kept))
    return tuple(out)


def data_top(table):
    """표의 첫 데이터 행. 머리글이 없으면 범위의 첫 행이다."""
    rows = table["header_rows"]
    return rows[1] + 1 if rows else table["area"][0]


def db_column_name(text, col_letter):
    """샌드박스 열 이름 규칙에 맞는 이름. 언어는 그대로 두고 한글 · 영문 · 숫자 · 「_」 밖의 글자만 뺀다."""
    name = re.sub(r"[^0-9A-Za-z_가-힣]", "", text)
    if not name:
        return f"c_{col_letter}"
    return f"c_{name}" if name[0].isdigit() else name


def is_constant_formula(formula):
    """셀 · 범위 참조와 함수가 없는 수식(`=10369.6+6.04`)이면 True. 값으로 본다."""
    try:
        tokens = Tokenizer(formula).items
    except Exception:
        return False
    return not any(t.type == "FUNC" or (t.type == "OPERAND" and t.subtype == "RANGE") for t in tokens)


def _split(pos):
    """칸 위치 집합을 빈 열로 먼저, 이어서 빈 행으로 나눈 범위 목록(capture_views.detect_blocks 와 같은 규칙)."""
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
        for x in rg:
            inside = [(r, c) for r, c in pos if x[0] <= r <= x[-1] and g[0] <= c <= g[-1]]
            out.append((x[0], min(c for _, c in inside), x[-1], max(c for _, c in inside)))
    return out


def _split_around(pos, excel_areas):
    """_split 과 같되, 나눈 범위가 엑셀 표와 겹치면 그 엑셀 표의 위 · 아래 · 왼쪽 · 오른쪽 셀로 다시 나눈다.
    엑셀 표 아래 합계 행처럼 엑셀 표 밖 셀이 직사각형이 아닐 때 이름 없는 범위가 엑셀 표를 감싸지 않게 한다."""
    out = []
    for rect in _split(pos):
        ex = next((a for a in excel_areas if _overlap(a, rect)), None)
        if ex is None:
            out.append(rect)
            continue
        cells = {p for p in pos if _inside(p, rect)}
        parts = [{(r, c) for r, c in cells if r < ex[0]}, {(r, c) for r, c in cells if r > ex[2]},
                 {(r, c) for r, c in cells if ex[0] <= r <= ex[2] and c < ex[1]},
                 {(r, c) for r, c in cells if ex[0] <= r <= ex[2] and c > ex[3]}]
        for part in parts:
            out.extend(_split_around(part, excel_areas))
    return out


def _inside(pos, area):
    return area[0] <= pos[0] <= area[2] and area[1] <= pos[1] <= area[3]


def _has_formula(book, sheet, area):
    cells = book.cells[sheet]
    return any(c.kind == "formula" and _inside(p, area) and not is_constant_formula(book.formula(sheet, p) or "")
               for p, c in cells.items())


def _title(book, sheet, area, head):
    """머리글 행 위쪽(범위 안) 또는 범위 바로 위 2행의 첫 글자 셀."""
    vals = book.sheet_values(sheet)
    top = head if head else area[0]
    for r in list(range(area[0], top)) + list(range(max(1, area[0] - 2), area[0])):
        for c in range(area[1], area[3] + 1):
            if _text(vals.get((r, c))):
                return _text(vals[(r, c)])
    return ""


def find_tables(book, sheet):
    """시트의 표 목록. 엑셀 표를 먼저 정하고, 엑셀 표 밖 칸을 데이터 범위로 나눈다."""
    excel = [(name, tuple(t.area)) for name, t in book.tables.items() if t.sheet == sheet]
    pos = {p for p in set(book.cells.get(sheet, {})) | set(book.sheet_values(sheet))
           if not any(_inside(p, area) for _, area in excel)}
    out = [_make_table(book, sheet, whole, name, pos)
           for name, whole in excel + [(None, area) for area in _split_around(pos, [a for _, a in excel])]]
    return sorted(out, key=lambda t: (t["area"][0], t["area"][1]))


def _make_table(book, sheet, whole, name=None, pos=None):
    """범위 하나의 표 사전. pos 를 주면 오른쪽 끝의 머리글 없는 열을 뺀다."""
    rows = header_rows(book, sheet, whole)
    head = rows[0] if rows else None
    levels = column_levels(book, sheet, whole, rows)
    area, trimmed = (whole, []) if name or not rows or pos is None else _trim_headerless(whole, levels, pos)
    levels = tuple(line[:area[3] - area[1] + 1] for line in levels)
    return {"id": f"{sheet}!{a1(area[0], area[1])}:{a1(area[2], area[3])}", "sheet": sheet, "area": area,
            "header_row": head, "header_rows": rows, "levels": levels, "trimmed_cells": trimmed,
            "header": join_levels(levels) if rows else None, "excel_table": name,
            "title": _title(book, sheet, area, head), "has_formula": _has_formula(book, sheet, whole)}


def defined_area(table):
    """표 정의의 범위. 머리글 첫 행부터 마지막 행까지다. 제목 행과 기준일 표시 행을 표에 넣지 않는다."""
    r1, c1, r2, c2 = table["area"]
    return (table["header_row"] or r1, c1, r2, c2)


def apply_areas(book, found, saved):
    """결과 파일에서 고친 범위를 표 목록에 반영한다. 표 id 는 그대로 둔다. added 표시가 있는 항목은 새 표로 추가한다."""
    by_id = {t["id"]: t for t in found}
    for s in saved:
        area = tuple(s.get("area") or ())
        old = by_id.get(s["id"])
        if len(area) == 4 and old and area != defined_area(old):
            by_id[s["id"]] = {**_make_table(book, s["sheet"], area, old["excel_table"]), "id": s["id"]}
        elif len(area) == 4 and not old and s.get("added"):
            by_id[s["id"]] = {**_make_table(book, s["sheet"], area), "id": s["id"]}
    return list(by_id.values())


def date_header_columns(book, table):
    """날짜가 열로 펼쳐진 머리글 열 목록 [{"col", "rel"}]. 수식으로 만든 날짜 머리글이 2개 이상 이어져야 한다."""
    if not table["header_rows"]:
        return []
    r, (_, c1, _, c2) = table["header_rows"][1], table["area"]
    vals = book.sheet_values(table["sheet"])

    def dated(c):
        formula, value = book.formula(table["sheet"], (r, c)), vals.get((r, c))
        return bool(formula) and ("TODAY()" in formula.upper() or isinstance(value, dt.datetime) or bool(DATE_TEXT.fullmatch(str(value))))

    runs, run = [], []
    for c in range(c1, c2 + 2):
        if c <= c2 and dated(c):
            run.append(c)
        else:
            runs.append(run)
            run = []
    best = max(runs, key=len)
    return [{"col": col_name(c), "rel": i} for i, c in enumerate(best, 1)] if len(best) >= 2 else []


def _trim_headerless(area, levels, pos):
    """표 오른쪽 끝에서 머리글이 빈 열을 뺀다. (줄인 범위, 뺀 셀 위치 목록). 담당자가 표 옆에 둔 값이 표에 섞이지 않게 한다."""
    names = join_levels(levels)
    last = area[1] + max(i for i, name in enumerate(names) if name)
    cut = (area[0], area[1], area[2], last)
    return cut, sorted(p for p in pos if _inside(p, area) and p[1] > last)


def group_tables(tables):
    """같은 시트에서 머리글 행 글자가 같은 표끼리 묶는다. 공백과 괄호 안 글자(단위 등)는 비교에서 뺀다.
    머리글 행이 없는 표는 혼자 묶음이다."""
    groups, by_key = [], {}
    for t in tables:
        key = (t["sheet"], tuple(re.sub(r"\([^)]*\)|\s+", "", h) for h in t["header"])) if t["header"] else None
        if key in by_key:
            by_key[key]["tables"].append(t)
            continue
        g = {"id": f"g{len(groups) + 1}", "sheet": t["sheet"], "header": t["header"], "tables": [t]}
        groups.append(g)
        if key:
            by_key[key] = g
    return groups


def _numbers(name):
    return tuple(int(x) for x in re.findall(r"\d+", name))


def date_groups(sheet_names):
    """이름에서 숫자만 다르고 이름에 연도나 날짜 숫자가 있는 시트가 2개 이상이면 군이다. 기준은 이름 속 숫자가 가장 큰 시트."""
    fam = {}
    for s in sheet_names:
        if DATED.search(s):
            fam.setdefault(re.sub(r"\d+", "#", s.replace(" ", "")), []).append(s)
    out = []
    for pattern, sheets in fam.items():
        if len(sheets) < 2:
            continue
        ranked = sorted(sheets, key=_numbers)
        out.append({"pattern": pattern, "sheets": sorted(sheets, key=_numbers), "base": ranked[-1], "previous": ranked[-2]})
    return out


def analyzed_sheets(book, base_override=None):
    """(분석할 시트, 날짜 시트 군). 군의 기준 시트가 아닌 날짜 시트는 뺀다. base_override 는 {pattern: 시트}."""
    base_override = base_override or {}
    # 기준 시트가 None 인 군은 날짜 시트 군이 아니라는 사용자 답이므로 풀어서 모든 시트를 분석한다
    groups = [g for g in date_groups(book.order) if not (g["pattern"] in base_override and base_override[g["pattern"]] is None)]
    for g in groups:
        if base_override.get(g["pattern"]) in g["sheets"]:
            g["base"] = base_override[g["pattern"]]
            i = g["sheets"].index(g["base"])  # sheets 는 이름 속 숫자 순서다
            g["previous"] = g["sheets"][i - 1] if i > 0 else None
    skipped = {s for g in groups for s in g["sheets"] if s != g["base"]}
    return [s for s in book.order if s not in skipped], groups


def _overlap(area, other):
    """other 의 None 끝은 열린 끝(행 · 열 1부터 끝까지)이다."""
    r1, c1, r2, c2 = other
    r1, r2 = (r1 or 1), (r2 or 10 ** 7)
    c1, c2 = (c1 or 1), (c2 or 10 ** 5)
    return area[0] <= max(r1, r2) and area[2] >= min(r1, r2) and area[1] <= max(c1, c2) and area[3] >= min(c1, c2)


def _formula_cells(book, t):
    cells = book.cells[t["sheet"]]
    for p, c in cells.items():
        if c.kind == "formula" and (_inside(p, t["area"]) or p in t["trimmed_cells"]) and (t["sheet"], p) not in book.pivot_at:
            f = book.formula(t["sheet"], p) or ""
            if not is_constant_formula(f):
                yield p, f


def read_map(book, tables, skipped):
    """(표 id → 그 표 수식이 읽는 표 id 집합, 모호한 참조 목록 {sheet, cell, why}).

    why 는 broken(깨진 참조), dynamic(INDIRECT · OFFSET), past_sheet(분석하지 않는 날짜 시트)다. 외부 파일 참조는 둘 다에서 뺀다.
    """
    from types import SimpleNamespace
    import trace_cells
    by_sheet = {}
    for t in tables:
        by_sheet.setdefault(t["sheet"], []).append(t)
    reads, odd, seen = {t["id"]: set() for t in tables}, [], set()

    def note(sheet, p, why):
        if (sheet, p, why) not in seen:
            seen.add((sheet, p, why))
            odd.append({"sheet": sheet, "cell": a1(*p), "why": why})

    for t in tables:
        for p, f in _formula_cells(book, t):
            probe = SimpleNamespace(broken_refs=set(), dynamic_refs=set())
            refs = trace_cells._references(f, probe, (t["sheet"], *p))
            if probe.dynamic_refs:
                note(t["sheet"], p, "dynamic")
            if probe.broken_refs:
                note(t["sheet"], p, "broken")
            for ref in refs:
                got = book.resolve(ref[0] if isinstance(ref, tuple) else ref, t["sheet"], p)
                if got == "external":
                    continue
                if isinstance(got, str):
                    note(t["sheet"], p, "broken")
                    continue
                for other, area in got:
                    if other in skipped:
                        note(t["sheet"], p, "past_sheet")
                        continue
                    reads[t["id"]] |= {u["id"] for u in by_sheet.get(other, []) if u["id"] != t["id"] and _reads_table(u, area)}
    return reads, odd


def _reads_table(table, area):
    """참조 범위가 표나 표에서 뺀 셀과 겹치면 True."""
    return _overlap(table["area"], area) or any(_overlap((*p, *p), area) for p in table["trimmed_cells"])


def read_cells(book, tables, ids):
    """ids 표의 수식이 읽는 셀 집합 {(시트, (행, 열))}. 값이나 수식이 있는 셀만 센다."""
    from types import SimpleNamespace
    import trace_cells
    areas = set()
    for t in tables:
        if t["id"] not in ids:
            continue
        for p, f in _formula_cells(book, t):
            probe = SimpleNamespace(broken_refs=set(), dynamic_refs=set())
            for ref in trace_cells._references(f, probe, (t["sheet"], *p)):
                got = book.resolve(ref[0] if isinstance(ref, tuple) else ref, t["sheet"], p)
                if not isinstance(got, str):
                    areas.update((sheet, tuple(area)) for sheet, area in got)
    out = set()
    for sheet in {s for s, _ in areas}:
        mine = [a for s, a in areas if s == sheet]
        for p in set(book.cells.get(sheet, {})) | set(book.sheet_values(sheet)):
            if any(_overlap((*p, *p), a) for a in mine):
                out.add((sheet, p))
    return out


def outside_cells(book, sheet, used, unused, read, skip=()):
    """시트에서 쓰인 표 밖의 값 · 수식 셀 목록. {"items": 앞의 항목들, "total": 전체 수}.
    머리글이 있는 쓰이지 않는 표는 한 줄로 적고, 결과가 읽는 셀이 든 표와 머리글 없는 범위는 셀마다 적는다."""
    vals = book.sheet_values(sheet)
    titles = {t["title"] for t in used if t["title"]}
    whole = [t for t in unused if t["header_rows"] and not any((sheet, p) in read for p in _table_cells(book, t))]
    items = [{"kind": "표", "where": t["id"].rpartition("!")[2], "value": t["title"], "formula": None,
              "read_by_result": False, "action": "버림"} for t in whole]
    for p in sorted(set(book.cells.get(sheet, {})) | set(vals)):
        inside = any(_inside(p, t["area"]) and p[0] >= (t["header_row"] or 0) for t in used)  # 머리글 위 행은 표가 아니다
        formula = book.formula(sheet, p)
        if inside or p in skip or any(_inside(p, t["area"]) for t in whole) or _text(vals.get(p)) in titles or not (formula or p in vals):
            continue
        hit = (sheet, p) in read
        items.append({"kind": "셀", "where": a1(*p), "value": vals.get(p), "formula": formula, "read_by_result": hit,
                      "action": "별도 표로 저장" if hit else "개발 고정값 표에 저장"})
    return {"items": items[:OUTSIDE_LIMIT], "total": len(items)}


def _table_cells(book, table):
    sheet = table["sheet"]
    return [p for p in set(book.cells.get(sheet, {})) | set(book.sheet_values(sheet)) if _inside(p, table["area"])]


def _ancestors(reads, ids):
    out, todo = set(), list(ids)
    while todo:
        for nxt in reads.get(todo.pop(), ()):
            if nxt not in out:
                out.add(nxt)
                todo.append(nxt)
    return out


def nameless_read(tables, reads, result_ids):
    """결과표가 직접이나 간접으로 읽는 표 중 머리글 행이 없는 표 id."""
    up = _ancestors(reads, result_ids) - set(result_ids)
    return [t["id"] for t in tables if t["id"] in up and t["header"] is None]


def candidates(tables, reads):
    """결과표 후보 시트 목록. 후보 표는 수식 셀이 있고 다른 표가 읽지 않는 표다. reads 는 그 시트 후보들이 읽는 표 수.

    표끼리 서로 읽는 순환은 순환 밖의 표가 읽지 않으면 순환 안의 표를 모두 후보로 본다.
    """
    readers = {}
    for k, v in reads.items():
        for x in v:
            readers.setdefault(x, set()).add(k)
    out = {}
    for t in tables:
        up = _ancestors(reads, [t["id"]])
        if t["has_formula"] and all(r in up for r in readers.get(t["id"], ())):
            out.setdefault(t["sheet"], []).append(t["id"])
    return [{"sheet": s, "tables": ids, "reads": len(_ancestors(reads, ids) - set(ids))} for s, ids in out.items()]


def column_kinds(book, table):
    """(값만 있는 열 수, 수식 열 수). 머리글 행 아래만 본다. 상수 수식은 값으로 센다."""
    r1, c1, r2, c2 = table["area"]
    top = data_top(table)
    cells, vals = book.cells[table["sheet"]], book.sheet_values(table["sheet"])
    values = formulas = 0
    for c in range(c1, c2 + 1):
        kinds = set()
        for r in range(top, r2 + 1):
            cell = cells.get((r, c))
            if cell is not None and cell.kind == "formula":
                kinds.add("v" if is_constant_formula(book.formula(table["sheet"], (r, c)) or "") else "f")
            elif (r, c) in vals:
                kinds.add("v")
        if "f" in kinds:
            formulas += 1
        elif "v" in kinds:
            values += 1
    return values, formulas


def classify(book, tables, reads, result_ids):
    """결과표의 조상을 원천과 계산으로 나눈다. 값 열 수가 수식 열 수보다 많으면 원천, 아니면 계산."""
    up = _ancestors(reads, result_ids) - set(result_ids)
    by_id = {t["id"]: t for t in tables}
    source, calc = [], []
    for t in tables:
        if t["id"] in up:
            v, f = column_kinds(book, by_id[t["id"]])
            (source if v > f else calc).append(t["id"])
    level = {}

    def depth(i, path=()):
        if i not in level:
            ups = [j for j in reads.get(i, ()) if j in up and j not in path]
            level[i] = 1 + max((depth(j, path + (i,)) for j in ups), default=-1)
        return level[i]

    members = [t["id"] for t in tables if t["id"] in up or t["id"] in result_ids]
    order = sorted(members, key=lambda i: (depth(i), members.index(i)))
    return {"source": source, "calc": calc, "result": [t["id"] for t in tables if t["id"] in result_ids], "order": order}


def row_order(book, table):
    """「순위」를 포함한 머리글 열의 값이 행 순서대로 오름차순이면 「순위 순」, 아니면 「판정할 수 없음」."""
    if not table["header"]:
        return "판정할 수 없음"
    vals = book.sheet_values(table["sheet"])
    r1, c1, r2, _ = table["area"]
    for i, h in enumerate(table["header"]):
        if "순위" in h:
            seq = [vals.get((r, c1 + i)) for r in range(data_top(table), r2 + 1)]
            nums = [x for x in seq if isinstance(x, (int, float)) and not isinstance(x, bool)]
            if len(nums) >= 2 and nums == sorted(nums) and len(nums) == len([x for x in seq if x is not None]):
                return "순위 순"
    return "판정할 수 없음"


def _column_of(token, table):
    """참조 글자가 이 표의 한 열 안이면 (열 번호, 행 목록). 다른 시트 참조나 표 밖이면 None."""
    import trace_cells
    area = None if token is None or "!" in token.value else trace_cells._parse_area(token.value)
    r1, c1, r2, c2 = table["area"]
    if not area or None in area or area[1] != area[3] or not (c1 <= area[1] <= c2 and r1 <= area[0] and area[2] <= r2):
        return None
    return area[1], range(area[0], area[2] + 1)


def _call_args(items, start):
    """함수 여는 토큰 위치에서 (닫는 토큰 위치, 인수별 토큰 목록)."""
    args, depth = [[]], 0
    for i in range(start + 1, len(items)):
        t = items[i]
        if t.subtype == "CLOSE" and t.type == "FUNC" and depth == 0:
            return i, args
        depth += (t.type in ("FUNC", "PAREN") and t.subtype == "OPEN") - (t.type in ("FUNC", "PAREN") and t.subtype == "CLOSE")
        if t.type == "SEP" and depth == 0:
            args.append([])
        else:
            args[-1].append(t)
    return len(items), args


def _summary_call(name, args, table, names, found, rows):
    """함수 하나를 식 문법으로 옮긴다. 문법에 없는 함수나 인수는 None. 읽는 데이터 행을 rows 에 추가한다."""
    def column(arg):
        got = _column_of(arg[0], table) if len(arg) == 1 and arg[0].subtype == "RANGE" else None
        if got:
            rows.update(r for r in got[1] if r not in found)
        return names[got[0] - table["area"][1]] if got else None

    if name in SUMMARY_FUNCS:
        cols = {column(a) for a in args}
        return f"{name}({cols.pop()})" if len(cols) == 1 and None not in cols else None
    if name == "SUMPRODUCT" and len(args) == 2:
        a, b = column(args[0]), column(args[1])
        return f"SUMPRODUCT({a}, {b})" if a and b else None
    if name == "SUMIF" and len(args) == 3 and len(args[1]) == 1 and args[1][0].subtype in ("TEXT", "NUMBER"):
        a, b = column(args[0]), column(args[2])
        return f"SUMIF({a}, {args[1][0].value}, {b})" if a and b else None
    return None


def _summary_expr(formula, table, names, found):
    """합계 셀 수식을 식 문법으로 옮긴다. (식, 읽는 데이터 행 집합). 옮기지 못하면 (None, 빈 집합).
    found 는 표의 소계 행 번호 → {"label", "rows"} 이다."""
    items = [t for t in Tokenizer(formula).items if t.type != "WHITE-SPACE"]
    cells = [_column_of(t, table) for t in items[::2]]
    if len(items) > 1 and all(cells) and all(t.value == "+" for t in items[1::2]) and len({c[0] for c in cells}) == 1:
        got = [found.get(r, {"rows": {r}}).get("rows") for c in cells for r in c[1]]  # 셀 더하기는 그 열의 합이다
        if None not in got:
            return f"SUM({names[cells[0][0] - table['area'][1]]})", set().union(*got)
    out, rows, i = [], set(), 0
    while i < len(items):
        t = items[i]
        if t.type == "FUNC" and t.subtype == "OPEN":
            i, args = _call_args(items, i)
            out.append(_summary_call(t.value[:-1].upper(), args, table, names, found, rows))
        elif t.type == "OPERAND" and t.subtype == "NUMBER":
            out.append(t.value)
        elif t.type == "OPERAND" and t.subtype == "RANGE":
            got = _column_of(t, table)
            row = got[1][0] if got and len(got[1]) == 1 else None
            label = found.get(row, {}).get("label")
            out.append(f'ROW("{label}", {names[got[0] - table["area"][1]]})' if label else None)
        elif t.type == "OPERATOR-INFIX" and t.value in "+-*/":
            out.append(f" {t.value} ")
        elif t.type == "PAREN":
            out.append(t.value)
        else:
            out.append(None)
        if out[-1] is None:
            return None, set()
        i += 1
    return "".join(out), rows


def _sums_above(formula, col, top, row):
    m = SUM_ABOVE.fullmatch((formula or "").replace("$", ""))
    return bool(m) and m[1] == m[3] == col_name(col) and top <= int(m[2]) and int(m[4]) < row


def _group_column(book, table, rows, data, names):
    """rows 의 값이 모두 같고 나머지 데이터 행과 다른 왼쪽 첫 글자 열 이름. 없으면 None."""
    _, c1, _, c2 = table["area"]
    for c in range(c1, c2 + 1):
        inside = {_cell_text(book, table["sheet"], (r, c)) for r in rows}
        outside = {_cell_text(book, table["sheet"], (r, c)) for r in data if r not in rows}
        if len(inside) == 1 and None not in inside and not inside & outside:
            return names[c - c1]
    return None


def summary_rows(book, table):
    """표의 소계 · 합계 행 목록. 행은 개발 시점 엑셀 행이고, 운영 중 묶음은 group_by 열 값으로 정한다.
    식 문법 밖의 셀, 값을 직접 적은 셀, 묶는 열을 찾지 못한 셀은 expr 값이 None 이다."""
    r1, c1, r2, c2 = table["area"]
    sheet, top, vals = table["sheet"], data_top(table), book.sheet_values(table["sheet"])
    header = table["header"] or ("",) * (c2 - c1 + 1)
    names = [db_column_name(h, col_name(c1 + i)) for i, h in enumerate(header)]
    found = {}
    for r in range(top, r2 + 1):
        label = next(((c, _text(vals.get((r, c)))) for c in range(c1, c2 + 1)
                      if _text(vals.get((r, c))) and SUMMARY_LABEL.fullmatch(_text(vals[(r, c)]))), None)
        numbers = [c for c in range(c1, c2 + 1) if book.formula(sheet, (r, c)) or _is_number(vals.get((r, c)))]
        sums = [c for c in numbers if _sums_above(book.formula(sheet, (r, c)), c, top, r)]
        if label or (sums and 2 * len(sums) >= len(numbers)):
            found[r] = {"label": label[1] if label else "", "label_col": names[label[0] - c1] if label else None, "numbers": numbers}
    data = [r for r in range(top, r2 + 1) if r not in found]
    out = []
    for r, s in found.items():
        cells = {}
        for c in s["numbers"]:
            formula = book.formula(sheet, (r, c))
            cells[names[c - c1]] = _summary_expr(formula, table, names, found) if formula else (None, set())
        sets = Counter(frozenset(rows) for _, rows in cells.values() if rows)
        main = set(sets.most_common(1)[0][0]) if sets else set()
        group = None if not main or main >= set(data) else _group_column(book, table, main, data, names)
        keep = not main or main >= set(data) or group is not None
        s["rows"] = main
        out.append({"row": r, "label": s["label"], "label_col": s["label_col"], "group_by": group,
                    "expr": {n: e if keep and (not rows or rows == main) else None for n, (e, rows) in cells.items()}})
    return out


def data_rows(table, summaries):
    """표의 데이터 행 번호 목록. 소계 · 합계 행은 뺀다."""
    skip = {s["row"] for s in summaries}
    return [r for r in range(data_top(table), table["area"][2] + 1) if r not in skip]
