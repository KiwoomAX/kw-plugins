# extracting-excel-queries 시험. 각 모듈의 자체 시험과, 출처 대응표 · 설명기용 scan_file 을 본다.
#   uv run --no-project --with olefile --with oletools --with openpyxl --with pytest pytest tests/test_extracting_excel_queries.py
import importlib
import json
import os
import pathlib
import sys

import pytest

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "plugins/kw-dashboard/skills/extracting-excel-queries/scripts"
sys.path.insert(0, str(SCRIPTS))
import extract_queries  # noqa: E402
import source_rules  # noqa: E402
from _classify import classify  # noqa: E402
from _model import Connection  # noqa: E402
from _vba import Module  # noqa: E402

RULES = {"servers": {"TESTSRV": "WINUS"}, "schemas": {"SCHEMA_A": "WINUS"},
         "links": {"TESTLINK": "WFS"}, "paths": {"FORM_FOLDER": "WFS"}}
EMPTY = {"servers": {}, "schemas": {}, "links": {}, "paths": {}}


@pytest.mark.parametrize("mod", ["_classify", "_index", "_model", "_mquery", "_ooxml", "_secrets", "_vba",
                                 "_vba_scan", "_vba_sql", "_xls", "extract_queries"])
def test_module_selfcheck(mod):
    importlib.import_module(mod)._selfcheck()


def conn(**k):
    return Connection(kind=k.pop("kind", "ODBC 쿼리 테이블"), location="연결 q", **k)


def test_rules_label_winus_and_wfs():
    assert classify(conn(sql="select 1 from t", target="TESTSRV"), r"C:\a.xlsx", RULES) == "WINUS"
    assert classify(conn(sql="select * from SCHEMA_A.T1"), r"C:\a.xlsx", RULES) == "WINUS"
    assert classify(conn(sql="select * from T@TESTLINK3", target="TESTSRV"), r"C:\a.xlsx", RULES) == "WFS"
    assert classify(conn(kind="VBA 파일 읽기"), r"C:\FORM_FOLDER\a.xls", RULES) == "WFS"


def test_without_rules_db_connection_is_unknown():
    assert classify(conn(sql="select 1 from t", target="TESTSRV"), r"C:\a.xlsx", EMPTY) == "미판별"
    assert classify(conn(kind="외부 통합문서 링크"), r"C:\a.xlsx", EMPTY) == "외부"
    assert classify(conn(kind="처리 오류"), r"C:\a.xlsx", EMPTY) == ""


def test_load_rules_reads_file_or_reports_failure(tmp_path):
    path = tmp_path / "source_rules.json"
    path.write_bytes(b"\xef\xbb\xbf" + json.dumps(RULES).encode("utf-8"))   # 메모장 BOM 도 읽는다
    assert source_rules.load_rules(path) == (RULES, "읽음")
    assert source_rules.load_rules(tmp_path / "없음.json") == (EMPTY, "읽기 실패")


def fake_scan(conns, sources):
    return lambda path: (conns, [Module(name=f"M{i}", source=s, standard=True) for i, s in enumerate(sources)])


def test_scan_file_classifies_and_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(extract_queries, "_scan", fake_scan([conn(sql="select 1 from t", target="TESTSRV",
                                                                  output_range="S A1:B3")], []))
    monkeypatch.setattr(extract_queries, "load_rules", lambda: (RULES, "읽음"))
    conns = extract_queries.scan_file(tmp_path / "a.xlsx")
    assert [(c.origin, c.output_range) for c in conns] == [("WINUS", "S A1:B3")]
    assert list(tmp_path.iterdir()) == []


def test_scan_file_turns_leaked_secret_into_error_row(tmp_path, monkeypatch):
    leaked = conn(kind="VBA ADODB SQL", sql="select * from t where k = 'pw1secret'", target="TESTSRV")
    monkeypatch.setattr(extract_queries, "_scan", fake_scan([leaked], ['c = "DSN=x;UID=testuser;PWD=pw1secret;"']))
    monkeypatch.setattr(extract_queries, "load_rules", lambda: (EMPTY, "읽기 실패"))
    conns = extract_queries.scan_file(tmp_path / "a.xlsm")
    assert [c.kind for c in conns] == ["처리 오류"]
    assert "pw1secret" not in str(conns) and "testuser" not in str(conns)


def test_main_reports_rules_state_first(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(extract_queries, "load_rules", lambda: (EMPTY, "읽기 실패"))
    (tmp_path / "in").mkdir()
    assert extract_queries.main([str(tmp_path / "in"), "--out", str(tmp_path / "out")]) == 0
    assert capsys.readouterr().out.splitlines()[0] == "출처 대응표: 읽기 실패"


def test_rule_values_are_upper_cased(tmp_path):
    path = tmp_path / "r.json"
    path.write_text('{"schemas": {"schema_a": "winus"}}', encoding="utf-8")
    rules, _ = source_rules.load_rules(path)
    assert rules["schemas"] == {"SCHEMA_A": "WINUS"}


# 매크로 표본 경로는 사용자 PC 마다 달라 환경 변수로 받는다. 없으면 건너뛴다
LOCKED_XLS = pathlib.Path(os.environ.get("EXTRACT_LOCKED_XLS", "/없음"))
DRAMATIC = pathlib.Path(os.environ.get("EXPLAIN_DRAMATIC_XLSM", "/없음"))


def sample_modules(path):
    import io
    import zipfile
    import olefile
    import _vba
    if path.suffix.lower() == ".xlsm":
        with zipfile.ZipFile(path) as z:
            ole, root = olefile.OleFileIO(io.BytesIO(z.read("xl/vbaProject.bin"))), ["VBA"]
    else:
        ole, root = olefile.OleFileIO(str(path)), ["_VBA_PROJECT_CUR", "VBA"]
    return ole, root, _vba.modules(ole, root)


@pytest.mark.skipif(not LOCKED_XLS.exists(), reason="EXTRACT_LOCKED_XLS 없음")
def test_locked_project_modules_are_read():
    import _vba
    ole, root, mods = sample_modules(LOCKED_XLS)
    assert _vba.has_project_password(ole, root)
    assert sorted((m.name, m.standard) for m in mods) == [("Module1", True), ("Sheet1", False), ("Sheet2", False), ("ThisWorkbook", False)]
    assert all(m.source.startswith("Attribute VB_Name") for m in mods) and "Sub " in next(m.source for m in mods if m.name == "Module1")


@pytest.mark.skipif(not DRAMATIC.exists(), reason="EXPLAIN_DRAMATIC_XLSM 없음")
def test_open_project_modules_are_read():
    _, _, mods = sample_modules(DRAMATIC)
    assert len(mods) == 18 and sum(m.standard for m in mods) == 10


def test_main_says_oletools_is_needed(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "oletools", None)  # import 가 실패하게 한다
    assert extract_queries.main(["x.xlsx"]) == 1
    assert "oletools" in capsys.readouterr().out
