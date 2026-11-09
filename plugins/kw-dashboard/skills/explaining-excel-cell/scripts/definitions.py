"""결과에 쓰이는 표의 정의를 제안하고, 저장된 정의와 합치고, 확인할 항목을 찾는다.

정의는 explain_results.json 의 definitions 에 남고, 대시보드 스킬은 이 항목만 읽는다.
"""
import datetime as dt
import re
from collections import Counter

import sources
import tables as tb
from explain_cell import a1, col_name, parse_a1


LABEL_START = re.compile(r", (?=변수 |셀 |쿼리 )")
TODAY = re.compile(r"=\s*(?:TEXT\()?\s*TODAY\(\)\s*([+-]\s*\d+)?\s*(?:,[^()]*\))?\s*", re.I)
CELL_IN_LABEL = re.compile(r'셀 ([A-Z]+\d+) 를 읽는|(?:(?:Work)?[Ss]heets\("([^"]+)"\)\.)?(?:Range\("([A-Z]+\d+)"\)|Cells\((\d+),\s*(\d+)\))')


def base_date_relation(book, found):
    """기준일 셀과 오늘 날짜와의 관계. 수식 전체가 TODAY()±n 인 셀 중 수식이 가장 많이 읽는 셀이다. 없으면 None.
    WORKDAY 같은 함수로 감싼 수식은 며칠 차이인지 알 수 없으므로 후보에서 빼고 개발자에게 묻는다.
    데이터 행이 있는 표의 머리글 셀은 날짜 머리글이므로 뺀다."""
    heads = {(t["sheet"], (r, c)) for t in found if t["header_rows"] and tb.data_top(t) <= t["area"][2]
             for r in range(t["header_rows"][0], t["header_rows"][1] + 1) for c in range(t["area"][1], t["area"][3] + 1)}
    cands = {}
    for sheet in dict.fromkeys(t["sheet"] for t in found):
        for p, cell in book.cells[sheet].items():
            hit = TODAY.fullmatch(cell.formula or "") if cell.kind == "formula" else None
            if hit and (sheet, p) not in heads:
                cands[(sheet, p)] = hit
    if not cands:
        return None
    counts = tb.read_count(book, found, set(cands))
    sheet, p = max(cands, key=lambda k: counts[k])
    days = (cands[(sheet, p)].group(1) or "0").replace(" ", "")
    return {"sheet": sheet, "cell": a1(*p), "formula": book.formula(sheet, p), "days": int(days)}


def suggested(relation):
    """기준일 관계로 만든 질문 제안값. 관계를 모르면 비워 둔다."""
    if relation is None:
        return {"date_input": {"on": True, "default": ""}, "allow_today": None}
    days = relation["days"]
    default = {-1: "어제", 0: "오늘"}.get(days, f"오늘 {days:+d}일")
    return {"date_input": {"on": True, "default": default}, "allow_today": days >= 0}


def input_cells(text, sheet_names):
    """연결의 입력 글자에서 셀 주소를 찾는다. (찾은 셀 목록, 찾지 못한 입력 글자 목록)."""
    found, unknown = [], []
    for label in (x.strip() for x in LABEL_START.split(text) if x.strip()):
        hits = list(CELL_IN_LABEL.finditer(label))
        if not hits:
            unknown.append(label)
        for m in hits:
            cell = m[1] or m[3] or a1(int(m[4]), int(m[5]))
            found.append({"sheet": m[2] if m[2] in sheet_names else None, "cell": cell})
    return found, unknown


def parameter_cells(book):
    """WINUS 쿼리에 넣는 값이 든 셀. 입력 글자에 시트가 없으면 sheet 를 None 으로 두고 개발자에게 묻는다."""
    found, unknown = [], []
    for x in book.loaded_ranges:
        cells, rest = input_cells(x.get("inputs") or "", book.order)
        found += [{**c, "connection": x["name"]} for c in cells]
        unknown += rest
    return {"found": [dict(t) for t in dict.fromkeys(tuple(f.items()) for f in found)], "unknown": list(dict.fromkeys(unknown))}


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


