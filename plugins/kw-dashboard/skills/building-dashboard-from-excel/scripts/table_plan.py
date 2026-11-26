"""엑셀 분석기의 표 정의로 만들 표의 이름 · 열 · primary key 를 정한다.

표 이름은 `{엑셀}__{단계}__{대상}` 이고, 단계는 raw_winus · raw_wfs · raw_manual · fixed · calc · stat 이다. stat(통계 표)은 저장하지 않고 calc.py 가 계산만 한다.
실행: python table_plan.py check <엑셀> --results explain_results.json --facts explain_facts.json   표 정의 검사(먼저 실행)
      python table_plan.py <explain_results.json> --slug <엑셀 영문 이름> --sources <sources.json> --schema <스키마> --out table_plan.json
      python table_plan.py requests --plan table_plan.json --out create        표마다 만들기 요청 파일
      python table_plan.py compare --plan table_plan.json --described described.json   이미 있는 표와 대조
      python table_plan.py columns <엑셀> --results explain_results.json --definition <표 id>   열마다 결과 계산이 읽는지
"""
import argparse
import datetime as dt
import json
import re
import sys
from collections import Counter
from pathlib import Path

from openpyxl.formula import Tokenizer
from openpyxl.utils import column_index_from_string, get_column_letter

STAGE = {"winus": "raw_winus", "wfs": "raw_wfs", "manual": "raw_manual"}
COMMON = [{"name": "base_date", "type": "date"}, {"name": "base_time", "type": "timestamptz"}, {"name": "loaded_at", "type": "timestamptz"}]
TYPES = {"text": {"type": "text"}, "code": {"type": "varchar", "length": 50}, "number": {"type": "numeric"}, "date": {"type": "date"}}
COLUMN = re.compile(r"^\$?([A-Za-z]{1,3})(?:\$?\d+)?$")  # A1 · $A$1 · A(열 전체)
REGISTRY = [("excel", "text"), ("table_name", "text"), ("stage", "text"), ("definition_id", "text"), ("schema_name", "text"), ("columns_json", "text"),
            ("row_map_json", "text"), ("query_id", "integer"), ("waiting_query", "boolean"), ("updated_at", "timestamptz")]
UPLOAD = [("upload_id", "text"), ("excel", "text"), ("base_date", "date"), ("base_time", "timestamptz"), ("status", "text"), ("kind", "text"),
          ("uploaded_by", "text"), ("started_at", "timestamptz"), ("finished_at", "timestamptz")]


def _key(hourly, last):
    return ["base_date"] + (["base_time"] if hourly else []) + [last]


def _column(c, levels, index):
    return {"name": c["db"], **TYPES[c["type"]], "header": c["header"], "levels": [line[index] for line in levels], "excel_col": c["col"]}


def _kind(d, sources):
    """표의 출처 종류. 4단계에서 정한 값이 우선이고, 없으면 분석기의 역할과 연결로 정한다."""
    if d["id"] in sources:
        return sources[d["id"]]
    if d["role"] == "수기 입력":
        return "manual"
    origin = (d.get("source") or {}).get("origin")
    return {"WINUS": "winus", "WFS": "wfs"}.get(origin, "manual")


def _table(excel, stage, target, d, extra, key, **more):
    columns = [_column(c, d["levels"], i) for i, c in enumerate(d["columns"])]
    return {"name": f"{excel}__{stage}__{target}", "stage": stage, "definition_id": d["id"], "primary_key": key,
            "description": f"{excel} 엑셀 「{d['sheet']}」 시트의 표({d['id'].rsplit('!', 1)[-1]})",
            "columns": COMMON + extra + columns, "summaries": d["summaries"], "editable": False, "waiting_query": False, "query_id": None, **more}


def _simple(name, stage, description, columns, key):
    return {"name": name, "stage": stage, "description": description, "columns": [{"name": n, "type": t} for n, t in columns],
            "primary_key": key, "editable": False, "waiting_query": False, "query_id": None}


