"""결과에 쓰이는 표의 정의를 제안하고, 저장된 정의와 합치고, 확인할 항목을 찾는다.

정의는 explain_results.json 의 definitions 에 남고, 대시보드 스킬은 이 항목만 읽는다.
"""
import datetime as dt
from collections import Counter

import sources
import tables as tb
from explain_cell import a1, col_name


def _area_text(area):
    return f"{a1(area[0], area[1])}:{a1(area[2], area[3])}"


def _role(book, table, classes, result_ids):
    if table["id"] in result_ids:
        return "결과"
    if table["id"] in classes["calc"]:
        return "계산"
    return "수기 입력" if list(sources.source_of(book, [table])["kinds"]) == ["수기 입력"] else "원천"


def _connection(book, table):
    """표 범위를 채우는 연결. 없으면 None."""
    hit = next((x for x in book.loaded_ranges if x["sheet"] == table["sheet"] and tb._overlap(table["area"], x["area"])), None)
    return {"name": hit["name"], "kind": hit["kind"], "origin": hit["source"]} if hit else None


def column_type(book, table, col, summaries):
    """열의 형식. text · code · number · date 중 하나다. 코드 열을 숫자로 두면 맨 앞의 0 이 사라지므로 따로 나눈다."""
    vals = book.sheet_values(table["sheet"])
    seen = [vals[(r, col)] for r in tb.data_rows(table, summaries) if (r, col) in vals]
    head = (table["header"] or ("",) * (col + 1))[col - table["area"][1]]
    if "코드" in head or any(isinstance(v, str) and v.isdigit() and v.startswith("0") for v in seen):
        return "code"
    if seen and all(isinstance(v, (dt.datetime, dt.date)) for v in seen):
        return "date"
    return "number" if seen and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in seen) else "text"


def _columns(book, table, summaries, dated):
    _, c1, _, c2 = table["area"]
    header = table["header"] or ("",) * (c2 - c1 + 1)
    relative = {d["col"]: f"t_plus_{d['rel']}" for d in dated}
    out = []
    for i, c in enumerate(range(c1, c2 + 1)):
        letter = col_name(c)
        out.append({"col": letter, "header": header[i], "db": relative.get(letter) or tb.db_column_name(header[i], letter),
                    "type": column_type(book, table, c, summaries)})
    return out


def _entry(book, table, classes, result_ids, outside):
    summaries = tb.summary_rows(book, table)
    dated = tb.date_header_columns(book, table)
    return {"id": table["id"], "sheet": table["sheet"], "area": list(tb.defined_area(table)), "target": "", "confirmed": False,
            "role": _role(book, table, classes, result_ids), "source": _connection(book, table),
            "header_rows": list(table["header_rows"] or []), "levels": [list(x) for x in table["levels"]],
            "columns": _columns(book, table, summaries, dated), "date_columns": dated, "summaries": summaries,
            "outside": outside, "data_row_count": len(tb.data_rows(table, summaries))}


def propose(book, analysis, results, saved=()):
    """결과에 쓰이는 표마다 정의를 제안한다. 결과표와 그 조상 표, 저장된 정의에 있는 표가 대상이다.
    표 밖 셀 목록은 시트마다 하나이고, 그 시트에서 가장 큰 쓰인 표의 정의에 넣는다."""
    found, reads = analysis["tables"], analysis["reads"]
    result_ids = {r["table"] for r in results["results"]}
    classes = tb.classify(book, found, reads, result_ids)
    known = {t["id"] for t in found}
    ids = set(classes["source"]) | set(classes["calc"]) | result_ids | ({s["id"] for s in saved} & known)
    read = tb.read_cells(book, found, ids)
    used = [t for t in found if t["id"] in ids]
    empty = {"items": [], "total": 0}
    owners = {}
    for sheet in dict.fromkeys(t["sheet"] for t in used):
        mine = [t for t in used if t["sheet"] == sheet]
        biggest = max(mine, key=lambda t: (t["area"][2] - t["area"][0] + 1) * (t["area"][3] - t["area"][1] + 1))
        rest = [t for t in found if t["sheet"] == sheet and t["id"] not in ids]
        owners[biggest["id"]] = tb.outside_cells(book, sheet, mine, rest, read)
    return [_entry(book, t, classes, result_ids, owners.get(t["id"], empty)) for t in used]


def merge(proposed, saved):
    """저장된 값을 우선하고 제안에만 있는 항목을 채운다. 분석이 찾지 못한 저장 항목은 지우지 않고 orphan 으로 표시한다."""
    old = {s["id"]: s for s in saved}
    out = []
    for p in proposed:
        kept = {k: v for k, v in old.pop(p["id"], {}).items() if k != "orphan"}
        out.append({**p, **kept})
    return out + [{**s, "orphan": True} for s in old.values()]


def conflicts(defs):
    """개발자에게 확인할 항목 목록(문장)."""
    out = []
    targets = Counter(d.get("target") for d in defs if d.get("target"))
    for i, d in enumerate(defs):
        where = f"{d['sheet']}!{_area_text(d['area'])}"
        if d.get("orphan"):
            out.append(f"{where}: 표를 찾지 못함")
            continue
        names = Counter(c["db"] for c in d.get("columns", []))
        out += [f"{where}: 열 이름 겹침 {n}" for n, count in names.items() if count > 1]
        for other in defs[i + 1:]:
            if other["sheet"] == d["sheet"] and not other.get("orphan") and tb._overlap(d["area"], other["area"]):
                out.append(f"{where}: 범위 겹침 {_area_text(other['area'])}")
        if d.get("confirmed") and not d.get("target"):
            out.append(f"{where}: 대상 이름 없음")
        if targets.get(d.get("target"), 0) > 1:
            out.append(f"{where}: 대상 이름 겹침 {d['target']}")
        out += [f"{where}: 소계 식 확인 필요 {s['label']}" for s in d.get("summaries", []) if None in s["expr"].values()]
    return out
