"""등록 번호가 오면 쿼리 응답 열과 표의 열을 값으로 맞추고 「쿼리 연결 대기」를 푼다."""
import copy

from colmap import _key, match


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