def _dates_table(excel, d, hourly):
    columns = [{"name": f"t_plus_{x['rel']}", "type": "date"} for x in d["date_columns"]]
    return {"name": f"{excel}__calc__{d['target']}_dates", "stage": "calc", "definition_id": d["id"], "primary_key": ["base_date"] + (["base_time"] if hourly else []),
            "description": f"{excel} 엑셀 {d['target']} 표의 기준일별 실제 날짜", "columns": COMMON + columns,
            "editable": False, "waiting_query": False, "query_id": None}


def _stat_tables(excel, d, hourly):
    """결과표의 소계 항목을 target 으로 묶어 대상마다 통계 표 하나. 열은 이름 열 · 묶는 열 · 값 열을 처음 나온 순서로 둔다."""
    by_db = {c["db"]: (c, i) for i, c in enumerate(d["columns"])}
    groups = {}
    for s in d["summaries"]:
        names = groups.setdefault(s["target"], [])
        for n in [s["label_col"], s["group_by"], *s["values"]]:
            if n is not None and n not in names:
                names.append(n)
    labels = {s["label_col"] for s in d["summaries"]}
    out = []
    for target, names in groups.items():
        columns = []
        for n in names:
            if n not in by_db:
                sys.exit(f"표 정의 {d['id']}: 소계 항목의 열 {n} 이 columns 에 없음")
            c, i = by_db[n]
            columns.append(_column({**c, "type": "text"} if n in labels else c, d["levels"], i))
        out.append({"name": f"{excel}__stat__{target}", "stage": "stat", "definition_id": d["id"], "primary_key": _key(hourly, "row_seq"),
                    "description": f"{excel} 엑셀 {d['target']} 표의 소계 · 합계({target})",
                    "columns": COMMON + [{"name": "row_seq", "type": "integer"}] + columns, "summaries": [],
                    "editable": False, "waiting_query": False, "query_id": None})
    return out


def _source_table(excel, d, kind, hourly):
    if kind in ("winus", "wfs"):  # 쿼리 결과는 여러 테이블을 잇거나 묶은 값이라 원본 테이블의 key 를 쓸 수 없다. 저장은 기준일 범위 교체, 조회는 모든 열 정렬이라 key 없이 둔다
        return _table(excel, STAGE[kind], d["target"], d, [], [], waiting_query=True)
    return _table(excel, STAGE[kind], d["target"], d, [{"name": "row_id", "type": "integer"}], _key(hourly, "row_id"), editable=True)


ANALYZER = Path(__file__).resolve().parents[2] / "explaining-excel-cell/scripts"
TOP_KEYS = ("settings", "definitions", "date_groups", "base_date", "parameters")
SETTINGS_KEYS = ("date_input", "refresh_unit", "allow_today")
DEF_KEYS = ("id", "sheet", "area", "header_rows", "levels", "columns", "date_columns", "summaries", "role", "target", "confirmed", "source", "outside")
ITEM_KEYS = {"columns": ("col", "db", "type", "header"), "date_columns": ("col", "rel"),
             "summaries": ("label", "label_col", "group_by", "target", "values")}


def _analyzer():
    if str(ANALYZER) not in sys.path:
        sys.path.insert(0, str(ANALYZER))


