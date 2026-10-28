"""기능 이전 3단계에서 기능 레포의 파일을 중앙 레포의 기능 폴더로 들여온다. commit 은 하지 않는다.

    python import_feature.py --central <중앙 레포> --feature-repo <기능 레포> --feature <기능 이름> --branch <기본 branch> --history yes --plan
    python import_feature.py --central <중앙 레포> --feature-repo <기능 레포> --feature <기능 이름> --branch <기본 branch> --history yes|no [--extra <경로>]... [--exclude <경로>]...
    python import_feature.py --check                     # 가짜 레포(fixture)로 자체 시험

--plan 은 최상위 항목을 move(옮김)·skip(옮기지 않음)·ask(개발자에게 물음)로 나눠 보여 주기만 한다.
실행하면 이력을 가져올 때(--history yes)는 진행 중 merge 상태로, 이력 없이 가져올 때는 stage 한 상태로 끝난다.
그다음 commit 은 kw-github 저장 명령(--intake)으로 한다.
"""
from __future__ import annotations

import argparse
import fnmatch
import shutil
import sys
from pathlib import Path

import intake_common as common


SKIP_NAMES = {
    "requirements.txt", "package.json", "package-lock.json", ".env", ".gitignore", ".kiwoom-feature", ".venv/",
    "node_modules/", "docker-compose.yml", "Jenkinsfile", "dev/", "dev_app.py", "index.html", "tsconfig.json",
}
SKIP_PATTERNS = (".env.*", "tsconfig.*.json", "vite.config.*", "tailwind.config.*", "postcss.config.*")


def classify_top(entries: list[str], has_backend: bool) -> dict[str, list[str]]:
    """기능 레포의 최상위 항목(폴더는 끝에 / 를 붙인다)을 move·skip·ask 로 나눈다."""
    result = {"move": [], "skip": [], "ask": []}
    for entry in entries:
        if entry in ("frontend/", "backend/", "README.md") or (entry == "tests/" and has_backend):
            result["move"].append(entry)
        elif entry in SKIP_NAMES or any(fnmatch.fnmatchcase(entry, p) for p in SKIP_PATTERNS):
            result["skip"].append(entry)
        else:
            result["ask"].append(entry)
    return result


def destination(entry: str, feature: str, has_backend: bool) -> str:
    """최상위 항목을 옮길 중앙 레포 경로. 폴더는 / 로 끝난다."""
    fe = f"{common.FE_FEATURES}{feature}/"
    be = f"{common.BE_FEATURES}{feature}/"
    if entry == "frontend/":
        return fe
    if entry == "backend/":
        return be
    if entry == "tests/":
        return be + "tests/"
    return (be if has_backend else fe) + entry  # README.md 와 --extra 항목(작성자 결정)


def top_entries(feature_repo: Path, ref: str) -> list[str]:
    entries = []
    for line in common.git_z(feature_repo, "ls-tree", "-z", ref):
        meta, name = line.split("\t", 1)
        entries.append(name + "/" if meta.split()[1] == "tree" else name)
    return entries


def _targets(files: list[str], moves: list[str], feature: str, has_backend: bool, exclude: set[str]) -> list[tuple[str, str]]:
    """옮길 파일마다 (기능 레포 경로, 중앙 레포 경로) 짝을 만든다."""
    pairs = []
    for path in files:
        if path in exclude:
            continue
        for entry in moves:
            if entry.endswith("/") and path.startswith(entry):
                pairs.append((path, destination(entry, feature, has_backend) + path[len(entry):]))
            elif path == entry:
                pairs.append((path, destination(entry, feature, has_backend)))
    return pairs


def _in_feature(path: str, feature: str) -> bool:
    return path.startswith((f"{common.FE_FEATURES}{feature}/", f"{common.BE_FEATURES}{feature}/"))


