"""DBGateway 샌드박스 경로(/sandbox/*)를 접근 키로 호출한다.

하위 명령마다 DBGateway 경로 하나를 부른다. 표·컬럼 이름이 한글이라 요청은 JSON 파일로 받는다. PowerShell 5.1 은
명령 인자의 큰따옴표를 지우고 파이프로 넘긴 한글을 깨뜨리므로, 명령 인자나 표준 입력으로는 받지 않는다.

접근 키 확인과 401·리다이렉트 처리는 같은 플러그인의 searching-winus 스크립트(fetch_manifest)를 그대로 쓴다.
두 스킬이 같은 키와 같은 안내를 쓰게 하기 위해서다.

어떤 요청도 자동으로 다시 보내지 않는다. 거절되면 거절 코드와 다음 행동 한 줄을 내고 멈춘다.

종료 코드: 0 성공, 1 거절·중단, 3 확인 필요(argparse 의 인자 오류 2 와 겹치지 않게).

표준 라이브러리만 쓴다.

사용: python scripts/sandbox.py <하위 명령> ...
"""
import argparse
import http.client
import io
import json
import os
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "searching-winus" / "scripts"))
import fetch_manifest as gw  # noqa: E402
import record  # noqa: E402

# 같은 코드는 같은 다음 행동이다. 계약에 없는 코드는 kind 로 고른다(Kiwoom-DBgateway ADR-0042).
NEXT_BY_CODE = {
    "write_outcome_unknown": "반영 여부 모름. 같은 요청을 다시 보내지 않고 조회로 확인."
                             " primary key 없는 표의 append 였으면 조회로도 확인할 수 없으니 다시 보낼지 사용자에게 물음",
    "sandbox_undecided": "반영 여부 모름. 같은 요청을 다시 보내지 않고 조회로 확인."
                         " primary key 없는 표의 append 였으면 조회로도 확인할 수 없으니 다시 보낼지 사용자에게 물음",
    "sandbox_unreachable": "다시 시도하지 않고 사용자에게 알림. 설정 오류일 수 있음",
    "sandbox_busy": "잠시 뒤 사용자가 다시 요청",
    "sandbox_table_busy": "잠시 뒤 사용자가 다시 요청. 다른 사람이 같은 표를 고치는 중",
    "sandbox_schema_not_permitted": "이 키로 쓸 수 있는 스키마를 schemas 명령으로 확인",
    "sandbox_privilege_mismatch": "DBGateway 설정 문제. AX팀에 문의",
    "query_timeout": "조건을 좁혀 다시 요청",
    "sandbox_too_large": "조건이나 값을 줄여 다시 요청",
    "body_too_large": "행을 나눠 여러 번 요청",
    "sandbox_schema_full": "스키마 용량이 참. 쓰지 않는 표를 정리하거나 AX팀에 문의",
    "invalid_request": "문제 칸을 고쳐 다시 요청",
    "no_answer": "쓰기였으면 반영 여부 모름. 같은 요청을 다시 보내지 않고 조회로 확인",
}
NEXT_BY_KIND = {
    "범위 초과 거절": "detail 대로 요청을 고침",
    "혼잡 거절": "잠시 뒤 사용자가 다시 요청",
    "판정 불능": "쓰기였으면 같은 요청을 다시 보내지 않고 조회로 반영 여부를 확인",
    "신원 거절": "이 키로 쓸 수 있는 스키마를 schemas 명령으로 확인",
}


class Refused(Exception):
    """DBGateway 가 거절한 요청. code 는 공개 거절 코드, kind 는 거절 종류다."""

    def __init__(self, code: str, kind: str, detail: str) -> None:
        super().__init__(f"거절({code}): {detail}")
        self.code, self.kind, self.detail = code, kind, detail


def next_action(r: Refused) -> str:
    return NEXT_BY_CODE.get(r.code) or NEXT_BY_KIND.get(r.kind) or "detail 을 사용자에게 그대로 전함"


