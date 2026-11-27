"""등록 번호가 오면 개발자가 정한 열 대응대로 엑셀 표와 쿼리 응답을 대조하고, 맞으면 「쿼리 연결 대기」를 푼다.

실행: python query_link.py <엑셀> --plan table_plan.json --results explain_results.json --table <표 이름> --query-id <번호>
        --response response.json --key <엑셀 열> <응답 열> [--key ...] [--map 엑셀열=응답열[:변환] ...] [--args args.json] [--accept]
        --out-plan table_plan.json --out-registry upsert_excel_registry.json
response.json 은 searching-winus 로 받은 한 기준일의 응답 행 목록이다. 대기가 풀릴 때만 두 파일을 쓴다.
열 대응은 스크립트가 찾지 않는다. 대응이 빠진 열이 있으면 엑셀 값과 응답 값 몇 개를 보이므로, Claude 가 보고 대응을 제안한다.
"""
import argparse
import copy
import json
import string
import sys
from pathlib import Path

from colmap import compare, pair_rows  # colmap 이 서버 폴더(templates/backend)를 경로에 넣는다
import transform  # noqa: E402


FILLED = {"base_date", "yyyymmdd"}  # 운영 중 서버가 업로드한 기준일로 채우는 이름


def _fillable(v):
    """서버가 운영 중에 채울 수 있는 값 틀인가. 글자 하나이거나, 그런 글자의 빈 배열 아닌 목록이다."""
    if isinstance(v, list):
        return bool(v) and all(isinstance(x, str) and _fillable(x) for x in v)
    if not isinstance(v, str):
        return False
    try:
        names = {n for _, n, _, _ in string.Formatter().parse(v) if n is not None}
    except ValueError:  # 중괄호 짝이 맞지 않는 틀
        return False
    return names <= FILLED


def bad_args(query_args, each_arg=None):
    """[(인자, 값 틀)]. 운영 중 서버가 만들 수 없는 값이다. 고정 글자와 {base_date} · {yyyymmdd} 만 받고, 목록 인자는 원소마다 같은 기준으로 본다.
    each_arg 는 query_each 가 목록 값마다 채우는 인자라 틀을 보지 않는다."""
    return [(arg, v) for arg, v in (query_args or {}).items() if arg != each_arg and not _fillable(v)]


def parse_map(items):
    """["엑셀열=응답열[:변환]"] 을 {엑셀열: (응답열, 변환)} 으로. 변환을 적지 않으면 same 이다."""
    out = {}
    for item in items or []:
        col, _, rest = item.partition("=")
        column, _, name = rest.partition(":")
        out[col.strip()] = (column.strip(), name.strip() or "same")
    return out


def bad_map(given, excel_rows, response_rows):
    """[안내 문구]. 엑셀 표에 없는 열, 응답에 없는 열, 읽을 수 없는 변환 이름을 알린다."""
    excel_cols = set(excel_rows[0]) if excel_rows else set()
    response_cols = set(response_rows[0]) if response_rows else set()
    bad = []
    for col, (column, name) in given.items():
        if col not in excel_cols:
            bad.append(f"표에 {col} 열이 없습니다")
        if column not in response_cols:
            bad.append(f"응답에 {column} 열이 없습니다({col})")
        if name != "same" and not transform.NAME.fullmatch(name):
            bad.append(f"변환 이름 {name} 을 읽을 수 없습니다({col}). 예: /1e8, *100, round(/1e6)")
    return bad


