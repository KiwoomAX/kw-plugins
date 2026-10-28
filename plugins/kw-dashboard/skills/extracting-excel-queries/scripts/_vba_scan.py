"""VBA 모듈에서 SQL 과 파일 읽기·웹 호출·외부 프로그램 실행 연결을 찾는다."""
import re

from _model import Connection
from _vba import Module
from _vba_sql import PROC_END, PROC_START, _literal, _logical_lines, _split_top, find_sql

FILE_READ = (
    re.compile(r"^\s*Open\s+(.+?)\s+For\s+(?:Input|Binary|Random)\b", re.I),
    re.compile(r"\bWorkbooks\.Open\s*\(?\s*(.+)$", re.I),
    re.compile(r"\.OpenTextFile\s*\(\s*(.+)$", re.I),
    re.compile(r"\bGetOpenFilename\b()", re.I),
)
SHELL = (
    re.compile(r"\bShell\s*\(\s*(.+)$", re.I),
    re.compile(r"^\s*(?:Call\s+)?Shell\s+(.+)$", re.I),
    re.compile(r"(?<!Application)\.(?:Run|Exec)\b\s*\(?\s*(.+)$", re.I),
)
WEB_LIB = re.compile(r"XMLHTTP|WinHttp|URLDownloadToFile", re.I)
URL = re.compile(r'"(https?://[^"]+)"', re.I)
HTTP_OPEN = re.compile(r'\.Open\s*\(?\s*"(?:GET|POST|PUT|DELETE|HEAD|PATCH)"\s*,\s*(.+)$', re.I)


def _first_arg(text: str) -> str:
    arg = _split_top(text, ",")[0].strip().rstrip(")").strip()
    lit = _literal(arg)
    return lit if lit is not None else arg


def _procedures(source: str):
    cur, name = None, None
    for line in _logical_lines(source):
        if cur is None:
            m = PROC_START.match(line)
            if m:
                name, cur = m.group(1), []
            continue
        if PROC_END.match(line):
            yield name, cur
            cur = None
            continue
        cur.append(line)


def _scan_proc(module: str, name: str, lines: list[str], web: bool) -> list[Connection]:
    found: dict[str, str] = {}
    for line in lines:
        for pat in FILE_READ:
            m = pat.search(line)
            if m and "VBA 파일 읽기" not in found:
                found["VBA 파일 읽기"] = _first_arg(m.group(1)) if m.group(1) else "파일 선택 대화상자"
        for pat in SHELL:
            m = pat.search(line)
            if m and "VBA 외부 프로그램 실행" not in found:
                found["VBA 외부 프로그램 실행"] = _first_arg(m.group(1))
        if web and "VBA 웹 호출" not in found:
            m = URL.search(line)
            if m:
                found["VBA 웹 호출"] = m.group(1)
            else:
                m = HTTP_OPEN.search(line)
                if m:  # URL 이 변수나 식이면 식을 그대로 남긴다
                    found["VBA 웹 호출"] = _first_arg(m.group(1))
    return [Connection(kind=k, location=f"VBA {module}.{name}", target=t) for k, t in found.items()]


def scan_modules(mods: list[Module]) -> list[Connection]:
    out: list[Connection] = []
    for m in mods:
        out += find_sql(m.name, m.source)
        web = bool(WEB_LIB.search(m.source))
        for name, lines in _procedures(m.source):
            out += _scan_proc(m.name, name, lines, web)
    return out


def _selfcheck() -> None:
    M = lambda src: [Module("M", src, True)]
    kinds = lambda src: sorted(c.kind for c in scan_modules(M(src)))
    # test_specialfolders_not_shell
    assert kinds('Sub P()\nSet f = CreateObject("WScript.Shell").SpecialFolders\nOpen DataFile For Input As #1\nEnd Sub') == ["VBA 파일 읽기"]
    assert kinds('Sub P()\nShell("C:\\a.exe")\nEnd Sub') == ["VBA 외부 프로그램 실행"]
    assert kinds('Sub P()\nCreateObject("WScript.Shell").Run "b.bat"\nEnd Sub') == ["VBA 외부 프로그램 실행"]
    [c] = scan_modules(M('\' MSXML2.XMLHTTP\nSub P()\nh.Open "GET", "https://x.example/api", False\nEnd Sub'))
    assert c.kind == "VBA 웹 호출" and c.target == "https://x.example/api"
    assert kinds('Sub P()\nWorkbooks.Open "\\\\srv\\a.xlsx"\nEnd Sub') == ["VBA 파일 읽기"]
    # test_web_url_expression: URL 이 리터럴이 아니어도 행을 남긴다
    [c] = scan_modules(M('\' XMLHTTP\nSub P()\nh.Open "GET", baseUrl & "/api", False\nEnd Sub'))
    assert c.kind == "VBA 웹 호출" and c.target == 'baseUrl & "/api"'
    # test_statement_shell: 괄호 없는 Shell 문장
    assert kinds('Sub P()\nShell "notepad.exe"\nEnd Sub') == ["VBA 외부 프로그램 실행"]


if __name__ == "__main__":
    _selfcheck()
    print("selfcheck ok")