def missing_fields(results):
    """손으로 쓴 결과 파일에서 뒤 스크립트가 바로 읽는 항목 중 빠진 것을 모두 적는다. 빠진 항목마다 한 줄이다."""
    out = [f"{k} 없음" for k in TOP_KEYS if k not in results]
    out += [f"settings.{k} 없음" for k in SETTINGS_KEYS if k not in results.get("settings", {})]
    for i, g in enumerate(results.get("date_groups") or []):
        out += [f"date_groups[{i}].{k} 없음" for k in ("pattern", "base", "sheets", "dates") if k not in g]
    for n, d in enumerate(results.get("definitions") or []):
        if d.get("orphan"):
            continue
        where = f"표 정의 {d.get('id', f'[{n}]')}"
        out += [f"{where}: {k} 없음" for k in DEF_KEYS if k not in d]
        area = d.get("area")
        if area is not None and not (isinstance(area, list) and len(area) == 4 and all(isinstance(x, int) for x in area)):
            out.append(f"{where}: area 는 숫자 4개여야 함")
        for key, need in ITEM_KEYS.items():
            for i, item in enumerate(d.get(key) or []):
                out += [f"{where}: {key}[{i}].{k} 없음" for k in need if k not in item]
        for i, item in enumerate((d.get("outside") or {}).get("items", [])):
            need = ("action", "where", "value", "formula") + (("target",) if item.get("action") == "별도 표로 저장" else ())
            out += [f"{where}: outside.items[{i}].{k} 없음" for k in need if k not in item]
    return out


def _cells(text):
    """「B5:B7」 · 「C2」 를 (행, 열) 집합으로."""
    from openpyxl.utils.cell import range_boundaries
    c1, r1, c2, r2 = range_boundaries(text)
    return {(r, c) for r in range(r1, r2 + 1) for c in range(c1, c2 + 1)}


def uncovered(results, facts):
    """결과에 쓰이는 셀 중 어느 표 정의 범위에도, 표 밖 셀 항목에도 들지 않는 셀. {시트: ["E9"]} 형식이다."""
    covered = set()
    for d in results["definitions"]:
        if d.get("orphan"):
            continue
        r1, c1, r2, c2 = d["area"]
        covered |= {(d["sheet"], (r, c)) for r in range(r1, r2 + 1) for c in range(c1, c2 + 1)}
        for item in d["outside"]["items"]:
            covered |= {(item.get("sheet", d["sheet"]), p) for p in _cells(item["where"])}
    left = {(s, p) for s, texts in facts["used_cells"].items() for x in texts for p in _cells(x)} - covered
    _analyzer()
    import facts as analyzer_facts
    return analyzer_facts.ranges_text(left)


def build(results, excel_slug, sources):
    """저장 설계. 역할이 「계산」인 표는 저장하지 않고 계산 코드 안에서만 쓴다."""
    missing = missing_fields(results)
    if missing:
        sys.exit("결과 파일의 빠진 항목:\n" + "\n".join(missing))
    hourly = results["settings"]["refresh_unit"] == "시간"
    defs = [d for d in results["definitions"] if not d.get("orphan")]
    for d in defs:
        if not d.get("confirmed"):
            sys.exit(f"확인되지 않은 표 정의: {d['id']}")
    tables, extra = [], {}
    for d in defs:
        if d["role"] == "결과":
            tables.append(_table(excel_slug, "calc", d["target"], d, [{"name": "row_seq", "type": "integer"}], _key(hourly, "row_seq")))
            if d["date_columns"]:
                tables.append(_dates_table(excel_slug, d, hourly))
            tables += _stat_tables(excel_slug, d, hourly)
        elif d["role"] != "계산":
            tables.append(_source_table(excel_slug, d, _kind(d, sources), hourly))
        for item in d["outside"]["items"]:
            if item["action"] == "별도 표로 저장":
                extra.setdefault(item["target"], d)
    fixed = [("sheet", "text"), ("cell", "text"), ("value", "text"), ("formula", "text")]
    tables += [_simple(f"{excel_slug}__fixed__{t}", "fixed", f"{excel_slug} 엑셀에서 표 밖에 있던 값({t})", fixed, ["sheet", "cell"]) for t in extra]
    tables.append(_simple(f"{excel_slug}__fixed__override", "fixed", f"{excel_slug} 엑셀의 개발 고정값",
                          [("table_name", "text"), ("row_key", "text"), ("column_name", "text"), ("value", "text"), ("note", "text")],
                          ["table_name", "row_key", "column_name"]))
    tables.append(_simple(f"{excel_slug}__fixed__worker_cells", "fixed", f"{excel_slug} 엑셀의 담당자 작업 셀", fixed, ["sheet", "cell"]))
    tables.append(_simple("excel_registry", "common", "엑셀 목록과 표별 열 정리", REGISTRY, ["excel", "table_name"]))
    tables.append(_simple("excel_upload", "common", "엑셀 업로드 이력", UPLOAD, ["upload_id"]))
    return {"excel": excel_slug, "settings": results["settings"], "tables": tables}