def _columns(book, table, summaries, dated, old):
    """열 목록. old 는 저장된 정의이고, 개발자가 고친 열 이름과 형식을 지킨다."""
    _, c1, _, c2 = table["area"]
    header = table["header"] or ("",) * (c2 - c1 + 1)
    relative = {d["col"]: f"t_plus_{d['rel']}" for d in dated}
    kept = {c["col"]: c for c in old.get("columns", [])}
    out = []
    for i, c in enumerate(range(c1, c2 + 1)):
        letter = col_name(c)
        mine = kept.get(letter, {})
        out.append({"col": letter, "header": header[i],
                    "db": mine.get("db") or relative.get(letter) or tb.db_column_name(header[i], letter),
                    "type": mine.get("type") or column_type(book, table, c, summaries)})
    return out


def _entry(book, table, classes, result_ids, outside, old):
    rows = tb.summary_rows(book, table)
    dated = tb.date_header_columns(book, table)
    columns = _columns(book, table, rows, dated, old)
    summaries = tb.summary_rows(book, table, [c["db"] for c in columns])
    return {"id": table["id"], "sheet": table["sheet"], "area": list(tb.defined_area(table)), "target": "", "confirmed": False,
            "role": _role(book, table, classes, result_ids), "source": _connection(book, table),
            "header_rows": list(table["header_rows"] or []), "levels": [list(x) for x in table["levels"]],
            "columns": columns, "date_columns": dated, "summaries": summaries,
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
    base = base_date_relation(book, found)
    owners = {}
    for sheet in dict.fromkeys(t["sheet"] for t in used):
        mine = [t for t in used if t["sheet"] == sheet]
        biggest = max(mine, key=lambda t: (t["area"][2] - t["area"][0] + 1) * (t["area"][3] - t["area"][1] + 1))
        rest = [t for t in found if t["sheet"] == sheet and t["id"] not in ids]
        skip = {parse_a1(base["cell"])} if base and base["sheet"] == sheet else set()  # 기준일 셀은 결과 파일의 base_date 가 맡는다
        owners[biggest["id"]] = tb.outside_cells(book, sheet, mine, rest, read, skip)
    old = {s["id"]: s for s in saved}
    return [_entry(book, t, classes, result_ids, owners.get(t["id"], empty), old.get(t["id"], {})) for t in used]


def _keep_answers(new, old):
    """분석 값은 새로 쓰고, 개발자가 정한 값과 모르는 항목은 지킨다. 역할은 표를 확인한 뒤부터 지킨다."""
    out = {**{k: v for k, v in old.items() if k != "orphan"}, **new}
    out["target"], out["confirmed"] = old.get("target", new["target"]), old.get("confirmed", new["confirmed"])
    if out["confirmed"]:
        out["role"] = old.get("role", new["role"])
    answers = {i["where"]: i for i in old.get("outside", {}).get("items", [])}
    items = [{**i, "action": answers.get(i["where"], i)["action"], "target": answers.get(i["where"], {}).get("target", i.get("target", ""))}
             for i in new["outside"]["items"]]
    out["outside"] = {**new["outside"], "items": items}
    answers = {s["row"]: s["expr"] for s in old.get("summaries", [])}
    out["summaries"] = [{**s, "expr": {k: v if v is not None else answers.get(s["row"], {}).get(k) for k, v in s["expr"].items()}}
                        for s in new["summaries"]]
    return out


def merge(proposed, saved):
    """제안을 저장된 정의와 합친다. 분석이 찾지 못한 저장 항목은 지우지 않고 orphan 으로 표시한다."""
    old = {s["id"]: s for s in saved}
    out = [_keep_answers(p, old.pop(p["id"])) if p["id"] in old else p for p in proposed]
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
        for item in d.get("outside", {}).get("items", []):
            if item["action"] == "확인 필요":
                out.append(f"{where}: 혼자 있는 값 확인 필요 {item['where']}")
            elif item["action"] == "별도 표로 저장" and not item.get("target"):
                out.append(f"{where}: 저장할 표 이름 없음 {item['where']}")
    return out
