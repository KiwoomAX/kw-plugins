"""AX 지원 문의(1:1 문의·환경변수(env) 등록)를 개인 접근 키로 접수한다.

명령:
  env-keys <.env>                               키 이름과 규칙에 맞지 않는 줄, 고칠 수 있는 줄을 알린다(값은 내지 않음)
  fix-env --draft <초안 파일> --env <.env>       초안에서 고른 키의 닫히지 않은 따옴표와 겹친 키를 .env 에서 고친다
  send-inquiry --draft <초안 파일>               1:1 문의를 접수한다
  send-env --draft <초안 파일> --env <.env>      환경변수 등록을 접수한다. 초안에서 고른 키의 줄만 보낸다

초안 파일은 UTF-8 JSON 이다. 1:1 문의는 {"type", "title", "body"}, 환경변수 등록은
{"repo_name", "body", "keys": {키 이름: 용도}} 이고 값은 모두 문자열이다. PowerShell 5.1 이 명령 인자의 큰따옴표를
지우고 파이프로 넘긴 한글을 깨뜨리므로 내용은 파일로만 받는다.

접근 키는 환경 변수에서만 읽고 출력하지 않는다. .env 값도 출력하지 않고, 보낼 줄은 메모리에서만 만든다.
입력을 먼저 검사하고, 입력이 틀리면 키를 읽지 않고 멈춘다.

「접수 경로 없음」·「접수 확인 필요」 뒤에는 다시 보내지 않는다. 저장이 끝난 뒤에도 502 나 시간 초과가 올 수 있고,
신청자가 문의를 취소할 방법이 없어 다시 보내면 같은 문의가 두 건 생기기 때문이다. 내 문의 화면에서 확인한다.

설치 없이 실행되도록 표준 라이브러리만 쓴다.

종료 코드: 0 완료, 3 입력 오류, 4 키 없음·키 거절, 5 접수 경로 없음, 6 접수 확인 필요, 7 접수 거절.

사용: python scripts/ax_inquiry.py <명령> ...
"""
import argparse
import http.client
import json
import os
import re
import socket
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "searching-winus" / "scripts"))
import fetch_manifest as gw  # noqa: E402

KEY_ENV = gw.KEY_ENV
REOPEN = gw.REOPEN
registry_key = gw.registry_key

BASE = os.environ.get("AX_INQUIRY_URL", "http://192.7.9.45/ax")
DIRECT = "http://192.7.9.45/ax/"
MINE = "http://192.7.9.45/ax/mine"
TIMEOUT_SECONDS = 60
MAX_BODY = 1_048_576  # 게이트웨이 접근 키 경로의 본문 상한

# AX 지원 문의 서비스가 .env 를 읽는 규칙과 같다. 서비스와 같은 사례 파일로 시험한다.
KEY_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
LINE_BREAK = re.compile(r"\r\n|\n|\r")
JS_SPACE = ("\t\n\x0b\x0c\r \xa0            "
            "    　﻿")
QUOTES = ('"', "'")
UNCLOSED = "따옴표 미닫힘"
DUPLICATE = "겹친 키"


class Stop(Exception):
    """출력 줄과 종료 코드를 들고 main 으로 돌아간다."""

    def __init__(self, code: int, *lines: str):
        super().__init__(lines[0] if lines else "")
        self.code = code
        self.lines = lines


def input_error(reason: str) -> Stop:
    return Stop(3, f"입력 오류: {reason}", "- 보내지 않음")


# ---------------------------------------------------------------- .env 읽기

def key_reason(name: str) -> str | None:
    if KEY_RE.fullmatch(name):
        return None
    if name == "":
        return "키 이름이 비어 있습니다"
    if name[0].isascii() and name[0].isdigit():
        return "키 이름이 숫자로 시작합니다"
    return "키 이름에 영문·숫자·_ 가 아닌 글자가 있습니다"


