"""DBGateway 에서 쿼리 목차나 고른 쿼리의 상세를 받아 표준 출력에 낸다.

인자 없이 실행하면 쿼리 단위 목차(id·이름·설명·사용 테이블)를 내고, --query 뒤에 쿼리 id 를 주면 그
쿼리들의 이름·설명·사용 테이블·인자·등록된 SQL 을 낸다. 목차에는 SQL 이 없고, SQL 은 고른 id 만
DBGateway 에 묻는다. 쓰지 않을 쿼리의 SQL 까지 사용자 PC 에 받지 않으려고 나눴다.

요청마다 환경변수 KIWOOM_ACCESS_KEY 의 접근 키를 함께 보낸다. 키가 없거나 DBGateway 가 키를 거절하면
접근 키 화면을 알리고(Windows 에서는 브라우저로 열고) 멈춘다. 오래된 목차 복사본으로 건너뛰지 않는다.

목차는 ~/.claude/cache/searching-winus/manifest_index.json 에 받은 키의 확인값과 함께 남긴다. DBGateway 는
사람마다 허용된 쿼리만 목차에 포함하므로, 키가 다른 복사본은 없는 것으로 본다. 한 시간이 지나지 않은 복사본이
있으면 DBGateway 를 부르지 않고 그것을 쓴다. 목차를 못 받았는데 복사본이 오래됐으면 오래된 것을 쓰되 첫 줄에
그렇게 적는다. 복사본이 아예 없으면 멈춘다. SQL 은 남기지 않는다.

표준 라이브러리만 쓴다. 사내 SDK 는 비공개 저장소에 있어 사용자 PC 에서 설치하지 못한다.

사용: python scripts/fetch_manifest.py [--query id ...]
"""
import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

TTL_SECONDS = 3600
GATEWAY = os.environ.get("QUERY_GATEWAY_URL", "http://192.7.9.45:9101")
KEY_ENV = "KIWOOM_ACCESS_KEY"
KEY_PAGE = "http://192.7.9.45:3000/#access-key"
# 다른 OS 에서 그래픽 브라우저가 없으면 webbrowser 가 터미널 브라우저(lynx 등)를 앞에서 실행해 명령이 멈출 수 있다.
OPEN_BROWSER = sys.platform == "win32"