def create_requests(plan, schema):
    """표를 만드는 요청 목록."""
    out = []
    for t in plan["tables"]:
        if t["stage"] == "stat":  # 통계 표는 저장하지 않으므로 만들지 않는다
            continue
        columns = [{k: c[k] for k in ("name", "type", "length") if k in c} | ({"nullable": False} if c["name"] in t["primary_key"] else {})
                   for c in t["columns"]]
        req = {"schema": schema, "table": t["name"], "description": t["description"], "columns": columns}
        out.append(req | ({"primary_key": t["primary_key"]} if t["primary_key"] else {}))
    return out


def existing(plan, described):
    """이미 있는 표와 대조한다. described 는 {표 이름: 열 목록} 이다."""
    out = {"same": [], "different": [], "missing": []}
    for t in plan["tables"]:
        if t.get("stage") == "stat":
            continue
        if t["name"] not in described:
            out["missing"].append(t["name"])
            continue
        want = {(c["name"], c["type"]) for c in t["columns"]}
        have = {(c["name"], c["type"]) for c in described[t["name"]]}
        out["same" if want == have else "different"].append(t["name"])
    return out


def _found_lines(book, d):
    """분석기 소계 행 찾기가 정의 범위에서 찾은 소계 · 합계 행 {row, label, label_col, col}. col 은 이름 글자가 있는 열 글자다."""
    _analyzer()
    import tables as analyzer_tables
    r1, c1, r2, c2 = d["area"]
    by_col = {column_index_from_string(c["col"]): c["db"] for c in d["columns"]}
    names = [by_col.get(c, get_column_letter(c)) for c in range(c1, c2 + 1)]
    letters = {n: get_column_letter(c1 + i) for i, n in enumerate(names)}
    table = {"sheet": d["sheet"], "area": tuple(d["area"]), "header_rows": d["header_rows"], "header": None}
    return [{"row": s["row"], "label": s["label"], "label_col": s["label_col"], "col": letters.get(s["label_col"], get_column_letter(c1))}
            for s in analyzer_tables.summary_rows(book, table, names)]


def summary_lines(book, d):
    """정의 범위의 소계 · 합계 행 중 이름 글자가 그 정의의 summaries[].label 에 있는 행만. 정의가 적지 않은 「자산총계」 같은 원천 행이
    데이터에서 빠지지 않게 하기 위해서다."""
    labels = {s["label"] for s in d["summaries"]}
    return [{k: x[k] for k in ("row", "label", "label_col")} for x in _found_lines(book, d) if x["label"] in labels] if labels else []


def unlisted_lines(book, d):
    """찾은 소계 · 합계 행 중 정의에 적지 않은 행의 셀 위치(예: 결과!A8). Claude 는 이 행을 소계로 정의할지 데이터 행으로 둘지 묻는다.
    데이터 행으로 두기로 한 행 이름은 정의의 data_labels 에 적혀 있어 다시 묻지 않는다."""
    labels = {s["label"] for s in d["summaries"]} | set(d.get("data_labels") or [])
    return [f"{d['sheet']}!{x['col']}{x['row']}" for x in _found_lines(book, d) if x["label"] not in labels]