def _restore_outside(central: Path, feature: str) -> None:
    """기능 폴더 밖 경로를 합치기 직전(HEAD) 상태로 되돌린다."""
    changed = set(common.git_z(central, "diff", "--cached", "--name-only", "-z", "HEAD"))
    changed |= set(common.git_z(central, "diff", "--name-only", "--diff-filter=U", "-z"))
    for path in sorted(changed):
        if _in_feature(path, feature):
            continue
        if common.blob(central, "HEAD", path):
            common.git(central, "checkout", "HEAD", "--", path)
        else:
            common.git(central, "rm", "-f", "-q", "--cached", "--", path)
            (central / path).unlink(missing_ok=True)


def run(central: Path, feature_repo: Path, feature: str, branch: str, history: bool,
        extra: list[str] | None = None, exclude: list[str] | None = None, plan: bool = False) -> dict:
    ref = branch if common.git(feature_repo, "rev-parse", "--verify", "--quiet", branch, check=False).strip() else f"origin/{branch}"
    entries = top_entries(feature_repo, ref)
    has_backend = "backend/" in entries
    groups = classify_top(entries, has_backend)
    if plan:
        return {"status": "ok", **groups}

    result = {"status": "ok", "head": common.git(feature_repo, "rev-parse", ref).strip(), "moved": [],
              "outside_clean": False, "detail": ""}
    if common.git_z(central, "status", "--porcelain", "-z", "--untracked-files=all"):
        return {**result, "status": "stop", "detail": "중앙 레포에 commit 하지 않은 변경이 있다"}
    existing = [p for p in common.tree_files(central, "origin/main")
                if p.lower().startswith((f"{common.FE_FEATURES}{feature}/".lower(), f"{common.BE_FEATURES}{feature}/".lower()))]
    if existing:
        return {**result, "status": "stop", "detail": f"main 에 같은 이름의 기능 폴더가 있다: {existing[0]}"}

    chosen, unknown = [], []
    for item in extra or []:  # 끝의 / 가 빠진 폴더 이름도 받는다. 목록에 없는 값은 조용히 버리지 않는다
        name = item if item in groups["ask"] else item.rstrip("/") + "/"
        (chosen if name in groups["ask"] else unknown).append(name if name in groups["ask"] else item)
    if unknown:
        return {**result, "status": "stop",
                "detail": f"--extra 값이 옮길지 물을 항목(ask)에 없다: {', '.join(unknown)}. ask: {', '.join(groups['ask'])}"}
    moves = groups["move"] + chosen
    excluded = set(exclude or [])
    written: list[str] = []
    try:
        if history:
            common.git(central, "fetch", "-q", str(feature_repo), branch)
            source = "FETCH_HEAD"
            common.git(central, "merge", "--allow-unrelated-histories", "--no-commit", "--no-ff", "-q", source, check=False)
            if not common.merge_in_progress(central):
                raise RuntimeError("합치기를 시작하지 못했다")
            files = common.tree_files(feature_repo, ref)
            read = lambda p: common.git_bytes(central, "show", f"{source}:{p}")
        else:
            files = common.tree_files(feature_repo, ref)
            read = lambda p: common.git_bytes(feature_repo, "show", f"{ref}:{p}")
        for src, dst in _targets(files, moves, feature, has_backend, excluded):
            common.write_file(central / dst, read(src))
            written.append(dst)
            common.git(central, "add", "--", dst)
            result["moved"].append({"from": src, "to": dst})
        if history:
            _restore_outside(central, feature)
    except Exception as exc:
        if history:
            common.git(central, "merge", "--abort", check=False)
        for dst in written:
            common.git(central, "rm", "-f", "-q", "--cached", "--ignore-unmatch", "--", dst, check=False)
            (central / dst).unlink(missing_ok=True)
        for folder in (f"{common.FE_FEATURES}{feature}", f"{common.BE_FEATURES}{feature}"):
            shutil.rmtree(central / folder, ignore_errors=True)
        return {**result, "status": "failed", "moved": [], "detail": str(exc)}

    unmerged = common.git_z(central, "diff", "--name-only", "--diff-filter=U", "-z")
    staged = common.git_z(central, "diff", "--cached", "--name-only", "-z", "HEAD")
    result["outside_clean"] = not unmerged and all(_in_feature(p, feature) for p in staged)
    return result


