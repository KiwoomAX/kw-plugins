"""압축 형식(.xlsx·.xlsm·.xlsb) 엑셀에서 외부 데이터 연결을 찾는다."""
import html
import io
import pathlib
import posixpath
import re
import tempfile
import zipfile

from _model import Connection
from _mquery import decode_mashup, scan_m
from _vba import Module, has_project_password, modules
from _vba_scan import scan_modules
from _vba_sql import _target

CONN_TYPES = {"1": "ODBC 쿼리 테이블", "5": "OLE DB 쿼리 테이블"}
BIN_PARTS = re.compile(r"^xl/(connections\.bin|externalLinks/[^/]+\.bin|queryTables/[^/]+\.bin)$")
CELL = re.compile(r'<c\b([^>]*?)(?:/>|>(.*?)</c>)', re.S)
CELL_FORMULA = re.compile(r"<f\b[^>]*>([^<]*)</f>")
EXTERNAL_FN = re.compile(r"_xll\.([\w.]+)\(|\b(RTD|WEBSERVICE|CUBE[A-Z]+)\(")
EXTERNAL_HINT = re.compile(rb"_xll\.|RTD\(|WEBSERVICE\(|CUBE[A-Z]+\(")


def _attr(tag: str, name: str) -> str:
    m = re.search(rf'\b{name}="([^"]*)"', tag)
    return html.unescape(m.group(1)) if m else ""


def _rels(z: zipfile.ZipFile, part: str) -> dict[str, str]:
    """part 의 관계 파일을 읽어 Id → 절대 부품 경로(또는 외부 Target) 를 돌려준다."""
    d, f = posixpath.split(part)
    rel = f"{d}/_rels/{f}.rels"
    if rel not in z.namelist():
        return {}
    out = {}
    for tag in re.findall(rb"<Relationship\b[^>]*>", z.read(rel)):
        tag = tag.decode("utf-8", "replace")
        target = _attr(tag, "Target")
        if _attr(tag, "TargetMode") != "External" and not re.match(r"^\w+:", target):
            target = posixpath.normpath(posixpath.join(d, target)).lstrip("/")
        out[_attr(tag, "Id") or target] = target
    return out


def _sheet_names(z: zipfile.ZipFile) -> dict[str, str]:
    """시트 부품 경로 → 표시 이름."""
    if "xl/workbook.xml" not in z.namelist():
        return {}
    rels = _rels(z, "xl/workbook.xml")
    out = {}
    for tag in re.findall(r"<sheet\b[^>]*>", z.read("xl/workbook.xml").decode("utf-8", "replace")):
        rid = _attr(tag, "r:id")
        if rid in rels:
            out[rels[rid]] = _attr(tag, "name")
    return out


def _result_ranges(z: zipfile.ZipFile, names: dict[str, str]) -> dict[str, str]:
    """연결 id → '시트 범위'. 시트 → 표 → 쿼리 테이블 → connectionId 관계를 따라간다."""
    out = {}
    for sheet in [n for n in z.namelist() if re.match(r"^xl/worksheets/[^/]+\.xml$", n)]:
        for table in _rels(z, sheet).values():
            if not table.startswith("xl/tables/") or table not in z.namelist():
                continue
            ref = _attr(z.read(table).decode("utf-8", "replace").split(">", 2)[1], "ref")
            for qt in _rels(z, table).values():
                if qt.startswith("xl/queryTables/") and qt in z.namelist():
                    cid = _attr(z.read(qt).decode("utf-8", "replace"), "connectionId")
                    out[cid] = f"{names.get(sheet, posixpath.splitext(posixpath.basename(sheet))[0])} {ref}".strip()
    return out