def _decode_like_service(data: bytes) -> str:
    if data[:2] == b"\xff\xfe":
        return data[2:].decode("utf-16-le", errors="replace")
    if data[:2] == b"\xfe\xff":
        return data[2:].decode("utf-16-be", errors="replace")
    text = data.decode("utf-8", errors="replace")
    return text[1:] if text.startswith("﻿") else text


def read_env_keys(data: bytes) -> tuple[list[tuple[str, int]], list[tuple[int, str]]]:
    """AX 지원 문의 서비스와 같은 규칙으로 (키 이름, 줄 번호) 목록과 (줄 번호, 이유) 목록을 돌려준다."""
    keys: list[tuple[str, int]] = []
    problems: list[tuple[int, str]] = []
    quote: str | None = None
    for number, raw in enumerate(LINE_BREAK.split(_decode_like_service(data)), start=1):
        if quote:
            if quote in raw:
                quote = None
            continue
        line = raw.strip(JS_SPACE)
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        name, rest = line.split("=", 1)
        name, rest = name.strip(JS_SPACE), rest.strip(JS_SPACE)
        if rest[:1] in QUOTES and rest[0] not in rest[1:]:
            quote = rest[0]
        reason = key_reason(name)
        if reason:
            problems.append((number, reason))
        else:
            keys.append((name, number))
    return keys, problems


class _Text:
    """고쳐 쓸 수 있게 원래 인코딩·BOM·줄 끝을 지켜 둔 .env 내용."""

    def __init__(self, data: bytes):
        if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
            self.encoding = "utf-16-le" if data[:2] == b"\xff\xfe" else "utf-16-be"
            self.bom, body, self.errors = data[:2], data[2:], "surrogatepass"
        else:
            self.encoding, self.errors = "utf-8", "surrogateescape"
            self.bom, body = (data[:3], data[3:]) if data[:3] == b"\xef\xbb\xbf" else (b"", data)
        text = body.decode(self.encoding, errors=self.errors)
        self.lines: list[str] = []
        self.ends: list[str] = []
        start = 0
        for m in LINE_BREAK.finditer(text):
            self.lines.append(text[start:m.start()])
            self.ends.append(m.group())
            start = m.end()
        self.lines.append(text[start:])
        self.ends.append("")

    def encode(self, lines: list[str], ends: list[str]) -> bytes:
        text = "".join(line + end for line, end in zip(lines, ends))
        return self.bom + text.encode(self.encoding, errors=self.errors)


class _Entry:
    def __init__(self, key: str | None, reason: str | None, first: int, last: int, quote: str | None, closed: bool):
        self.key, self.reason, self.first, self.last, self.quote, self.closed = key, reason, first, last, quote, closed


def _entries(text: _Text) -> list[_Entry]:
    """키 줄과 그 값이 이어지는 줄의 범위. 파일 끝까지 닫히지 않은 따옴표는 그 줄에서 닫힌 것으로 보고 다음 줄부터 읽는다.

    fix-env 가 그 줄 끝에 따옴표를 붙여 고치므로, 고친 뒤에 보일 키를 미리 찾기 위해서다.
    """
    out: list[_Entry] = []
    i, n = 0, len(text.lines)
    while i < n:
        line = text.lines[i].strip(JS_SPACE)
        if not line or line.startswith("#") or "=" not in line:
            i += 1
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        name, rest = line.split("=", 1)
        name, rest = name.strip(JS_SPACE), rest.strip(JS_SPACE)
        reason = key_reason(name)
        key = None if reason else name
        if rest[:1] in QUOTES and rest[0] not in rest[1:]:
            quote = rest[0]
            end = next((j for j in range(i + 1, n) if quote in text.lines[j]), None)
            if end is None:
                out.append(_Entry(key, reason, i, i, quote, False))
                i += 1
            else:
                out.append(_Entry(key, reason, i, end, quote, True))
                i = end + 1
            continue
        out.append(_Entry(key, reason, i, i, None, True))
        i += 1
    return out