def data_rows(book, d):
    """데이터 행 번호. 머리글 아래부터 범위 끝까지에서 summary_lines 의 행을 뺀다."""
    skip = {x["row"] for x in summary_lines(book, d)}
    top = d["header_rows"][1] + 1 if d["header_rows"] else d["area"][0]
    return [r for r in range(top, d["area"][2] + 1) if r not in skip]


def column_report(book, definition, read_columns):
    """열마다 결과 계산이 읽는지와 0 · 빈 값 비율. 저장 여부를 물을 때 쓴다."""
    vals, rows = book.sheet_values(definition["sheet"]), data_rows(book, definition)
    out = []
    for c in definition["columns"]:
        col = column_index_from_string(c["col"])
        empty = sum(vals.get((r, col)) in (None, 0, "") for r in rows)
        out.append({"column": c["db"], "read_by_result": c["col"] in read_columns, "zero_blank_ratio": empty / len(rows) if rows else 0})
    return out


def _read_columns(formula):
    """수식이 읽는 (시트, 열) 집합. 범위는 처음 열부터 끝 열까지 모두 든다(예: 원천!A:F 는 A~F)."""
    out = set()
    for tok in Tokenizer(formula).items:
        if tok.type == "OPERAND" and tok.subtype == "RANGE":
            sheet, _, ref = tok.value.rpartition("!")
            ends = [COLUMN.match(part) for part in ref.split(":")]
            if ends and all(ends):
                first, last = sorted(column_index_from_string(m[1].upper()) for m in (ends[0], ends[-1]))
                out |= {(sheet, get_column_letter(c)) for c in range(first, last + 1)}
    return out


def split_points(book, definition):
    """수식 열의 절반 이상에서 읽는 원천 열이 함께 바뀌고 다음 행까지 이어지는 행 번호. 이런 행에서 표를 나눈다.
    한 행만 다른 수식이나 한두 열만 바뀌는 행은 구간이 아니라 예외 셀이므로 세지 않는다."""
    changed, rows = Counter(), data_rows(book, definition)
    formula_columns = 0
    for c in definition["columns"]:
        col = column_index_from_string(c["col"])
        reads = [(r, _read_columns(f)) for r in rows if (f := book.formula(definition["sheet"], (r, col)))]  # 빈 셀은 건너뛰고 앞뒤 수식을 비교한다
        formula_columns += bool(reads)
        for i in range(1, len(reads) - 1):
            stable = i == 1 or reads[i - 2][1] == reads[i - 1][1]
            if stable and reads[i][1] != reads[i - 1][1] and reads[i][1] == reads[i + 1][1]:
                changed[reads[i][0]] += 1
    return sorted(r for r, n in changed.items() if 2 * n >= formula_columns)


def registry_rows(plan, results, schema, book):
    """엑셀 목록 표에 넣을 행. 응용화면 개발자가 보는 열 정리가 여기에 남는다. 통계 표는 저장하지 않으므로 넣지 않는다."""
    by_id = {d["id"]: d for d in results["definitions"]}
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    out = []
    for t in plan["tables"]:
        if t["stage"] in ("common", "stat"):
            continue
        d = by_id.get(t.get("definition_id"), {})
        row_map = {i: r for i, r in enumerate(data_rows(book, d), 1)} if d and t["stage"] == "calc" else {}
        out.append({"excel": plan["excel"], "table_name": t["name"], "stage": t["stage"], "definition_id": t.get("definition_id"), "schema_name": schema,
                    "columns_json": json.dumps(t["columns"], ensure_ascii=False),
                    "row_map_json": json.dumps(row_map), "query_id": t["query_id"], "waiting_query": t["waiting_query"], "updated_at": now})
    return out


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _print(body):
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(body, ensure_ascii=False, indent=1))


