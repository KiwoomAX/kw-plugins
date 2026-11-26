"""등록 번호가 오면 쿼리 응답 열과 표의 열을 값으로 맞추고 「쿼리 연결 대기」를 푼다.

실행: python query_link.py <엑셀> --plan table_plan.json --results explain_results.json --table <표 이름> --query-id <번호>
        --response response.json --key <엑셀 열> <응답 열> [--args args.json] [--map 엑셀열=응답열[:변환] ...] --out-plan table_plan.json --out-registry upsert_excel_registry.json
response.json 은 searching-winus 로 받은 한 기준일의 응답 행 목록이다. 대기가 풀릴 때만 두 파일을 쓴다.
값으로 찾은 열 대응은 제안이다. 찾지 못한 열과 틀린 열은 개발자가 --map 으로 정한다.
"""
import argparse
import copy
import json
import string
import sys
from pathlib import Path

from colmap import _key, match  # colmap 이 서버 폴더(templates/backend)를 경로에 넣는다
import transform  # noqa: E402


FILLED = {"base_date", "yyyymmdd"}  # 운영 중 서버가 업로드한 기준일로 채우는 이름


def bad_args(query_args, each_arg=None):
    """[(인자, 값 틀)]. 운영 중 서버가 만들 수 없는 값이다. 고정 글자와 {base_date} · {yyyymmdd} 만 받는다.
    each_arg 는 query_each 가 목록 값마다 채우는 인자라 틀을 보지 않는다."""
    bad = []
    for arg, v in (query_args or {}).items():
        if arg == each_arg:
            continue
        try:
            names = {n for _, n, _, _ in string.Formatter().parse(v) if n is not None} if isinstance(v, str) else None
        except ValueError:  # 중괄호 짝이 맞지 않는 틀
            names = None
        if names is None or not names <= FILLED:
            bad.append((arg, v))
    return bad


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


def link(plan, table, query_id, response_rows, excel_rows, key_columns, query_args=None, given=None):
    """{"mapped": {표 열: {column, transform, match}}, "missing": [표 열], "unmatched_rows": 개수, "plan": 새 설계}.
    given({표 열: (응답 열, 변환)})은 개발자가 정한 대응이라 값으로 찾은 대응보다 앞서고, match 는 None 으로 남긴다.
    unmatched_rows 는 키가 응답에 없는 엑셀 행 수다. 엑셀이 레코드 하나를 두 줄로 보이거나 합계 줄이 섞이면 생긴다.
    맞지 않는 열이나 행이 있으면 설계를 바꾸지 않는다. 그때는 개발자에게 알려 열 대응이나 행 정리 코드를 정한다."""
    got = match(excel_rows, response_rows, key_columns)
    mapped = {key_columns[0]: {"column": key_columns[1], "transform": "same", "match": 1.0}, **got["mapped"],
              **{col: {"column": column, "transform": name, "match": None} for col, (column, name) in (given or {}).items()}}
    missing = [c for c in got["missing"] if c not in (given or {})]
    keys = {_key(r.get(key_columns[1])) for r in response_rows}
    unmatched = sum(1 for r in excel_rows if _key(r.get(key_columns[0])) not in keys or not _key(r.get(key_columns[0])))
    new = copy.deepcopy(plan)
    if not missing and not unmatched:
        t = next(x for x in new["tables"] if x["name"] == table)
        t.update(waiting_query=False, query_id=query_id, query_map=mapped, query_args=query_args or {})
    return {"mapped": mapped, "missing": missing, "unmatched_rows": unmatched, "plan": new}


def main(argv=None):
    ap = argparse.ArgumentParser(description="쿼리 응답 열을 표의 열과 맞추고 대기를 푼다")
    ap.add_argument("excel")
    ap.add_argument("--plan", required=True)
    ap.add_argument("--results", required=True)
    ap.add_argument("--table", required=True)
    ap.add_argument("--query-id", type=int, required=True)
    ap.add_argument("--response", required=True)
    ap.add_argument("--key", nargs=2, required=True, metavar=("엑셀_열", "응답_열"))
    ap.add_argument("--args", help="쿼리 인자 {이름: 값 틀}. 값은 고정 글자나 {base_date} · {yyyymmdd}. 예: {\"dt\": \"{yyyymmdd}\", \"gb\": \"1\"}")
    ap.add_argument("--map", action="append", metavar="엑셀열=응답열[:변환]", help="개발자가 정한 열 대응. 여러 번 쓴다. 예: 환매금액=RED_AMT:/1e8")
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
        print("쓸 수 있는 값은 고정 글자, {base_date}, {yyyymmdd}, 목록 값마다 호출하는 인자(query_each)입니다.")
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
    got = link(plan, a.table, a.query_id, response, excel_rows, tuple(a.key), query_args, given)
    new = got["plan"]
    if not next(x for x in new["tables"] if x["name"] == a.table)["waiting_query"]:
        Path(a.out_plan).write_text(json.dumps(new, ensure_ascii=False, indent=1), encoding="utf-8")
        rows = [r for r in table_plan.registry_rows(new, results, new["schema"], book) if r["table_name"] == a.table]
        Path(a.out_registry).write_text(json.dumps({"schema": new["schema"], "table": "excel_registry", "mode": "upsert", "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps({k: got[k] for k in ("mapped", "missing", "unmatched_rows")}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
