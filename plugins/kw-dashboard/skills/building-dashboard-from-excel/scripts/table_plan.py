"""엑셀 분석기의 표 정의로 만들 표의 이름 · 열 · primary key 를 정한다.

표 이름은 `{엑셀}__{단계}__{대상}` 이고, 단계는 raw_winus · raw_external · raw_manual · fixed · calc 다.
실행: python table_plan.py <explain_results.json> --slug <엑셀 영문 이름> --sources <sources.json> --out table_plan.json
"""
import argparse
import datetime as dt
import json
import re
import sys
from collections import Counter
from pathlib import Path

from openpyxl.formula import Tokenizer
from openpyxl.utils import column_index_from_string

STAGE = {"winus": "raw_winus", "external": "raw_external", "manual": "raw_manual"}
COMMON = [{"name": "base_date", "type": "date"}, {"name": "base_time", "type": "timestamptz"}, {"name": "loaded_at", "type": "timestamptz"}]
TYPES = {"text": {"type": "text"}, "code": {"type": "varchar", "length": 50}, "number": {"type": "numeric"}, "date": {"type": "date"}}
CELL = re.compile(r"^\$?([A-Za-z]{1,3})\$?\d+")
MIN_DATES = 3  # primary key 를 정하기 전에 확인할 기준일 수
REGISTRY = [("excel", "text"), ("table_name", "text"), ("stage", "text"), ("definition_id", "text"), ("schema_name", "text"), ("columns_json", "text"),
            ("summaries_json", "text"), ("row_map_json", "text"), ("query_id", "integer"), ("waiting_query", "boolean"), ("updated_at", "timestamptz")]
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
    return "winus" if (d.get("source") or {}).get("origin") == "WINUS" else "external"


def _table(excel, stage, target, d, extra, key, **more):
    columns = [_column(c, d["levels"], i) for i, c in enumerate(d["columns"])]
    return {"name": f"{excel}__{stage}__{target}", "stage": stage, "definition_id": d["id"], "primary_key": key,
            "description": f"{excel} 엑셀 「{d['sheet']}」 시트의 표({d['id'].rsplit('!', 1)[-1]})",
            "columns": COMMON + extra + columns, "editable": False, "waiting_query": False, "query_id": None, **more}


def _simple(name, stage, description, columns, key):
    return {"name": name, "stage": stage, "description": description, "columns": [{"name": n, "type": t} for n, t in columns],
            "primary_key": key, "editable": False, "waiting_query": False, "query_id": None}


def _dates_table(excel, d):
    columns = [{"name": f"t_plus_{x['rel']}", "type": "date"} for x in d["date_columns"]]
    return {"name": f"{excel}__calc__{d['target']}_dates", "stage": "calc", "definition_id": d["id"], "primary_key": ["base_date"],
            "description": f"{excel} 엑셀 {d['target']} 표의 기준일별 실제 날짜", "columns": COMMON + columns,
            "editable": False, "waiting_query": False, "query_id": None}


def _source_table(excel, d, kind, hourly):
    if kind == "winus":  # primary key 는 기준일 세 개의 응답으로 확인한 뒤 정한다. 표를 만든 뒤에는 바꿀 수 없다
        return _table(excel, "raw_winus", d["target"], d, [], [], waiting_query=True)
    return _table(excel, STAGE[kind], d["target"], d, [{"name": "row_id", "type": "integer"}], _key(hourly, "row_id"), editable=True)


def build(results, excel_slug, sources):
    """저장 설계. 역할이 「계산」인 표는 저장하지 않고 계산 코드 안에서만 쓴다."""
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
                tables.append(_dates_table(excel_slug, d))
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
        columns = [{k: c[k] for k in ("name", "type", "length") if k in c} | ({"nullable": False} if c["name"] in t["primary_key"] else {})
                   for c in t["columns"]]
        req = {"schema": schema, "table": t["name"], "description": t["description"], "columns": columns}
        out.append(req | ({"primary_key": t["primary_key"]} if t["primary_key"] else {}))
    return out