def _connections(z: zipfile.ZipFile, ranges: dict[str, str], pq_ranges: dict[str, str]) -> list[Connection]:
    """연결마다 행을 만든다. Power Query 결과를 불러오는 Mashup 연결은 행 대신 pq_ranges 에 결과 범위를 적는다."""
    out = []
    text = z.read("xl/connections.xml").decode("utf-8", "replace")
    for block in re.findall(r"<connection\b.*?(?:</connection>|/>)", text, re.S):
        head = block.split(">", 1)[0]
        name, ctype = _attr(head, "name"), _attr(head, "type")
        db = re.search(r"<dbPr\b[^>]*>", block)
        conn = _attr(db.group(0), "connection") if db else ""
        cmd = _attr(db.group(0), "command") if db else ""
        if "Microsoft.Mashup" in conn:
            loc = re.search(r"Location=([^;]+)", conn)
            if loc:
                pq_ranges[loc.group(1).strip().strip('"')] = ranges.get(_attr(head, "id"), "")
            continue
        notes = ["열 때 새로 고침"] if _attr(head, "refreshOnLoad") in ("1", "true") else []
        kind = CONN_TYPES.get(ctype)
        if kind is None:
            kind = "기타 연결 흔적"
            notes.append("추출 미지원")
        out.append(Connection(kind=kind, location=f"연결 {name}", sql=cmd or None, target=_target([conn]),
                              output_range=ranges.get(_attr(head, "id"), ""), notes=notes))
    return out


def _external_links(z: zipfile.ZipFile) -> list[Connection]:
    out = []
    for part in sorted(n for n in z.namelist() if re.match(r"^xl/externalLinks/externalLink\d+\.xml$", n)):
        xml = z.read(part).decode("utf-8", "replace")
        dde = re.search(r"<ddeLink\b[^>]*>", xml)
        if dde:
            out.append(Connection(kind="DDE 링크", location=posixpath.basename(part),
                                  target=f"{_attr(dde.group(0), 'ddeService')}|{_attr(dde.group(0), 'ddeTopic')}"))
            continue
        targets = list(_rels(z, part).values())
        out.append(Connection(kind="외부 통합문서 링크", location=posixpath.basename(part),
                              target=targets[0] if targets else ""))
    return out


def _formulas(z: zipfile.ZipFile, names: dict[str, str]) -> list[Connection]:
    out = []
    for sheet in sorted(n for n in z.namelist() if re.match(r"^xl/worksheets/[^/]+\.xml$", n)):
        raw = z.read(sheet)
        if not EXTERNAL_HINT.search(raw):
            continue
        label = names.get(sheet, posixpath.splitext(posixpath.basename(sheet))[0])
        for attrs, body in CELL.findall(raw.decode("utf-8", "replace")):
            f = CELL_FORMULA.search(body or "")
            if not f:
                continue
            cell = _attr(attrs, "r")
            for xll, builtin in EXTERNAL_FN.findall(html.unescape(f.group(1))):
                out.append(Connection(kind="수식 외부 함수", location=f"{label} {cell} {xll or builtin}"))
    return out


def scan_zip(path: pathlib.Path) -> tuple[list[Connection], list[Module]]:
    out: list[Connection] = []
    mods: list[Module] = []
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        sheet_names = _sheet_names(z)
        pq_ranges: dict[str, str] = {}
        if "xl/connections.xml" in names:
            out += _connections(z, _result_ranges(z, sheet_names), pq_ranges)
        out += _external_links(z)
        for n in names:
            if re.match(r"^customXml/item\d+\.xml$", n) and any(m in z.read(n)[:4000] for m in (b"DataMashup", "DataMashup".encode("utf-16-le"))):
                code = decode_mashup(z.read(n))
                if code is None:
                    out.append(Connection(kind="Power Query", location=n, notes=["추출 미지원"]))
                    continue
                for c in scan_m(code):
                    c.output_range = pq_ranges.get(c.location.removeprefix("Power Query "), "")
                    out.append(c)
            elif BIN_PARTS.match(n):
                out.append(Connection(kind="기타 연결 흔적", location=n, notes=["추출 미지원"]))
            elif n.startswith("xl/pivotCache/pivotCacheDefinition") and re.search(rb'cacheSource [^>]*type="external"', z.read(n)):
                out.append(Connection(kind="기타 연결 흔적", location=n, notes=["추출 미지원"]))
        for prefix in ("xl/model/", "xl/xmlMaps.xml", "xl/richData/"):
            if any(n.startswith(prefix) for n in names):
                out.append(Connection(kind="기타 연결 흔적", location=prefix.rstrip("/"), notes=["추출 미지원"]))
        out += _formulas(z, sheet_names)
        if "xl/vbaProject.bin" in names:
            import olefile
            ole = olefile.OleFileIO(io.BytesIO(z.read("xl/vbaProject.bin")))
            mods = modules(ole, ["VBA"])
            vba = scan_modules(mods)
            if has_project_password(ole, ["VBA"]):
                for c in out + vba:
                    c.notes.append("VBA 프로젝트 암호")
            out += vba
    return out, mods