CENTRAL_FILES = {
    ".gitignore": "node_modules/\n.venv/\n",
    "README.md": "중앙 레포 설명\n",
    "src/frontend/src/features/.gitkeep": "",
    "src/backend/features/.gitkeep": "",
    "src/backend/main.py": "app = None\n",
}
FEATURE_FILES = {
    "frontend/index.tsx": "export default function Page() { return null }\n",
    "backend/router.py": "from fastapi import APIRouter\nrouter = APIRouter()\n",
    "backend/secret.py": "KEY = 'x'\n",
    "tests/test_a.py": "def test_a():\n    assert True\n",
    "dev/main.tsx": "import Page from '../frontend'\n",
    "dev_app.py": "app = None\n",
    ".gitignore": ".env\n",
    ".kiwoom-feature": "fund-aum\n",
    "requirements.txt": "fastapi==0.115.0\n",
    "README.md": "기능 설명\n",
    "notes.txt": "메모\n",
}
FE = "src/frontend/src/features/fund-aum/"
BE = "src/backend/features/fund-aum/"


def _fixture(tmp: Path, feature_files: dict | None = None, central_extra: dict | None = None) -> tuple[Path, Path]:
    tmp.mkdir(parents=True, exist_ok=True)
    source = common.make_repo(tmp / "central-src", {**CENTRAL_FILES, **(central_extra or {})})
    bare = tmp / "central.git"
    common.git(tmp, "clone", "-q", "--bare", str(source), str(bare))
    central = tmp / "중앙 레포"
    common.git(tmp, "clone", "-q", str(bare), str(central))
    common.git(central, "switch", "-q", "-c", "feat/fund-aum-x")
    feature = tmp / "홍길동 작업" / "fund-aum"
    feature.mkdir(parents=True)
    common.make_repo(feature, feature_files or FEATURE_FILES)
    return central, feature


def _staged_outside(central: Path) -> list[str]:
    staged = common.git_z(central, "diff", "--cached", "--name-only", "-z", "HEAD")
    return [p for p in staged if not (p.startswith(FE) or p.startswith(BE))]


def _read(central: Path, path: str) -> str:
    return (central / path).read_text(encoding="utf-8")


def check_plan(tmp: Path) -> None:
    central, feature = _fixture(tmp)
    result = run(central, feature, "fund-aum", "main", True, plan=True)
    assert result["ask"] == ["notes.txt"], result
    for name in ("dev/", "dev_app.py", ".kiwoom-feature", "requirements.txt"):
        assert name in result["skip"], (name, result)
    assert common.git_z(central, "status", "--porcelain", "-z") == []


def check_history_yes(tmp: Path) -> None:
    central, feature = _fixture(tmp)
    result = run(central, feature, "fund-aum", "main", True)
    assert result["status"] == "ok" and result["outside_clean"], result
    assert (central / ".git" / "MERGE_HEAD").exists()
    assert common.git_z(central, "diff", "--name-only", "--diff-filter=U", "-z") == []
    assert _staged_outside(central) == []
    assert _read(central, BE + "tests/test_a.py") == FEATURE_FILES["tests/test_a.py"]
    assert _read(central, BE + "README.md") == FEATURE_FILES["README.md"]
    assert _read(central, BE + "router.py") == FEATURE_FILES["backend/router.py"]
    assert _read(central, FE + "index.tsx") == FEATURE_FILES["frontend/index.tsx"]
    assert _read(central, "README.md") == CENTRAL_FILES["README.md"]
    assert not (central / ".kiwoom-feature").exists() and not (central / "dev_app.py").exists()
    head = common.git(feature, "rev-parse", "main").strip()
    assert result["head"] == head


def check_history_no(tmp: Path) -> None:
    central, feature = _fixture(tmp)
    result = run(central, feature, "fund-aum", "main", False, exclude=["backend/secret.py"])
    assert result["status"] == "ok" and result["outside_clean"], result
    assert not (central / ".git" / "MERGE_HEAD").exists()
    assert not (central / BE / "secret.py").exists()
    assert _read(central, BE + "tests/test_a.py") == FEATURE_FILES["tests/test_a.py"]
    assert _read(central, BE + "README.md") == FEATURE_FILES["README.md"]
    assert _staged_outside(central) == []
    assert common.git_z(central, "status", "--porcelain", "-z", "--untracked-files=all", "--", ".") \
        and all(e[3:].startswith((FE, BE)) for e in common.git_z(central, "status", "--porcelain", "-z", "--untracked-files=all"))