def _fixable(entries: list[_Entry]) -> list[tuple[int, str, str, _Entry]]:
    found = []
    last: dict[str, _Entry] = {}
    for e in entries:
        if e.key:
            last[e.key] = e
    for e in entries:
        if not e.key:
            continue
        if not e.closed:
            found.append((e.first + 1, e.key, UNCLOSED, e))
        if last[e.key] is not e:
            found.append((e.first + 1, e.key, DUPLICATE, e))
    return found


def find_fixable(data: bytes) -> list[tuple[int, str, str]]:
    """(줄 번호, 키, 종류) 목록. 종류는 따옴표 미닫힘과 겹친 키(같은 키의 마지막이 아닌 줄)다."""
    return [(line, key, kind) for line, key, kind, _ in _fixable(_entries(_Text(data)))]


def env_key_names(data: bytes) -> set[str]:
    return {e.key for e in _entries(_Text(data)) if e.key}


def pick_lines(data: bytes, keys: set[str]) -> bytes:
    """고른 키의 줄과 그 값이 이어지는 줄만 원래 순서로 남긴다. UTF-8, 줄 끝은 \\n."""
    text = _Text(data)
    entries = _entries(text)
    for key in sorted(keys):
        mine = [e for e in entries if e.key == key]
        if len(mine) > 1:
            raise ValueError(f"{key} 가 여러 번 있음, fix-env 로 고칠 수 있음")
        if mine and not mine[0].closed:
            raise ValueError(f"{key} 의 따옴표가 닫히지 않음, fix-env 로 고칠 수 있음")
    picked = [line for e in entries if e.key in keys for line in text.lines[e.first:e.last + 1]]
    return "".join(line + "\n" for line in picked).encode("utf-8", errors="surrogateescape")


def fix_env(data: bytes, keys: set[str]) -> tuple[bytes, list[tuple[int, str, str]]]:
    """고른 키의 따옴표 미닫힘은 그 줄 끝에 같은 따옴표를 붙이고, 겹친 키는 마지막이 아닌 줄을 지운다."""
    text = _Text(data)
    items = [f for f in _fixable(_entries(text)) if f[1] in keys]
    if not items:
        return data, []
    lines, ends = list(text.lines), list(text.ends)
    drop: set[int] = set()
    for _, _, kind, e in items:
        if kind == UNCLOSED:
            lines[e.first] += e.quote
    for _, _, kind, e in items:
        if kind == DUPLICATE:
            drop.update(range(e.first, e.last + 1))
    keep = [i for i in range(len(lines)) if i not in drop]
    fixed = text.encode([lines[i] for i in keep], [ends[i] for i in keep])
    return fixed, [(line, key, kind) for line, key, kind, _ in items]


# ---------------------------------------------------------------- 입력

def _read_bytes(path: str, what: str) -> bytes:
    try:
        return Path(path).read_bytes()
    except OSError:
        raise input_error(f"{what} 파일을 열 수 없음: {path}") from None


def load_draft(path: str, fields: tuple[str, ...], with_keys: bool) -> dict:
    try:
        draft = json.loads(_read_bytes(path, "초안").decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError):
        raise input_error("초안 파일이 UTF-8 JSON 이 아님") from None
    if not isinstance(draft, dict):
        raise input_error("초안 파일이 JSON 객체가 아님")
    for field in fields:
        if field not in draft:
            raise input_error(f"초안에 {field} 칸이 없음")
        if not isinstance(draft[field], str):
            raise input_error(f"초안의 {field} 칸이 문자열이 아님")
    if with_keys:
        keys = draft.get("keys")
        if not isinstance(keys, dict) or not keys:
            raise input_error("초안의 keys 칸이 비어 있지 않은 {키 이름: 용도} 객체가 아님")
        if not all(isinstance(v, str) for v in keys.values()):
            raise input_error("초안의 keys 용도가 문자열이 아님")
    return draft


