"""끊긴 기능 이전을 다시 실행할 때 어디서 이어 갈지 판정한다. 이전 절차는 실행할 때마다 이 판정을 맨 먼저 한다.

    python resume_state.py --central <중앙 레포> --feature-repo-name <기능 레포 이름> --feature <기능 이름>
    python resume_state.py --central <중앙 레포> --feature-repo-name <기능 레포 이름> --feature <기능 이름> --clean
    python resume_state.py --check                 # 가짜 레포(fixture)로 자체 시험

row 1: 이전 commit 이 main 에 있다. row 2: 이전 branch 가 업로드되었다(원격 branch 나 검토 요청이 있다).
row 3: 로컬에만 이전 branch 가 있다. row 4: 이전 흔적이 없다.
--clean 은 row 3 이고 기능 폴더와 진행 중 merge 밖에 commit 하지 않은 변경이 없을 때만, merge 를 취소하고 이전 branch 를 지운다.
조회가 하나라도 실패하면 status failed 를 내고 아무것도 지우지 않는다.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import intake_common as common


def _feature_branch(central: Path, feature: str) -> str | None:
    out = common.git(central, "config", "--get-regexp", r"^branch\..*\.kwfeature$", check=False)
    for line in out.splitlines():
        key, _, value = line.partition(" ")
        if value.strip() == feature:
            return key[len("branch."):-len(".kwfeature")]
    return None


def _uncommitted(central: Path, feature: str, merging: bool) -> list[str]:
    """기능 폴더와 진행 중 merge 가 바꾼 경로를 뺀, commit 하지 않은 경로. 이 경로는 다시 만들 수 없다."""
    merged: set[str] = set()
    if merging:  # 이력이 이어지지 않는 merge 에는 공통 조상이 없으므로 MERGE_HEAD 트리 전체가 merge 가 가져온 경로다
        base = common.git(central, "merge-base", "HEAD", "MERGE_HEAD", check=False).strip()
        merged = set(common.git_z(central, "diff", "--name-only", "-z", base, "MERGE_HEAD")) if base \
            else set(common.tree_files(central, "MERGE_HEAD"))
    paths = []
    for entry in common.git_z(central, "status", "--porcelain", "-z", "--untracked-files=all"):
        path = entry[3:]
        if path in merged or path.startswith((f"{common.FE_FEATURES}{feature}/", f"{common.BE_FEATURES}{feature}/")):
            continue
        paths.append(path)
    return paths


def run(central: Path, repo_name: str, feature: str, clean: bool = False) -> dict:
    result = {"status": "ok", "row": None, "intake": None, "branch": None, "pr_state": None,
              "merge_in_progress": False, "branch_commits": [], "uncommitted": [], "cleaned": False}
    try:
        common.git(central, "fetch", "-q", "origin")
        intake = common.find_intake(central, repo_name)
        if intake:
            return {**result, "row": 1, "intake": intake}
        branch = _feature_branch(central, feature)
        if branch is None:
            return {**result, "row": 4}
        remote = bool(common.git(central, "ls-remote", "--heads", "origin", branch).strip())
        owner, name = common.owner_name(common.git(central, "config", "--get", "remote.origin.url").strip())
        prs = common.gh_json("pr", "list", "-R", f"{owner}/{name}", "--head", branch, "--state", "all", "--json", "state") or []
    except Exception as exc:
        return {**result, "status": "failed", "detail": str(exc)}

    result["branch"] = branch
    result["pr_state"] = prs[0]["state"].lower() if prs else None
    result["branch_commits"] = common.git(central, "log", "--format=%s", f"origin/main..{branch}").splitlines()
    if remote or prs:
        return {**result, "row": 2}

    merging = common.merge_in_progress(central)
    result.update(row=3, merge_in_progress=merging, uncommitted=_uncommitted(central, feature, merging))
    if clean and not result["uncommitted"]:
        if merging:
            common.git(central, "merge", "--abort")
        common.git(central, "reset", "-q", "--hard", "HEAD")
        for folder in (f"{common.FE_FEATURES}{feature}/", f"{common.BE_FEATURES}{feature}/"):
            common.git(central, "clean", "-fdq", "--", folder)
        common.git(central, "switch", "-q", "--detach", "origin/main")
        common.git(central, "branch", "-q", "-D", branch)
        result["cleaned"] = True
    return result


CENTRAL_URL = "https://github.com/KiwoomAX/x-dashboard.git"
BRANCH = "feat/fund-aum-isarah-intake"


def _fixture(tmp: Path, message: str | None = None) -> Path:
    tmp.mkdir(parents=True, exist_ok=True)
    source = common.make_repo(tmp / "central-src", {"src/backend/main.py": "app = None\n", "README.md": "중앙\n"})
    if message:
        common.git(source, "commit", "-q", "--allow-empty", "-m", message)
    bare = tmp / "central.git"
    common.git(tmp, "clone", "-q", "--bare", str(source), str(bare))
    central = tmp / "중앙 레포"
    common.git(tmp, "clone", "-q", str(bare), str(central))
    common.git(central, "remote", "set-url", "origin", CENTRAL_URL)
    common.git(central, "config", f"url.{bare.as_posix()}.insteadOf", CENTRAL_URL)
    return central


def _intake_branch(central: Path) -> None:
    common.git(central, "switch", "-q", "-c", BRANCH)
    common.git(central, "config", f"branch.{BRANCH}.kwFeature", "fund-aum")
    common.commit_files(central, {"src/backend/feature_loader.py": "loader\n"}, "구조 파일 맞추기")


def _start_merge(central: Path, tmp: Path) -> None:
    other = common.make_repo(tmp / "기능", {"backend/router.py": "router = None\n"})
    common.git(central, "fetch", "-q", str(other), "main")
    common.git(central, "merge", "--allow-unrelated-histories", "--no-commit", "--no-ff", "-q", "FETCH_HEAD")


def _with_gh(answer, fn):
    real = common.gh_json

    def fake(*args):
        if isinstance(answer, Exception):
            raise answer
        return answer

    common.gh_json = fake
    try:
        return fn()
    finally:
        common.gh_json = real


def check_row1(tmp: Path) -> None:
    central = _fixture(tmp, "기능 이전\n\nIntake-From: KiwoomAX/fund-aum\nIntake-Head: abc\nIntake-History: yes")
    result = _with_gh([], lambda: run(central, "fund-aum", "fund-aum"))
    expected = common.git(central, "rev-parse", "origin/main").strip()
    assert result["row"] == 1 and result["intake"]["commit"] == expected, result


def check_row2_remote(tmp: Path) -> None:
    central = _fixture(tmp)
    _intake_branch(central)
    common.git(central, "push", "-q", "origin", BRANCH)
    result = _with_gh([], lambda: run(central, "fund-aum", "fund-aum"))
    assert result["row"] == 2 and result["branch"] == BRANCH and result["pr_state"] is None, result


def check_row2_closed_pr(tmp: Path) -> None:
    central = _fixture(tmp)
    _intake_branch(central)
    result = _with_gh([{"state": "CLOSED"}], lambda: run(central, "fund-aum", "fund-aum"))
    assert result["row"] == 2 and result["pr_state"] == "closed", result


def check_row3_merge(tmp: Path) -> None:
    central = _fixture(tmp)
    _intake_branch(central)
    _start_merge(central, tmp)
    result = _with_gh([], lambda: run(central, "fund-aum", "fund-aum"))
    assert result["row"] == 3 and result["merge_in_progress"], result
    assert result["branch_commits"] == ["구조 파일 맞추기"] and result["uncommitted"] == [], result
    assert not result["cleaned"]


def check_clean(tmp: Path) -> None:
    central = _fixture(tmp)
    _intake_branch(central)
    _start_merge(central, tmp)
    (central / "src/backend/features/fund-aum").mkdir(parents=True)
    (central / "src/backend/features/fund-aum/router.py").write_text("x\n", encoding="utf-8")
    common.git(central, "add", "-A")
    result = _with_gh([], lambda: run(central, "fund-aum", "fund-aum", clean=True))
    assert result["cleaned"], result
    assert not common.merge_in_progress(central)
    assert common.git(central, "rev-parse", "HEAD").strip() == common.git(central, "rev-parse", "origin/main").strip()
    assert common.git(central, "branch", "--show-current").strip() == ""
    assert not common.git(central, "branch", "--list", BRANCH).strip()
    assert common.git_z(central, "status", "--porcelain", "-z", "--untracked-files=all") == []


def check_clean_refused(tmp: Path) -> None:
    central = _fixture(tmp)
    _intake_branch(central)
    _start_merge(central, tmp)
    (central / "README.md").write_text("개발자가 고친 내용\n", encoding="utf-8")
    result = _with_gh([], lambda: run(central, "fund-aum", "fund-aum", clean=True))
    assert result["row"] == 3 and result["uncommitted"] == ["README.md"] and not result["cleaned"], result
    assert common.merge_in_progress(central)
    assert common.git(central, "branch", "--list", BRANCH).strip()


def check_row4(tmp: Path) -> None:
    central = _fixture(tmp)
    result = _with_gh([], lambda: run(central, "fund-aum", "fund-aum"))
    assert result["row"] == 4 and result["status"] == "ok", result


def check_lookup_failure(tmp: Path) -> None:
    central = _fixture(tmp / "a")
    _intake_branch(central)
    _start_merge(central, tmp / "a")
    result = _with_gh(RuntimeError("gh: HTTP 401"), lambda: run(central, "fund-aum", "fund-aum", clean=True))
    assert result["status"] == "failed" and result["row"] is None and not result["cleaned"], result
    assert common.git(central, "branch", "--list", BRANCH).strip() and common.merge_in_progress(central)
    central = _fixture(tmp / "b")
    common.git(central, "remote", "set-url", "origin", (tmp / "없는 원격.git").as_posix())
    result = _with_gh([], lambda: run(central, "fund-aum", "fund-aum", clean=True))
    assert result["status"] == "failed" and result["row"] is None, result


CHECKS = [
    check_row1, check_row2_remote, check_row2_closed_pr, check_row3_merge,
    check_clean, check_clean_refused, check_row4, check_lookup_failure,
]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--central")
    ap.add_argument("--feature-repo-name")
    ap.add_argument("--feature")
    ap.add_argument("--clean", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if args.check:
        return common.run_checks(CHECKS)
    try:
        return common.emit(run(Path(args.central), args.feature_repo_name, args.feature, args.clean))
    except Exception as exc:  # 약속대로 JSON 하나와 종료 코드 0 으로 끝낸다
        return common.emit({"status": "failed", "row": None, "cleaned": False, "detail": str(exc)})


if __name__ == "__main__":
    sys.exit(main())
