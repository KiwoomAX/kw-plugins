"""VBA 소스에서 문자열을 이어 붙여 만든 SQL 을 정적으로 조립한다."""
import re

from _model import Connection

SQL_KEYWORD = re.compile(r"\b(select|insert|update|delete|merge|with)\b", re.I)
FRAGMENT_START = re.compile(r"^\s*(select|insert|update|delete|merge|with|where|and|or|order\s+by|group\s+by|having|from|union|join|left|inner)\b", re.I)
PROC_START = re.compile(r"^\s*(?:(?:Public|Private|Friend)\s+)?(?:Static\s+)?(?:Sub|Function)\s+(\w+)", re.I)
PROC_END = re.compile(r"^\s*End\s+(?:Sub|Function)\b", re.I)
BRANCH = re.compile(r"^\s*(If|ElseIf|Else|Select\s+Case|Case|For|Do|While|Loop|Next|End\s+If|End\s+Select|Wend)\b", re.I)
ONE_LINE_IF = re.compile(r"^\s*If\b.*?\bThen\s+(\S.*)$", re.I)
ASSIGN = re.compile(r"^\s*(?:(?:Let|Set)\s+)?([^\W\d]\w*)\s*=\s*(.+)$")
WITH_ADD = re.compile(r"^\s*With\s+(.*?)\.(QueryTables|ListObjects)\.Add\s*\((.*)$", re.I)
CELL_READ = re.compile(r'^(?:\w+\.)?Range\("([A-Za-z]+\d+)"\)(?:\.Value)?$|^(?:\w+\.)?Cells\(\s*(\d+)\s*,\s*(\d+)\s*\)(?:\.Value)?$', re.I)
CELL_WRITE = re.compile(r"^\s*(?:(\w+)\.)?Cells\(\s*[^,]+,\s*(\d+)\s*\)(?:\.Value)?\s*=", re.I)
TARGET_KEYS = ("DBQ", "Data Source", "SERVER", "DSN")
BUILTINS = {"vbcrlf": "\n", "vbcr": "\n", "vblf": "\n", "vbnewline": "\n", "vbtab": "\t"}
CHR = re.compile(r"^Chr\$?\(\s*(\d+)\s*\)$", re.I)


def _logical_lines(source: str) -> list[str]:
    """줄 연속 `_` 를 합치고 문자열 밖의 `'` 주석을 지운다."""
    out, buf = [], ""
    for line in source.replace("\r\n", "\n").split("\n"):
        line = _strip_comment(line)
        if re.search(r"\s_\s*$", line):
            buf += re.sub(r"\s_\s*$", " ", line)
            continue
        out.append(buf + line)
        buf = ""
    if buf:
        out.append(buf)
    return out


def _strip_comment(line: str) -> str:
    in_str = False
    for i, ch in enumerate(line):
        if ch == '"':
            in_str = not in_str
        elif ch == "'" and not in_str:
            return line[:i]
    if re.match(r"^\s*Rem\b", line, re.I):
        return ""
    return line


def _split_top(text: str, seps: str) -> list[str]:
    """문자열과 괄호 밖의 구분자로 나눈다."""
    parts, depth, in_str, cur = [], 0, False, ""
    for ch in text:
        if ch == '"':
            in_str = not in_str
        elif not in_str and ch == "(":
            depth += 1
        elif not in_str and ch == ")":
            depth -= 1
        elif not in_str and depth == 0 and ch in seps:
            parts.append(cur)
            cur = ""
            continue
        cur += ch
    parts.append(cur)
    return parts


def _literal(term: str) -> str | None:
    t = term.strip()
    if len(t) >= 2 and t[0] == '"' and t[-1] == '"' and '"' not in t[1:-1].replace('""', ""):
        return t[1:-1].replace('""', '"')
    return None


def _call(term: str) -> tuple[str, list[str]] | None:
    m = re.match(r"^([^\W\d][\w.]*\$?)\s*\((.*)\)$", term.strip(), re.S)
    if not m:
        return None
    return m.group(1), [a.strip() for a in _split_top(m.group(2), ",")]


def _named_args(text: str) -> dict[str, str]:
    """`Connection:="..." , Destination:=Range("A1")` 같은 이름 인자를 읽는다."""
    out = {}
    for arg in _split_top(text, ","):
        m = re.match(r"^\s*(\w+)\s*:=\s*(.+?)\s*$", arg, re.S)
        if m:
            out[m.group(1).lower()] = m.group(2)
    return out


def _target(texts: list[str]) -> str:
    for key in TARGET_KEYS:
        vals = []
        for t in texts:
            for v in re.findall(rf"(?i)\b{key}\s*=\s*([^;\"]+)", t):
                v = v.strip().upper()
                if v and v not in vals:
                    vals.append(v)
        if vals:
            return ", ".join(vals)
    return ""


