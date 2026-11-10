"""이전 commit 기록을 지우는 push 를 PC 에서 거부하는 pre-push 훅을 설치한다.

사람의 실수를 줄이는 장치다. 서버 쪽 branch 보호를 대신하지 못한다. 이 파일은 gitcmd 만 불러온다.
"""
from pathlib import Path

import gitcmd

HISTORY_REASON = "이전 기록을 지우는 push(업로드)는 차단됩니다. AX팀에 문의해 주세요."
# (fetch first) 는 저장 스크립트가 원격 변경을 알아보는 기존 판별 문구다.
FETCH_FIRST_REASON = "GitHub 에 PC 에 없는 commit 이 있습니다 (fetch first). 최신 내용을 받은 뒤 다시 올려 주세요."
TAG_REASON = "GitHub 의 태그 삭제는 차단됩니다. AX팀에 문의해 주세요."
INSTALL_FAILED_NOTE = "이 레포에는 기록 삭제 차단을 설치하지 못했습니다. AX팀에 문의해 주세요."
DELETE_ENV = "KW_GITHUB_BRANCH_DELETE"
HOOK_MARK = b"# kw-github pre-push"
ORIGINAL_NAME = "pre-push.kw-original"

HOOK_TEXT = f"""#!/bin/sh
{HOOK_MARK.decode()}
input=$(cat)

refuse() {{
    printf '%s\\n' "$1" >&2
    exit 1
}}

while read -r local_ref local_sha remote_ref remote_sha; do
    case "$remote_ref" in
        refs/heads/*) ;;
        refs/tags/*)
            case "$local_sha" in
                *[!0]*) continue ;;
                *) refuse "{TAG_REASON}" ;;
            esac
            ;;
        *) continue ;;
    esac
    case "$local_sha" in
        *[!0]*) ;;
        *)
            if [ "${DELETE_ENV}" = "1" ] && [ "$remote_ref" != "refs/heads/main" ]; then
                continue
            fi
            refuse "{HISTORY_REASON}"
            ;;
    esac
    case "$remote_sha" in
        *[!0]*) ;;
        *) continue ;;
    esac
    git cat-file -e "$remote_sha^{{commit}}" 2>/dev/null || refuse "{FETCH_FIRST_REASON}"
    git merge-base --is-ancestor "$remote_sha" "$local_sha" || refuse "{HISTORY_REASON}"
done <<KW_INPUT
$input
KW_INPUT

original="$(dirname "$0")/{ORIGINAL_NAME}"
if [ -f "$original" ]; then
    {{ [ -z "$input" ] || printf '%s\\n' "$input"; }} | "$original" "$@"
    exit $?
fi
exit 0
"""


def _write(hooks):
    """훅 폴더에 훅을 쓴다. 표시 없는 기존 훅은 옮겨 둔다. 쓰지 못할 상태면 False 다."""
    hook, original = hooks / "pre-push", hooks / ORIGINAL_NAME
    wanted = HOOK_TEXT.encode("utf-8")  # bytes 로 써야 Windows 에서도 줄바꿈이 LF 로 남는다
    if hook.exists():
        current = hook.read_bytes()
        if current == wanted:
            return True
        if HOOK_MARK not in current:
            if original.exists():
                return False
            hook.replace(original)
    hooks.mkdir(parents=True, exist_ok=True)
    hook.write_bytes(wanted)
    hook.chmod(0o755)
    return True


def install(top, deadline=None):
    """훅을 설치한다. 설치했거나 이미 있으면 True, 설치하지 못하면 False 다. 예외를 올리지 않는다."""
    try:
        if gitcmd.git_try(top, "config", "--get", "core.hooksPath", deadline=deadline)[0] == 0:
            return False
        out = gitcmd.git(top, "rev-parse", "--git-path", "hooks", deadline=deadline)
        return _write(Path(top) / out.strip())
    except (OSError, gitcmd.GitError, gitcmd.CommandTimeout, gitcmd.ToolMissing):
        return False
