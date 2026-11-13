"""네트워크 경로의 파일을 FileGateway 로 받아 보고, 로컬에서 읽은 파일과 크기·확인값을 비교한다.

네트워크 경로(\\\\서버\\공유 이름\\폴더\\파일 또는 Z:\\폴더\\파일)를 공유 이름과 상대 경로로 나눈다.
FileGateway 는 공유 이름을 그대로 받는다. 이 스크립트와 스킬은 공유 이름 목록을 포함하지 않는다.

접근 키 확인은 같은 플러그인의 searching-winus 스크립트(fetch_manifest)를 그대로 쓴다.
두 스킬이 같은 키와 같은 안내를 쓰게 하기 위해서다.

받은 파일은 저장하지 않는다. 어떤 요청도 자동으로 다시 보내지 않는다.

종료 코드: 0 받기 성공(비교까지 했으면 일치), 1 거절·불일치·중단.

표준 라이브러리만 쓴다.

사용: python scripts/filegw.py check --path "<네트워크 경로>"
"""
import argparse
import hashlib
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "searching-winus" / "scripts"))
import fetch_manifest as gw  # noqa: E402

FILE_GATEWAY = os.environ.get("FILE_GATEWAY_URL", "http://192.7.9.45:9009")
CHUNK = 1024 * 1024

# FileGateway 는 없는 파일, 권한 없음, 링크를 거친 경로를 모두 404 로 답한다.
NEXT_BY_STATUS = {
    400: "FileGateway 가 받지 않는 경로 형식. SKILL.md 「받지 않는 경로」의 조건에 해당하는지 확인",
    404: "FileGateway 에 연결되지 않은 공유, 없는 파일·폴더, 또는 이 키의 역할에 권한이 없음. FileGateway 는 이를 구분해 알려 주지 않음",
    503: "공유 연결 이상이거나 FileGateway 가 권한 정보를 읽지 못함. 잠시 뒤 사용자가 다시 요청",
}


class Stop(Exception):
    """사용자에게 그대로 전하고 멈출 내용."""


def drive_remote(drive: str) -> str:
    """Z: 같은 드라이브 문자에 연결된 네트워크 경로(\\\\서버\\공유 이름[\\폴더]). 연결이 없거나 Windows 가 아니면 빈 문자열."""
    if sys.platform != "win32":
        return ""
    import ctypes
    buffer, size = ctypes.create_unicode_buffer(1024), ctypes.c_ulong(1024)
    return buffer.value if ctypes.windll.mpr.WNetGetConnectionW(drive, buffer, ctypes.byref(size)) == 0 else ""


def resolve(network_path: str, remote_of=drive_remote) -> tuple[str, str, str]:
    """네트워크 경로를 (서버, 공유 이름, 상대 경로)로 나눈다."""
    path = network_path.strip().replace("/", "\\")
    if len(path) >= 2 and path[1] == ":":
        remote = remote_of(path[:2].upper())
        if not remote:
            raise Stop(f"{path[:2].upper()} 드라이브에 연결된 네트워크 경로를 찾지 못함\n"
                       "- 조치: \\\\서버\\공유 이름\\폴더\\파일 형태의 경로를 사용자에게 물음")
        path = remote.rstrip("\\") + "\\" + path[2:].lstrip("\\")
    if not path.startswith("\\\\"):
        raise Stop(f"네트워크 경로가 아님: {network_path}\n- 조치: \\\\서버\\공유 이름\\폴더\\파일 또는 Z:\\폴더\\파일 형태로 받음")
    parts = [p for p in path[2:].split("\\") if p]
    if len(parts) < 3:
        raise Stop(f"파일까지 적힌 경로가 아님: {network_path}\n- FileGateway 는 폴더 목록을 주지 않고 파일 하나만 내려 줌")
    return parts[0], parts[1], "/".join(parts[2:])


def measure(chunks) -> tuple[int, str]:
    """(크기, 확인값). 확인값은 SHA-256 이다."""
    size, digest = 0, hashlib.sha256()
    for chunk in chunks:
        size += len(chunk)
        digest.update(chunk)
    return size, digest.hexdigest()


def read_chunks(stream):
    while chunk := stream.read(CHUNK):
        yield chunk


def download(share: str, relative: str) -> tuple[int, str, int | None]:
    """FileGateway 에서 받아 (받은 크기, 확인값, Content-Length)를 돌려준다. 거절은 Stop 이나 SystemExit 로 올린다."""
    key = gw.access_key()
    url = (f"{FILE_GATEWAY}/api/files/{urllib.parse.quote(share, safe='')}"
           f"?path={urllib.parse.quote(relative, safe='')}")
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"})
    try:
        with gw.OPENER.open(request, timeout=60) as r:
            declared = r.headers.get("Content-Length")
            size, digest = measure(read_chunks(r))
            return size, digest, int(declared) if declared else None
    except urllib.error.HTTPError as e:
        if e.code == 401:
            registry = gw.registry_key()
            if registry and registry != key:
                raise gw.not_applied("새 접근 키가 설정됨: 이 창에는 이전 키가 남아 FileGateway 신원 거절(401)")
            raise gw.key_refused("FileGateway 신원 거절(401)")
        if 300 <= e.code < 400:
            raise Stop(f"다른 호스트로의 리다이렉트 거절: {e.headers.get('Location')}"
                       "\n- 접근 키를 그 주소로 보내지 않음\n- 조치: FILE_GATEWAY_URL 확인")
        raise Stop(f"FileGateway 거절({e.code})\n- {NEXT_BY_STATUS.get(e.code, '다시 시도하지 않고 사용자에게 알림')}")
    except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
        raise Stop(f"FileGateway 에 연결하지 못함: {e}\n- 조치: 사내망인지와 FILE_GATEWAY_URL({FILE_GATEWAY}) 확인")