def read_json(path: str) -> dict | list:
    # PowerShell 5.1 의 Set-Content -Encoding UTF8 은 BOM 을 붙인다.
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def call(method: str, path: str, body: dict | None = None) -> dict | None:
    """샌드박스 경로 하나를 부르고 JSON 응답을 돌려준다. 204 면 None. 거절은 Refused 나 SystemExit 로 올린다."""
    key = gw.access_key()
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode()
    headers = {"Authorization": f"Bearer {key}"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(gw.GATEWAY + urllib.parse.quote(path), data=data, method=method, headers=headers)
    try:
        with gw.OPENER.open(request, timeout=60) as r:
            raw = r.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        refused = gw.http_refusal(e, key)
        if refused:
            raise refused
        raw = e.read().decode("utf-8", "replace")
        try:
            answer = json.loads(raw)
        except ValueError:
            answer = None
        if isinstance(answer, dict) and {"kind", "code", "detail"} <= answer.keys():
            raise Refused(answer["code"], answer["kind"], answer["detail"])
        if e.code == 422 and isinstance(answer, dict) and isinstance(answer.get("detail"), list):
            problems = [f"{'.'.join(str(x) for x in d.get('loc', [])[1:]) or '본문'}: {d.get('msg', '')}"
                        for d in answer["detail"]]
            raise Refused("invalid_request", "형식 오류", "; ".join(problems))
        raise Refused(f"http_{e.code}", "", f"{e.code} {raw[:200]}")
    except (http.client.HTTPException, ConnectionError, TimeoutError) as e:
        # 요청을 보낸 뒤 응답을 받는 중에 끊긴 것이다. urllib 는 보내기 전 단계만 URLError 로 감싼다.
        raise Refused("no_answer", "판정 불능", f"응답을 받지 못함: {type(e).__name__}: {e}")


def order_for_paging(schema: str, table: str) -> list[dict]:
    """페이지를 넘겨도 행이 겹치거나 빠지지 않는 정렬. primary key 가 없으면 모든 컬럼으로 정렬한다."""
    detail = call("POST", "/sandbox/table/describe", {"schema": schema, "table": table})
    columns = detail["primary_key"] or [c["name"] for c in detail["columns"]]
    return [{"column": c} for c in columns]


def _paged(request: dict) -> dict:
    request = dict(request)
    if request.pop("_all", False) or request.get("offset", 0) > 0:
        # 사용자 정렬에 같은 값이 있으면 페이지마다 그 행들의 순서가 달라질 수 있어, 남은 정렬 컬럼으로 동점을 가른다.
        order = list(request.get("order_by") or [])
        used = {o["column"] for o in order}
        order += [o for o in order_for_paging(request["schema"], request["table"]) if o["column"] not in used]
        request["order_by"] = order
    return request


def select_all(request: dict) -> dict:
    """truncated 가 거짓이 될 때까지 다음 페이지를 받아 합친다."""
    request = _paged({**request, "_all": True})
    limit, offset = request.get("limit", 1000), request.get("offset", 0)
    columns, rows = [], []
    while True:
        page = call("POST", "/sandbox/rows/select", {**request, "offset": offset})
        columns, rows = page["columns"], rows + page["rows"]
        if not page["truncated"]:
            return {"columns": columns, "rows": rows}
        offset += limit


def _size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return ""


def _print_json(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def cmd_schemas(args) -> int:
    schemas = call("GET", "/sandbox/schemas")["schemas"]
    if not schemas:
        print("쓸 수 있는 스키마 없음: 이 사람의 조직에는 샌드박스가 없음\n- 조치: AX팀에 문의")
        return 0
    for s in schemas:
        print(f"{s['schema']}  사용 {_size(s['used_bytes'])} / 상한 {_size(s['cap_bytes'])}")
    return 0


def cmd_tables(args) -> int:
    listing = call("GET", f"/sandbox/schemas/{args.schema}")
    for t in listing["tables"]:
        rows = "추정 없음" if t["estimated_rows"] is None else f"추정 {t['estimated_rows']:,}행"
        mine = " · 내 표" if record.has(listing["schema"], t["table"]) else ""
        print(f"{t['table']}  {rows} · {_size(t['size_bytes'])}{mine}  {t['description'] or ''}".rstrip())
    return 0


def cmd_describe(args) -> int:
    _print_json(call("POST", "/sandbox/table/describe", {"schema": args.schema, "table": args.table}))
    return 0


def cmd_select(args) -> int:
    request = read_json(args.request)
    result = select_all(request) if args.all else call("POST", "/sandbox/rows/select", _paged(request))
    if args.out:
        Path(args.out).write_text(json.dumps({"columns": result["columns"], "rows": result["rows"]},
                                             ensure_ascii=False), encoding="utf-8")
        print(f"{len(result['rows'])}행을 {args.out} 에 씀")
    else:
        _print_json(result)
    return 0


MAX_ROWS = 30_000
"""조회 한 번의 상한(계약 request.MAX_LIMIT). 행 수를 셀 때 이보다 많으면 "30,000행 이상"으로 보인다."""

CHANGES = ("add_column", "drop_column", "rename_column", "rename_table", "set_description")
"""표 변경 요청의 다섯 모양(계약 changes.TableChange). 요청 하나에 하나만 든다."""


def _table_entry(schema: str, table: str) -> dict:
    for t in call("GET", f"/sandbox/schemas/{schema}")["tables"]:
        if t["table"] == table:
            return t
    raise Refused("sandbox_unknown_table", "범위 초과 거절", f"샌드박스 테이블 없음: {schema}.{table}")


def _describe(schema: str, table: str) -> dict:
    return call("POST", "/sandbox/table/describe", {"schema": schema, "table": table})


def preview(action: str, body: dict) -> tuple[str, list[str]]:
    """(확인값, 미리보기 줄들). 확인값은 실행 직전에 다시 계산해 미리보기 때와 같을 때만 실행한다."""
    schema, table = body["schema"], body["table"]
    lines = [f"대상: {schema}.{table}"]
    if not record.has(schema, table):
        lines.append("내 표 기록에 없음: 다른 사람이 만들었을 수 있는 표")
    if action in ("rename_table", "rename_column"):
        lines.append("이 이름을 쓰는 다른 사람의 서비스가 깨질 수 있음")
        return (body["rename_table"] if action == "rename_table" else body["rename_column"]["to"]), lines
    if action == "upsert":
        lines.append(f"보낼 행: {len(body['rows'])}. 같은 primary key 의 행은 보낸 컬럼만 수정됨")
        return str(len(body["rows"])), lines
    if action == "overwrite":
        lines.append(f"보낼 행: {len(body['rows'])}. 범위의 행을 모두 지우고 이 행들을 넣음")
        sent = set(body["rows"][0])  # DBGateway 는 행마다 컬럼이 다르면 거절한다
        empty = [c["name"] for c in _describe(schema, table)["columns"] if c["name"] not in sent]
        if empty:
            lines.append(f"비워질 컬럼: {', '.join(empty)}")
    if action in ("update", "delete", "overwrite") and not body.get("all"):
        # 값은 받지 않을 수 없으니, 짧은 primary key 컬럼 하나만 받고 출력하지 않는다.
        detail = _describe(schema, table)
        column = (detail["primary_key"] or [detail["columns"][0]["name"]])[0]
        page = call("POST", "/sandbox/rows/select", {"schema": schema, "table": table, "columns": [column],
                                                     "where": body.get("where"), "limit": MAX_ROWS})
        if page["truncated"]:
            if action == "overwrite":  # 보내는 행은 상한이 있지만 지워지는 행은 없다. 모르는 수만큼 지우지 않는다
                raise SystemExit("범위의 행: 30,000행 이상. 지워질 행 수를 셀 수 없어 실행하지 않음"
                                 "\n- 조치: 범위를 나눠(예: 월별) 범위마다 요청")
            lines.append("조건에 맞는 행: 30,000행 이상")
            return f"{MAX_ROWS}+", lines
        lines.append(f"조건에 맞는 행: {len(page['rows'])}")
        return str(len(page["rows"])), lines
    # 표 전체가 대상이면 행을 조회하지 않는다. 데이터가 PC 로 들어오지 않게 추정 행 수를 쓴다.
    entry = _table_entry(schema, table)
    estimated = entry["estimated_rows"]
    shown = "없음" if estimated is None else f"{estimated:,}"
    lines.append(f"추정 행: {shown} · 크기 {_size(entry['size_bytes'])}. 추정치라 동료가 방금 바꾼 행은 반영되지 않을 수 있음")
    if action == "drop_column":
        indexes = [i["name"] for i in _describe(schema, table)["indexes"] if body["drop_column"] in i["columns"]]
        if indexes:
            lines.append(f"함께 삭제됨: 인덱스 {', '.join(indexes)}")
    return ("추정없음" if estimated is None else str(estimated)), lines


def guarded(action: str, body: dict, confirm: str | None, send) -> int:
    """확인 대상 동작. 확인값 없이는 미리보기만 내고(종료 코드 3), 확인값이 바뀌었으면 실행하지 않는다."""
    token, lines = preview(action, body)
    if confirm is None:
        print("\n".join(lines))
        print(f"확인값: {token}")
        print(f"실행하려면 --confirm {token}")
        return 3
    if confirm != token:
        print(f"대상 규모가 바뀜: 미리보기 {confirm}, 지금 {token}. 실행하지 않음")
        return 1
    return send(token)


def _record(update) -> int:
    """변경이 반영된 뒤의 기록 갱신. 실패해도 변경을 다시 보내지 않게 그 사실을 함께 알린다."""
    try:
        update()
    except OSError as e:
        print(f"변경은 반영됨. 내 표 기록만 고치지 못함: {e}\n- 조치: 같은 요청을 다시 보내지 않고 record 명령으로 기록 수정")
        return 1
    return 0


ROW_LABELS = {"insert": "삽입한", "update": "수정한", "delete": "삭제한"}


def _rows(kind: str, body: dict, token: str | None) -> int:
    done = call("POST", f"/sandbox/rows/{kind}", body)
    if kind == "overwrite":
        line = f"삭제한 행: {done['deleted']} · 삽입한 행: {done['inserted']}"
    else:
        line = f"{ROW_LABELS[kind]} 행: {done['row_count']}"
        if "inserted" in done:  # upsert: 고치려던 행이 새로 들어갔으면 primary key 를 잘못 적은 것이다
            line += f" (새로 삽입 {done['inserted']} · 수정 {done['updated']})"
    print(line + (f" (확인값 {token})" if token else ""))
    return 0


def cmd_insert(args) -> int:
    body = read_json(args.request)
    if body.get("mode") == "upsert":
        return guarded("upsert", body, args.confirm, lambda token: _rows("insert", body, token))
    return _rows("insert", body, None)


def _cmd_target(kind: str):
    def run(args) -> int:
        body = read_json(args.request)
        whole = body.get("all") and kind != "delete"  # 행 삭제는 all 을 받지 않는다. 표를 비우는 일은 truncate 가 맡는다
        if body.get("where") is None and not whole:
            return _rows(kind, body, None)  # DBGateway 가 조건 없는 요청을 거절한다
        return guarded(kind, body, args.confirm, lambda token: _rows(kind, body, token))
    return run


def cmd_drop(args) -> int:
    body = {"schema": args.schema, "table": args.table}
    record.entries()  # 기록이 깨졌으면 변경 요청을 보내기 전에 멈춘다

    def send(token: str) -> int:
        call("POST", "/sandbox/table/drop", body)
        print(f"완료: {args.schema}.{args.table} 삭제")
        return _record(lambda: record.remove(args.schema, args.table))
    return guarded("drop", body, args.confirm, send)


def cmd_truncate(args) -> int:
    body = {"schema": args.schema, "table": args.table}

    def send(token: str) -> int:
        call("POST", "/sandbox/table/truncate", body)
        print(f"완료: {args.schema}.{args.table} 비움 (확인값 {token})")
        return 0
    return guarded("truncate", body, args.confirm, send)


def cmd_alter(args) -> int:
    body = read_json(args.change)
    kinds = [k for k in CHANGES if k in body]
    if len(kinds) != 1:
        raise SystemExit(f"변경 요청에는 다음 중 하나만 넣음: {', '.join(CHANGES)}")
    kind = kinds[0]

    def send(token: str | None) -> int:
        call("POST", "/sandbox/table/alter", body)
        if kind == "rename_table":
            print(f"완료: {body['schema']}.{body['table']} → {body['rename_table']}")
            return _record(lambda: record.rename(body["schema"], body["table"], body["rename_table"]))
        print(f"완료: {body['schema']}.{body['table']} {kind}")
        return 0
    if kind in ("drop_column", "rename_column", "rename_table"):
        if kind == "rename_table":
            record.entries()
        return guarded(kind, body, args.confirm, send)
    return send(None)


def cmd_create(args) -> int:
    spec = read_json(args.spec)
    if not spec.get("description"):
        raise SystemExit("DB 설명(description) 없음: 동료가 알아볼 짧은 요약 필요")
    record.entries()
    call("POST", "/sandbox/table/create", spec)
    print(f"완료: {spec['schema']}.{spec['table']} 생성, 내 표 기록에 추가")
    return _record(lambda: record.add(spec["schema"], spec["table"], args.purpose))


def cmd_index_create(args) -> int:
    spec = read_json(args.spec)
    call("POST", "/sandbox/index/create", spec)
    print(f"완료: 인덱스 {spec['name']} 생성")
    return 0


def cmd_index_drop(args) -> int:
    call("POST", "/sandbox/index/drop", {"schema": args.schema, "table": args.table, "name": args.name})
    print(f"완료: 인덱스 {args.name} 삭제")
    return 0


def cmd_record(args) -> int:
    if args.action == "list":
        names: dict[str, set[str]] = {}
        for t in record.entries():
            if t["schema"] not in names:
                names[t["schema"]] = {e["table"] for e in call("GET", f"/sandbox/schemas/{t['schema']}")["tables"]}
            gone = "" if t["table"] in names[t["schema"]] else "  · DBGateway 목록에 없음"
            print(f"{t['schema']}.{t['table']}  {t['created']}  {t['purpose']}{gone}")
        return 0
    if args.action == "add":
        _table_entry(args.schema, args.table)  # 없는 표는 기록하지 않는다
        record.add(args.schema, args.table, args.purpose)
        print(f"기록함: {args.schema}.{args.table}")
        return 0
    done = (record.remove(args.schema, args.table) if args.action == "remove"
            else record.rename(args.schema, args.table, args.to))
    print(f"{'기록 수정' if done else '기록에 없음'}: {args.schema}.{args.table}")
    return 0 if done else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DBGateway 샌드박스 경로를 접근 키로 호출한다.")
    parser.add_argument("--selfcheck", action="store_true", help=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("schemas", help="쓸 수 있는 조직 스키마").set_defaults(func=cmd_schemas)
    p = sub.add_parser("tables", help="스키마 안의 표 목록")
    p.add_argument("schema")
    p.set_defaults(func=cmd_tables)
    p = sub.add_parser("describe", help="표의 컬럼·primary key·인덱스")
    p.add_argument("--schema", required=True)
    p.add_argument("--table", required=True)
    p.set_defaults(func=cmd_describe)
    p = sub.add_parser("select", help="행 조회. 요청은 JSON 파일")
    p.add_argument("--request", required=True, metavar="FILE")
    p.add_argument("--all", action="store_true", help="모든 페이지를 받는다. --out 이 필요하다")
    p.add_argument("--out", metavar="FILE", help="결과를 이 파일에 쓴다")
    p.set_defaults(func=cmd_select)
    p = sub.add_parser("create", help="표 생성. 스펙은 JSON 파일, description 필수")
    p.add_argument("--spec", required=True, metavar="FILE")
    p.add_argument("--purpose", required=True, help="내 표 기록에 남길 자세한 용도")
    p.set_defaults(func=cmd_create)
    for name, func, file_arg, text in (("insert", cmd_insert, "--request", "행 삽입. upsert 는 확인 필요"),
                                       ("update", _cmd_target("update"), "--request", "행 수정. 확인 필요"),
                                       ("delete", _cmd_target("delete"), "--request", "행 삭제. 확인 필요"),
                                       ("overwrite", _cmd_target("overwrite"), "--request", "범위 교체. 확인 필요"),
                                       ("alter", cmd_alter, "--change", "표 변경. 컬럼 삭제·이름 변경은 확인 필요")):
        p = sub.add_parser(name, help=text)
        p.add_argument(file_arg, required=True, metavar="FILE")
        p.add_argument("--confirm", metavar="확인값")
        p.set_defaults(func=func)
    for name, func, text in (("drop", cmd_drop, "표 삭제. 확인 필요"), ("truncate", cmd_truncate, "표의 행을 모두 삭제. 확인 필요")):
        p = sub.add_parser(name, help=text)
        p.add_argument("--schema", required=True)
        p.add_argument("--table", required=True)
        p.add_argument("--confirm", metavar="확인값")
        p.set_defaults(func=func)
    p = sub.add_parser("index-create", help="인덱스 생성. 스펙은 JSON 파일")
    p.add_argument("--spec", required=True, metavar="FILE")
    p.set_defaults(func=cmd_index_create)
    p = sub.add_parser("index-drop", help="인덱스 삭제")
    p.add_argument("--schema", required=True)
    p.add_argument("--table", required=True)
    p.add_argument("--name", required=True)
    p.set_defaults(func=cmd_index_drop)
    p = sub.add_parser("record", help="내 표 기록 보기·고치기")
    actions = p.add_subparsers(dest="action", required=True)
    actions.add_parser("list", help="기록의 표와 DBGateway 목록 대조")
    for name, text in (("add", "DBGateway 에 있는 표를 기록에 추가"), ("remove", "기록에서 뺌"), ("rename", "기록의 표 이름 수정")):
        a = actions.add_parser(name, help=text)
        a.add_argument("--schema", required=True)
        a.add_argument("--table", required=True)
        if name == "add":
            a.add_argument("--purpose", required=True)
        if name == "rename":
            a.add_argument("--to", required=True)
    p.set_defaults(func=cmd_record)
    args = parser.parse_args(argv)
    if args.selfcheck:
        record._selfcheck()
        _selfcheck()
        print("selfcheck ok")
        return 0
    if not args.cmd:
        parser.error("하위 명령 필요")
    if args.cmd == "select" and args.all and not args.out:
        parser.error("--all 은 --out 과 함께 써야 함: 표 전체가 화면으로 나오지 않게 파일로 받음")
    try:
        return args.func(args)
    except Refused as r:
        print(f"거절({r.code}): {r.detail}\n- 조치: {next_action(r)}")
        return 1
    except urllib.error.URLError as e:
        print(f"DBGateway 에 연결하지 못함: {e.reason}\n- 조치: 사내망인지, QUERY_GATEWAY_URL 이 맞는지 확인")
        return 1
    except SystemExit as e:
        if isinstance(e.code, str):  # 접근 키 안내처럼 문구를 실은 종료
            print(e.code)
            return 1
        raise


# ── selfcheck: 가짜 DBGateway 와 시험 도우미 ─────────────────────────────────────

def _fake_tables() -> dict[str, dict]:
    return {
        "투자후보": {"columns": [{"name": "코드", "type": "text", "length": None, "nullable": False},
                             {"name": "단계", "type": "text", "length": None, "nullable": True}],
                  "primary_key": ["코드"], "indexes": [{"name": "ix_단계", "columns": ["단계"], "unique": False}],
                  "estimated_rows": 120, "size_bytes": 8192, "description": "투자 후보 목록",
                  "rows": [{"코드": c, "단계": "검토", "메모": "비밀값"} for c in "ABC"]},
        "무키표": {"columns": [{"name": "가", "type": "integer", "length": None, "nullable": True},
                            {"name": "나", "type": "text", "length": None, "nullable": True}],
                "primary_key": [], "indexes": [], "estimated_rows": 5, "size_bytes": 4096, "description": None,
                "rows": [{"가": 1, "나": "x"}, {"가": 1, "나": "y"}, {"가": 2, "나": "x"},
                         {"가": 3, "나": "z"}, {"가": 3, "나": "a"}]},
    }


class Fake:
    """가짜 DBGateway. 계약(Kiwoom-DBgateway 1bfb556)의 응답 모양만 흉내 낸다."""

    def __init__(self) -> None:
        import http.server
        import threading
        self.sent: list[tuple[str, dict | None]] = []
        self.tables = _fake_tables()
        self.fail: dict[str, tuple[str, str]] = {}
        self.hangup: set[str] = set()
        fake = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def _answer(self, status: int, body) -> None:
                self.send_response(status)
                self.end_headers()
                if body is not None:
                    self.wfile.write(json.dumps(body, ensure_ascii=False).encode())

            def _route(self, body: dict | None) -> None:
                path = urllib.parse.unquote(self.path)
                fake.sent.append((path, body))
                if path in fake.hangup:
                    fake.hangup.discard(path)
                    self.close_connection = True
                    return
                if path in fake.fail:
                    code, kind = fake.fail.pop(path)
                    return self._answer(503 if kind == "판정 불능" else 400, {"kind": kind, "code": code, "detail": "가짜 거절"})
                status, answer = fake.route(path, body)
                self._answer(status, answer)

            def do_GET(self):
                self._route(None)

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                self._route(json.loads(self.rfile.read(length) or b"null"))

            def log_message(self, *a):
                pass

        self.server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    def _unknown(self, table: str):
        return 400, {"kind": "범위 초과 거절", "code": "sandbox_unknown_table", "detail": f"샌드박스 테이블 없음: {table}"}

    def route(self, path: str, body: dict | None):
        if path == "/sandbox/schemas":
            return 200, {"schemas": [{"schema": "BS", "used_bytes": 12288, "cap_bytes": 10 * 1024 ** 3}]}
        if path == "/sandbox/schemas/unauth":
            return 401, {"kind": "신원 거절", "code": "unidentified", "detail": "폐기된 키"}
        if path == "/sandbox/schemas/BS":
            return 200, {"schema": "BS", "tables": [
                {"table": n, "size_bytes": t["size_bytes"], "estimated_rows": t["estimated_rows"],
                 "description": t["description"]} for n, t in sorted(self.tables.items())]}
        if path == "/sandbox/table/describe":
            t = self.tables.get(body["table"])
            if t is None:
                return self._unknown(body["table"])
            return 200, {"schema": body["schema"], "table": body["table"], "description": t["description"],
                         "columns": t["columns"], "primary_key": t["primary_key"], "indexes": t["indexes"]}
        if path == "/sandbox/rows/select":
            t = self.tables.get(body["table"])
            if t is None:
                return self._unknown(body["table"])
            rows = [r for r in t["rows"] if all(r.get(k) == v for k, v in (body.get("where") or {}).items())]
            for key in reversed(body.get("order_by") or []):
                rows.sort(key=lambda r: (r.get(key["column"]) is None, r.get(key["column"])),
                          reverse=key.get("descending", False))
            columns = body.get("columns") or [c["name"] for c in t["columns"]]
            offset, limit = body.get("offset", 0), body.get("limit", 1000)
            page = rows[offset:offset + limit]
            return 200, {"columns": columns, "rows": [[r.get(c) for c in columns] for r in page],
                         "truncated": len(rows) > offset + limit}
        if path == "/sandbox/rows/insert" and "rows" not in (body or {}):
            return 422, {"detail": [{"type": "missing", "loc": ["body", "rows"], "msg": "Field required"}]}
        if path == "/sandbox/rows/insert" and body.get("mode", "append") not in ("append", "upsert"):
            return 422, {"detail": [{"type": "enum", "loc": ["body", "mode"], "msg": "Input should be 'append' or 'upsert'"}]}
        if path == "/sandbox/rows/delete" and ("all" in body or "where" not in body):
            return 422, {"detail": [{"type": "extra_forbidden", "loc": ["body", "all"], "msg": "Extra inputs are not permitted"}]}
        if path == "/sandbox/table/truncate":
            if body["table"] not in self.tables:
                return self._unknown(body["table"])
            self.tables[body["table"]]["rows"] = []
            return 204, None
        if path.startswith("/sandbox/rows/"):
            t = self.tables.get(body["table"])
            if t is None:
                return self._unknown(body["table"])
            hit = [r for r in t["rows"] if body.get("all") or all(r.get(k) == v for k, v in body.get("where", {}).items())]
            if path.endswith("/insert"):
                if body.get("mode") != "upsert":
                    t["rows"] += [dict(r) for r in body["rows"]]
                    return 200, {"row_count": len(body["rows"])}
                key = t["primary_key"]
                inserted = updated = 0
                for new in body["rows"]:
                    old = next((r for r in t["rows"] if all(r.get(k) == new.get(k) for k in key)), None)
                    if old is None:
                        t["rows"].append(dict(new))
                        inserted += 1
                    else:
                        old.update(new)
                        updated += 1
                return 200, {"row_count": inserted + updated, "inserted": inserted, "updated": updated}
            if path.endswith("/overwrite"):
                t["rows"] = [r for r in t["rows"] if r not in hit] + [dict(r) for r in body["rows"]]
                return 200, {"deleted": len(hit), "inserted": len(body["rows"])}
            if path.endswith("/update"):
                for r in hit:
                    r.update(body["set"])
                return 200, {"row_count": len(hit)}
            if path.endswith("/delete"):
                t["rows"] = [r for r in t["rows"] if r not in hit]
                return 200, {"row_count": len(hit)}
        if path == "/sandbox/table/create":
            self.tables[body["table"]] = {"columns": body["columns"], "primary_key": body.get("primary_key", []),
                                          "indexes": [], "estimated_rows": None, "size_bytes": 8192,
                                          "description": body.get("description"), "rows": []}
            return self.route("/sandbox/table/describe", body)
        if path in ("/sandbox/table/drop", "/sandbox/table/alter", "/sandbox/index/drop"):
            t = self.tables.get(body["table"])
            if t is None:
                return self._unknown(body["table"])
            if path.endswith("/drop") and "index" not in path:
                del self.tables[body["table"]]
                return 204, None
            if "index" in path:
                t["indexes"] = [i for i in t["indexes"] if i["name"] != body["name"]]
                return 204, None
            if "rename_table" in body:
                self.tables[body["rename_table"]] = self.tables.pop(body["table"])
                return self.route("/sandbox/table/describe", {**body, "table": body["rename_table"]})
            return self.route("/sandbox/table/describe", body)
        return 404, {"detail": "Not Found"}


def run_cli(argv: list[str]) -> tuple[int, str]:
    """main() 을 실행하고 (종료 코드, 표준 출력과 표준 오류를 합친 글) 을 돌려준다."""
    out = io.StringIO()
    with redirect_stdout(out), redirect_stderr(out):
        try:
            code = main(argv)
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
    return code or 0, out.getvalue()


def raises(fn) -> "Refused":
    try:
        fn()
    except Refused as r:
        return r
    raise AssertionError("Refused 가 나야 한다")


def _selfcheck() -> None:
    tmp = Path(tempfile.mkdtemp())

    def json_file(obj) -> str:
        p = tmp / f"req{len(list(tmp.iterdir()))}.json"
        p.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
        return str(p)

    fake = Fake()
    opened: list[str] = []
    saved = (gw.GATEWAY, gw.OPEN_BROWSER, gw.registry_key, webbrowser.open, record.RECORD, os.environ.get(gw.KEY_ENV))
    gw.GATEWAY, gw.OPEN_BROWSER = fake.url, False
    gw.registry_key = lambda: ""  # Windows 에서도 사용자의 실제 HKCU 를 읽지 않는다
    webbrowser.open = lambda url: opened.append(url) or True
    record.RECORD = tmp / "기록" / "tables.json"
    os.environ[gw.KEY_ENV] = "kwam_x"

    def bodies_for(path: str) -> list[dict]:
        return [b for p, b in fake.sent if p == path]

    try:
        r = raises(lambda: call("POST", "/sandbox/table/describe", {"schema": "BS", "table": "없음"}))
        assert (r.code, r.kind) == ("sandbox_unknown_table", "범위 초과 거절"), r
        fake.fail["/sandbox/rows/select"] = ("future_code", "혼잡 거절")
        r = raises(lambda: call("POST", "/sandbox/rows/select", {"schema": "BS", "table": "투자후보"}))
        assert "잠시 뒤" in next_action(r), "모르는 코드는 kind 로 고른다"
        assert "다시 보내지 않" in next_action(Refused("undecided", "판정 불능", "x"))
        assert "다시 보내지 않" in next_action(Refused("sandbox_undecided", "판정 불능", "x"))
        assert "줄여" in next_action(Refused("sandbox_too_large", "범위 초과 거절", "x"))
        r = raises(lambda: call("POST", "/sandbox/rows/insert", {"bad": 1}))
        assert r.code == "invalid_request" and "rows" in r.detail, r.detail
        r = raises(lambda: call("GET", "/sandbox/없는경로"))
        assert r.code == "http_404", r.code
        os.environ.pop(gw.KEY_ENV)
        n = len(fake.sent)
        code, out = run_cli(["schemas"])
        assert code == 1 and "접근 키 없음" in out and len(fake.sent) == n, "키가 없으면 요청을 보내지 않는다"
        os.environ[gw.KEY_ENV] = "kwam_x"
        code, out = run_cli(["tables", "unauth"])
        assert code == 1 and "DBGateway 신원 거절(401)" in out and opened == [], (out, opened)
        p = json_file({})
        Path(p).write_bytes('﻿{"schema": "BS", "table": "투자후보"}'.encode("utf-8"))
        assert read_json(p) == {"schema": "BS", "table": "투자후보"}
        rows = select_all({"schema": "BS", "table": "무키표", "limit": 2})
        assert len(rows["rows"]) == 5, rows
        last = bodies_for("/sandbox/rows/select")[-1]
        assert last["order_by"] == [{"column": "가"}, {"column": "나"}] and last["offset"] == 4, last
        rows = select_all({"schema": "BS", "table": "무키표", "limit": 2, "order_by": [{"column": "가"}]})
        last = bodies_for("/sandbox/rows/select")[-1]
        assert len(rows["rows"]) == 5 and last["order_by"] == [{"column": "가"}, {"column": "나"}], "동점은 남은 컬럼으로 가른다"
        fake.hangup.add("/sandbox/rows/insert")  # 요청을 받고 응답 없이 끊는다
        code, out = run_cli(["insert", "--request", json_file({"schema": "BS", "table": "무키표", "rows": [{"가": 9}]})])
        assert code == 1 and "반영 여부 모름" in out and "다시 보내지 않" in out, out
        code, out = run_cli(["select", "--request", json_file({"schema": "BS", "table": "무키표"}), "--all"])
        assert code == 2, "--all 은 --out 없이 받지 않는다(argparse 오류)"
        code, out = run_cli(["tables", "BS"])
        assert code == 0 and "투자후보" in out and "kwam_x" not in out, out
        _selfcheck_writes(fake, json_file, bodies_for)
    finally:
        fake.close()
        gw.GATEWAY, gw.OPEN_BROWSER, gw.registry_key, webbrowser.open, record.RECORD, real_key = saved
        os.environ.pop(gw.KEY_ENV, None)
        if real_key is not None:
            os.environ[gw.KEY_ENV] = real_key
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def _selfcheck_writes(fake: Fake, json_file, bodies_for) -> None:
    """쓰기 명령과 확인 절차. 조회 시험이 남긴 가짜 서버와 내 표 기록을 이어받는다."""
    del_where = json_file({"schema": "BS", "table": "투자후보", "where": {"단계": "검토"}})
    code, out = run_cli(["delete", "--request", del_where])
    assert code == 3 and "대상: BS.투자후보" in out and "확인값: 3" in out and "--confirm 3" in out, out
    assert "내 표 기록에 없음" in out and not bodies_for("/sandbox/rows/delete"), out
    count_body = bodies_for("/sandbox/rows/select")[-1]
    assert count_body["columns"] == ["코드"] and count_body["limit"] == 30000 and "비밀값" not in out, count_body
    fake.tables["투자후보"]["rows"].append({"코드": "Z", "단계": "검토"})  # 동료가 행을 추가
    code, out = run_cli(["delete", "--request", del_where, "--confirm", "3"])
    assert code == 1 and "대상 규모가 바뀜" in out and not bodies_for("/sandbox/rows/delete"), out
    code, out = run_cli(["delete", "--request", del_where, "--confirm", "4"])
    assert code == 0 and bodies_for("/sandbox/rows/delete") and "4" in out, out
    inserts = len(bodies_for("/sandbox/rows/insert"))  # 조회 시험의 422 요청이 하나 남아 있다
    upsert = json_file({"schema": "BS", "table": "투자후보", "rows": [{"코드": "A"}], "mode": "upsert"})
    code, out = run_cli(["insert", "--request", upsert])
    assert code == 3 and len(bodies_for("/sandbox/rows/insert")) == inserts, out
    assert "보낸 컬럼만 수정" in out and "확인값: 1" in out, out
    code, out = run_cli(["insert", "--request", upsert, "--confirm", "1"])
    assert code == 0 and "새로 삽입 1" in out and "수정 0" in out, "upsert 는 새로 넣은 행과 고친 행을 나눠 보인다"
    inserts += 1
    code, out = run_cli(["insert", "--request", json_file({"schema": "BS", "table": "투자후보", "rows": [{"코드": "B"}]})])
    assert code == 0 and len(bodies_for("/sandbox/rows/insert")) == inserts + 1, "append 는 확인 없이 실행"
    upd_all = json_file({"schema": "BS", "table": "투자후보", "set": {"단계": "완료"}, "all": True})
    code, out = run_cli(["update", "--request", upd_all])
    assert code == 3 and "확인값: 120" in out and "추정치" in out and not bodies_for("/sandbox/rows/update"), out
    code, out = run_cli(["delete", "--request", json_file({"schema": "BS", "table": "투자후보", "all": True})])
    assert code == 1 and "확인값" not in out and "invalid_request" in out, "모든 행 삭제는 truncate 가 맡는다"
    ow_where = json_file({"schema": "BS", "table": "투자후보", "where": {"코드": "B"},
                          "rows": [{"코드": "B", "단계": "재검토"}, {"코드": "D", "단계": "재검토"}]})
    code, out = run_cli(["overwrite", "--request", ow_where])
    assert code == 3 and "확인값: 1" in out and "보낼 행: 2" in out and "비워질 컬럼" not in out, out
    assert not bodies_for("/sandbox/rows/overwrite"), out
    code, out = run_cli(["overwrite", "--request", ow_where, "--confirm", "1"])
    assert code == 0 and "삭제한 행: 1" in out and "삽입한 행: 2" in out, out
    ow_all = json_file({"schema": "BS", "table": "투자후보", "all": True, "rows": [{"코드": "E"}]})
    code, out = run_cli(["overwrite", "--request", ow_all])
    assert code == 3 and "확인값: 120" in out and len(bodies_for("/sandbox/rows/overwrite")) == 1, out
    assert "비워질 컬럼: 단계" in out, "보내지 않은 컬럼을 이름으로 알린다"
    fake.tables["큰표"] = {**_fake_tables()["투자후보"], "rows": [{"코드": str(i), "단계": "x"} for i in range(MAX_ROWS + 1)]}
    big = json_file({"schema": "BS", "table": "큰표", "where": {"단계": "x"}, "rows": [{"코드": "0", "단계": "x"}]})
    code, out = run_cli(["overwrite", "--request", big])
    assert code == 1 and "나눠" in out and "확인값" not in out, "지울 행 수를 모르는 범위 교체는 실행하지 않는다"
    del fake.tables["큰표"]
    fake.fail["/sandbox/rows/overwrite"] = ("write_outcome_unknown", "판정 불능")
    code, out = run_cli(["overwrite", "--request", ow_where, "--confirm", "1"])
    assert code == 1 and "다시 보내지 않" in out and len(bodies_for("/sandbox/rows/overwrite")) == 2, out
    code, out = run_cli(["truncate", "--schema", "BS", "--table", "투자후보"])
    assert code == 3 and "확인값: 120" in out and not bodies_for("/sandbox/table/truncate"), out
    code, out = run_cli(["truncate", "--schema", "BS", "--table", "투자후보", "--confirm", "120"])
    assert code == 0 and "비움" in out and fake.tables["투자후보"]["rows"] == [], out
    selects = len(bodies_for("/sandbox/rows/select"))
    code, out = run_cli(["drop", "--schema", "BS", "--table", "투자후보"])
    assert code == 3 and "확인값: 120" in out and len(bodies_for("/sandbox/rows/select")) == selects, out
    code, out = run_cli(["alter", "--change", json_file({"schema": "BS", "table": "투자후보", "drop_column": "단계"})])
    assert code == 3 and "ix_단계" in out, out
    code, out = run_cli(["alter", "--change", json_file({"schema": "BS", "table": "투자후보",
                                                          "rename_column": {"from": "단계", "to": "상태"}})])
    assert code == 3 and "확인값: 상태" in out and "깨질 수 있음" in out, out
    assert run_cli(["index-drop", "--schema", "BS", "--table", "투자후보", "--name", "ix_단계"])[0] == 0
    code, out = run_cli(["alter", "--change", json_file({"schema": "BS", "table": "투자후보",
                                                          "set_description": {"description": "요약"}})])
    assert code == 0, out
    new_table = {"schema": "BS", "table": "새표", "columns": [{"name": "코드", "type": "text"}],
                 "primary_key": ["코드"], "description": "요약"}
    code, out = run_cli(["create", "--spec", json_file(new_table), "--purpose", "월별 집계"])
    assert code == 0 and record.has("BS", "새표"), out
    no_desc = {k: v for k, v in new_table.items() if k != "description"} | {"table": "설명없는표"}
    assert run_cli(["create", "--spec", json_file(no_desc), "--purpose", "x"])[0] == 1 and "설명없는표" not in fake.tables
    code, out = run_cli(["alter", "--change", json_file({"schema": "BS", "table": "새표", "rename_table": "새표2"}),
                         "--confirm", "새표2"])
    assert code == 0 and "완료" in out and record.has("BS", "새표2") and not record.has("BS", "새표"), out
    fake.fail["/sandbox/table/drop"] = ("write_outcome_unknown", "판정 불능")
    code, out = run_cli(["drop", "--schema", "BS", "--table", "새표2", "--confirm", "추정없음"])
    assert code == 1 and record.has("BS", "새표2") and "다시 보내지 않" in out and bodies_for("/sandbox/table/drop"), out
    record.RECORD.write_text("{깨짐", encoding="utf-8")
    n = len(bodies_for("/sandbox/table/create"))
    code, out = run_cli(["create", "--spec", json_file(new_table | {"table": "새표3"}), "--purpose", "x"])
    assert code == 1 and "덮어쓰지 않음" in out and len(bodies_for("/sandbox/table/create")) == n, out
    _selfcheck_record()


def _selfcheck_record() -> None:
    """내 표 기록 명령. 쓰기 시험이 깨뜨려 둔 기록 파일을 지우고 시작한다."""
    record.RECORD.unlink(missing_ok=True)
    assert run_cli(["record", "add", "--schema", "BS", "--table", "투자후보", "--purpose", "동료 표 기록"])[0] == 0
    assert run_cli(["record", "add", "--schema", "BS", "--table", "없는표", "--purpose", "x"])[0] == 1
    assert not record.has("BS", "없는표")
    record.add("BS", "사라진표", "x")
    code, out = run_cli(["record", "list"])
    assert code == 0 and "사라진표" in out and "DBGateway 목록에 없음" in out, out
    assert run_cli(["record", "rename", "--schema", "BS", "--table", "투자후보", "--to", "후보"])[0] == 0
    assert record.has("BS", "후보") and not record.has("BS", "투자후보")
    assert run_cli(["record", "remove", "--schema", "BS", "--table", "사라진표"])[0] == 0
    assert not record.has("BS", "사라진표")


if __name__ == "__main__":
    # Windows 에서 출력이 파이프로 나가면 파이썬은 CP949 로 쓰고 한글 밖의 문자에서 멈춘다. --help 도 거치도록 main 앞에 둔다.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