def link(plan, table, query_id, response_rows, excel_rows, keys, mapping, query_args=None, accept=False):
    """{"missing", "checked", "unmatched_rows", "repeated_keys", "linked", "plan"} 에 대응이 빠지면 "samples" 를 더한다.
    keys 는 [(엑셀 열, 응답 열)], mapping 은 {표 열: (응답 열, 변환)}. 모든 열에 대응이 있고, 엑셀 행마다 짝이 되는 응답 행이 하나씩 있고,
    값이 모두 같을 때 대기를 푼다. 값이 다른 행이 있으면 개발자가 보고 accept 로 정한다. 그 밖에는 설계를 바꾸지 않는다."""
    key_cols = {e for e, _ in keys}
    columns = [c for c in (excel_rows[0] if excel_rows else {}) if c not in key_cols]
    missing = [c for c in columns if c not in mapping]
    got = compare(excel_rows, response_rows, keys, {c: mapping[c] for c in columns if c in mapping})
    differs = any(c["same"] != c["rows"] for c in got["checked"].values())
    linked = not missing and not got["unmatched_rows"] and not got["repeated_keys"] and (accept or not differs)
    new = copy.deepcopy(plan)
    if linked:
        query_map = {e: {"column": r, "transform": "same", "match": 1.0} for e, r in keys}
        query_map.update({c: {"column": v["column"], "transform": v["transform"], "match": round(v["same"] / v["rows"], 4) if v["rows"] else None}
                          for c, v in got["checked"].items()})
        t = next(x for x in new["tables"] if x["name"] == table)
        t.update(waiting_query=False, query_id=query_id, query_map=query_map, query_args=query_args or {})
    out = {"missing": missing, **got, "linked": linked, "plan": new}
    if missing:  # 키로 짝지은 행끼리 보여야 Claude 가 값을 대조해 응답 열과 배수를 제안할 수 있다
        out["samples"] = [{"key": [e.get(k) for k, _ in keys], "excel": {c: e.get(c) for c in missing}, "response": q}
                          for e, q in pair_rows(excel_rows, response_rows, keys)[0][:3]]
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="쿼리 응답 열을 표의 열과 맞추고 대기를 푼다")
    ap.add_argument("excel")
    ap.add_argument("--plan", required=True)
    ap.add_argument("--results", required=True)
    ap.add_argument("--table", required=True)
    ap.add_argument("--query-id", type=int, required=True)
    ap.add_argument("--response", required=True)
    ap.add_argument("--key", nargs=2, action="append", required=True, metavar=("엑셀_열", "응답_열"), help="행을 짝짓는 열. 여러 열이면 여러 번 쓴다")
    ap.add_argument("--args", help="쿼리 인자 {이름: 값 틀}. 값은 고정 글자나 {base_date} · {yyyymmdd}. 예: {\"dt\": \"{yyyymmdd}\", \"gb\": \"1\"}")
    ap.add_argument("--map", action="append", metavar="엑셀열=응답열[:변환]", help="표 열마다 대응하는 응답 열. 여러 번 쓴다. 예: 환매금액=RED_AMT:/1e8")
    ap.add_argument("--accept", action="store_true", help="값이 다른 행을 개발자가 보고 그대로 연결하기로 했을 때")
    ap.add_argument("--out-plan", required=True)
    ap.add_argument("--out-registry", required=True)
    a = ap.parse_args(argv)
    import initial_load
    import table_plan
    import verify_calc
    read = lambda p: json.loads(Path(p).read_text(encoding="utf-8-sig"))  # noqa: E731
    plan, results = read(a.plan), read(a.results)
    t = next(x for x in plan["tables"] if x["name"] == a.table)
    query_args = read(a.args) if a.args else None
    bad = bad_args(query_args, t.get("query_each", {}).get("arg"))
    if bad:
        sys.stdout.reconfigure(encoding="utf-8")
        for arg, v in bad:
            print(f"연결하지 않았습니다: 인자 {arg} 의 값 「{json.dumps(v, ensure_ascii=False)}」는 운영 중에 서버가 만들 수 없습니다.")
        print("쓸 수 있는 값은 고정 글자, {base_date}, {yyyymmdd}, 그런 값의 배열, 목록 값마다 호출하는 인자(query_each)입니다.")
        sys.exit(1)
    d = next(x for x in results["definitions"] if x["id"] == t["definition_id"])
    book = initial_load.open_book(a.excel)
    excel_rows = verify_calc.read_table(book, d)
    response = read(a.response)
    given = parse_map(a.map)
    wrong = bad_map(given, excel_rows, response)
    if wrong:
        sys.stdout.reconfigure(encoding="utf-8")
        print("연결하지 않았습니다: " + " · ".join(wrong))
        sys.exit(1)
    got = link(plan, a.table, a.query_id, response, excel_rows, [tuple(k) for k in a.key], given, query_args, a.accept)
    new = got["plan"]
    if got["linked"]:
        Path(a.out_plan).write_text(json.dumps(new, ensure_ascii=False, indent=1), encoding="utf-8")
        rows = [r for r in table_plan.registry_rows(new, results, new["schema"], book) if r["table_name"] == a.table]
        Path(a.out_registry).write_text(json.dumps({"schema": new["schema"], "table": "excel_registry", "mode": "upsert", "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps({k: v for k, v in got.items() if k != "plan"}, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()