def local_measure(network_path: str) -> tuple[int, str] | None:
    """이 PC 에서 그 경로의 파일을 읽은 (크기, 확인값). 읽지 못하면 None."""
    try:
        with open(network_path.strip(), "rb") as f:
            return measure(read_chunks(f))
    except OSError:
        return None


def check(network_path: str, fetch=download, local=local_measure, exists=os.path.isfile) -> list[str]:
    host, share, relative = resolve(network_path)
    lines = [f"서버: {host}", f"공유 이름: {share}", f"상대 경로: {relative}"]
    try:
        size, digest, declared = fetch(share, relative)
    except Stop as e:
        if "거절(404)" not in str(e):
            raise
        # 404 는 원인을 알려 주지 않으므로, 이 PC 에서 그 파일이 열리는지로 경로 오류와 공유 연결·권한 문제를 구분한다.
        seen = ("이 PC 에서는 그 파일이 열림: 경로는 맞고, 공유 연결이나 권한 문제" if exists(network_path.strip())
                else "이 PC 에서도 그 파일이 열리지 않음: 경로가 틀렸거나 이 터미널이 네트워크 드라이브를 열지 못함")
        raise Stop(f"{e}\n- {seen}")
    lines.append(f"FileGateway: {size:,}바이트, 확인값 {digest[:16]}")
    if declared is not None and declared != size:
        raise Stop("\n".join(lines) + f"\n받은 크기가 Content-Length({declared:,})와 다름\n- 전송 중에 파일이 바뀐 것. 사용자가 다시 요청")
    mine = local(network_path)
    if mine is None:
        lines.append("로컬 비교: 하지 못함. 이 PC 에서 그 경로의 파일을 읽지 못함")
        lines.append("- 받은 파일이 사용자가 가리킨 파일인지는 확인되지 않음. 그 사실을 사용자에게 알림")
    elif mine == (size, digest):
        lines.append("로컬 비교: 일치. 공유 이름과 상대 경로, 이 키의 권한, 전송이 모두 맞음")
    else:
        raise Stop("\n".join(lines) + f"\n로컬: {mine[0]:,}바이트, 확인값 {mine[1][:16]}\n로컬 비교: 다름"
                   "\n- FileGateway 가 같은 이름의 다른 공유를 연 것. 이 값으로 코드를 쓰지 않고 사용자에게 알림")
    return lines


def _selfcheck() -> None:
    assert resolve(r"\\filer\영업 1팀\a\한글 파일 (1).txt") == ("filer", "영업 1팀", "a/한글 파일 (1).txt")
    assert resolve("//filer/Team/a/b.txt") == ("filer", "Team", "a/b.txt")
    assert resolve(r"z:\a\b.txt", remote_of=lambda d: r"\\filer\Team\sub" if d == "Z:" else "") \
        == ("filer", "Team", "sub/a/b.txt")
    for bad in (r"\\filer\Team", r"C:\a.txt", "a/b.txt"):
        try:
            resolve(bad, remote_of=lambda d: "")
        except Stop:
            continue
        raise AssertionError(f"멈추지 않음: {bad}")

    body = "filegw-smoke".encode()
    same = measure([body])
    path = r"\\filer\Team\a.txt"
    asked = []
    lines = check(path, fetch=lambda s, p: asked.append((s, p)) or (*same, len(body)), local=lambda p: same)
    assert asked == [("Team", "a.txt")] and lines[-1].startswith("로컬 비교: 일치")
    assert "하지 못함" in check(path, fetch=lambda s, p: (*same, None), local=lambda p: None)[-2]

    def refuse(status):
        def fetch(s, p):
            raise Stop(f"FileGateway 거절({status})")
        return fetch
    for status, seen, expected in ((404, True, "그 파일이 열림"), (404, False, "열리지 않음"), (503, True, None)):
        try:
            check(path, fetch=refuse(status), exists=lambda p: seen)
        except Stop as e:
            assert (expected in str(e)) if expected else ("이 PC" not in str(e))
    for fetch, local in ((lambda s, p: (*same, len(body)), lambda p: measure([b"other"])),
                         (lambda s, p: (*same, len(body) + 1), lambda p: same)):
        try:
            check(path, fetch=fetch, local=local)
        except Stop:
            continue
        raise AssertionError("다른데 멈추지 않음")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--selfcheck", action="store_true", help=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest="command")
    p = sub.add_parser("check", help="FileGateway 로 받아 로컬 파일과 비교")
    p.add_argument("--path", required=True, help="네트워크 경로")
    args = parser.parse_args()
    if args.selfcheck:
        _selfcheck()
        print("selfcheck ok")
        return
    if args.command != "check":
        parser.error("하위 명령 check 가 필요함")
    try:
        print("\n".join(check(args.path)))
    except Stop as e:
        raise SystemExit(str(e))


if __name__ == "__main__":
    main()