def _columns(cols: list[int]) -> str:
    cols = sorted(set(cols))
    runs, start, prev = [], None, None
    for c in cols:
        if start is None:
            start = prev = c
        elif c == prev + 1:
            prev = c
        else:
            runs.append((start, prev))
            start = prev = c
    if start is not None:
        runs.append((start, prev))
    return "·".join(str(a) if a == b else f"{a}~{b}" for a, b in runs)


class _Proc:
    def __init__(self, module: str, name: str, lines: list[str], module_target: str):
        self.module, self.name, self.lines = module, name, lines
        self.module_target = module_target
        self.vars: dict[str, dict] = {}
        self.cells: dict[str, str] = {}
        self.branch_lines: list[int] = []
        self.out: list[Connection] = []
        self.expr_no = 0
        self.with_ctx: list[dict | None] = []

    # 식 평가: 항 목록 [("lit", 문자열) | ("bind", 이름, 변수)] 과 비고 집합
    def eval(self, expr: str, self_var: str | None = None) -> tuple[list, set]:
        parts, notes = [], set()
        call = _call(expr)
        if call and call[0].lower() == "array":
            for a in call[1]:
                p, n = self.eval(a)
                parts += p
                notes |= n
            return parts, notes
        for term in _split_top(expr, "&+"):
            t = term.strip()
            if not t:
                continue
            lit = _literal(t)
            if lit is not None:
                parts.append(("lit", lit))
                continue
            if t.lower() in BUILTINS:
                parts.append(("lit", BUILTINS[t.lower()]))
                continue
            m = CHR.match(t)
            if m:
                parts.append(("lit", {"9": "\t"}.get(m.group(1), "\n")))
                continue
            if re.fullmatch(r"\d+(\.\d+)?", t):
                parts.append(("lit", t))
                continue
            if re.fullmatch(r"[^\W\d]\w*", t):
                v = self.vars.get(t.lower())
                if t.lower() == (self_var or "").lower() and v:
                    parts += v["parts"]
                    notes |= v["notes"]
                elif v and v["fragment"]:
                    parts += v["parts"]
                    notes |= v["notes"]
                else:
                    parts.append(("bind", t.upper(), t))
                continue
            c = _call(t)
            if c:
                first = c[1][0] if c[1] else ""
                if re.fullmatch(r"[^\W\d]\w*", first):
                    parts.append(("bind", first.upper(), first))
                else:
                    self.expr_no += 1
                    parts.append(("bind", f"EXPR{self.expr_no}", ""))
                notes.add("함수 항 바인드")
                continue
            self.expr_no += 1
            parts.append(("bind", f"EXPR{self.expr_no}", ""))
            notes.add("함수 항 바인드")
        return parts, notes

    def render(self, parts: list, notes: set) -> tuple[str, set, list[str]]:
        notes = set(notes)
        parts = [list(p) for p in parts]
        for i, p in enumerate(parts):
            if p[0] != "bind" or i == 0 or i + 1 >= len(parts):
                continue
            a, b = parts[i - 1], parts[i + 1]
            if a[0] == "lit" and b[0] == "lit" and a[1].endswith("'") and b[1].startswith("'"):
                a[1], b[1] = a[1][:-1], b[1][1:]
                notes.add("따옴표 제거")
        text = "".join(p[1] if p[0] == "lit" else f"#{p[1]}#" for p in parts).strip()
        binds = []
        for p in parts:
            if p[0] == "bind" and p[2] and p[2] not in binds:
                binds.append(p[2])
        return text, notes, binds

    def emit(self, parts, notes, start: int, end: int, kind="VBA ADODB SQL", target=None, out_range=None):
        text, notes, binds = self.render(parts, notes)
        if not SQL_KEYWORD.search(text):
            return False
        if any(start < b <= end for b in self.branch_lines):
            notes.add("조립 분기 있음")
        inputs = ", ".join(f"셀 {self.cells[v.lower()]} 를 읽는 변수 {v}" if v.lower() in self.cells else f"변수 {v}" for v in binds)
        self.out.append(Connection(kind=kind, location=f"VBA {self.module}.{self.name}", sql=text,
                                   target=self.module_target if target is None else target,
                                   inputs=inputs, output_range=out_range or "", notes=sorted(notes)))
        return True

    def flush(self, var: str):
        v = self.vars.get(var)
        if v and not v["executed"] and not v["fragment"]:
            n = set(v["notes"]) | {"실행 호출 없음"}
            self.emit(v["parts"], n, v["start"], v["start"])

    def execute(self, expr: str, i: int, kind="VBA ADODB SQL", target=None, out_range=None):
        e = expr.strip()
        var = self.vars.get(e.lower()) if re.fullmatch(r"[^\W\d]\w*", e) else None
        if var:
            var["executed"] = True
            self.emit(var["parts"], var["notes"], var["start"], i, kind, target, out_range)
        else:
            parts, notes = self.eval(e)
            self.emit(parts, notes, i, i, kind, target, out_range)

    def run(self) -> list[Connection]:
        cols, sheets = [], set()
        for i, raw in enumerate(self.lines):
            line = raw.strip()
            if not line:
                continue
            m = ONE_LINE_IF.match(line)
            if m:
                self.branch_lines.append(i)
                line = m.group(1).strip()
            elif BRANCH.match(line):
                self.branch_lines.append(i)
                continue
            m = WITH_ADD.match(line)
            if m:
                args = _named_args(m.group(3).rsplit(")", 1)[0] if ")" in m.group(3) else m.group(3))
                conn = args.get("connection") or args.get("source") or ""
                ctext = "".join(p[1] for p in self.eval(conn)[0] if p[0] == "lit") if conn else ""
                dest = re.search(r'Range\("([^"]+)"\)', args.get("destination", ""))
                self.with_ctx.append({"sheet": m.group(1).strip(), "target": _target([ctext]),
                                      "dest": dest.group(1) if dest else ""})
                if "sql" in args:
                    ctx = self.with_ctx[-1]
                    self.execute(args["sql"], i, "VBA 쿼리 테이블 생성", ctx["target"], f"{ctx['sheet']} {ctx['dest']}".strip())
                continue
            if re.match(r"^With\b", line, re.I):
                self.with_ctx.append(None)
                continue
            if re.match(r"^End\s+With\b", line, re.I):
                if self.with_ctx:
                    self.with_ctx.pop()
                continue
            m = CELL_WRITE.match(line)
            if m:
                cols.append(int(m.group(2)))
                sheets.add(m.group(1) or "ActiveSheet")
                continue
            m = re.match(r"^\.CommandText\s*=\s*(.+)$", line, re.I)
            if m:
                ctx = self.with_ctx[-1] if self.with_ctx else None
                if ctx:
                    self.execute(m.group(1), i, "VBA 쿼리 테이블 생성", ctx["target"], f"{ctx['sheet']} {ctx['dest']}".strip())
                else:
                    self.execute(m.group(1), i)
                continue
            m = re.search(r"\.Execute\b\s*\(?\s*(.+)$", line, re.I)
            if m:
                arg = _split_top(m.group(1).rstrip(")"), ",")[0]
                self.execute(arg, i)
                continue
            m = re.search(r"\.Open\b\s*\(?\s*(.+)$", line, re.I)
            if m:
                arg = _split_top(m.group(1), ",")[0].rstrip(")")
                self.execute(arg, i)
                continue
            m = ASSIGN.match(line)
            if m:
                name, expr = m.group(1), m.group(2).strip()
                key = name.lower()
                cell = CELL_READ.match(expr)
                if cell:
                    self.cells[key] = cell.group(1) or self._a1(int(cell.group(2)), int(cell.group(3)))
                first = _split_top(expr, "&+")[0].strip().lower()
                if first != key:
                    self.flush(key)
                    parts, notes = self.eval(expr)
                    start = i
                else:
                    parts, notes = self.eval(expr, self_var=name)
                    start = self.vars[key]["start"] if key in self.vars else i
                lit_only = all(p[0] == "lit" for p in parts)
                text = "".join(p[1] for p in parts if p[0] == "lit")
                self.vars[key] = {"parts": parts, "notes": notes, "start": start, "executed": False,
                                  "fragment": lit_only and bool(text.strip()) and bool(FRAGMENT_START.match(text))
                                  and not SQL_KEYWORD.match(text.strip())}
        for key in list(self.vars):
            self.flush(key)
        if cols:
            sheet = sorted(sheets)[0]
            for c in self.out:
                if c.kind == "VBA ADODB SQL" and not c.output_range:
                    c.output_range = f"{sheet} 열 {_columns(cols)}"
        return self.out

    @staticmethod
    def _a1(row: int, col: int) -> str:
        s = ""
        while col:
            col, r = divmod(col - 1, 26)
            s = chr(65 + r) + s
        return f"{s}{row}"


