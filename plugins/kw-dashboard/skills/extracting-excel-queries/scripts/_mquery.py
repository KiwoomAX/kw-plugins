"""Power Query(DataMashup) 의 M 코드를 풀고, 쿼리마다 SQL 과 외부 데이터 읽기를 찾는다."""
import base64
import binascii
import io
import re
import struct
import zipfile

from _model import Connection
from _secrets import collect, mask
from _vba_sql import SQL_KEYWORD, _target

SQL_CALLS = ("Odbc.Query", "OleDb.Query", "Value.NativeQuery")
DB_CALLS = ("Sql.Database", "Oracle.Database")
READ_CALLS = ("Web.Contents", "File.Contents", "Folder.Files", "SharePoint.Files", "SharePoint.Contents",
              "SharePoint.Tables", "OData.Feed", "Odbc.DataSource", "OleDb.DataSource", "Sql.Database", "Oracle.Database")
ESCAPES = {"lf": "\n", "cr": "\r", "tab": "\t", "cr,lf": "\r\n", "#": "#"}
NAME = r'#"(?:[^"]|"")*"|[^\W\d][\w.]*'


def decode_mashup(xml: bytes) -> str | None:
    """customXml 부품에서 base64 DataMashup 을 풀어 Formulas/Section1.m 을 돌려준다. 풀지 못하면 None."""
    try:
        text = xml.decode("utf-16") if xml[:2] in (b"\xff\xfe", b"\xfe\xff") else xml.decode("utf-8", "replace")
        m = re.search(r"<DataMashup\b[^>]*>\s*([A-Za-z0-9+/=\s]+?)\s*</DataMashup>", text)
        if not m:
            return None
        blob = base64.b64decode(m.group(1), validate=False)
        size = struct.unpack_from("<I", blob, 4)[0]
        with zipfile.ZipFile(io.BytesIO(blob[8:8 + size])) as z:
            return z.read("Formulas/Section1.m").decode("utf-8-sig", "replace")
    except (binascii.Error, struct.error, zipfile.BadZipFile, KeyError, UnicodeDecodeError):
        return None


def _strip_comments(m: str) -> str:
    out, i, in_str = [], 0, False
    while i < len(m):
        ch = m[i]
        if in_str:
            out.append(ch)
            if ch == '"':
                if m[i + 1:i + 2] == '"':
                    out.append('"')
                    i += 1
                else:
                    in_str = False
        elif ch == '"':
            in_str = True
            out.append(ch)
        elif m.startswith("//", i):
            j = m.find("\n", i)
            i = len(m) if j < 0 else j
            continue
        elif m.startswith("/*", i):
            j = m.find("*/", i + 2)
            i = len(m) if j < 0 else j + 2
            continue
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def _split_top(text: str, sep: str) -> list[str]:
    parts, depth, in_str, cur, i = [], 0, False, "", 0
    while i < len(text):
        ch = text[i]
        if ch == '"':
            in_str = not in_str
        elif not in_str and ch in "([{":
            depth += 1
        elif not in_str and ch in ")]}":
            depth -= 1
        elif not in_str and depth == 0 and text.startswith(sep, i):
            parts.append(cur)
            cur = ""
            i += len(sep)
            continue
        cur += ch
        i += 1
    parts.append(cur)
    return parts


def _name(raw: str) -> str:
    raw = raw.strip()
    return raw[2:-1].replace('""', '"') if raw.startswith('#"') else raw


def queries(m: str) -> dict[str, str]:
    """`shared 이름 = 식;` 을 이름 → 식으로 돌려준다."""
    m = _strip_comments(m)
    out = {}
    for stmt in _split_top(m, ";"):
        mm = re.match(rf"^\s*shared\s+({NAME})\s*=\s*(.*)$", stmt, re.S)
        if mm:
            out[_name(mm.group(1))] = mm.group(2).strip()
    return out


def _bindings(expr: str) -> dict[str, str]:
    mm = re.match(r"^\s*let\b(.*)\bin\b(.*)$", expr, re.S)
    if not mm:
        return {}
    out = {}
    for b in _split_top(mm.group(1), ","):
        kv = re.match(rf"^\s*({NAME})\s*=\s*(.*)$", b, re.S)
        if kv:
            out[_name(kv.group(1))] = kv.group(2).strip()
    return out


