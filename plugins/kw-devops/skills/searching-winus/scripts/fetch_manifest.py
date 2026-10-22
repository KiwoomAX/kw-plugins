"""DBGateway 에서 쿼리 목차나 고른 쿼리의 상세를 받아 표준 출력에 낸다.

인자 없이 실행하면 쿼리 단위 목차(id·이름·설명·사용 테이블)를 내고, --query 뒤에 쿼리 id 를 주면 그
쿼리들의 이름·설명·사용 테이블·인자·등록된 SQL 을 낸다. 목차에는 SQL 이 없고, SQL 은 고른 id 만
DBGateway 에 묻는다. 쓰지 않을 쿼리의 SQL 까지 사용자 PC 에 받지 않으려고 나눴다.

요청마다 환경 변수 KIWOOM_ACCESS_KEY 의 접근 키를 함께 보낸다. 키가 없거나 DBGateway 가 키를 거절하면
접근 키 화면을 알리고(Windows 에서는 브라우저로 열고) 멈춘다. 오래된 목차 복사본으로 건너뛰지 않는다.
다만 Windows 레지스트리(HKCU\\Environment)에는 키가 있는데 이 프로그램의 환경 변수에 없거나 이전 키가 남았으면,
발급 화면 대신 창을 모두 닫고 다시 열라고 안내하고 멈춘다. 레지스트리 값은 확인에만 쓰고 요청에는 쓰지 않는다.

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


REOPEN = ("클로드 코드를 실행한 프로그램의 창을 모두 닫고 다시 연 뒤 새 세션에서 같은 요청"
          " (터미널이면 Windows Terminal·PowerShell 창 전부, VS Code·JetBrains·클로드 데스크톱 앱이면 그 프로그램 창 전부)")
STILL_SAME = "그래도 같으면 Windows 로그아웃 후 다시 로그인\n- 키를 다시 발급하지 않음"


def key_refused(reason: str) -> SystemExit:
    """접근 키 화면을 알리고(Windows 에서는 브라우저로 열고), 발급·설정 순서를 적은 종료를 돌려준다."""
    opened = OPEN_BROWSER and webbrowser.open(KEY_PAGE)
    page = f"접근 키 화면 {KEY_PAGE} ({'브라우저로 열림' if opened else '브라우저로 열지 못함'})"
    return SystemExit(f"{reason}\n- 조치: {page}에서 키 발급·「사용 방법」대로 환경 변수 {KEY_ENV} 설정\n"
                      f"- 설정 뒤: {REOPEN}\n- 키 원문은 대화에 붙여 넣지 않음")


def not_applied(reason: str, still_same: str = STILL_SAME) -> SystemExit:
    """키는 설정됐는데 이 프로그램에 아직 반영되지 않았을 때의 종료. 재발급이 필요하다고 오해하지 않게 발급 화면을 열지 않는다."""
    return SystemExit(f"{reason}\n- 조치: {REOPEN}\n- 같은 창에서 클로드 코드만 다시 실행하면 반영되지 않음"
                      f"\n- {still_same}")


def registry_key() -> str:
    """Windows 사용자 환경 변수 저장소(HKCU\\Environment)의 접근 키. 없거나 Windows 가 아니면 빈 문자열.

    접근 키 화면의 설정 명령이 저장하는 곳이다. 실행 중인 프로그램의 환경 변수는 시작할 때 부모에게서 복사된 것이라,
    설정 뒤 창을 다시 열지 않으면 이 값과 다르다. 반영 여부를 판단하는 데만 쓰고 요청에는 쓰지 않는다.
    """
    if sys.platform != "win32":
        return ""
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            return str(winreg.QueryValueEx(k, KEY_ENV)[0]).strip()
    except OSError:
        return ""


def access_key() -> str:
    """환경 변수의 접근 키. 없으면 DBGateway 에 묻지 않고, 목차 복사본도 내지 않고 멈춘다."""
    key = os.environ.get(KEY_ENV, "").strip()
    if key:
        return key
    if registry_key():
        raise not_applied("접근 키는 설정됨: 이 창에는 아직 반영되지 않음")
    raise key_refused(f"접근 키 없음: 환경 변수 {KEY_ENV}")


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
    key = access_key()
    request = urllib.request.Request(GATEWAY + path, headers={"Authorization": f"Bearer {key}"})
    try:
        with OPENER.open(request, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            registry = registry_key()
            # 재발급한 새 키가 레지스트리에 있는데 이 창에는 이전 키가 남은 상태로 본다. 다만 이 창의 키가 레지스트리가 아닌
            # 곳(클로드 코드 설정의 env 등)에서 오면 창을 다시 열어도 같으므로, 그때 재발급으로 빠져나갈 길을 함께 적는다.
            if registry and registry != key:
                raise not_applied("새 접근 키가 설정됨: 이 창에는 이전 키가 남아 DBGateway 신원 거절(401)",
                                  f"다시 연 뒤에도 같은 거절이면 이 창의 키는 레지스트리가 아닌 곳(클로드 코드 설정의 env 등)에서"
                                  f" 오는 것: 접근 키 화면 {KEY_PAGE}에서 재발급해 그곳의 키 교체")
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
    # 사용자의 실제 복사본과 섞이지 않게 빈 임시 폴더를 쓴다.
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
        _selfcheck_registry()
        _selfcheck_key_and_http()
    finally:
        shutil.rmtree(CACHE.parent, ignore_errors=True)
        CACHE, OLD_CACHE = saved


def _selfcheck_registry() -> None:
    """실제 winreg 경로. 쓰지 않는 이름으로 값을 잠깐 만들었다 지우므로 사용자의 접근 키는 건드리지 않는다."""
    global KEY_ENV
    if sys.platform != "win32":
        return
    import winreg
    saved_name, KEY_ENV = KEY_ENV, "KW_SEARCHING_WINUS_SELFCHECK"
    try:
        assert registry_key() == "", "값이 없으면 OSError 를 삼키고 빈 문자열"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, KEY_ENV, 0, winreg.REG_SZ, " kwam_probe \n")
        assert registry_key() == "kwam_probe", "앞뒤 공백·줄바꿈을 지운 값"
    finally:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE) as k:
            try:
                winreg.DeleteValue(k, KEY_ENV)
            except OSError:
                pass
        KEY_ENV = saved_name


def _selfcheck_key_and_http() -> None:
    """접근 키와 DBGateway 응답 처리. 실제 브라우저가 열리지 않게 webbrowser.open 을 바꾸고, 가짜 서버로 응답을 만든다."""
    import http.server
    import threading
    global GATEWAY, OPEN_BROWSER, registry_key
    saved = GATEWAY, OPEN_BROWSER, webbrowser.open, registry_key, os.environ.get(KEY_ENV)
    opened, paths = [], []
    webbrowser.open = lambda url: opened.append(url) or True
    registry = {"key": ""}  # 레지스트리 대신 쓴다. Windows 에서 실행해도 사용자의 실제 레지스트리를 읽지 않는다
    registry_key = lambda: registry["key"]  # noqa: E731

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
        stops(lambda: get("/ok"), f"접근 키 없음: 환경 변수 {KEY_ENV}", "브라우저로 열림")
        assert opened == [KEY_PAGE] and paths == [], (opened, paths)
        OPEN_BROWSER = False
        stops(access_key, "브라우저로 열지 못함", KEY_PAGE)
        assert opened == [KEY_PAGE], opened
        # 레지스트리에는 있는데 이 창에 없으면 발급 화면을 열지 않고 창을 다시 열라고 한다
        OPEN_BROWSER = True
        registry["key"] = "kwam_new"
        msg = stops(lambda: get("/ok"), "접근 키는 설정됨: 이 창에는 아직 반영되지 않음", "창을 모두 닫고", "키를 다시 발급하지 않음")
        assert "kwam_new" not in msg and opened == [KEY_PAGE] and paths == [], (msg, opened, paths)
        OPEN_BROWSER = False
        registry["key"] = ""
        os.environ[KEY_ENV] = " kwam_x\n"
        # 같은 호스트의 리다이렉트는 따라가고, 다른 호스트로는 접근 키를 보내지 않는다
        assert get("/same") == {"queries": [{"query_id": 9}]} and paths == ["/same", "/ok"], paths
        stops(lambda: get("/other"), "다른 호스트로의 리다이렉트 거절", "/stolen")
        assert "/stolen" not in paths, paths
        # 401 은 DBGateway 의 사유를 올리고, 오래된 복사본이 있어도 그것으로 건너뛰지 않는다
        stops(lambda: get("/unauth"), "DBGateway 신원 거절(401): 폐기된 키")
        # 401 인데 레지스트리에 다른(재발급한) 키가 있으면 이 창에 이전 키가 남은 것으로 보고 발급 화면을 열지 않는다
        OPEN_BROWSER = True
        registry["key"] = "kwam_new"
        msg = stops(lambda: get("/unauth"), "새 접근 키가 설정됨", "창을 모두 닫고", f"{KEY_PAGE}에서 재발급")
        assert "키를 다시 발급하지 않음" not in msg and opened == [KEY_PAGE], (msg, opened)
        registry["key"] = "kwam_x"  # 같은 키가 거절되면 키 자체의 문제다
        stops(lambda: get("/unauth"), "DBGateway 신원 거절(401): 폐기된 키", "브라우저로 열림")
        assert opened == [KEY_PAGE, KEY_PAGE], opened
        OPEN_BROWSER = False
        registry["key"] = ""
        CACHE.write_text(json.dumps({"key": key_tag("kwam_x"), "queries": [{"query_id": 1}]}), encoding="utf-8")
        os.utime(CACHE, (0, 0))
        stops(lambda: manifest("kwam_x", lambda: get("/unauth")), "신원 거절(401)")
    finally:
        server.shutdown()
        server.server_close()
        GATEWAY, OPEN_BROWSER, webbrowser.open, registry_key, real_key = saved
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
