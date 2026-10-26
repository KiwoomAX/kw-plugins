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


def order_for_paging(schema: str, table: str) -> list[dict]:
    """페이지를 넘겨도 행이 겹치거나 빠지지 않는 정렬. primary key 가 없으면 모든 컬럼으로 정렬한다."""
    detail = call("POST", "/sandbox/table/describe", {"schema": schema, "table": table})
    columns = detail["primary_key"] or [c["name"] for c in detail["columns"]]
    return [{"column": c} for c in columns]


def _paged(request: dict) -> dict:
    request = dict(request)
    if not request.get("order_by") and (request.get("offset", 0) > 0 or request.pop("_all", False)):
        request["order_by"] = order_for_paging(request["schema"], request["table"])
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
    """가짜 DBGateway. 계약(Kiwoom-DBgateway 8defc95)의 응답 모양만 흉내 낸다."""

    def __init__(self) -> None:
        import http.server
        import threading
        self.sent: list[tuple[str, dict | None]] = []
        self.tables = _fake_tables()
        self.fail: dict[str, tuple[str, str]] = {}
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
        code, out = run_cli(["select", "--request", json_file({"schema": "BS", "table": "무키표"}), "--all"])
        assert code == 2, "--all 은 --out 없이 받지 않는다(argparse 오류)"
        code, out = run_cli(["tables", "BS"])
        assert code == 0 and "투자후보" in out and "kwam_x" not in out, out
    finally:
        fake.close()
        gw.GATEWAY, gw.OPEN_BROWSER, gw.registry_key, webbrowser.open, record.RECORD, real_key = saved
        os.environ.pop(gw.KEY_ENV, None)
        if real_key is not None:
            os.environ[gw.KEY_ENV] = real_key
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    # Windows 에서 출력이 파이프로 나가면 파이썬은 CP949 로 쓰고 한글 밖의 문자에서 멈춘다. --help 도 거치도록 main 앞에 둔다.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
