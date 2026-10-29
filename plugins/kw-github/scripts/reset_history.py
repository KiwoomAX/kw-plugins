"""과거 커밋이 검사에 걸렸을 때 예전 기록을 local-history 로 옮기고 지금 파일만으로 새 main 을 연다.

잘못 실행하면 예전 기록이 사라지는 동작이라 늘 이 순서로만 돈다. 이미 GitHub 에 연결한 레포에는
쓰지 않는다. 새 main 의 첫 커밋은 save_work.py 가 검사를 거쳐 만든다. local-history 는 올리지도
지우지도 않는다.
"""
import argparse
import json
import sys
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


def reset(repo):
    top = Path(gitcmd.git(repo, "rev-parse", "--show-toplevel").strip())
    if _ok(top, "remote", "get-url", "origin"):
        raise ResetRefused("origin 이 이미 있다. 이미 연결한 레포의 기록은 이 스크립트로 옮기지 않는다.")
    if _ok(top, "rev-parse", "--verify", "-q", f"refs/heads/{HISTORY_BRANCH}"):
        raise ResetRefused(f"{HISTORY_BRANCH} 가 이미 있다. 예전 기록을 덮어쓰지 않도록 멈췄다.")
    code, branch, _ = gitcmd.git_try(top, "symbolic-ref", "--short", "-q", "HEAD")
    if code != 0:
        raise ResetRefused("HEAD 가 분리되어 있다. 브랜치로 돌아간 뒤 다시 부른다.")
    if not _ok(top, "rev-parse", "--verify", "-q", "HEAD"):
        raise ResetRefused("커밋이 없어 옮길 기록이 없다.")
    branch = branch.strip()
    # 지금 branch 만 옮기므로, 남은 main 이 있으면 checkout --orphan main 이 실패해 중간 상태로 끝난다.
    if branch != BRANCH and _ok(top, "rev-parse", "--verify", "-q", f"refs/heads/{BRANCH}"):
        raise ResetRefused(f"{BRANCH} 가 따로 있다. 지금 branch {branch} 만 옮기면 새 {BRANCH} 를 열지 못해 멈췄다.")
    # 다른 branch 의 예전 commit 은 옮겨지지 않아 나중에 함께 올라갈 수 있다.
    others = [name for name in gitcmd.git(top, "for-each-ref", "--format=%(refname:short)", "refs/heads/").split()
              if name != branch]
    if others:
        raise ResetRefused(f"다른 branch 가 있다: {', '.join(others)}. 그 기록은 옮기지 않으므로 멈췄다.")
    gitcmd.git(top, "branch", "-m", branch, HISTORY_BRANCH)
    # checkout --orphan 은 작업 트리를 그대로 두고 부모 없는 main 을 연다. switch --orphan 은 파일을 지운다.
    gitcmd.git(top, "checkout", "-q", "--orphan", BRANCH)
    # 새 main 의 첫 저장이 모든 파일을 처음부터 검사하도록 인덱스를 비운다.
    gitcmd.git(top, "read-tree", "--empty")
    return top


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="예전 기록을 local-history 로 옮기고 새 main 을 연다.")
    parser.add_argument("--repo", required=True)
    args = parser.parse_args(argv)
    try:
        reset(Path(args.repo))
        payload = {"status": "reset", "message": MESSAGE,
                   "detail": f"예전 기록은 {HISTORY_BRANCH} 에 있다. 이어서 save_work.py commit 으로 첫 commit 을 하라."}
    except ResetRefused as exc:
        payload = {"status": "refused", "message": MSG_FAILED, "detail": str(exc)}
    except Exception as exc:  # noqa: BLE001 — 스킬은 어떤 경우에도 JSON 을 받아야 한다
        payload = {"status": "failed", "message": MSG_FAILED, "detail": f"{exc.__class__.__name__}: {exc}"}
    # ASCII 로만 내보낸다. cp949 로 설정된 PowerShell 이 출력을 담아도 한글이 깨지지 않는다.
    print(json.dumps(payload))
    return 0 if payload["status"] == "reset" else 1


if __name__ == "__main__":
    raise SystemExit(main())
