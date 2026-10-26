"""기능 이전 2단계에서 기능 레포의 상태를 확인한다. 기능 레포는 읽기만 한다.

    python check_feature.py --feature-repo <기능 레포 폴더>
    python check_feature.py --check                            # 가짜 레포(fixture)로 자체 시험

결과는 JSON 하나다. status 는 ok, stop(commit 하지 않은 변경이 있거나 진입점이 없음), failed(기본 branch 를 알 수 없음)다.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import intake_common as common


def _dirty(repo: Path) -> list[str]:
    entries = common.git_z(repo, "status", "--porcelain", "-z", "--untracked-files=all")
    paths, skip = [], False
    for entry in entries:
        if skip:  # 이름 바꾸기·복사 항목 뒤에 오는 옛 경로
            skip = False
            continue
        paths.append(entry[3:])
        skip = entry[0] in "RC"
    return paths


def check(repo: Path) -> dict:
    result = {"status": "ok", "default_branch": None, "dirty": [], "entry": {"frontend": False, "backend": False},
              "other_branches": []}
    branch = common.default_branch(repo)
    if branch is None:
        return {**result, "status": "failed", "detail": "원격의 기본 branch 를 알 수 없다"}
    result["default_branch"] = branch
    ref = branch if common.git(repo, "rev-parse", "--verify", "--quiet", branch, check=False).strip() else f"origin/{branch}"
    result["dirty"] = _dirty(repo)
    result["entry"] = {"frontend": common.blob(repo, ref, "frontend/index.tsx") is not None,
                       "backend": common.blob(repo, ref, "backend/router.py") is not None}
    for name in common.git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads").split():
        if name in (branch, "local-history"):
            continue
        ahead = int(common.git(repo, "rev-list", "--count", f"{ref}..{name}").strip())
        if ahead:
            subject = common.git(repo, "log", "-1", "--format=%s", name).strip()
            result["other_branches"].append({"name": name, "ahead": ahead, "last_subject": subject})
    if result["dirty"] or not any(result["entry"].values()):
        result["status"] = "stop"
    return result


FEATURE_FILES = {
    "frontend/index.tsx": "export default function Page() { return null }\n",
    "backend/router.py": "from fastapi import APIRouter\nrouter = APIRouter()\n",
    ".gitignore": ".env\n",
}


def _pushed(tmp: Path, files: dict, branch: str = "main") -> Path:
    """로컬에서 만든 뒤 push 한 기능 레포를 만든다. 이렇게 만든 레포에는 origin/HEAD 가 없다."""
    tmp.mkdir(parents=True, exist_ok=True)
    bare = tmp / "remote.git"
    common.git(tmp, "init", "-q", "--bare", "-b", branch, str(bare))
    repo = tmp / "김연수 작업" / "fund-aum"
    repo.mkdir(parents=True)
    common.git(repo, "init", "-q", "-b", branch)
    common.commit_files(repo, files, "init")
    common.git(repo, "remote", "add", "origin", bare.as_posix())
    common.git(repo, "push", "-q", "origin", branch)
    return repo


def check_clone_master(tmp: Path) -> None:
    source = common.make_repo(tmp / "src", FEATURE_FILES)
    common.git(source, "branch", "-m", "master")
    bare = tmp / "remote.git"
    common.git(tmp, "clone", "-q", "--bare", str(source), str(bare))
    repo = tmp / "김연수 작업" / "fund-aum"
    common.git(tmp, "clone", "-q", str(bare), str(repo))
    assert check(repo)["default_branch"] == "master"


def check_no_origin_head(tmp: Path) -> None:
    repo = _pushed(tmp, FEATURE_FILES)
    has_head = common.git(repo, "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD", check=False).strip()
    assert not has_head, "fixture 에 origin/HEAD 가 없어야 한다"
    result = check(repo)
    assert result["default_branch"] == "main" and result["status"] == "ok", result


def check_no_remote_branch(tmp: Path) -> None:
    repo = _pushed(tmp, FEATURE_FILES)
    common.git(repo, "remote", "set-url", "origin", (tmp / "없는 원격.git").as_posix())
    result = check(repo)
    assert result["default_branch"] is None and result["status"] == "failed", result


def check_dirty_tracked(tmp: Path) -> None:
    repo = _pushed(tmp, FEATURE_FILES)
    (repo / "frontend/index.tsx").write_text("changed\n", encoding="utf-8")
    result = check(repo)
    assert result["dirty"] == ["frontend/index.tsx"] and result["status"] == "stop", result


def check_dirty_untracked(tmp: Path) -> None:
    repo = _pushed(tmp, FEATURE_FILES)
    (repo / "backend/new api.py").write_text("x = 1\n", encoding="utf-8")
    result = check(repo)
    assert "backend/new api.py" in result["dirty"] and result["status"] == "stop", result


def check_ignored_not_dirty(tmp: Path) -> None:
    repo = _pushed(tmp, FEATURE_FILES)
    (repo / ".env").write_text("KEY=1\n", encoding="utf-8")
    result = check(repo)
    assert result["dirty"] == [] and result["status"] == "ok", result


def check_entry(tmp: Path) -> None:
    files = {k: v for k, v in FEATURE_FILES.items() if k != "backend/router.py"}
    result = check(_pushed(tmp / "a", files))
    assert result["entry"] == {"frontend": True, "backend": False} and result["status"] == "ok", result
    result = check(_pushed(tmp / "b", {"README.md": "x\n"}))
    assert result["entry"] == {"frontend": False, "backend": False} and result["status"] == "stop", result


def check_other_branch(tmp: Path) -> None:
    repo = _pushed(tmp, FEATURE_FILES)
    common.git(repo, "switch", "-q", "-c", "feat/x")
    common.commit_files(repo, {"backend/extra.py": "y = 2\n"}, "추가 기능")
    common.git(repo, "switch", "-q", "-c", "local-history")
    common.commit_files(repo, {"old.txt": "old\n"}, "옛 기록")
    common.git(repo, "switch", "-q", "main")
    result = check(repo)
    assert result["other_branches"] == [{"name": "feat/x", "ahead": 1, "last_subject": "추가 기능"}], result


CHECKS = [
    check_clone_master, check_no_origin_head, check_no_remote_branch, check_dirty_tracked,
    check_dirty_untracked, check_ignored_not_dirty, check_entry, check_other_branch,
]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--feature-repo")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if args.check:
        return common.run_checks(CHECKS)
    try:
        return common.emit(check(Path(args.feature_repo)))
    except Exception as exc:  # 약속대로 JSON 하나와 종료 코드 0 으로 끝낸다
        return common.emit({"status": "failed", "detail": str(exc)})


if __name__ == "__main__":
    sys.exit(main())
