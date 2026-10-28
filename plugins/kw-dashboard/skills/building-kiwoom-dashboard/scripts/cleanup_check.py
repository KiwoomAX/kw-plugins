"""기능 이전 12단계에서 기능 레포를 지우기 전에 사라질 수 있는 것을 점검한다. 기능 레포는 읽기만 한다.

    python cleanup_check.py --central <중앙 레포> --feature-repo <기능 레포> --feature-repo-name <기능 레포 이름> --feature <기능 이름>
    python cleanup_check.py --check                 # 가짜 레포(fixture)로 자체 시험

점검마다 action 을 낸다. pass 는 통과, confirm 은 개발자에게 목록을 보여 주고 처분을 받아야 함, stop 은 삭제 안내를 멈춤이다.
조회가 실패한 점검은 stop 이고 status 는 failed 다. 포트 등록부와 Jenkins 잡 검색은 이 스크립트가 하지 않는다.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import import_feature as imp
import intake_common as common


def _tracked(feature_repo: Path, ref: str) -> list[tuple[str, int]]:
    files = []
    for line in common.git_z(feature_repo, "ls-tree", "-r", "-l", "-z", ref):
        meta, path = line.split("\t", 1)
        size = meta.split()[3]
        files.append((path, int(size) if size.isdigit() else 0))
    return files


def _status_paths(feature_repo: Path) -> list[str]:
    """commit 하지 않은 모든 경로(무시된 파일, 추적하지 않는 파일, 고친 파일)."""
    paths, skip = [], False
    for entry in common.git_z(feature_repo, "status", "--ignored", "--porcelain", "-z", "--untracked-files=all"):
        if skip:
            skip = False
            continue
        paths.append(entry[3:])
        skip = entry[0] in "RC"
    return paths


def _action(items: list, when: str) -> str:
    return when if items else "pass"


def run(central: Path, feature_repo: Path, repo_name: str, feature: str) -> dict:
    checks: list[dict] = []
    failed = False

    def lookup_failed(name: str, exc: Exception) -> None:
        nonlocal failed
        failed = True
        checks.append({"name": name, "action": "stop", "items": [str(exc)]})

    common.git(central, "fetch", "-q", "origin")
    intake = common.find_intake(central, repo_name)
    if intake is None:
        return {"status": "stop", "intake": None, "checks": [], "detail": "main 에서 이 기능 레포의 이전 commit 을 찾지 못했다"}
    branch = common.default_branch(feature_repo)
    if branch is None:
        return {"status": "failed", "intake": intake, "checks": [], "detail": "기능 레포의 기본 branch 를 알 수 없다"}

    try:
        common.git(feature_repo, "fetch", "-q", "origin")
        heads = []
        local = common.git(feature_repo, "rev-parse", "--verify", "--quiet", branch, check=False).strip()
        if local and local != intake["head"]:
            heads.append({"where": "local", "head": local})
        remote = common.git(feature_repo, "rev-parse", "--verify", "--quiet", f"origin/{branch}", check=False).strip()
        if remote and remote != intake["head"]:
            heads.append({"where": "remote", "head": remote})
        checks.append({"name": "new-commits", "action": _action(heads, "stop"), "items": heads})
        unpushed = []
        for name in common.git(feature_repo, "for-each-ref", "--format=%(refname:short)", "refs/heads").split():
            subjects = common.git(feature_repo, "log", "--format=%s", name, "--not", "--remotes=origin").splitlines()
            if subjects:
                unpushed.append({"branch": name, "subjects": subjects})
        checks.append({"name": "unpushed", "action": _action(unpushed, "confirm"), "items": unpushed})
    except Exception as exc:
        lookup_failed("new-commits", exc)

    pc_only = [p for p in _status_paths(feature_repo) if not common.is_generated(p)]
    checks.append({"name": "pc-only", "action": _action(pc_only, "confirm"), "items": pc_only})

    entries = imp.top_entries(feature_repo, intake["head"])
    has_backend = "backend/" in entries
    groups = imp.classify_top(entries, has_backend)
    central_tree = set(common.tree_files(central, "origin/main"))

    def moved_to(path: str) -> str:
        entry = path.split("/", 1)[0] + "/" if "/" in path else path
        base = imp.destination(entry, feature, has_backend)
        return base + path[len(entry):] if entry.endswith("/") else base

    tracked = _tracked(feature_repo, intake["head"])
    def size_of(path: str) -> int:  # commit 하지 않고 지운 추적 파일은 크기 없이 확장자로만 판정한다
        target = feature_repo / path
        return target.stat().st_size if target.is_file() else 0

    data = [p for p in pc_only if not p.endswith("/") and common.is_data(p, size_of(p))]
    data += [p for p, size in tracked if common.is_data(p, size) and moved_to(p) not in central_tree]
    checks.append({"name": "data-files", "action": _action(data, "confirm"), "items": data})

    not_moved = []
    if intake["history"] == "no":
        for path, size in tracked:
            entry = path.split("/", 1)[0] + "/" if "/" in path else path
            if entry in groups["skip"] or common.is_data(path, size):
                continue
            if moved_to(path) not in central_tree:
                not_moved.append(path)
    checks.append({"name": "not-moved", "action": _action(not_moved, "confirm"), "items": not_moved})

    for name, fields in (("issues", "number,title,body"), ("prs", "number,title")):
        kind = "issue" if name == "issues" else "pr"
        try:
            items = common.gh_json(kind, "list", "-R", f"KiwoomAX/{repo_name}", "--state", "open", "--limit", "1000",
                                   "--json", fields) or []  # gh 기본값은 30건이라 31번째부터 점검에서 빠진다
            checks.append({"name": name, "action": _action(items, "confirm"), "items": items})
        except Exception as exc:
            lookup_failed(name, exc)

    status = "failed" if failed else ("stop" if any(c["action"] == "stop" for c in checks) else "ok")
    return {"status": status, "intake": intake, "checks": checks}


BASE_FILES = {
    "frontend/index.tsx": "export default function Page() { return null }\n",
    "backend/router.py": "from fastapi import APIRouter\nrouter = APIRouter()\n",
    "README.md": "기능 설명\n",
    ".gitignore": "내 데이터.xlsx\n.venv/\nnode_modules/\n",
}


def _top(path: str) -> str:
    return path.split("/", 1)[0] + "/" if "/" in path else path


def _fixture(tmp: Path, files: dict, history: str = "yes", not_moved: tuple = ()) -> tuple[Path, Path]:
    """기능 레포(원격에 push 됨)와, 그 레포를 기능 이름 fund_aum 으로 이전해 반영한 중앙 레포를 만든다.

    not_moved 에 든 기능 레포 경로는 중앙 레포에 넣지 않는다. 데이터 파일과 옮기지 않는 파일도 넣지 않는다.
    """
    tmp.mkdir(parents=True, exist_ok=True)
    remote = tmp / "feature.git"
    common.git(tmp, "init", "-q", "--bare", "-b", "main", str(remote))
    feature = tmp / "홍길동 작업" / "fund-aum"
    feature.mkdir(parents=True)
    common.git(feature, "init", "-q", "-b", "main")
    common.commit_files(feature, files, "init")
    common.git(feature, "remote", "add", "origin", remote.as_posix())
    common.git(feature, "push", "-q", "origin", "main")
    head = common.git(feature, "rev-parse", "main").strip()

    entries = imp.top_entries(feature, "main")
    has_backend = "backend/" in entries
    groups = imp.classify_top(entries, has_backend)
    central_files = {"src/backend/main.py": "app = None\n"}
    for path, text in files.items():
        entry = _top(path)
        if entry not in groups["move"] or path in not_moved or common.is_data(path, len(text.encode())):
            continue
        base = imp.destination(entry, "fund_aum", has_backend)
        central_files[base + path[len(entry):] if entry.endswith("/") else base] = text
    source = common.make_repo(tmp / "central-src", central_files,
                              f"기능 이전\n\nIntake-From: KiwoomAX/fund-aum\nIntake-Head: {head}\nIntake-History: {history}")
    bare = tmp / "central.git"
    common.git(tmp, "clone", "-q", "--bare", str(source), str(bare))
    central = tmp / "중앙 레포"
    common.git(tmp, "clone", "-q", str(bare), str(central))
    return central, feature


def _run(central: Path, feature: Path, gh=None) -> dict:
    real = common.gh_json

    def fake(*args):
        if isinstance(gh, Exception):
            raise gh
        return gh or []

    common.gh_json = fake
    try:
        return run(central, feature, "fund-aum", "fund_aum")
    finally:
        common.gh_json = real


def _check(result: dict, name: str) -> dict:
    return next(c for c in result["checks"] if c["name"] == name)


def check_clean_state(tmp: Path) -> None:
    result = _run(*_fixture(tmp, BASE_FILES))
    assert result["status"] == "ok", result
    assert all(c["action"] == "pass" for c in result["checks"]), result
    assert {c["name"] for c in result["checks"]} == {
        "new-commits", "unpushed", "pc-only", "data-files", "not-moved", "issues", "prs"}


def check_new_commit(tmp: Path) -> None:
    central, feature = _fixture(tmp, BASE_FILES)
    common.commit_files(feature, {"backend/later.py": "x = 1\n"}, "이전 뒤 수정")
    result = _run(central, feature)
    assert _check(result, "new-commits")["action"] == "stop" and result["status"] == "stop", result


def check_unpushed(tmp: Path) -> None:
    central, feature = _fixture(tmp, BASE_FILES)
    common.git(feature, "switch", "-q", "-c", "feat/y")
    common.commit_files(feature, {"backend/y.py": "y = 1\n"}, "올리지 않은 작업")
    common.git(feature, "switch", "-q", "main")
    unpushed = _check(_run(central, feature), "unpushed")
    assert unpushed["action"] == "confirm", unpushed
    assert unpushed["items"] == [{"branch": "feat/y", "subjects": ["올리지 않은 작업"]}], unpushed


def check_pc_only(tmp: Path) -> None:
    central, feature = _fixture(tmp, BASE_FILES)
    for path in ("내 데이터.xlsx", ".venv/x", "frontend/node_modules/a.js"):
        (feature / path).parent.mkdir(parents=True, exist_ok=True)
        (feature / path).write_text("x\n", encoding="utf-8")
    result = _run(central, feature)
    assert _check(result, "pc-only")["items"] == ["내 데이터.xlsx"], result
    assert _check(result, "pc-only")["action"] == "confirm"
    assert "내 데이터.xlsx" in _check(result, "data-files")["items"]


def check_data_files(tmp: Path) -> None:
    files = {**BASE_FILES, "data.xlsx": "엑셀\n", "backend/sample.xlsx": "엑셀\n"}
    data = _check(_run(*_fixture(tmp, files, history="no")), "data-files")
    assert sorted(data["items"]) == ["backend/sample.xlsx", "data.xlsx"] and data["action"] == "confirm", data


def check_big_json(tmp: Path) -> None:
    files = {**BASE_FILES, "backend/data.json": "[" + "1," * 80000 + "1]"}
    data = _check(_run(*_fixture(tmp, files)), "data-files")
    assert data["items"] == ["backend/data.json"], data


def check_not_moved_no(tmp: Path) -> None:
    files = {**BASE_FILES, "notes.txt": "메모\n"}
    result = _run(*_fixture(tmp, files, history="no"))
    moved = _check(result, "not-moved")
    assert moved["items"] == ["notes.txt"] and moved["action"] == "confirm" and result["status"] == "ok", result


def check_not_moved_yes(tmp: Path) -> None:
    files = {**BASE_FILES, "notes.txt": "메모\n"}
    moved = _check(_run(*_fixture(tmp, files, history="yes")), "not-moved")
    assert moved["items"] == [] and moved["action"] == "pass", moved


def check_feature_name_differs(tmp: Path) -> None:
    result = _run(*_fixture(tmp, BASE_FILES, history="no"))
    assert _check(result, "not-moved")["items"] == [], result
    result = _run(*_fixture(tmp / "b", BASE_FILES, history="no", not_moved=("backend/router.py",)))
    assert _check(result, "not-moved")["items"] == ["backend/router.py"], result


def check_gh_failure(tmp: Path) -> None:
    result = _run(*_fixture(tmp, BASE_FILES), gh=RuntimeError("gh: HTTP 401"))
    assert _check(result, "issues")["action"] == "stop" and result["status"] == "failed", result


def check_deleted_tracked_file(tmp: Path) -> None:
    central, feature = _fixture(tmp, {**BASE_FILES, "backend/sample.xlsx": "엑셀\n"})
    (feature / "backend/router.py").unlink()
    (feature / "backend/sample.xlsx").unlink()
    result = _run(central, feature)
    assert result["status"] == "ok" or result["status"] == "stop", result
    pc_only = _check(result, "pc-only")["items"]
    assert "backend/router.py" in pc_only and "backend/sample.xlsx" in pc_only, result
    assert "backend/sample.xlsx" in _check(result, "data-files")["items"], result


def check_gh_limit(tmp: Path) -> None:
    central, feature = _fixture(tmp, BASE_FILES)
    calls = []
    real = common.gh_json

    def fake(*args):
        calls.append(args)
        return []

    common.gh_json = fake
    try:
        run(central, feature, "fund-aum", "fund_aum")
    finally:
        common.gh_json = real
    lists = [c for c in calls if "list" in c]
    assert lists and all("--limit" in c for c in lists), calls


CHECKS = [
    check_gh_limit,
    check_deleted_tracked_file,
    check_clean_state, check_new_commit, check_unpushed, check_pc_only, check_data_files,
    check_big_json, check_not_moved_no, check_not_moved_yes, check_feature_name_differs, check_gh_failure,
]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--central")
    ap.add_argument("--feature-repo")
    ap.add_argument("--feature-repo-name")
    ap.add_argument("--feature")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if args.check:
        return common.run_checks(CHECKS)
    try:
        return common.emit(run(Path(args.central), Path(args.feature_repo), args.feature_repo_name, args.feature))
    except Exception as exc:  # 약속대로 JSON 하나와 종료 코드 0 으로 끝낸다
        return common.emit({"status": "failed", "detail": str(exc), "checks": []})


if __name__ == "__main__":
    sys.exit(main())