def _multipart(fields: dict[str, str], env: bytes | None) -> tuple[bytes, str]:
    boundary = "----ax-inquiry-" + uuid.uuid4().hex
    parts = []
    for name, value in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
                     + value.encode("utf-8") + b"\r\n")
    if env is not None:
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="env_file"; filename=".env"\r\n'
                     "Content-Type: application/octet-stream\r\n\r\n".encode() + env + b"\r\n")
    body = b"".join(parts) + f"--{boundary}--\r\n".encode()
    if len(body) > MAX_BODY:
        raise input_error(f"보낼 내용이 {MAX_BODY:,} 바이트(1MB)를 넘음")
    return body, f"multipart/form-data; boundary={boundary}"


# ---------------------------------------------------------------- 전송

class NoRedirect(urllib.request.HTTPRedirectHandler):
    """리다이렉트를 따라가지 않는다. 따라가면 POST 가 GET 으로 바뀌고, 3xx 는 접수 경로가 없다는 뜻이다."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _open(request: urllib.request.Request) -> tuple[int, str, bytes]:
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read()
    except urllib.error.HTTPError as e:
        ctype = e.headers.get("Content-Type", "") if e.headers else ""
        return e.code, ctype, e.read()


def access_key() -> str:
    key = os.environ.get(KEY_ENV, "").strip()
    if key:
        return key
    if registry_key():
        raise Stop(4, "키 없음: 접근 키가 설정되지 않음", "- 키는 설정됨, 이 창에는 아직 반영되지 않음: " + REOPEN)
    raise Stop(4, "키 없음: 접근 키가 설정되지 않음", f"- 조치: {DIRECT} 에서 직접 작성")


def _json(body: bytes):
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None


NO_RESEND = f"- 다시 보내지 않음. {MINE} 에서 접수 여부 확인"


def send(path: str, fields: dict[str, str], env: bytes | None = None) -> Stop:
    body, ctype = _multipart(fields, env)
    key = access_key()
    request = urllib.request.Request(
        BASE.rstrip("/") + path, data=body, method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": ctype, "Accept": "application/json"})
    try:
        status, rtype, rbody = _open(request)
    except (socket.timeout, TimeoutError):
        return Stop(6, "접수 확인 필요: 시간 초과", NO_RESEND)
    except urllib.error.URLError as e:
        kind = "시간 초과" if isinstance(e.reason, (socket.timeout, TimeoutError)) else "접속 실패"
        return Stop(6, f"접수 확인 필요: {kind}", NO_RESEND)
    except (OSError, http.client.HTTPException):
        return Stop(6, "접수 확인 필요: 접속 실패", NO_RESEND)
    is_json = "json" in rtype.lower()
    data = _json(rbody) if is_json else None
    if status == 201:
        ticket = data.get("id") if isinstance(data, dict) else None
        if isinstance(ticket, int) and not isinstance(ticket, bool):
            return Stop(0, f"접수 완료: #{ticket} {BASE.rstrip('/')}/mine?id={ticket}")
        return Stop(6, "접수 확인 필요: 201 응답에 접수 번호 없음", NO_RESEND)
    if status == 401 and is_json:
        lines = ["키 거절: AX 지원 문의 서비스가 접근 키를 거절함"]
        new = registry_key()
        if new and new != key:
            lines.append("- 새 키가 설정됨: " + REOPEN)
        lines.append(f"- 조치: {DIRECT} 에서 직접 작성. 키 재발급은 원할 때만")
        return Stop(4, *lines)
    if status in (401, 404) or 300 <= status < 400:
        return Stop(5, f"접수 경로 없음: 접근 키 접수 경로가 열리지 않음({status})", NO_RESEND)
    # 접수 완료는 201 하나로만 본다. 두 접수 경로는 성공하면 늘 201 로 답하므로, 201 이 아닌 2xx 는 중간에서 바뀐
    # 응답이라 접수됐는지 알 수 없다. 완료로 보면 실패를 놓치고, 실패로 보면 다시 보내 같은 문의가 두 건 생기므로
    # 다시 보내지 않고 내 문의 목록에서 확인하게 한다.
    if status >= 500 or 200 <= status < 300:
        return Stop(6, f"접수 확인 필요: {status}", NO_RESEND)
    detail = data.get("detail") if isinstance(data, dict) else None
    return Stop(7, f"접수 거절({status}): {detail if isinstance(detail, str) and detail else '응답 본문 없음'}",
                "- 초안을 고친 뒤 다시 보낼 수 있음")


# ---------------------------------------------------------------- 명령

ENV_FIELDS = ("repo_name", "body")


def cmd_env_keys(args) -> Stop:
    """닫히지 않은 따옴표 뒤의 줄도 읽어 알린다. 그 줄은 fix-env 가 닫으므로, 뒤의 키도 등록할 키로 고를 수 있어야 한다.

    닫히지 않은 따옴표가 없으면 AX 지원 문의 서비스가 읽는 결과(read_env_keys)와 같다.
    """
    data = _read_bytes(args.env, ".env")
    entries = _entries(_Text(data))
    lines = [e.key for e in entries if e.key]
    lines += [f"{e.first + 1}번째 줄: {e.reason}" for e in entries if e.reason]
    lines += [f"고칠 수 있음: {line}번째 줄 {key} {kind}" for line, key, kind in find_fixable(data)]
    return Stop(0, *lines)


def cmd_fix_env(args) -> Stop:
    draft = load_draft(args.draft, ENV_FIELDS, with_keys=True)
    data = _read_bytes(args.env, ".env")
    fixed, done = fix_env(data, set(draft["keys"]))
    if not done:
        return Stop(0, "고칠 것 없음")
    try:
        Path(args.env).write_bytes(fixed)
    except OSError:
        raise input_error(f".env 파일에 쓸 수 없음: {args.env}") from None
    return Stop(0, *[f"고침: {line}번째 줄 {key} {kind}" for line, key, kind in done])


def cmd_send_inquiry(args) -> Stop:
    draft = load_draft(args.draft, ("type", "title", "body"), with_keys=False)
    return send("/api/agent/inquiry", {k: draft[k] for k in ("type", "title", "body")})


def cmd_send_env(args) -> Stop:
    draft = load_draft(args.draft, ENV_FIELDS, with_keys=True)
    data = _read_bytes(args.env, ".env")
    keys = set(draft["keys"])
    missing = sorted(keys - env_key_names(data))
    if missing:
        raise input_error(".env 에 없는 키: " + ", ".join(missing))
    try:
        subset = pick_lines(data, keys)
    except ValueError as e:
        raise input_error(str(e)) from None
    fields = {"repo_name": draft["repo_name"], "body": draft["body"],
              "key_purposes": json.dumps(draft["keys"], ensure_ascii=False)}
    return send("/api/agent/env-request", fields, subset)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="AX 지원 문의를 개인 접근 키로 접수한다")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("env-keys")
    p.add_argument("env")
    p.set_defaults(run=cmd_env_keys)
    for name, run, with_env in (("fix-env", cmd_fix_env, True), ("send-inquiry", cmd_send_inquiry, False),
                                ("send-env", cmd_send_env, True)):
        p = sub.add_parser(name)
        p.add_argument("--draft", required=True)
        if with_env:
            p.add_argument("--env", required=True)
        p.set_defaults(run=run)
    args = parser.parse_args(argv)
    try:
        result = args.run(args)
    except Stop as stop:
        result = stop
    for line in result.lines:
        print(line)
    raise SystemExit(result.code)


if __name__ == "__main__":
    # Windows 에서 출력이 파이프로 나가면 파이썬은 CP949 로 써서 한글 밖의 문자에서 멈춘다. --help 도 거치도록 main 앞에 둔다.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    main()
