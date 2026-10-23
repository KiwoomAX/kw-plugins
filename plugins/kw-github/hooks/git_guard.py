"""기능 레포에서 saving-work 를 건너뛰는 직접 commit·push 를 거부한다.

명령 문자열을 먼저 보고, 살펴볼 명령이 없으면 git 을 부르지 않고 통과시킨다. 이 훅은 보안 경계가
아니다. Claude 가 실수로 저장 스크립트의 검사를 건너뛰지 않게 하는 장치다. 브랜치·merge 는 거부하지
않고, 기능 레포가 아닌 폴더에서는 아무것도 거부하지 않는다.
"""
import json
import os
import re
import shlex
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

SAVE_REASON = "commit과 push는 saving-work 로 한다."

SEPARATOR_CHARS = ";&|"
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
CD_WORDS = {"cd", "chdir", "pushd", "set-location", "sl"}
GIT_VALUE_OPTS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}
GH_API_VALUE_OPTS = {
    "-X", "--method", "-H", "--header", "-f", "--raw-field", "-F", "--field", "--input",
    "-q", "--jq", "-t", "--template", "--hostname", "--cache", "-p", "--preview",
}
GH_API_BODY_OPTS = {"-f", "--raw-field", "-F", "--field", "--input"}
WRITE_METHODS = {"PUT", "POST", "PATCH", "DELETE"}


def segments(command):
    """명령을 조각으로 나눈다. 따옴표 안의 ; 는 나누지 않는다."""
    text = command.replace("\r\n", "\n").replace("\n", " ; ")
    lexer = shlex.shlex(text, posix=True, punctuation_chars=SEPARATOR_CHARS)
    lexer.whitespace_split = True
    lexer.commenters = ""
    lexer.escape = ""  # Windows 경로의 역슬래시를 글자 그대로 둔다
    try:
        tokens = list(lexer)
    except ValueError:  # 따옴표가 닫히지 않았다
        tokens = re.findall(r"[;&|]+|[^\s;&|]+", text)
    parts, current = [], []
    for token in tokens:
        if token and set(token) <= set(SEPARATOR_CHARS):
            if current:
                parts.append(current)
            current = []
        else:
            current.append(token)
    if current:
        parts.append(current)
    return parts


def _strip_assignments(words):
    index = 0
    while index < len(words) and ASSIGNMENT.match(words[index]):
        index += 1
    return words[index:]


def _cd_target(words):
    if words[0].lower() not in CD_WORDS:
        return None
    targets = [word for word in words[1:] if not word.startswith("-")]
    return targets[-1] if targets else "~"


MSYS_DRIVE = re.compile(r"^/([A-Za-z])(?=/|$)")


def _resolve(base, target):
    # Bash 도구는 Git Bash 라서 C:\work 를 /c/work 로 쓴다. 그대로 읽으면 C:\c\work 가 된다.
    target = MSYS_DRIVE.sub(lambda found: found.group(1).upper() + ":", str(target))
    return Path(base) / Path(target).expanduser()


def _git_reason(words):
    """git 명령 한 조각을 본다. (기능 레포에서 막을 이유, -C 로 준 폴더) 를 돌려준다."""
    index, workdir = 1, None
    while index < len(words) and words[index].startswith("-"):
        if words[index] in GIT_VALUE_OPTS:
            if words[index] == "-C" and index + 1 < len(words):
                workdir = words[index + 1] if workdir is None else str(Path(workdir) / words[index + 1])
            index += 2
        else:
            index += 1
    if index >= len(words):
        return None, workdir
    return (SAVE_REASON if words[index] in ("commit", "push") else None), workdir


def _gh_reason(words):
    """gh 명령 한 조각을 본다. 기능 레포에서 막을 이유를 돌려준다."""
    if words[1:3] == ["repo", "create"]:
        return SAVE_REASON if "--push" in words else None
    if len(words) < 2 or words[1] != "api":
        return None
    method, target, has_body, index = "", "", False, 2
    while index < len(words):
        word = words[index]
        if word.startswith("--method="):
            method = word.split("=", 1)[1]
        elif word.startswith("-X") and len(word) > 2:
            method = word[2:]
        elif word in GH_API_VALUE_OPTS:
            # 옵션 값을 경로로 집지 않도록 값까지 건너뛴다.
            if word in ("-X", "--method") and index + 1 < len(words):
                method = words[index + 1]
            has_body = has_body or word in GH_API_BODY_OPTS
            index += 2
            continue
        elif not word.startswith("-") and not target:
            target = word
        index += 1
    # gh api 는 -f 나 -F 로 본문을 주면 -X 가 없어도 POST 로 보낸다.
    method = (method or ("POST" if has_body else "GET")).upper()
    if method not in WRITE_METHODS:
        return None
    parts = target.lstrip("/").split("/")
    # 이슈 요청은 코드를 올리지 않는다. 작업 이슈와 기능 이슈의 Issue Type 설정이 이 요청을 쓴다.
    is_issue = parts[0] == "repos" and len(parts) > 3 and parts[3] == "issues"
    return SAVE_REASON if parts[0] == "repos" and not is_issue else None


def blocked_commands(command, cwd):
    """기능 레포에서 막을 명령마다 (막을 이유, 그 명령이 실행되는 폴더) 를 돌려준다. git 을 부르지 않는다."""
    found, here = [], Path(cwd)
    for words in segments(command):
        words = _strip_assignments(words)
        if not words:
            continue
        target = _cd_target(words)
        if target is not None:
            here = _resolve(here, target)
            continue
        if words[0] == "git":
            reason, workdir = _git_reason(words)
            where = _resolve(here, workdir) if workdir else here
        elif words[0] == "gh":
            reason, where = _gh_reason(words), here
        else:
            continue
        if reason:
            found.append((reason, where))
    return found


def blocked(command):
    found = blocked_commands(command, ".")
    return found[0][0] if found else None


def _deny(reason):
    # ensure_ascii 를 켠 채 내보낸다. 한국어 Windows 의 cp949 표준 출력에서도 글자가 깨지지 않는다.
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))


def _mark_session(payload):
    """셸 명령마다 이 세션이 작업 중이라고 표시한다. 실패해도 판정에는 영향을 주지 않는다."""
    try:
        import session_mark

        session_mark.touch(payload.get("cwd") or os.getcwd(), payload.get("session_id"))
    except Exception:  # noqa: BLE001 — 표시는 보조 정보다
        pass


def main():
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8") or "{}")
        command = (payload.get("tool_input") or {}).get("command") or ""
        _mark_session(payload)
        found = blocked_commands(command, payload.get("cwd") or os.getcwd())
        if not found:
            return 0
        import gitcmd
        import save_work

        for reason, where in found:
            try:
                top = save_work.locate(where)
            except gitcmd.ToolMissing:
                return 0  # git 이 없으면 막으려던 명령도 실행되지 않는다
            if top is None:
                continue  # 레포가 아닌 폴더에서는 git push 가 실행되지 않는다
            if save_work.is_feature_repo(top):
                _deny(reason)
                return 0
    except Exception as exc:  # noqa: BLE001 — 판단하지 못하면 통과시키지 않는다
        _deny(f"저장 가드가 판단하지 못해 막았다: {exc.__class__.__name__}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
