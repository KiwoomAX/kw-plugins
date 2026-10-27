"""엑셀 전체 분석 모드가 쓰는 표 단위 판단. 표, 머리글 행, 표 묶음, 날짜 시트 군을 찾는다.

표는 엑셀 표가 있으면 그 표이고, 없으면 빈 행과 빈 열로 나뉜 데이터 범위 하나다.
위치는 (r1, c1, r2, c2) 이고, 표 id 는 「시트!A1:C3」 형식이다.
"""
import re

from openpyxl.formula import Tokenizer

from explain_cell import a1

HEADER_MIN = 3  # 머리글 행으로 볼 글자 셀 최소 개수(근거 없는 시작 값)
HEADER_SHARE = 0.6  # 그 행 셀 중 글자 셀 비율(근거 없는 시작 값)
DATED = re.compile(r"(19|20)\d\d|(?<!\d)\d{6}(?!\d)|(?<!\d)\d{8}(?!\d)")


def _text(v):
    return str(v).replace("\n", " ").strip() if isinstance(v, str) else None


def header_row(book, sheet, area):
    """위쪽 3행 안에서 글자 셀이 3개 이상이고 그 행 셀의 60% 이상인 첫 행 번호. 열이 2개인 표는 글자 셀 2개면 된다."""
    r1, c1, r2, c2 = area
    vals = book.sheet_values(sheet)
    need = HEADER_MIN if c2 == c1 else min(HEADER_MIN, c2 - c1 + 1)
    for r in range(r1, min(r1 + 3, r2 + 1)):
        texts = [c for c in range(c1, c2 + 1) if _text(vals.get((r, c)))]
        if len(texts) >= need and len(texts) >= HEADER_SHARE * (c2 - c1 + 1):
            return r
    return None


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
    out = []
    for name, area in excel + [(None, area) for area in _split_around(pos, [a for _, a in excel])]:
        head = header_row(book, sheet, area)
        vals = book.sheet_values(sheet)
        header = tuple(_text(vals.get((head, c))) or "" for c in range(area[1], area[3] + 1)) if head else None
        out.append({"id": f"{sheet}!{a1(area[0], area[1])}:{a1(area[2], area[3])}", "sheet": sheet, "area": area,
                    "header_row": head, "header": header, "excel_table": name,
                    "title": _title(book, sheet, area, head), "has_formula": _has_formula(book, sheet, area)})
    return sorted(out, key=lambda t: (t["area"][0], t["area"][1]))


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
        if c.kind == "formula" and _inside(p, t["area"]) and (t["sheet"], p) not in book.pivot_at:
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
                    reads[t["id"]] |= {u["id"] for u in by_sheet.get(other, []) if u["id"] != t["id"] and _overlap(u["area"], area)}
    return reads, odd


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


def result_tables(tables, groups, reads, sheet, excel_table=None):
    """사용자가 고른 시트의 결과표 id 집합. 엑셀 표를 골랐으면 그 표다.

    시트 안에서 같은 시트의 다른 묶음이 읽지 않는 묶음의 표가 결과표다. 같은 묶음 안의 읽기는 따지지 않는다.
    모든 묶음이 서로 읽으면 시트의 모든 표가 결과표다.
    """
    mine = [t for t in tables if t["sheet"] == sheet and (not excel_table or t["excel_table"] == excel_table)]
    if excel_table:
        return {t["id"] for t in mine}
    group_of = {t["id"]: g["id"] for g in groups for t in g["tables"]}
    ids = {t["id"] for t in mine}
    read = {x for t in mine for x in reads.get(t["id"], ()) if x in ids and group_of[x] != group_of[t["id"]]}
    return (ids - read) or ids


def column_kinds(book, table):
    """(값만 있는 열 수, 수식 열 수). 머리글 행 아래만 본다. 상수 수식은 값으로 센다."""
    r1, c1, r2, c2 = table["area"]
    top = (table["header_row"] or r1 - 1) + 1
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
            seq = [vals.get((r, c1 + i)) for r in range(table["header_row"] + 1, r2 + 1)]
            nums = [x for x in seq if isinstance(x, (int, float)) and not isinstance(x, bool)]
            if len(nums) >= 2 and nums == sorted(nums) and len(nums) == len([x for x in seq if x is not None]):
                return "순위 순"
    return "판정할 수 없음"