def existing(plan, described):
    """이미 있는 표와 대조한다. described 는 {표 이름: 열 목록} 이다."""
    out = {"same": [], "different": [], "missing": []}
    for t in plan["tables"]:
        if t["name"] not in described:
            out["missing"].append(t["name"])
            continue
        want = {(c["name"], c["type"]) for c in t["columns"]}
        have = {(c["name"], c["type"]) for c in described[t["name"]]}
        out["same" if want == have else "different"].append(t["name"])
    return out


def _data_rows(d):
    skip = {s["row"] for s in d["summaries"]}
    top = d["header_rows"][1] + 1 if d["header_rows"] else d["area"][0]
    return [r for r in range(top, d["area"][2] + 1) if r not in skip]


def column_report(book, definition, read_columns):
    """열마다 결과 계산이 읽는지와 0 · 빈 값 비율. 저장 여부를 물을 때 쓴다."""
    vals, rows = book.sheet_values(definition["sheet"]), _data_rows(definition)
    out = []
    for c in definition["columns"]:
        col = column_index_from_string(c["col"])
        empty = sum(vals.get((r, col)) in (None, 0, "") for r in rows)
        out.append({"column": c["db"], "read_by_result": c["col"] in read_columns, "zero_blank_ratio": empty / len(rows) if rows else 0})
    return out


def _read_columns(formula):
    """수식이 읽는 (시트, 열) 집합."""
    out = set()
    for tok in Tokenizer(formula).items:
        if tok.type == "OPERAND" and tok.subtype == "RANGE":
            sheet, _, ref = tok.value.rpartition("!")
            m = CELL.match(ref)
            if m:
                out.add((sheet, m[1].upper()))
    return out


def split_points(book, definition):
    """수식 열의 절반 이상에서 읽는 원천 열이 함께 바뀌고 다음 행까지 이어지는 행 번호. 이런 행에서 표를 나눈다.
    한 행만 다른 수식이나 한두 열만 바뀌는 행은 구간이 아니라 예외 셀이므로 세지 않는다."""
    changed, rows = Counter(), _data_rows(definition)
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


def primary_key_check(rows_by_date, columns):
    """columns 가 기준일마다 유일한지 확인한다. 서로 다른 기준일 세 개가 있어야 unique 가 참이 된다."""
    for rows in rows_by_date.values():
        keys = [tuple(r.get(c) for c in columns) for r in rows]
        if len(keys) != len(set(keys)):
            return {"unique": False, "dates": len(rows_by_date)}
    return {"unique": len(rows_by_date) >= MIN_DATES, "dates": len(rows_by_date)}


def registry_rows(plan, results, schema):
    """엑셀 목록 표에 넣을 행. 응용화면 개발자가 보는 열 정리와 소계 정의가 여기에 남는다."""
    by_id = {d["id"]: d for d in results["definitions"]}
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    out = []
    for t in plan["tables"]:
        if t["stage"] == "common":
            continue
        d = by_id.get(t.get("definition_id"), {})
        row_map = {i: r for i, r in enumerate(_data_rows(d), 1)} if d and t["stage"] == "calc" else {}
        out.append({"excel": plan["excel"], "table_name": t["name"], "stage": t["stage"], "definition_id": t.get("definition_id"), "schema_name": schema,
                    "columns_json": json.dumps(t["columns"], ensure_ascii=False), "summaries_json": json.dumps(d.get("summaries", []), ensure_ascii=False),
                    "row_map_json": json.dumps(row_map), "query_id": t["query_id"], "waiting_query": t["waiting_query"], "updated_at": now})
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="엑셀 분석기의 표 정의로 저장 설계 파일을 만든다")
    ap.add_argument("results")
    ap.add_argument("--slug", required=True, help="엑셀의 영문 이름(소문자 · 숫자 · _)")
    ap.add_argument("--sources", required=True, help="4단계에서 정한 표별 출처 JSON {표 id: winus | external | manual}")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    if not re.fullmatch(r"[a-z0-9_]+", a.slug):
        sys.exit(f"엑셀 영문 이름 오류: {a.slug}")
    plan = build(json.loads(Path(a.results).read_text(encoding="utf-8-sig")), a.slug, json.loads(Path(a.sources).read_text(encoding="utf-8-sig")))
    Path(a.out).write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"만들 표 {len(plan['tables'])}개: {a.out}")


if __name__ == "__main__":
    main()