def find_sql(module: str, source: str) -> list[Connection]:
    lines = _logical_lines(source)
    literals = re.findall(r'"((?:[^"]|"")*)"', source)
    module_target = _target(literals)
    out, cur, name = [], None, None
    for line in lines:
        if cur is None:
            m = PROC_START.match(line)
            if m:
                name, cur = m.group(1), []
            continue
        if PROC_END.match(line):
            out += _Proc(module, name, cur, module_target).run()
            cur = None
            continue
        cur.append(line)
    return out


def _selfcheck() -> None:
    flat = lambda s: " ".join(s.split())
    mmf = '''Sub connect_open()
    connstr = "Driver={Oracle in " & conninfo & "};Dbq=testsrv;uid=u;PWD=p;"
    connobj.Open
End Sub
Sub MMF()
    s_ilja = Range("U4").Value
    connect_open
    Qstring = ""
    Qstring = Qstring + " select A.x from dw_t A "
    Qstring = Qstring + " where A.d = '" + s_ilja + "' "
    Set cn = connobj.Execute(Qstring, adCmdText)
    Cells(cur_row, 3).Value = fund
    Cells(cur_row, 6).Value = amt
End Sub'''
    [c] = find_sql("Module1", mmf)
    assert c.kind == "VBA ADODB SQL" and c.location == "VBA Module1.MMF"
    assert flat(c.sql) == "select A.x from dw_t A where A.d = #S_ILJA#"
    assert "따옴표 제거" in c.notes and c.inputs == "셀 U4 를 읽는 변수 s_ilja"
    assert c.target == "TESTSRV" and c.output_range == "ActiveSheet 열 3·6"

    # test_reassign_splits
    two = 'Sub P()\nq = "select 1 from a"\ncn.Execute q\nq = "select 2 from b"\ncn.Execute q\nEnd Sub'
    assert [flat(c.sql) for c in find_sql("M", two)] == ["select 1 from a", "select 2 from b"]
    # test_branch_flag (여러 줄 If 와 한 줄 If)
    br = 'Sub P()\nq = "select a from t"\nIf x Then\nq = q & " where k = 1"\nEnd If\ncn.Execute q\nEnd Sub'
    assert "조립 분기 있음" in find_sql("M", br)[0].notes
    one = 'Sub P()\nq = "select a from t"\nIf x Then q = q & " where k = 1"\ncn.Execute q\nEnd Sub'
    [c] = find_sql("M", one)
    assert flat(c.sql) == "select a from t where k = 1" and "조립 분기 있음" in c.notes
    # test_continuation_and_amp
    cont = 'Sub P()\nq = "select a " & _\n    "from t"\nrs.Open q, cn\nEnd Sub'
    assert flat(find_sql("M", cont)[0].sql) == "select a from t"
    # test_doubled_quote
    dq = 'Sub P()\nq = "select ""A"" from t"\ncn.Execute q\nEnd Sub'
    assert find_sql("M", dq)[0].sql == 'select "A" from t'
    # test_builtin_and_function_terms
    fn = 'Sub P()\nq = "select a" & vbCrLf & "from t where d = " & Format(d, "yyyymmdd")\ncn.Execute q\nEnd Sub'
    [c] = find_sql("M", fn)
    assert flat(c.sql) == "select a from t where d = #D#" and "함수 항 바인드" in c.notes
    # test_fragment_variable
    frag = 'Sub P()\nw = " where k = 1"\nq = "select a from t" & w\ncn.Execute q\nEnd Sub'
    assert flat(find_sql("M", frag)[0].sql) == "select a from t where k = 1"
    # test_unexecuted_sql
    [c] = find_sql("M", 'Sub P()\nq = "select a from t"\nRunSQL q\nEnd Sub')
    assert flat(c.sql) == "select a from t" and "실행 호출 없음" in c.notes
    # test_hangul_variables: 한글 변수도 추적한다
    kor = 'Sub P()\n일자 = Range("U4").Value\n쿼리 = "select a from t where d = \'" & 일자 & "\'"\ncn.Execute 쿼리\nEnd Sub'
    [c] = find_sql("M", kor)
    assert flat(c.sql) == "select a from t where d = #일자#" and c.inputs == "셀 U4 를 읽는 변수 일자"
    assert "함수 항 바인드" not in c.notes
    # test_querytable_array
    qt = '''Sub P()
With ActiveSheet.QueryTables.Add(Connection:="ODBC;DSN=x;DBQ=TESTSRV;", Destination:=Range("A1"))
.CommandText = Array("select a ", "from t")
.Refresh BackgroundQuery:=False
End With
End Sub'''
    [c] = find_sql("M", qt)
    assert c.kind == "VBA 쿼리 테이블 생성" and flat(c.sql) == "select a from t"
    assert c.target == "TESTSRV" and c.output_range == "ActiveSheet A1"
    # test_listobjects_add
    lo = 'Sub P()\nWith ws.ListObjects.Add(SourceType:=0, Source:="ODBC;DBQ=TESTSRV;", Destination:=Range("B2")).QueryTable\n.CommandText = "select b from u"\nEnd With\nEnd Sub'
    [c] = find_sql("M", lo)
    assert c.kind == "VBA 쿼리 테이블 생성" and c.output_range == "ws B2"


if __name__ == "__main__":
    _selfcheck()
    print("selfcheck ok")
