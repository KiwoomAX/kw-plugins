"""접속 정보 속 비밀번호를 모으고 가리며, 결과 폴더에 비밀번호가 남았는지 검사한다."""
import pathlib
import re
import tempfile

# 접속 문자열의 키=값 은 = 앞뒤에 공백이 없다. SQL 조건(uid = ...)과 구분하려고 공백을 허용하지 않는다.
PASS_KEY = re.compile(r"(?i)\b(PWD|Password)=([^;\"&\s]*)")
PASS_VAR = re.compile(r"(?i)\b(?:PWD|Password)=\"\s*&\s*([^\W\d]\w*)")
LITERAL = re.compile(r'"((?:[^"]|"")*)"')
# 문자열 리터럴 안 어디에 있든 사용자/비밀번호@별칭 (예: Shell 명령의 sqlplus 접속 인자)
USER_PASS_IN = re.compile(r'(?<![\w/])([\w$#]+)/([^@/\s"]+)@([\w.]+)')
ANY_KEY = re.compile(r"(?i)\b(PWD|Password|UID|User ID)(=)([^;\"&\s]*)")
OPEN_CALL = re.compile(r"(\w+)\.Open\s+(.+)$", re.M)
USER_PASS = re.compile(r'"([\w$#]+)/([^@/\s"]+)@([\w.]+)"')
HTTP_VERB = re.compile(r'^"(GET|POST|PUT|DELETE|HEAD|PATCH)"$', re.I)


def _args(text: str) -> list[str]:
    out, in_str, cur = [], False, ""
    for ch in text:
        if ch == '"':
            in_str = not in_str
        if ch == "," and not in_str:
            out.append(cur.strip())
            cur = ""
            continue
        cur += ch
    out.append(cur.strip())
    return out


def _lookup(text: str, var: str) -> str | None:
    m = re.search(rf'(?im)^\s*(?:(?:Public|Private|Dim|Global)\s+)?(?:Const\s+)?{re.escape(var)}\b(?:\s+As\s+\w+)?\s*=\s*"([^"]*)"', text)
    return m.group(1) if m else None


def _value(text: str, arg: str) -> str | None:
    if len(arg) >= 2 and arg[0] == arg[-1] == '"':
        return arg[1:-1]
    if re.fullmatch(r"[^\W\d]\w*", arg):
        return _lookup(text, arg)
    return None


def _open_passwords(text: str) -> list[str]:
    out = []
    for m in OPEN_CALL.finditer(text):
        args = _args(m.group(2))
        if len(args) < 3 or HTTP_VERB.match(args[0]) or args[1].lower().startswith('"http'):
            continue
        v = _value(text, args[2])
        if v:
            out.append(v)
    return out


def collect(text: str) -> set[str]:
    """PWD·Password 키, Connection.Open 셋째 인자, 사용자/비밀번호@별칭 형태에서 비밀번호만 모은다."""
    found = {m.group(2) for m in PASS_KEY.finditer(text) if m.group(2)}
    for m in PASS_VAR.finditer(text):
        v = _lookup(text, m.group(1))
        if v:
            found.add(v)
    found.update(_open_passwords(text))
    found.update(m.group(2) for m in USER_PASS.finditer(text))
    for lit in LITERAL.findall(text):
        found.update(m.group(2) for m in USER_PASS_IN.finditer(lit))
    return {s for s in found if s}


