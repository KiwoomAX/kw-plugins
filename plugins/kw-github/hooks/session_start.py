"""세션을 새로 열 때 남은 변경을 로컬 commit 으로 만들고 Claude 에게 결과와 push 질문 지시를 넣는다.

기능 레포인지 가장 먼저 본다. commit 은 save_work.commit_work 를 같은 프로세스에서 실행해 45초 안에 끝낸다.
이 훅은 push 와 로그인 확인을 하지 않는다. push 는 개발자가 승인한 뒤 saving-work 가 한다.
"""
import json
import os
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import gitcmd  # noqa: E402
import repo_setup  # noqa: E402
import save_work  # noqa: E402
import session_mark  # noqa: E402

CODE_RULES_PATH = PLUGIN_ROOT / "feature_code_rules.md"
GIT_TERMS_PATH = PLUGIN_ROOT / "git_terms.md"
REMINDER = (
    "이 폴더는 기능 레포다. 기능 단위가 끝날 때마다 saving-work 스킬로 commit 하라. commit 은 saving-work 로 "
    "하고, push 는 개발자가 승인한 것만 한다. 결과는 message 만 개발자에게 전한다. detail 은 Claude 가 읽고 "
    "처리한다."
)
UNPUSHED_NOTE = (
    "GitHub 에 올리지 않은 commit 이 있다. 개발자에게 '업로드되지 않은 작업이 있습니다.' 라고 한 줄 알린 뒤 "
    "saving-work 스킬의 「push 질문」 절에 따라 묻고, 동의하면 「push 절차」 절을 하라. 아래 first_push 와 "
    "history_reset 은 그 절의 덧붙임 문장을 정하는 값이다. '나중에'라고 하면 이 세션에서는 다시 묻지 않는다."
)
OTHER_OWNER_NOTE = (
    "이 폴더의 origin 은 회사 GitHub(KiwoomAX) 밖이다. 올릴지 물을 때 그 주소를 함께 알리고, 회사 GitHub 이 아닌 "
    "곳에 올려도 되는지 확인하라."
)
INSTALL_HELP = (
    "{tool} 를 찾지 못해 이 기능 레포를 commit 하지 못했다. 개발자에게 사내 설치기 kw_install 을 다시 "
    "실행하라고 알려라. 설치한 뒤에는 saving-work 로 commit 하라."
)


def marker_above(start):
    path = Path(start).resolve()
    return any((folder / save_work.MARKER).is_file() for folder in (path, *path.parents))


def feature_top(cwd):
    top = save_work.locate(cwd)
    return top if top is not None and save_work.is_feature_repo(top) else None


def build_context(result, elsewhere=False):
    if result["status"] == "not-feature-repo":
        return None
    lines = [REMINDER, f"세션 시작 commit 결과: {result['status']}",
             f"개발자에게 전할 말(message): {result['message']}"]
    if result.get("detail"):
        lines.append(f"처리할 것(detail): {result['detail']}")
    if result.get("excluded"):
        lines.append("빠진 파일(excluded): " + json.dumps(result["excluded"], ensure_ascii=False))
    if result["status"] == "failed":
        lines.append("saving-work 스킬의 「결과 처리」 절에 따라 처리하라.")
    if result.get("unpushed"):
        lines.append(UNPUSHED_NOTE)
        lines.append(f"first_push: {str(bool(result.get('first_push'))).lower()}, "
                     f"history_reset: {result.get('history_reset') or '없음'}")
        if elsewhere:
            # 사용자 결정(2026-10-20): KiwoomAX 밖으로 올리는 것은 막지 않고 한 번 확인받는다.
            lines.append(OTHER_OWNER_NOTE)
    return "\n".join(lines)


def code_rules():
    return CODE_RULES_PATH.read_text(encoding="utf-8")


def _with_rules(text):
    # 기능 레포에서는 저장이 어떻게 끝나든 코드를 쓰는 동안 지킬 규칙을 함께 넣는다.
    # 개발자에게 하는 말의 git 용어 규칙(git_terms.md)도 함께 넣는다.
    terms = GIT_TERMS_PATH.read_text(encoding="utf-8")
    return f"{text}\n\n{code_rules()}\n\n{terms}"


OTHER_SESSION_NOTE = (
    "다른 세션이 이 기능 레포에서 작업 중이라 이전 세션의 변경을 commit 하지 않았다. 그 세션이 commit 한다. "
    "이 세션도 기능 단위가 끝나면 saving-work 로 commit 하라. 개발자에게는 따로 알리지 않는다."
)


START_NOTE = (
    "이 PC 는 회사 코드를 회사 GitHub(KiwoomAX)의 기능 레포에 저장한다. 개발자가 기능·앱·화면·스크립트 "
    "코드를 만들어 달라고 하면 브레인스토밍이나 다른 작업보다 먼저 starting-feature-repo 스킬로 이 작업 "
    "폴더를 기능 레포로 등록하라. 코드는 Artifact 나 세션 임시 폴더가 아니라 이 작업 폴더에 만든다. 결과물을 "
    "어디에 둘지 개발자에게 묻지 않는다. 질문에 답하거나 코드를 읽기만 하는 요청이면 등록하지 않는다."
)
ELSEWHERE_NOTE = (
    "이 폴더는 회사 GitHub(KiwoomAX) 밖의 원격과 연결되어 있다. 회사 코드는 KiwoomAX 에만 올라가므로, "
    "개발자가 회사 기능을 새로 만들려고 하면 이 폴더 대신 새 폴더에서 클로드 코드를 다시 열라고 안내하라."
)


def _guidance_for(cwd):
    """기능 레포가 아닌 폴더에 넣을 안내다. 회사의 다른 레포에는 넣지 않는다."""
    state = repo_setup.inspect(cwd).get("state")
    if state in ("not-git", "local-only"):
        return _with_rules(START_NOTE)
    if state == "other-remote":
        return ELSEWHERE_NOTE
    return None


def context_for(cwd, session_id=None):
    try:
        top = feature_top(cwd)
    except gitcmd.ToolMissing:
        return _with_rules(INSTALL_HELP.format(tool="git")) if marker_above(cwd) else None
    if top is None:
        return _guidance_for(cwd)
    if session_id:
        # 다른 세션이 작업 중이면 그 세션의 미완성 코드를 commit 하지 않도록 저장을 건너뛴다.
        busy = session_mark.others_active(top, session_id)
        session_mark.touch(top, session_id)
        if busy:
            return _with_rules(OTHER_SESSION_NOTE)
    owner = save_work.origin_owner(top) if save_work.origin_url(top) else save_work.ORG
    elsewhere = (owner or "").lower() != save_work.ORG.lower()
    context = build_context(save_work.commit_work(top, None, catch_up=True), elsewhere)
    return _with_rules(context) if context else None


def main():
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8") or "{}")
        context = context_for(payload.get("cwd") or os.getcwd(), payload.get("session_id"))
    except Exception as exc:  # noqa: BLE001 — 훅이 죽으면 저장 알림도 사라진다
        context = (f"세션 시작 훅이 실패했다: {exc.__class__.__name__}: {exc}. "
                   "이 폴더가 기능 레포면 saving-work 로 commit 하라.")
    if context:
        # ensure_ascii 를 켠 채 내보낸다. 한국어 Windows 의 cp949 표준 출력에서도 글자가 깨지지 않는다.
        print(json.dumps({
            "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}
        }))


if __name__ == "__main__":
    main()