class SameHostRedirect(urllib.request.HTTPRedirectHandler):
    """같은 호스트 안의 리다이렉트만 따라간다. urllib 는 따라갈 때 Authorization 헤더까지 새 주소로 보내므로, 다른 호스트나
    https 에서 http 로 내려가는 주소면 따라가지 않고 그 3xx 를 오류로 남긴다."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        old, new = urllib.parse.urlsplit(req.full_url), urllib.parse.urlsplit(newurl)
        if new.hostname != old.hostname or (old.scheme == "https" and new.scheme != "https"):
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


OPENER = urllib.request.build_opener(SameHostRedirect)
CONFIG_DIR = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
CACHE = CONFIG_DIR / "cache" / "searching-winus" / "manifest_index.json"
# 이전 버전이 MongoDB 에서 받아 남긴 복사본이다. 쿼리 전체의 SQL 이 들어 있어 보이는 대로 지운다.
OLD_CACHE = CACHE.with_name("query_index.json")


def key_refused(reason: str) -> SystemExit:
    """접근 키 화면을 알리고(Windows 에서는 브라우저로 열고), 발급·설정 순서를 적은 종료를 돌려준다."""
    opened = OPEN_BROWSER and webbrowser.open(KEY_PAGE)
    page = f"접근 키 화면 {KEY_PAGE} ({'브라우저로 열림' if opened else '브라우저로 열지 못함'})"
    return SystemExit(f"{reason}\n- 조치: {page}에서 키 발급·「사용 방법」대로 환경변수 {KEY_ENV} 설정 후 새 Claude Code"
                      " 세션에서 다시 요청\n- 키 원문은 대화에 붙여 넣지 않음")


def access_key() -> str:
    """환경변수의 접근 키. 없으면 DBGateway 에 묻지 않고, 목차 복사본도 내지 않고 멈춘다."""
    key = os.environ.get(KEY_ENV, "").strip()
    if not key:
        raise key_refused(f"접근 키 없음: 환경변수 {KEY_ENV}")
    return key


def key_tag(key: str) -> str:
    """목차 복사본이 어느 키로 받은 것인지 가리키는 확인값. 키 원문은 남기지 않는다."""
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def refusal_detail(e: urllib.error.HTTPError) -> str:
    body = e.read().decode("utf-8", "replace")
    try:
        return json.loads(body).get("detail") or body
    except ValueError:
        return body


def get(path: str) -> dict:
    """DBGateway GET. 400·401·3xx 는 DBGateway 앞에서 판정이 끝난 응답이라 오래된 복사본으로 건너뛰지 않고 멈춘다."""
    request = urllib.request.Request(GATEWAY + path, headers={"Authorization": f"Bearer {access_key()}"})
    try:
        with OPENER.open(request, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise key_refused(f"DBGateway 신원 거절(401): {refusal_detail(e)}")
        if 300 <= e.code < 400:
            raise SystemExit(f"다른 호스트로의 리다이렉트 거절: {e.headers.get('Location')}"
                             " — 접근 키를 그 주소로 보내지 않음, QUERY_GATEWAY_URL 확인 필요")
        if e.code != 400:
            raise
        raise SystemExit(f"DBGateway 가 거절했다: {refusal_detail(e)}")


def fetch_index() -> list[dict]:
    rows = get("/winus/manifest")["queries"]
    if not rows:
        raise ValueError("DBGateway 목차가 비어 있다")
    return rows


def cache_age() -> float | None:
    """복사본을 받은 지 몇 초 지났는가. 복사본이 없으면 None."""
    try:
        return time.time() - CACHE.stat().st_mtime
    except FileNotFoundError:
        return None


def read_cache(tag: str) -> list[dict] | None:
    """이 키(확인값 tag)로 받은 복사본의 목차 행. 다른 키로 받았거나 키를 남기지 않은 이전 형식이면 None."""
    try:
        saved = json.loads(CACHE.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return None
    return saved["queries"] if isinstance(saved, dict) and saved.get("key") == tag else None


def manifest(key: str, fetch=fetch_index) -> tuple[list[dict], str | None]:
    """(목차 행, 경고). 경고가 있으면 오래된 복사본을 낸 것이다. key 는 접근 키이고 확인값만 복사본에 남긴다."""
    OLD_CACHE.unlink(missing_ok=True)
    tag = key_tag(key)
    age = cache_age()
    cached = read_cache(tag) if age is not None else None
    if cached is not None and age < TTL_SECONDS:
        return cached, None
    try:
        rows = fetch()
    except Exception as e:
        detail = f"{type(e).__name__}: {e}"
        if cached is None:
            raise SystemExit(f"쿼리 목차를 받지 못했고 이 키로 받은 복사본도 없다 — 사내망인지 확인한다. {detail}")
        return cached, f"DBGateway 에서 목차를 받지 못해 {age / 3600:.1f}시간 지난 복사본을 쓴다 — {detail}"
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    # 다른 세션이 반쯤 쓴 복사본을 읽지 않도록 임시 파일에 쓴 뒤 바꿔 끼운다. Windows 에서는 그 순간
    # 다른 세션이 복사본을 열고 있으면 교체가 거부되는데, 복사본은 다음 실행에 다시 받으면 되므로 건너뛴다.
    tmp = CACHE.with_name(f"{CACHE.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps({"key": tag, "queries": rows}, ensure_ascii=False), encoding="utf-8")
    try:
        os.replace(tmp, CACHE)
    except OSError:
        tmp.unlink(missing_ok=True)
    return rows, None


def cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def render_index(rows: list[dict]) -> str:
    lines = ["# DBGateway 쿼리 목차", "", "| id | 이름 | 설명 | 사용 테이블 |", "|---|---|---|---|"]
    lines += [f"| {q['query_id']} | {cell(q['query_name'])} | {cell(q['description'])} | {cell(', '.join(q['tables']))} |"
              for q in rows]
    return "\n".join(lines)


def render_detail(q: dict) -> str:
    args = ", ".join(f"`{a['name']}`({a['kind']}" + (f", 최대 {a['max_items']}개" if a.get("max_items") else "") + ")"
                     for a in q["arguments"]) or "없음"
    return "\n".join([f"## id {q['query_id']} · {q['query_name']}", "", f"- 설명: {q['description']}",
                      f"- 사용 테이블: {', '.join(q['tables'])}", f"- 인자: {args}", "- 등록된 SQL:", "",
                      "```sql", q["sql"], "```", ""])


def _selfcheck() -> None:
    import shutil
    global CACHE, OLD_CACHE
    # 사용자의 실제 사본과 섞이지 않게 빈 임시 폴더를 쓴다.
    saved = CACHE, OLD_CACHE
    CACHE = Path(tempfile.mkdtemp()) / "manifest_index.json"
    OLD_CACHE = CACHE.with_name("query_index.json")
    boom = lambda: (_ for _ in ()).throw(RuntimeError("끊김"))
    new = [{"query_id": 1, "query_name": "가", "description": "설명 | 하나", "tables": ["T_A", "T_B"]}]
    other = [{"query_id": 2, "query_name": "나", "description": "둘", "tables": ["T_C"]}]
    try:
        OLD_CACHE.write_text("{}", encoding="utf-8")
        assert manifest("kwam_a", lambda: new) == (new, None), "복사본이 없으면 받아서 낸다"
        assert not OLD_CACHE.exists(), "이전 복사본은 지운다"
        assert "kwam_a" not in CACHE.read_text(encoding="utf-8"), "키 원문은 복사본에 남기지 않는다"
        assert manifest("kwam_a", lambda: other) == (new, None), "같은 키의 복사본이 한 시간 안이면 받지 않는다"
        assert manifest("kwam_b", lambda: other) == (other, None), "다른 키로 받은 복사본은 다시 받는다"
        os.utime(CACHE, (0, 0))
        assert manifest("kwam_b", lambda: new) == (new, None), "복사본이 오래되면 다시 받는다"
        os.utime(CACHE, (0, 0))
        rows, warning = manifest("kwam_b", boom)
        assert (rows, bool(warning)) == (new, True), "못 받으면 오래된 복사본을 내고 알린다"
        try:
            manifest("kwam_c", boom)
        except SystemExit:
            pass
        else:
            raise AssertionError("다른 키로 받은 복사본은 못 받았을 때도 내지 않는다")
        CACHE.write_text(json.dumps(new), encoding="utf-8")  # 키를 남기지 않은 이전 형식
        assert manifest("kwam_b", lambda: other) == (other, None), "이전 형식의 복사본은 다시 받는다"
        os.utime(CACHE, (0, 0))
        try:
            manifest("kwam_b", lambda: (_ for _ in ()).throw(SystemExit("DBGateway 가 거절했다: x")))
        except SystemExit as e:
            assert "거절" in str(e), e
        else:
            raise AssertionError("DBGateway 가 거절하면 오래된 복사본으로 건너뛰지 않는다")
        CACHE.unlink()
        try:
            manifest("kwam_b", boom)
        except SystemExit:
            pass
        else:
            raise AssertionError("복사본이 없는데 못 받으면 멈춘다")
        out = render_index(new)
        assert "| 1 | 가 | 설명 \\| 하나 | T_A, T_B |" in out, out
        d = render_detail({"query_id": 7, "query_name": "기준일", "description": "d", "tables": ["T"],
                           "sql": "SELECT 1 FROM T", "arguments": [{"name": "오늘", "kind": "스칼라"},
                                                                    {"name": "codes", "kind": "목록", "max_items": 100}]})
        assert "## id 7 · 기준일" in d and "- 인자: `오늘`(스칼라), `codes`(목록, 최대 100개)" in d, d
        assert "```sql\nSELECT 1 FROM T\n```" in d, d
        assert "- 인자: 없음" in render_detail({"query_id": 1, "query_name": "a", "description": "",
                                                 "tables": [], "sql": "", "arguments": []})
        _selfcheck_key_and_http()
    finally:
        shutil.rmtree(CACHE.parent, ignore_errors=True)
        CACHE, OLD_CACHE = saved


def _selfcheck_key_and_http() -> None:
    """접근 키와 DBGateway 응답 처리. 실제 브라우저가 열리지 않게 webbrowser.open 을 바꾸고, 가짜 서버로 응답을 만든다."""
    import http.server
    import threading
    global GATEWAY, OPEN_BROWSER
    saved = GATEWAY, OPEN_BROWSER, webbrowser.open, os.environ.get(KEY_ENV)
    opened, paths = [], []
    webbrowser.open = lambda url: opened.append(url) or True

    class Gateway(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            paths.append(self.path)
            port = self.server.server_address[1]
            redirect = {"/same": "/ok", "/other": f"http://localhost:{port}/stolen"}.get(self.path)
            if redirect:
                self.send_response(302)
                self.send_header("Location", redirect)
                self.end_headers()
                return
            status, body = (401, {"kind": "신원 거절", "code": "unidentified", "detail": "폐기된 키"}) \
                if self.path == "/unauth" else (200, {"queries": [{"query_id": 9}]})
            self.send_response(status)
            self.end_headers()
            self.wfile.write(json.dumps(body, ensure_ascii=False).encode())

        def log_message(self, *a):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Gateway)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    GATEWAY = f"http://127.0.0.1:{server.server_port}"

    def stops(call, *said):
        try:
            call()
        except SystemExit as e:
            assert all(s in str(e) for s in said), e
            return str(e)
        raise AssertionError(f"멈춰야 한다: {said}")

    try:
        # 키가 없으면 DBGateway 를 부르지 않고 화면을 알린다. 열었는지는 문구로 구분한다
        os.environ.pop(KEY_ENV, None)
        OPEN_BROWSER = True
        stops(lambda: get("/ok"), f"접근 키 없음: 환경변수 {KEY_ENV}", "브라우저로 열림")
        assert opened == [KEY_PAGE] and paths == [], (opened, paths)
        OPEN_BROWSER = False
        stops(access_key, "브라우저로 열지 못함", KEY_PAGE)
        assert opened == [KEY_PAGE], opened
        os.environ[KEY_ENV] = " kwam_x\n"
        # 같은 호스트의 리다이렉트는 따라가고, 다른 호스트로는 접근 키를 보내지 않는다
        assert get("/same") == {"queries": [{"query_id": 9}]} and paths == ["/same", "/ok"], paths
        stops(lambda: get("/other"), "다른 호스트로의 리다이렉트 거절", "/stolen")
        assert "/stolen" not in paths, paths
        # 401 은 DBGateway 의 사유를 올리고, 오래된 복사본이 있어도 그것으로 건너뛰지 않는다
        stops(lambda: get("/unauth"), "DBGateway 신원 거절(401): 폐기된 키")
        CACHE.write_text(json.dumps({"key": key_tag("kwam_x"), "queries": [{"query_id": 1}]}), encoding="utf-8")
        os.utime(CACHE, (0, 0))
        stops(lambda: manifest("kwam_x", lambda: get("/unauth")), "신원 거절(401)")
    finally:
        server.shutdown()
        server.server_close()
        GATEWAY, OPEN_BROWSER, webbrowser.open, real_key = saved
        os.environ.pop(KEY_ENV, None)
        if real_key is not None:
            os.environ[KEY_ENV] = real_key


def main() -> None:
    # Windows 에서 출력이 파이프로 나가면 파이썬은 CP949 로 쓰고, 목차의 '—'·'−' 에서 멈춘다.
    # --help 와 인자 오류도 이 설정을 거치도록 인자를 해석하기 전에 둔다.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="DBGateway 의 쿼리 목차나 고른 쿼리의 상세를 낸다.")
    parser.add_argument("--query", nargs="+", type=int, default=[], metavar="id",
                        help="이 쿼리들의 이름·설명·사용 테이블·인자·등록된 SQL 을 낸다")
    parser.add_argument("--selfcheck", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.selfcheck:
        _selfcheck()
        print("selfcheck ok")
        return
    key = access_key()  # 목차 복사본을 내는 경로도 키가 없으면 멈추게 요청보다 먼저 확인한다
    if args.query:
        print("\n".join(render_detail(get(f"/winus/manifest/{i}")) for i in args.query))
        return
    rows, warning = manifest(key)
    if warning:
        print(f"경고: {warning}", file=sys.stderr)
        print(f"> **경고 — {warning}**\n")
    print(render_index(rows))


if __name__ == "__main__":
    main()
