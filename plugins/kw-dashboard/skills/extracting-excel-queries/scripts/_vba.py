"""VBA 프로젝트(MS-OVBA)에서 모듈 소스와 암호 여부를 읽는다. 프로젝트 암호와 무관하게 읽힌다.

소스 읽기(압축 풀기와 모듈 목록 해석)는 공개 라이브러리 oletools 의 olevba 가 맡는다. 이 모듈은 결과를 Module 로 바꾸고,
oletools 에 없는 프로젝트 암호 여부 판정만 직접 한다.
"""
import re
from dataclasses import dataclass


@dataclass
class Module:
    name: str
    source: str
    standard: bool  # 표준 모듈(.bas)이면 참, 시트 · 통합 문서 · 폼 · 클래스 모듈이면 거짓


def _paths(root: list[str]) -> tuple[str, str, str]:
    """VBA 폴더 경로(예: ["_VBA_PROJECT_CUR", "VBA"])를 olevba 가 받는 (VBA 프로젝트 폴더, PROJECT 스트림, dir 스트림) 경로로 바꾼다."""
    base = "".join(p + "/" for p in root[:-1])
    return base, base + "PROJECT", base + "/".join([root[-1], "dir"])


class VbaReadError(Exception):
    """VBA 프로젝트가 있는데 소스를 읽지 못했다. 호출한 쪽은 「VBA 읽기 실패」 행을 남기고 추출을 이어 간다."""


def modules(ole, root: list[str]) -> list[Module]:
    """olefile 로 연 VBA 프로젝트의 모듈 목록. 읽지 못하면 VbaReadError 를 낸다."""
    from oletools.olevba import VBA_Project
    base, project, dir_path = _paths(root)
    try:
        vba = VBA_Project(ole, base, project, dir_path, relaxed=True)
        vba.parse_project_stream()
        found = list(vba.parse_modules())
    except Exception as e:  # olevba 는 깨진 프로젝트에서 여러 종류의 예외를 낸다
        raise VbaReadError(type(e).__name__) from e
    out = []
    for _, filename, code in found:
        source = code.decode("cp949", "replace") if isinstance(code, bytes) else code
        out.append(Module(filename.rsplit(".", 1)[0], source, filename.lower().endswith(".bas")))
    return out


def has_project_password(ole, root: list[str]) -> bool:
    """PROJECT 스트림의 DPB hex 길이로 판정한다.

    MS-OVBA 2.3.1.16·2.4.3 기준으로 암호가 없으면 0x00 한 바이트를 암호화해 16~22자,
    암호가 있으면 29바이트 해시를 암호화해 72~78자다(2026-10-16 사례 78자). 경계는 그 사이의 40 이다.
    """
    path = root[:-1] + ["PROJECT"]
    if not ole.exists("/".join(path)):
        return False
    m = re.search(rb'DPB="([0-9A-Fa-f]*)"', ole.openstream(path).read())
    return bool(m) and len(m.group(1)) > 40


def _selfcheck() -> None:
    assert _paths(["VBA"]) == ("", "PROJECT", "VBA/dir")
    assert _paths(["_VBA_PROJECT_CUR", "VBA"]) == ("_VBA_PROJECT_CUR/", "_VBA_PROJECT_CUR/PROJECT", "_VBA_PROJECT_CUR/VBA/dir")

    class Fake:  # PROJECT 스트림만 있는 olefile 대역
        def __init__(self, dpb):
            self.data = f'ID="{{x}}"\r\nDPB="{dpb}"\r\n'.encode()

        def exists(self, path):
            return path == "PROJECT"

        def openstream(self, path):
            import io
            return io.BytesIO(self.data)

    assert not has_project_password(Fake("A" * 18), ["VBA"]) and has_project_password(Fake("A" * 78), ["VBA"])
    try:  # dir 스트림이 없으면 읽기 실패다
        modules(Fake("A" * 18), ["VBA"])
        raise AssertionError("VbaReadError 를 내야 한다")
    except VbaReadError:
        pass


if __name__ == "__main__":
    _selfcheck()
    print("selfcheck ok")
