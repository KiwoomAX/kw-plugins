"""등록 번호가 오면 쿼리 응답 열과 표의 열을 값으로 맞추고 「쿼리 연결 대기」를 푼다."""
import copy

from colmap import match


def link(plan, table, query_id, response_rows, excel_rows, key_columns, query_args=None):
    """{"mapped": {표 열: {column, transform, match}}, "missing": [표 열], "plan": 새 설계}.
    맞지 않는 열이 있으면 설계를 바꾸지 않는다. 그때는 개발자에게 알려 열 대응을 정한다."""
    got = match(excel_rows, response_rows, key_columns)
    mapped = {key_columns[0]: {"column": key_columns[1], "transform": "same", "match": 1.0}, **got["mapped"]}
    new = copy.deepcopy(plan)
    if not got["missing"]:
        t = next(x for x in new["tables"] if x["name"] == table)
        t.update(waiting_query=False, query_id=query_id, query_map=mapped, query_args=query_args or {})
    return {"mapped": mapped, "missing": got["missing"], "plan": new}
