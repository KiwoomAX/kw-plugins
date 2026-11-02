"""과거 커밋이 검사에 걸렸을 때 예전 기록을 local-history 로 옮기고 지금 파일만으로 새 main 을 연다.

잘못 실행하면 예전 기록이 사라지는 동작이라 늘 이 순서로만 돈다. 이미 GitHub 에 연결한 레포에는
쓰지 않는다. 새 main 의 첫 커밋은 save_work.py 가 검사를 거쳐 만든다. local-history 는 올리지도
지우지도 않는다.
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import gitcmd

HISTORY_BRANCH = "local-history"
BRANCH = "main"
MESSAGE = "예전 파일 가운데 회사 밖으로 나가면 안 되는 것이 있어 지금 파일만 등록했습니다."
MSG_FAILED = "예전 기록을 정리하지 못했습니다. 이어서 확인합니다."


class ResetRefused(Exception):
    """옮기면 안 되는 상태라 아무것도 바꾸지 않았을 때 올린다."""


def _ok(top, *args):
    return gitcmd.git_try(top, *args)[0] == 0


def _branch_exists(top, name):
    return _ok(top, "rev-parse", "--verify", "-q", f"refs/heads/{name}")


def _keep_name(top, base, stamp, taken):
    """보관할 branch 이름을 고른다. 같은 이름이 있으면 시각과 번호를 붙여 기존 기록을 덮어쓰지 않는다."""
    name, number = base, 1
    while name in taken or _branch_exists(top, name):
        name = f"{base}-{stamp}" if number == 1 else f"{base}-{stamp}-{number}"
        number += 1
    taken.add(name)
    return name


def reset(repo, stamp=None):
    """예전 기록을 local-history 로 옮긴다. 보관한 다른 branch 의 {원래 이름: 새 이름} 을 돌려준다."""
    top = Path(gitcmd.git(repo, "rev-parse", "--show-toplevel").strip())
    stamp = stamp or datetime.now().strftime("%Y%m%d-%H%M%S")
    if _ok(top, "remote", "get-url", "origin"):
        raise ResetRefused("origin 이 이미 있다. 이미 연결한 레포의 기록은 이 스크립트로 옮기지 않는다.")
    if not _ok(top, "rev-parse", "--verify", "-q", "HEAD"):
        raise ResetRefused("커밋이 없어 옮길 기록이 없다.")
    code, branch, _ = gitcmd.git_try(top, "symbolic-ref", "--short", "-q", "HEAD")
    branch = branch.strip() if code == 0 else None
    kept, taken = {}, set()
    # 앞서 정리한 기록은 시각을 붙인 이름으로 옮겨 보관한다.
    if branch != HISTORY_BRANCH and _branch_exists(top, HISTORY_BRANCH):
        kept[HISTORY_BRANCH] = _keep_name(top, f"{HISTORY_BRANCH}-{stamp}", stamp, taken)
    # 다른 branch(남은 main 포함)는 local-history-<이름> 으로 보관한다. 이 이름은 업로드 대상이 아니다.
    for name in gitcmd.git(top, "for-each-ref", "--format=%(refname:short)", "refs/heads/").split():
        # 앞서 보관한 local-history-* 는 이미 업로드 대상이 아니라 그대로 둔다.
        if name in (branch, HISTORY_BRANCH) or name.startswith(f"{HISTORY_BRANCH}-"):
            continue
        kept[name] = _keep_name(top, f"{HISTORY_BRANCH}-{name.replace('/', '-')}", stamp, taken)
    for name, new_name in kept.items():
        gitcmd.git(top, "branch", "-m", name, new_name)
    if branch is None:
        # 분리된 HEAD 는 지금 commit 에 local-history 를 만들어 옮긴다.
        gitcmd.git(top, "branch", HISTORY_BRANCH, "HEAD")
    elif branch != HISTORY_BRANCH:
        gitcmd.git(top, "branch", "-m", branch, HISTORY_BRANCH)
    # checkout --orphan 은 작업 트리를 그대로 두고 부모 없는 main 을 연다. switch --orphan 은 파일을 지운다.
    gitcmd.git(top, "checkout", "-q", "--orphan", BRANCH)
    # 새 main 의 첫 저장이 모든 파일을 처음부터 검사하도록 인덱스를 비운다.
    gitcmd.git(top, "read-tree", "--empty")
    return kept


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="예전 기록을 local-history 로 옮기고 새 main 을 연다.")
    parser.add_argument("--repo", required=True)
    args = parser.parse_args(argv)
    try:
        kept = reset(Path(args.repo))
        payload = {"status": "reset", "message": MESSAGE, "kept": kept,
                   "detail": f"예전 기록은 {HISTORY_BRANCH} 에 있다. 이어서 save_work.py commit 으로 첫 commit 을 하라."}
    except ResetRefused as exc:
        payload = {"status": "refused", "message": MSG_FAILED, "kept": {}, "detail": str(exc)}
    except Exception as exc:  # noqa: BLE001 — 스킬은 어떤 경우에도 JSON 을 받아야 한다
        payload = {"status": "failed", "message": MSG_FAILED, "kept": {}, "detail": f"{exc.__class__.__name__}: {exc}"}
    # ASCII 로만 내보낸다. cp949 로 설정된 PowerShell 이 출력을 담아도 한글이 깨지지 않는다.
    print(json.dumps(payload))
    return 0 if payload["status"] == "reset" else 1


if __name__ == "__main__":
    raise SystemExit(main())