def mask(text: str, secrets: set[str]) -> str:
    """네 키 값, Connection.Open 의 아이디·비밀번호 인자, 사용자/비밀번호@별칭, 모은 비밀번호를 *** 로 바꾼다."""
    text = ANY_KEY.sub(lambda m: m.group(1) + m.group(2) + ("***" if m.group(3).strip() else m.group(3)), text)
    text = USER_PASS.sub(lambda m: f'"***/***@{m.group(3)}"', text)
    text = LITERAL.sub(lambda m: '"' + USER_PASS_IN.sub(lambda u: f"***/***@{u.group(3)}", m.group(1)) + '"', text)

    def _open(m):
        args = _args(m.group(2))
        if len(args) < 3 or HTTP_VERB.match(args[0]) or args[1].lower().startswith('"http'):
            return m.group(0)
        for k in (1, 2):
            if args[k].startswith('"'):
                args[k] = '"***"'
        return f"{m.group(1)}.Open " + ", ".join(args)
    text = OPEN_CALL.sub(_open, text)
    for s in sorted(secrets, key=len, reverse=True):
        if len(s) >= 8:
            text = text.replace(s, "***")
        else:  # 짧은 값은 SQL 의 다른 이름과 겹치므로 단어 경계로만 가린다(_contains 와 같은 기준)
            text = re.sub(rf"(?<![\w]){re.escape(s)}(?![\w])", "***", text)
    return text


def _contains(text: str, secret: str) -> bool:
    if len(secret) >= 8:
        return secret in text
    return re.search(rf"(?<![\w]){re.escape(secret)}(?![\w])", text) is not None


def _texts(path: pathlib.Path) -> list[str]:
    if path.suffix == ".sql":
        return [path.read_text(encoding="utf-8")]
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True)
    try:
        return [str(v) for ws in wb.worksheets for row in ws.iter_rows(values_only=True) for v in row if v is not None]
    finally:
        wb.close()


def find_leaks(folder: pathlib.Path, secrets: set[str]) -> list[pathlib.Path]:
    """폴더 안 .sql 과 .xlsx 셀 문자열에서 비밀번호가 보이는 파일을 돌려준다."""
    leaks = []
    if not secrets:
        return leaks
    for p in sorted(folder.rglob("*")):
        if p.suffix not in (".sql", ".xlsx") or p.name.startswith("~$"):
            continue
        if any(_contains(t, s) for t in _texts(p) for s in secrets):
            leaks.append(p)
    return leaks


def _selfcheck() -> None:
    s = 'connstr = "Driver={Oracle};Dbq=testsrv;uid=testuser;PWD=pw1;"'
    sec = collect(s)
    assert sec == {"pw1"}
    m = mask(s, sec)
    assert "pw1" not in m and "testuser" not in m and "uid=***" in m
    assert collect('cn.Open connstr, "usr", "pw2"') == {"pw2"}
    assert collect('h.Open "GET", "https://x", False') == set()
    assert collect('c = "scott/pw3@TESTSRV"') == {"pw3"}
    assert collect('p = "pw4"\nconnstr = "DSN=x;Password=" & p') == {"pw4"}
    assert collect('Public Const PW As String = "pw5"\nconnstr = "PWD=" & PW') == {"pw5"}
    assert collect("Password=;") == set()
    assert mask("select x/y from t@lnk", set()) == "select x/y from t@lnk"
    # test_user_pass_inside_command: 명령 문자열 안의 사용자/비밀번호@별칭 도 잡는다
    sh = 'Shell("sqlplus scott/tiger9@TESTSRV @run.sql")'
    assert "tiger9" in collect(sh) and "tiger9" not in mask(sh, collect(sh))
    # test_sql_columns_untouched: SQL 의 uid·password 칼럼 조건은 접속 문자열 키가 아니다
    sql = "where a.uid = #S_UID# and a.d = #S_ILJA# order by 1"
    assert mask(sql, set()) == sql and collect("where pwd = 'x' and k = 1") == set()
    # test_short_secret_word_boundary: 짧은 비밀번호는 단어 경계로만 가린다
    assert mask("select kw12col from tkw12 where p = kw12", {"kw12"}) == "select kw12col from tkw12 where p = ***"
    with tempfile.TemporaryDirectory() as d:
        p = pathlib.Path(d, "q1.sql"); p.write_text("select * from TESTUSER.t", encoding="utf-8")
        assert find_leaks(pathlib.Path(d), {"pw1"}) == []
        p.write_text("x pw1", encoding="utf-8")
        assert find_leaks(pathlib.Path(d), {"pw1"}) == [p]


if __name__ == "__main__":
    _selfcheck()
    print("selfcheck ok")
