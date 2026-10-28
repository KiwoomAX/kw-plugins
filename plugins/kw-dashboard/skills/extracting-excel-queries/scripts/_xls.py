"""OLE 형식(.xls) 엑셀의 BIFF 레코드와 VBA 에서 외부 데이터 연결을 찾는다."""
import pathlib
import struct

from _model import Connection
from _vba import Module, VbaReadError, has_project_password, modules
from _vba_scan import scan_modules

# MS-XLS 레코드 번호. 연결 레코드는 원본 하나에 종류마다 행 하나를 만든다.
SUPBOOK, EXTERNNAME, FILEPASS = 0x01AE, 0x0023, 0x002F
# 웹 쿼리는 별도 레코드가 아니라 DbOrParamQry 의 종류와 DBQueryExt 로 나타난다고 보고 따로 두지 않았다
# (lens-grounding 이 기억한 MS-XLS 2.3 목록 기준, 명세 원문은 이 세션에서 열지 못했다).
CONNECTION_RECORDS = {0x0876: "DConn", 0x01AD: "Qsi", 0x00DC: "DbOrParamQry", 0x0803: "DBQueryExt", 0x0805: "TxtQry"}
VBA_ROOT = ["_VBA_PROJECT_CUR", "VBA"]


def _records(stream: bytes):
    i = 0
    while i + 4 <= len(stream):
        rid, ln = struct.unpack_from("<HH", stream, i)
        yield rid, stream[i + 4:i + 4 + ln]
        i += 4 + ln


def _xl_string(body: bytes, i: int, cch: int) -> str:
    """XLUnicodeStringNoCch: fHighByte 1바이트 뒤에 글자."""
    if i >= len(body):
        return ""
    high = body[i] & 1
    raw = body[i + 1:i + 1 + cch * (2 if high else 1)]
    return raw.decode("utf-16-le" if high else "latin-1", "replace")


def _decode_path(p: str) -> str:
    """MS-XLS VirtualPath 의 제어 문자를 경로 구분자로 바꾼다. 맨 앞 0x01 은 인코딩된 경로라는 표시다."""
    if p.startswith("\x01"):
        p = p[1:]
    out, i = "", 0
    while i < len(p):
        ch = p[i]
        if ch == "\x01" and i + 1 < len(p):
            nxt = p[i + 1]
            if nxt == "@":
                out += "\\\\"
            elif nxt.isalpha():
                out += nxt + ":\\"
            else:
                out += nxt
            i += 2
            continue
        out += {"\x02": "\\", "\x03": "\\", "\x04": "..\\"}.get(ch, ch if ord(ch) >= 32 else "")
        i += 1
    return out


def scan_biff(stream: bytes) -> list[Connection]:
    out: list[Connection] = []
    kind = None
    seen_records = set()
    for rid, body in _records(stream):
        if rid == SUPBOOK and len(body) >= 4:
            ctab, cch = struct.unpack_from("<HH", body, 0)
            if cch == 0x0401:
                kind = "self"
            elif cch == 0x3A01:
                kind = "addin"
            else:
                path = _xl_string(body, 4, cch)
                if ctab == 0:
                    kind = "dde"
                    out.append(Connection(kind="DDE 링크", location="SupBook", target=path.replace("\x03", "|")))
                else:
                    kind = "external"
                    out.append(Connection(kind="외부 통합문서 링크", location="SupBook", target=_decode_path(path)))
        elif rid == EXTERNNAME and kind == "addin" and len(body) >= 8:
            name = _xl_string(body, 7, body[6])
            out.append(Connection(kind="수식 외부 함수", location=f"추가 기능 {name}"))
        elif rid in CONNECTION_RECORDS and rid not in seen_records:
            seen_records.add(rid)
            out.append(Connection(kind=".xls 연결 레코드", location=CONNECTION_RECORDS[rid], notes=["추출 미지원"]))
    return out


def _workbook_stream(ole) -> bytes:
    return ole.openstream("Workbook" if ole.exists("Workbook") else "Book").read()


def is_encrypted(ole) -> bool:
    """EncryptedPackage 스트림이나 FILEPASS 레코드가 있으면 참이다.

    FILEPASS 가 있어도 기본 암호(VelvetSweatshop)로 암호 없이 열리는 파일은 구분하지 않는다.
    """
    if ole.exists("EncryptedPackage"):
        return True
    if not (ole.exists("Workbook") or ole.exists("Book")):
        return False
    for rid, _ in _records(_workbook_stream(ole)):
        if rid == FILEPASS:
            return True
        if rid == 0x0085:  # BoundSheet8 에 닿으면 FILEPASS 가 나올 자리를 지났다
            return False
    return False


def scan_ole(path: pathlib.Path) -> tuple[list[Connection], list[Module]]:
    import olefile
    with olefile.OleFileIO(str(path)) as ole:
        out = scan_biff(_workbook_stream(ole))
        mods: list[Module] = []
        if ole.exists("/".join(VBA_ROOT)):
            try:
                mods = modules(ole, VBA_ROOT)
                out += scan_modules(mods)
            except VbaReadError as e:  # 매크로 연결이 빠졌다는 사실을 결과에 남긴다
                out.append(Connection(kind="VBA 읽기 실패", location="VBA 프로젝트", notes=[str(e)]))
            if has_project_password(ole, VBA_ROOT):
                for c in out:
                    c.notes.append("VBA 프로젝트 암호")
    return out, mods


def _selfcheck() -> None:
    rec = lambda rid, body: struct.pack("<HH", rid, len(body)) + body
    self_sb = rec(0x01AE, b"\x02\x00\x01\x04")
    addin_sb = rec(0x01AE, b"\x01\x00\x01\x3a")
    xn = rec(0x0023, b"\x00\x00\x00\x00\x00\x00\x03\x00BDP")
    ext_sb = rec(0x01AE, b"\x01\x00" + b"\x06\x00\x00" + b"\x01a.xls")
    dde_sb = rec(0x01AE, b"\x00\x00" + b"\x03\x00\x00" + b"DDE")
    dde_xn = rec(0x0023, b"\x10\x00" + b"\x00\x00\x00\x00" + b"\x05\x00" + b"TOPIC")
    assert scan_biff(self_sb) == []
    got = scan_biff(addin_sb + xn + ext_sb + rec(0x0876, b"\x00" * 8))
    assert [c.kind for c in got] == ["수식 외부 함수", "외부 통합문서 링크", ".xls 연결 레코드"]
    assert got[0].location == "추가 기능 BDP" and got[1].target == "a.xls"
    assert "추출 미지원" in got[2].notes
    assert [c.kind for c in scan_biff(dde_sb + dde_xn)] == ["DDE 링크"]


if __name__ == "__main__":
    _selfcheck()
    print("selfcheck ok")
