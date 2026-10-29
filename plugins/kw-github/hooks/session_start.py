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
import main_branch  # noqa: E402
import repo_setup  # noqa: E402
import save_work  # noqa: E402
import session_mark  # noqa: E402
import shared_repo  # noqa: E402

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
NEEDS_AUTHOR_NOTE = (
    "[kw-github] commit 명의가 없어 commit 하지 않았다. saving-work 스킬의 「commit 명의」 절에 따라 개발자에게 이름과 "
    "메일을 물어 설정한 뒤 saving-work 로 commit 하라."
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
    if result["status"] == "needs-author":
        lines.append(NEEDS_AUTHOR_NOTE)
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
        # 사용자 결정(2026-10-28): 기능 코드 규칙과 git 용어표는 starting-feature-repo 가 준비할 때 읽는다.
        return START_NOTE
    if state == "other-remote":
        return ELSEWHERE_NOTE
    return None


# 2026-10-27 globalbond-dashboard 의 fetch 10번 실측 최댓값 3.10초의 3배를 올림했다.
SYNC_FETCH_SECONDS = 10
SHARED_REMINDER = (
    "[kw-github] 이 폴더는 여러 개발자가 함께 쓰는 공유 대시보드 레포다. 세션 시작 때 commit 하지 않는다. 기능마다 "
    "save_work.py switch-feature 와 commit --feature <기능> 으로 commit 하고, 올리기는 saving-work 스킬로 한다."
)
SHARED_DIRTY_NOTE = (
    "[kw-github] 공유 대시보드 레포에 commit 하지 않은 변경이 있다: {groups}. 개발자와 기능을 확인하고 "
    "save_work.py switch-feature 와 commit --feature <기능> 으로 기능마다 commit 하라."
)
BEHIND_NOTE = ("[kw-github] 지금 작업 branch 가 공유 코드보다 {count}개 commit 뒤처져 있다. 작업 branch 에 main 을 "
               "자동으로 합치지 않았다.")
SHARED_UNPUSHED_NOTE = (
    "[kw-github] GitHub 에 올리지 않은 commit 이 있다. 개발자에게 '업로드되지 않은 작업이 있습니다.' 라고 한 줄 알린 뒤 "
    "saving-work 스킬의 「push 질문」 절에 따라 묻고, 동의하면 「공유 대시보드 레포」의 「올리기 흐름」을 하라."
)
INTAKE_BRANCH_NOTE = (
    "[kw-github] 지금 branch 는 kw-dashboard 기능 이전 중인 branch 다. saving-work 의 「push 질문」을 하지 말고, "
    "commit 하지 않은 변경도 기능별로 commit 하지 마라. kw-dashboard 기능 이전 절차의 「다시 실행 판정」부터 이어 가고, "
    "업로드 승인은 그 절차가 공유 코드 반영 직전에 하는 질문으로 받아라."
)
UNSUPPORTED_NOTE = (
    "[kw-github] 이 공유 대시보드 레포는 아직 기능별 폴더 구조가 아니라 kw-github 가 commit 과 업로드를 하지 않는다. "
    "개발자가 올리기를 원하면 AX팀에 문의하라고 안내하라."
)
MAIN_DECISION_NOTE = (
    "[kw-github] 예전 기본 branch {old} 에 main 에 없는 commit 이 있다: {commits}. saving-work 스킬의 「기본 branch "
    "맞추기」 절에 따라 개발자에게 반영할지 버릴지 물어라."
)
MAIN_FAILED_NOTE = "[kw-github] GitHub 의 기본 branch 를 main 으로 바꾸지 못했다. {detail}"
LOCK_NOTE = ("[kw-github] 세션 시작 fetch 가 {seconds}초 안에 끝나지 않아 멈췄다. .git 아래에 lock 파일이 남아 있다: "
             "{locks}. 다른 git 명령이 실행 중이 아니면 이 파일을 지운 뒤 fetch 하라.")


def _move_main(top, session_id):
    """spec 「세션 시작 동기화」 3단계다. 조건을 모두 만족할 때만 PC 의 main 을 origin/main 으로 옮긴다."""
    old = gitcmd.git_try(top, "rev-parse", "--verify", "-q", "refs/heads/main")[1].strip()
    new = gitcmd.git(top, "rev-parse", save_work.REMOTE_REF).strip()
    if not old or old == new or shared_repo.worktree_paths(top):
        return
    if gitcmd.git_try(top, "merge-base", "--is-ancestor", old, new)[0] != 0:
        return
    if not save_work._main_free(top, None):
        return
    if session_id and session_mark.others_active(top, session_id):
        return
    if save_work.current_branch(top) == save_work.BRANCH:
        gitcmd.git(top, "merge", "-q", "--ff-only", save_work.REMOTE_REF)
    else:
        gitcmd.git(top, "update-ref", "refs/heads/main", new, old)


def _main_notes(top, session_id=None, deadline=None):
    """기본 branch 를 main 으로 맞춘다(spec 「기본 branch 를 main 으로 맞추기」). 지원 구조 판정보다 먼저 한다.

    이미 main 으로 맞춘 레포는 GitHub 를 부르지 않는다. 다른 세션이 같은 폴더에서 작업 중이면 그 세션의
    branch 를 바꾸지 않도록 _move_main 과 같은 조건으로 건너뛴다.
    """
    if session_id and session_mark.others_active(top, session_id):
        return []
    try:
        if main_branch.settled(top, deadline):
            return []
        fixed = main_branch.normalize(top, save_work._full_name(top), deadline)
    except save_work.GH_ERRORS:
        return []  # 다음 세션에 다시 맞춘다
    if fixed["status"] == "needs-decision":
        return [MAIN_DECISION_NOTE.format(old=fixed["old_branch"], commits=", ".join(fixed["commits"]))]
    if fixed["status"] == "failed":
        return [MAIN_FAILED_NOTE.format(detail=fixed["detail"])]
    return []


def sync_shared(top, session_id=None):
    """세션 시작 동기화다. Claude 에게 넣을 알림 문장 목록을 돌려준다."""
    notes = []
    try:
        # fetch 와 기본 branch 맞추기가 한 제한 시간을 함께 쓴다. 세션 시작의 최대 대기 시간이 늘지 않게 하기 위해서다.
        deadline = gitcmd.Deadline(SYNC_FETCH_SECONDS)
        gitcmd.git(top, "fetch", "-q", "origin", deadline=deadline)
        notes += _main_notes(top, session_id, deadline)
        _move_main(top, session_id)
    except gitcmd.CommandTimeout:
        _, common = save_work._git_dirs(top)
        locks = sorted(str(path) for path in common.rglob("*.lock"))
        if locks:
            notes.append(LOCK_NOTE.format(seconds=SYNC_FETCH_SECONDS, locks=", ".join(locks)))
    except gitcmd.GitError:
        pass  # fetch 가 실패해도 세션 시작을 이어 간다
    current = save_work.current_branch(top)
    if current and current.startswith(save_work.WORK_PREFIXES) and save_work._ref_exists(top, save_work.REMOTE_REF,
                                                                                       None):
        count = save_work._count(top, f"HEAD..{save_work.REMOTE_REF}", None)
        if count:
            notes.append(BEHIND_NOTE.format(count=count))
    return notes


def _dirty_groups(top):
    counts = {}
    for path in shared_repo.worktree_paths(top):
        group = shared_repo.feature_of(path) or "공용"
        counts[group] = counts.get(group, 0) + 1
    order = sorted(name for name in counts if name != "공용") + (["공용"] if "공용" in counts else [])
    return ", ".join(f"{name} {counts[name]}개" for name in order)


def _unpushed_quietly(top):
    """세션 시작의 업로드 질문 판정이다. GitHub 확인(PR 상태)만 fetch 와 같은 상한 안에서 한다."""
    try:
        pending = save_work.pending_filter(top, gitcmd.Deadline(SYNC_FETCH_SECONDS), strict=True, record=False)
    except save_work.GH_ERRORS:
        pending = {"excluded": []}  # GitHub 를 확인하지 못하면 모든 작업 branch 를 센다
    try:
        return save_work.unpushed(top, pending=pending)
    except save_work.GH_ERRORS:
        return False  # 다음 commit 결과가 다시 알린다


def shared_context(top, session_id=None):
    # 다른 세션 확인(sync_shared)을 이 세션 표시보다 먼저 한다.
    notes = sync_shared(top, session_id)
    if session_id:
        session_mark.touch(top, session_id)
    current = save_work.current_branch(top)
    if current and save_work.is_intake_branch(top, current):
        # 기능 이전 중에는 이전 절차만 commit·업로드하므로 기능별 commit 안내를 넣지 않는다.
        notes.append(INTAKE_BRANCH_NOTE)
    # 지원 구조가 아니면 경로를 기능별로 묶을 기준이 없고, commit 도 하지 않는다.
    elif not shared_repo.supported(top):
        notes.insert(0, UNSUPPORTED_NOTE)
    else:
        notes.insert(0, SHARED_REMINDER)
        groups = _dirty_groups(top)
        if groups:
            notes.append(SHARED_DIRTY_NOTE.format(groups=groups))
        if _unpushed_quietly(top):
            notes.append(SHARED_UNPUSHED_NOTE)
    # 기능 코드 규칙은 기능 레포 구조를 정하므로 넣지 않는다. 개발자에게 하는 말의 git 용어 규칙만 넣는다.
    return "\n".join(notes) + "\n\n" + GIT_TERMS_PATH.read_text(encoding="utf-8")


def context_for(cwd, session_id=None):
    try:
        top = save_work.locate(cwd)
        if top is not None and shared_repo.repo_kind(top) == "shared":
            return shared_context(top, session_id)
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