def _selfcheck() -> None:
    def make(parts):
        p = pathlib.Path(tempfile.mkdtemp(), "t.xlsx")
        with zipfile.ZipFile(p, "w") as z:
            for k, v in parts.items():
                z.writestr(k, v)
        return p
    conns = ('<connections xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
             '<connection id="1" name="testsrv_Query" type="1" refreshOnLoad="1">'
             '<dbPr connection="DSN=x;DBQ=TESTSRV;UID=u;PWD=p;" command="select a from t"/></connection></connections>')
    cs, _ = scan_zip(make({"xl/connections.xml": conns,
                           "xl/externalLinks/externalLink1.xml": "<externalLink><externalBook/></externalLink>",
                           "xl/externalLinks/_rels/externalLink1.xml.rels": '<Relationships><Relationship Target="file:///C:/a.xls"/></Relationships>',
                           "customXml/item1.xml": "<DataMashup>AAA</DataMashup>",
                           "xl/worksheets/sheet1.xml": '<worksheet><sheetData><row><c r="B2"><f>_xll.BDP("A","PX")</f></c></row></sheetData></worksheet>'}))
    by = {c.kind: c for c in cs}
    q = by["ODBC 쿼리 테이블"]
    assert q.sql == "select a from t" and q.target == "TESTSRV" and q.location == "연결 testsrv_Query"
    assert "열 때 새로 고침" in q.notes
    assert by["외부 통합문서 링크"].target == "file:///C:/a.xls"
    assert "추출 미지원" in by["Power Query"].notes
    assert by["수식 외부 함수"].location == "sheet1 B2 BDP"
    # test_power_query_sql: Mashup 껍데기 연결 대신 M 코드 안의 SQL 을 행으로 낸다
    from _mquery import _mashup_xml
    m = 'section Section1;\nshared 국내쿼리 = let\n  Q = "select a from SCHEMA_A.T",\n  S = Odbc.Query("dbq=TESTSRV", Q)\nin S;'
    mash = ('<connections xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<connection id="2" name="쿼리 - 국내쿼리" type="5"><dbPr connection="Provider=Microsoft.Mashup.OleDb.1;'
            'Data Source=$Workbook$;Location=국내쿼리" command="SELECT * FROM [국내쿼리]"/></connection></connections>')
    cs, _ = scan_zip(make({"xl/connections.xml": mash, "customXml/item1.xml": _mashup_xml(m)}))
    assert [(c.kind, c.location, c.sql, c.target) for c in cs] == [("Power Query", "Power Query 국내쿼리", "select a from SCHEMA_A.T", "TESTSRV")]
    cs, _ = scan_zip(make({"xl/connections.bin": b"\x00"}))
    assert [c.kind for c in cs] == ["기타 연결 흔적"] and "추출 미지원" in cs[0].notes


if __name__ == "__main__":
    _selfcheck()
    print("selfcheck ok")