def _requests_command(argv):
    ap = argparse.ArgumentParser(description="표마다 샌드박스 표 만들기 요청 파일(create --spec)을 쓴다")
    ap.add_argument("--plan", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    plan, out = _read(a.plan), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for req in create_requests(plan, plan["schema"]):
        (out / f"create_{req['table']}.json").write_text(json.dumps(req, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"만들기 요청 {len(plan['tables'])}개: {out}")


def _compare_command(argv):
    ap = argparse.ArgumentParser(description="이미 있는 표와 설계를 대조한다")
    ap.add_argument("--plan", required=True)
    ap.add_argument("--described", required=True, help="샌드박스 describe 로 읽은 열 목록 {표 이름: 열 목록}")
    a = ap.parse_args(argv)
    _print(existing(_read(a.plan), _read(a.described)))


def _columns_command(argv):
    ap = argparse.ArgumentParser(description="열마다 결과 계산이 읽는지와 0 · 빈 값 비율을 낸다")
    ap.add_argument("excel")
    ap.add_argument("--results", required=True)
    ap.add_argument("--definition", required=True, help="표 정의의 id")
    a = ap.parse_args(argv)
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "explaining-excel-cell/scripts"))
    import explain_cell
    book = explain_cell.Book(a.excel)
    d = next(x for x in _read(a.results)["definitions"] if x["id"] == a.definition)
    read = {col for sheet, cells in book.cells.items() for pos in cells if (f := book.formula(sheet, pos))
            for ref_sheet, col in _read_columns(f) if (ref_sheet.strip("'") or sheet) == d["sheet"]}
    _print(column_report(book, d, read))


def unlisted_report(book, results):
    """정의 범위에서 찾은 소계 · 합계 행 중 표 정의에 적지 않은 행의 위치."""
    return [x for d in results["definitions"] if not d.get("orphan") for x in unlisted_lines(book, d)]


def _check_command(argv):
    """빠진 항목, 표 정의 범위 밖의 결과 셀, 정의에 적지 않은 소계 행을 낸다. 하나라도 있으면 1 을 돌려준다."""
    ap = argparse.ArgumentParser(description="손으로 쓴 결과 파일을 뒤 단계 전에 검사한다")
    ap.add_argument("excel")
    ap.add_argument("--results", required=True)
    ap.add_argument("--facts", required=True, help="분석기 --facts 실행이 쓴 explain_facts.json")
    a = ap.parse_args(argv)
    results = _read(a.results)
    report = {"missing": missing_fields(results), "uncovered": {}, "unlisted": []}
    if not report["missing"]:
        _analyzer()
        import explain_cell
        report["uncovered"] = uncovered(results, _read(a.facts))
        report["unlisted"] = unlisted_report(explain_cell.Book(a.excel), results)
    _print(report)
    return 1 if any(report.values()) else 0


COMMANDS = {"requests": _requests_command, "compare": _compare_command, "columns": _columns_command, "check": _check_command}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in COMMANDS:
        return COMMANDS[argv[0]](argv[1:])
    ap = argparse.ArgumentParser(description="엑셀 분석기의 표 정의로 저장 설계 파일을 만든다")
    ap.add_argument("results")
    ap.add_argument("--slug", required=True, help="엑셀의 영문 이름(소문자 · 숫자 · _)")
    ap.add_argument("--sources", required=True, help="4단계에서 정한 표별 출처 JSON {표 id: winus | wfs | manual}")
    ap.add_argument("--schema", required=True, help="개발자가 고른 저장 스키마. 화면 API 가 이 스키마의 표를 연다")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    if not re.fullmatch(r"[a-z0-9_]+", a.slug):
        sys.exit(f"엑셀 영문 이름 오류: {a.slug}")
    plan = build(json.loads(Path(a.results).read_text(encoding="utf-8-sig")), a.slug, json.loads(Path(a.sources).read_text(encoding="utf-8-sig")))
    plan["schema"] = a.schema
    Path(a.out).write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"만들 표 {len(plan['tables'])}개: {a.out}")


if __name__ == "__main__":
    sys.exit(main())