def _m_literal(term: str) -> str | None:
    t = term.strip()
    if len(t) < 2 or t[0] != '"' or t[-1] != '"' or '"' in t[1:-1].replace('""', ""):
        return None
    s = t[1:-1].replace('""', '"')
    return re.sub(r"#\(([^)]*)\)", lambda e: ESCAPES.get(e.group(1).lower(), e.group(0)), s)


def _call_args(text: str, start: int) -> list[str]:
    """text[start] 이 '(' 일 때 짝 괄호까지의 인자를 최상위 쉼표로 나눈다."""
    depth, in_str = 0, False
    for i in range(start, len(text)):
        ch = text[i]
        if ch == '"':
            in_str = not in_str
        elif not in_str and ch in "([{":
            depth += 1
        elif not in_str and ch in ")]}":
            depth -= 1
            if depth == 0:
                return [a.strip() for a in _split_top(text[start + 1:i], ",")]
    return []


class _Query:
    def __init__(self, name: str, expr: str, shared: set[str]):
        self.name, self.expr, self.shared = name, expr, shared
        self.binds = _bindings(expr)
        self.notes: set[str] = set()
        self.inputs: list[str] = []
        self.no = 0

    def eval(self, expr: str, depth: int = 0) -> list:
        parts = []
        for term in _split_top(expr, "&"):
            t = term.strip()
            if not t:
                continue
            lit = _m_literal(t)
            if lit is not None:
                parts.append(("lit", lit))
                continue
            if re.fullmatch(NAME, t):
                n = _name(t)
                if n in self.binds and depth < 5:
                    saved = (list(self.inputs), set(self.notes), self.no)
                    inner = self.eval(self.binds[n], depth + 1)
                    if any(p[0] == "lit" for p in inner):  # 문자열이 든 단계(SQL 조각)는 펼친다
                        parts += inner
                        continue
                    self.inputs, self.notes, self.no = saved  # 펼치지 않으면 시험 평가의 흔적을 지운다
                self._input(n)
                parts.append(("bind", n))
                continue
            call = re.match(rf"^({NAME})\s*\(", t)
            first = _call_args(t, call.end() - 1)[0] if call else ""
            if first and re.fullmatch(NAME, first):
                self._input(_name(first))
                parts.append(("bind", _name(first)))
            else:
                self.no += 1
                parts.append(("bind", f"EXPR{self.no}"))
            self.notes.add("함수 항 바인드")
        return parts

    def _input(self, n: str):
        if n in self.binds:
            expr = mask(" ".join(self.binds[n].split()), collect(self.binds[n]))
            label = f"변수 {n} = {expr[:60]}"
        elif n in self.shared:
            label = f"쿼리 {n}"
        else:
            label = f"변수 {n}"
        if label not in self.inputs:
            self.inputs.append(label)

    def render(self, parts: list) -> str:
        parts = [list(p) for p in parts]
        for i in range(1, len(parts) - 1):
            a, p, b = parts[i - 1], parts[i], parts[i + 1]
            if p[0] == "bind" and a[0] == b[0] == "lit" and a[1].endswith("'") and b[1].startswith("'"):
                a[1], b[1] = a[1][:-1], b[1][1:]
                self.notes.add("따옴표 제거")
        return "".join(p[1] if p[0] == "lit" else "#" + re.sub(r"\s+", "_", p[1].upper()) + "#" for p in parts).strip()

    def _text(self, expr: str) -> str:
        """식이 가리키는 문자열 리터럴과 단계 변수의 리터럴을 모은다(접속 대상 찾기용)."""
        e = expr.strip()
        if re.fullmatch(NAME, e) and _name(e) in self.binds:
            e = self.binds[_name(e)]
        return " ".join(_m_literal(x) or "" for x in re.findall(r'"(?:[^"]|"")*"', e))

    def scan(self) -> list[Connection]:
        out, body = [], self.expr
        for fn in SQL_CALLS:
            for mm in re.finditer(rf"\b{re.escape(fn)}\s*\(", body):
                args = _call_args(body, mm.end() - 1)
                if len(args) < 2:
                    continue
                sql = self.render(self.eval(args[1]))
                if SQL_KEYWORD.search(sql):
                    out.append(self._conn(sql, _target([self._text(args[0])])))
        for fn in DB_CALLS:
            for mm in re.finditer(rf"\b{re.escape(fn)}\s*\(", body):
                args = _call_args(body, mm.end() - 1)
                q = re.search(r"\bQuery\s*=\s*(.+)$", args[-1] if args else "", re.S)
                if not q:
                    continue
                sql = self.render(self.eval(_split_top(q.group(1).rstrip("] \n"), ",")[0]))
                server = (_m_literal(args[0]) or "") if args else ""
                if SQL_KEYWORD.search(sql):
                    out.append(self._conn(sql, server.upper()))
        if out:
            return out
        for fn in READ_CALLS:
            mm = re.search(rf"\b{re.escape(fn)}\s*\(", body)
            if mm:
                args = _call_args(body, mm.end() - 1)
                target = (_m_literal(args[0]) or args[0]) if args else ""
                return [Connection(kind="Power Query", location=f"Power Query {self.name}",
                                   target=_target([target]) or target, notes=["추출 미지원"])]
        return []

    def _conn(self, sql: str, target: str) -> Connection:
        return Connection(kind="Power Query", location=f"Power Query {self.name}", sql=sql, target=target,
                          inputs=", ".join(self.inputs), notes=sorted(self.notes))


