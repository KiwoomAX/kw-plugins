"""등록 번호가 오면 쿼리 응답 열과 표의 열을 값으로 맞추고 「쿼리 연결 대기」를 푼다.

실행: python query_link.py <엑셀> --plan table_plan.json --results explain_results.json --table <표 이름> --query-id <번호>
        --response response.json --key <엑셀 열> <응답 열> [--args args.json] --out-plan table_plan.json --out-registry upsert_excel_registry.json
response.json 은 searching-winus 로 받은 한 기준일의 응답 행 목록이다. 대기가 풀릴 때만 두 파일을 쓴다.
"""
import argparse
import copy
import json
import string
import sys
from pathlib import Path

from colmap import _key, match


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


def link(plan, table, query_id, response_rows, excel_rows, key_columns, query_args=None):
    """{"mapped": {표 열: {column, transform, match}}, "missing": [표 열], "unmatched_rows": 개수, "plan": 새 설계}.
    unmatched_rows 는 키가 응답에 없는 엑셀 행 수다. 엑셀이 레코드 하나를 두 줄로 보이거나 합계 줄이 섞이면 생긴다.
    맞지 않는 열이나 행이 있으면 설계를 바꾸지 않는다. 그때는 개발자에게 알려 열 대응이나 행 정리 코드를 정한다."""
    got = match(excel_rows, response_rows, key_columns)
    mapped = {key_columns[0]: {"column": key_columns[1], "transform": "same", "match": 1.0}, **got["mapped"]}
    keys = {_key(r.get(key_columns[1])) for r in response_rows}
    unmatched = sum(1 for r in excel_rows if _key(r.get(key_columns[0])) not in keys or not _key(r.get(key_columns[0])))
    new = copy.deepcopy(plan)
    if not got["missing"] and not unmatched:
        t = next(x for x in new["tables"] if x["name"] == table)
        t.update(waiting_query=False, query_id=query_id, query_map=mapped, query_args=query_args or {})
    return {"mapped": mapped, "missing": got["missing"], "unmatched_rows": unmatched, "plan": new}


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
    got = link(plan, a.table, a.query_id, read(a.response), excel_rows, tuple(a.key), query_args)
    new = got["plan"]
    if not next(x for x in new["tables"] if x["name"] == a.table)["waiting_query"]:
        Path(a.out_plan).write_text(json.dumps(new, ensure_ascii=False, indent=1), encoding="utf-8")
        rows = [r for r in table_plan.registry_rows(new, results, new["schema"], book) if r["table_name"] == a.table]
        Path(a.out_registry).write_text(json.dumps({"schema": new["schema"], "table": "excel_registry", "mode": "upsert", "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps({k: got[k] for k in ("mapped", "missing", "unmatched_rows")}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
