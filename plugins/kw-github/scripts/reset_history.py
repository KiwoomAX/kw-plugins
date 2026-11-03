"""과거 커밋이 검사에 걸렸을 때 예전 기록을 local-history 로 옮기고 지금 파일만으로 새 main 을 연다.

잘못 실행하면 예전 기록이 사라지는 동작이라 늘 이 순서로만 돈다. 이미 GitHub 에 연결한 레포에는
쓰지 않는다. 다른 branch 와 앞서 정리한 local-history 는 local-history-<이름> 으로 보관한다. branch 이름은
update-ref 한 번으로 함께 바꾸므로 중간에 실패해도 하나도 바뀌지 않는다. 새 main 의 첫 커밋은
save_work.py 가 검사를 거쳐 만든다. local-history 와 local-history-* 는 올리지도 지우지도 않는다.
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
# 이 표시 파일이 있으면 merge·rebase·cherry-pick·revert 가 진행 중이다.
IN_PROGRESS = ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "rebase-merge", "rebase-apply")


def is_history_branch(name):
    """보관한 예전 기록 branch 인지 본다. 이 branch 는 업로드·이전·정리 대상이 아니다."""
    return name == HISTORY_BRANCH or name.startswith(f"{HISTORY_BRANCH}-")


class ResetRefused(Exception):
    """옮기면 안 되는 상태라 아무것도 바꾸지 않았을 때 올린다. reason 은 스킬이 읽는 구분값이다."""

    def __init__(self, reason, message, branches=()):
        super().__init__(message)
        self.reason = reason
        self.branches = list(branches)


def _ok(top, *args):
    return gitcmd.git_try(top, *args)[0] == 0


def _heads(top):
    """{branch 이름: commit} 이다. lstrip=2 는 같은 이름의 tag 가 있어도 heads/ 를 붙이지 않는다."""
    out = gitcmd.git(top, "for-each-ref", "--format=%(refname:lstrip=2) %(objectname)", "refs/heads/")
    return dict(line.split(" ", 1) for line in out.splitlines() if line.strip())


def _clashes(name, names):
    """같은 이름이거나, 한쪽이 다른 쪽의 상위 폴더라 ref 파일을 만들 수 없으면 참이다."""
    return any(name == other or other.startswith(f"{name}/") or name.startswith(f"{other}/") for other in names)


def _keep_name(base, stamp, taken):
    """보관할 branch 이름을 고른다. 쓰이는 이름과 겹치면 시각과 번호를 붙여 기존 기록을 덮어쓰지 않는다."""
    name, number = base, 1
    while _clashes(name, taken):
        name = f"{base}-{stamp}" if number == 1 else f"{base}-{stamp}-{number}"
        number += 1
    taken.add(name)
    return name


def _check_state(top):
    if _ok(top, "remote", "get-url", "origin"):
        raise ResetRefused("connected", "origin 이 이미 있다. 이미 연결한 레포의 기록은 이 스크립트로 옮기지 않는다.")
    for mark in IN_PROGRESS:
        path = Path(gitcmd.git(top, "rev-parse", "--git-path", mark).strip())
        if not path.is_absolute():
            path = top / path
        if path.exists():
            raise ResetRefused("in-progress", f"진행 중인 git 작업이 있다({mark}). 그 작업을 마치거나 취소한 뒤 다시 실행한다.")
    if gitcmd.git(top, "ls-files", "-u").strip():
        raise ResetRefused("in-progress", "충돌을 풀지 않은 파일이 있다. 충돌을 푼 뒤 다시 실행한다.")


def _attach_head(top, heads):
    """분리된 HEAD 를 같은 commit 의 branch 로 돌린다. 그런 branch 가 없으면 거부한다."""
    head = gitcmd.git(top, "rev-parse", "HEAD").strip()
    same = sorted(name for name, sha in heads.items() if sha == head and not is_history_branch(name))
    if not same:
        newer = sorted(name for name in heads if not is_history_branch(name))
        raise ResetRefused("detached", "HEAD 가 분리되어 있고 지금 폴더는 어느 branch 의 끝도 아닌 예전 시점이다. "
                           "개발자에게 최신 작업으로 돌아갈지 묻는다.", newer)
    branch = BRANCH if BRANCH in same else same[0]
    # 같은 commit 이라 파일은 바뀌지 않는다.
    gitcmd.git(top, "switch", "-q", branch)
    return branch


def reset(repo, stamp=None):
    """예전 기록을 local-history 로 옮긴다. 보관한 다른 branch 의 {원래 이름: 새 이름} 을 돌려준다."""
    top = Path(gitcmd.git(repo, "rev-parse", "--show-toplevel").strip())
    stamp = stamp or datetime.now().strftime("%Y%m%d-%H%M%S")
    _check_state(top)
    heads = _heads(top)
    code, branch, _ = gitcmd.git_try(top, "symbolic-ref", "--short", "-q", "HEAD")
    branch = branch.strip() if code == 0 else None
    if not _ok(top, "rev-parse", "--verify", "-q", "HEAD"):
        if branch and HISTORY_BRANCH in heads:
            # 앞선 실행이 branch 를 옮긴 뒤 멈췄다. HEAD 가 가리키는 branch 가 없다. 남은 단계만 마친다.
            gitcmd.git(top, "symbolic-ref", "HEAD", f"refs/heads/{BRANCH}")
            gitcmd.git(top, "read-tree", "--empty")
            return {}
        raise ResetRefused("no-commits", "커밋이 없어 옮길 기록이 없다.")
    if branch is None:
        branch = _attach_head(top, heads)
    taken = set(heads)
    kept = {}
    # 앞서 정리한 기록은 시각을 붙인 이름으로 보관한다.
    if branch != HISTORY_BRANCH and HISTORY_BRANCH in heads:
        kept[HISTORY_BRANCH] = _keep_name(f"{HISTORY_BRANCH}-{stamp}", stamp, taken)
    # 다른 branch(남은 main 포함)는 local-history-<이름> 으로 보관한다. 앞서 보관한 것은 그대로 둔다.
    for name in heads:
        if name != branch and not is_history_branch(name):
            kept[name] = _keep_name(f"{HISTORY_BRANCH}-{name.replace('/', '-')}", stamp, taken)
    moves = dict(kept)
    if branch != HISTORY_BRANCH:
        moves[branch] = HISTORY_BRANCH
    # 새 이름을 만들고 옛 이름을 지운다. 같은 이름이 양쪽에 있으면(local-history) update 로 바꾼다.
    created = {new: heads[old] for old, new in moves.items()}
    lines = []
    for new, sha in created.items():
        lines.append(f"update refs/heads/{new} {sha} {heads[new]}" if new in moves else f"create refs/heads/{new} {sha}")
    lines += [f"delete refs/heads/{old} {heads[old]}" for old in moves if old not in created]
    if lines:
        gitcmd.git(top, "update-ref", "--stdin", stdin=("\n".join(lines) + "\n").encode("utf-8"))
    # 작업 트리를 그대로 두고 부모 없는 main 을 연다. 첫 저장이 모든 파일을 처음부터 검사하도록 인덱스를 비운다.
    gitcmd.git(top, "symbolic-ref", "HEAD", f"refs/heads/{BRANCH}")
    gitcmd.git(top, "read-tree", "--empty")
    return kept


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="예전 기록을 local-history 로 옮기고 새 main 을 연다.")
    parser.add_argument("--repo", required=True)
    args = parser.parse_args(argv)
    try:
        kept = reset(Path(args.repo))
        payload = {"status": "reset", "reason": "", "message": MESSAGE, "kept": kept, "branches": [],
                   "detail": f"예전 기록은 {HISTORY_BRANCH} 에 있다. 이어서 save_work.py commit 으로 첫 commit 을 하라."}
    except ResetRefused as exc:
        payload = {"status": "refused", "reason": exc.reason, "message": MSG_FAILED, "kept": {},
                   "branches": exc.branches, "detail": str(exc)}
    except Exception as exc:  # noqa: BLE001 — 스킬은 어떤 경우에도 JSON 을 받아야 한다
        payload = {"status": "failed", "reason": "", "message": MSG_FAILED, "kept": {}, "branches": [],
                   "detail": f"{exc.__class__.__name__}: {exc}"}
    # ASCII 로만 내보낸다. cp949 로 설정된 PowerShell 이 출력을 담아도 한글이 깨지지 않는다.
    print(json.dumps(payload))
    return 0 if payload["status"] == "reset" else 1


if __name__ == "__main__":
    sys.exit(main())