def scan_m(m: str) -> list[Connection]:
    qs = queries(m)
    out = []
    for name, expr in qs.items():
        out += _Query(name, expr, set(qs)).scan()
    return out


def _mashup_xml(m_code: str) -> bytes:
    """시험용: M 코드를 DataMashup customXml 부품 바이트로 만든다."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("Formulas/Section1.m", m_code)
    pkg = buf.getvalue()
    blob = struct.pack("<II", 0, len(pkg)) + pkg
    xml = ('<?xml version="1.0" encoding="utf-16"?><DataMashup xmlns="http://schemas.microsoft.com/DataMashup">'
           + base64.b64encode(blob).decode() + "</DataMashup>")
    return xml.encode("utf-16")


def _selfcheck() -> None:
    flat = lambda s: " ".join(s.split())
    m = '''section Section1;

shared 시작일 = let
    원본 = Text.From(Excel.CurrentWorkbook(){[Name="StartDate"]}[Content]{0}[Column1])
in
    원본;

shared 종료일 = let
    원본 = Text.From(Excel.CurrentWorkbook(){[Name="EndDate"]}[Content]{0}[Column1])
in
    원본;

shared 국내쿼리 = let
    // 주석
    시작일_정제 = Text.Trim(시작일),
    SQL_Query = "SELECT a.x#(lf)FROM SCHEMA_A.DW_T a#(lf)WHERE a.d BETWEEN '" & 시작일_정제 & "' AND '" & 종료일 & "'",
    Source = Odbc.Query("driver={Oracle};dbq=TESTSRV;uid=u;pwd=p9", SQL_Query)
in
    Source;

shared #"웹 자료" = let
    Source = Json.Document(Web.Contents("https://x.example/api"))
in
    Source;

shared 오라클 = let
    Source = Oracle.Database("TESTSRV", [Query="select 1 from dual"])
in
    Source;'''
    assert decode_mashup(_mashup_xml(m)) == m
    assert decode_mashup(b"<DataMashup>not base64!</DataMashup>") is None
    assert list(queries(m)) == ["시작일", "종료일", "국내쿼리", "웹 자료", "오라클"]
    cs = scan_m(m)
    by = {c.location: c for c in cs}
    assert set(by) == {"Power Query 국내쿼리", "Power Query 웹 자료", "Power Query 오라클"}
    q = by["Power Query 국내쿼리"]
    assert q.kind == "Power Query" and q.target == "TESTSRV"
    assert flat(q.sql) == "SELECT a.x FROM SCHEMA_A.DW_T a WHERE a.d BETWEEN #시작일_정제# AND #종료일#"
    assert "따옴표 제거" in q.notes and q.inputs == "변수 시작일_정제 = Text.Trim(시작일), 쿼리 종료일"
    assert by["Power Query 웹 자료"].sql is None and by["Power Query 웹 자료"].target == "https://x.example/api"
    assert "추출 미지원" in by["Power Query 웹 자료"].notes
    assert by["Power Query 오라클"].sql == "select 1 from dual" and by["Power Query 오라클"].target == "TESTSRV"
    # test_input_label_masked: 입력 열에 옮기는 단계 식의 비밀번호를 가린다
    leak = 'section S;\nshared Q = let\n  C = Text.Trim("dsn=X;pwd=sec1"),\n  S = Odbc.Query("dbq=TESTSRV", "select a from t where k = " & C)\nin S;'
    [c] = scan_m(leak)
    assert "sec1" not in c.inputs and "pwd=***" in c.inputs


if __name__ == "__main__":
    _selfcheck()
    print("selfcheck ok")
