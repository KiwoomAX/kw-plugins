"""SQL 과 접속 문자열과 원본 경로에 드러난 근거로 출처 분류를 정한다. DB 에는 묻지 않는다.

값은 WINUS, WFS(우리펀드 서비스), 외부, 미판별이다. WINUS · WFS 를 가르는 이름은 대응표(source_rules)에서 읽는다.
"""
import re

from _model import READ_FAILURE_KINDS, Connection

DB_LINK = re.compile(r"\b[\w$#]+(?:\.[\w$#]+)?@([A-Za-z][\w.]*)")
SCHEMA = re.compile(r"\b([A-Za-z][\w$#]*)\.[A-Za-z_가-힣]")
EXTERNAL = {"외부 통합문서 링크", "DDE 링크", "VBA 웹 호출", "수식 외부 함수"}


def classify(c: Connection, win_path: str, rules: dict | None = None) -> str:
    if rules is None:
        from source_rules import load_rules
        rules = load_rules()[0]
    if c.kind in READ_FAILURE_KINDS:
        return ""
    links = [m.upper() for m in DB_LINK.findall(c.sql or "")]
    if any(rules["links"].get(name) == "WFS" for link in links for name in rules["links"] if link.startswith(name)):
        return "WFS"
    if c.kind == "VBA 파일 읽기" and any(v == "WFS" and f"\\{name}\\" in f"\\{win_path.upper()}\\"
                                        for name, v in rules["paths"].items()):
        return "WFS"
    target = c.target.upper()
    schemas = {m.upper() for m in SCHEMA.findall(c.sql or "")}
    if not links and (any(v == "WINUS" and name in target for name, v in rules["servers"].items())
                      or any(rules["schemas"].get(s) == "WINUS" for s in schemas)):
        return "WINUS"
    if c.kind in EXTERNAL:
        return "외부"
    return "미판별"


def _selfcheck() -> None:
    rules = {"servers": {"TESTSRV": "WINUS"}, "schemas": {"SCHEMA_A": "WINUS", "SCHEMA_B": "WINUS"},
             "links": {"TESTLINK": "WFS"}, "paths": {"FORM_FOLDER": "WFS"}}
    C = lambda **k: Connection(kind=k.pop("kind", "VBA ADODB SQL"), location="x", **k)
    assert classify(C(sql="select * from A@TESTLINK3", target="TESTSRV"), r"C:\a.xls", rules) == "WFS"
    assert classify(C(kind="VBA 파일 읽기"), r"C:\FORM_FOLDER\f.xls", rules) == "WFS"
    assert classify(C(sql="select 1 from t", target="TESTSRV"), r"C:\a.xls", rules) == "WINUS"
    assert classify(C(sql="select * from A@OTHER", target="TESTSRV"), r"C:\a.xls", rules) == "미판별"
    assert classify(C(kind="외부 통합문서 링크"), r"C:\a.xls", rules) == "외부"
    assert classify(C(kind="VBA 외부 프로그램 실행"), r"C:\a.xls", rules) == "미판별"
    assert classify(C(kind="처리 오류"), r"C:\a.xls", rules) == ""
    # test_winus_schema: 접속 대상을 몰라도 WINUS 스키마 객체를 읽으면 WINUS
    assert classify(C(sql="select * from schema_a.DW_T a"), r"C:\a.xls", rules) == "WINUS"
    assert classify(C(sql="select * from SCHEMA_B.V_X"), r"C:\a.xls", rules) == "WINUS"
    assert classify(C(sql="select * from SCHEMA_A.T, B.X@TESTLINK3"), r"C:\a.xls", rules) == "WFS"
    # test_empty_rules: 대응표가 비면 DB 연결은 미판별
    empty = {"servers": {}, "schemas": {}, "links": {}, "paths": {}}
    assert classify(C(sql="select * from SCHEMA_A.T", target="TESTSRV"), r"C:\a.xls", empty) == "미판별"


if __name__ == "__main__":
    _selfcheck()
    print("selfcheck ok")