def check_frontend_only_with_tests(tmp: Path) -> None:
    files = {"frontend/index.tsx": FEATURE_FILES["frontend/index.tsx"], "tests/test_a.py": FEATURE_FILES["tests/test_a.py"]}
    central, feature = _fixture(tmp, files)
    assert "tests/" in run(central, feature, "fund-aum", "main", True, plan=True)["ask"]
    result = run(central, feature, "fund-aum", "main", True)
    assert result["status"] == "ok", result
    assert not (central / BE).exists()
    assert (central / FE / "index.tsx").exists()


def check_existing_feature(tmp: Path) -> None:
    central, feature = _fixture(tmp, central_extra={BE + "router.py": "router = None\n"})
    before = common.git(central, "rev-parse", "HEAD").strip()
    result = run(central, feature, "fund-aum", "main", True)
    assert result["status"] == "stop", result
    assert common.git(central, "rev-parse", "HEAD").strip() == before
    assert not (central / ".git" / "MERGE_HEAD").exists()
    assert common.git_z(central, "status", "--porcelain", "-z") == []


def check_dirty_central(tmp: Path) -> None:
    central, feature = _fixture(tmp)
    (central / "메모.txt").write_text("x\n", encoding="utf-8")
    result = run(central, feature, "fund-aum", "main", True)
    assert result["status"] == "stop", result
    assert not (central / ".git" / "MERGE_HEAD").exists()
    assert not (central / FE).exists()


def check_history_no_failure_rollback(tmp: Path) -> None:
    central, feature = _fixture(tmp)
    before = common.git_z(central, "status", "--porcelain", "-z", "--untracked-files=all")
    real = common.write_file
    calls = {"n": 0}

    def failing(path: Path, data: bytes) -> None:
        calls["n"] += 1
        if calls["n"] == 3:
            raise OSError("디스크 오류")
        real(path, data)

    common.write_file = failing
    try:
        result = run(central, feature, "fund-aum", "main", False)
    finally:
        common.write_file = real
    assert result["status"] == "failed", result
    assert common.git_z(central, "status", "--porcelain", "-z", "--untracked-files=all") == before
    assert not (central / FE).exists() and not (central / BE).exists()


def check_extra_without_slash(tmp: Path) -> None:
    central, feature = _fixture(tmp, {**FEATURE_FILES, "docs/guide.md": "안내\n"})
    result = run(central, feature, "fund-aum", "main", True, extra=["docs"])
    assert result["status"] == "ok", result
    assert _read(central, BE + "docs/guide.md") == "안내\n"


def check_extra_unknown(tmp: Path) -> None:
    central, feature = _fixture(tmp)
    result = run(central, feature, "fund-aum", "main", True, extra=["없는파일.txt"])
    assert result["status"] == "stop" and "없는파일.txt" in result["detail"], result
    assert not common.merge_in_progress(central)
    assert common.git_z(central, "status", "--porcelain", "-z") == []


CHECKS = [
    check_extra_without_slash, check_extra_unknown,
    check_plan, check_history_yes, check_history_no, check_frontend_only_with_tests,
    check_existing_feature, check_dirty_central, check_history_no_failure_rollback,
]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--central")
    ap.add_argument("--feature-repo")
    ap.add_argument("--feature")
    ap.add_argument("--branch")
    ap.add_argument("--history", choices=["yes", "no"])
    ap.add_argument("--extra", action="append", default=[])
    ap.add_argument("--exclude", action="append", default=[])
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if args.check:
        return common.run_checks(CHECKS)
    try:
        return common.emit(run(Path(args.central), Path(args.feature_repo), args.feature, args.branch,
                               args.history == "yes", args.extra, args.exclude, args.plan))
    except Exception as exc:  # 약속대로 JSON 하나와 종료 코드 0 으로 끝낸다
        return common.emit({"status": "failed", "detail": str(exc)})


if __name__ == "__main__":
    sys.exit(main())
