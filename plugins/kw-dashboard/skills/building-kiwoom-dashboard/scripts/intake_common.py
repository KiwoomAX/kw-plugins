"""기능 이전 스크립트가 함께 쓰는 상수와 git·gh 호출, 판정 함수다.

스크립트는 Windows PowerShell 에서 `python` 으로 실행된다. 경로에 한글과 공백이 들 수 있으므로 git 은 셸 없이
호출하고, 경로 목록은 `-z` 출력으로 읽는다.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import traceback
from pathlib import Path

STRUCTURE_FILES = [
    "src/backend/feature_loader.py",
    "src/backend/main.py",
    "src/backend/tests/test_health.py",
    "src/frontend/src/feature-menu.ts",
    "src/frontend/src/routes.tsx",
]
SHELL_DIR = "src/frontend/src/shell/"
FE_FEATURES = "src/frontend/src/features/"
BE_FEATURES = "src/backend/features/"
TEMPLATE_URL = "https://github.com/KiwoomAX/dashboard-template.git"
TEMPLATE_REF = "refs/kw-intake/template"


class GitError(RuntimeError):
    pass


def git(repo: Path, *args: str, check: bool = True) -> str:
    r = subprocess.run(
        ["git", "-c", "core.quotepath=false", *args], cwd=repo,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if check and r.returncode != 0:
        raise GitError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout


def git_bytes(repo: Path, *args: str) -> bytes:
    """파일 내용처럼 글자로 바꾸면 안 되는 출력을 받는다."""
    r = subprocess.run(["git", "-c", "core.quotepath=false", *args], cwd=repo, capture_output=True)
    if r.returncode != 0:
        raise GitError(f"git {' '.join(args)}: {r.stderr.decode('utf-8', 'replace').strip()}")
    return r.stdout


def write_file(path: Path, data: bytes) -> None:
    """레포 작업 트리에 파일을 쓴다. 자체 시험이 실패 상황을 만들려고 이 함수를 바꾼다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def git_z(repo: Path, *args: str) -> list[str]:
    """`-z` 를 붙인 git 명령의 출력을 NUL 로 나눈 목록으로 돌려준다."""
    return [part for part in git(repo, *args).split("\0") if part]


def gh_json(*args: str) -> object:
    """gh 호출은 이 함수 하나로만 한다. 자체 시험은 이 함수를 가짜로 바꿔 실행한다."""
    r = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)}: {r.stderr.strip()}")
    return json.loads(r.stdout) if r.stdout.strip() else None


def owner_name(url: str) -> tuple[str, str]:
    m = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?/?$", url.strip())
    if not m:
        raise ValueError(f"GitHub 주소가 아니다: {url}")
    return m.group(1), m.group(2)


def fetch_template(repo: Path) -> None:
    git(repo, "fetch", "-q", "--no-tags", TEMPLATE_URL, f"+main:{TEMPLATE_REF}")


def blob(repo: Path, ref: str, path: str) -> str | None:
    out = git(repo, "rev-parse", "--verify", "--quiet", f"{ref}:{path}", check=False).strip()
    return out or None


def default_branch(repo: Path) -> str | None:
    """원격의 기본 branch 이름. 로컬에서 만든 뒤 push 한 레포에는 origin/HEAD 가 없으므로 원격에 직접 묻는다."""
    local = git(repo, "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD", check=False).strip()
    if local:
        return local.split("/", 1)[1]
    remote = git(repo, "ls-remote", "--symref", "origin", "HEAD", check=False)
    m = re.search(r"^ref: refs/heads/(\S+)\tHEAD$", remote, re.M)
    return m.group(1) if m else None


def tree_files(repo: Path, ref: str, prefix: str = "") -> list[str]:
    args = ["ls-tree", "-r", "-z", "--name-only", ref]
    if prefix:
        args += ["--", prefix]
    return git_z(repo, *args)


def find_intake(central: Path, repo_name: str) -> dict | None:
    """origin/main 에서 `Intake-From: KiwoomAX/<repo_name>` 줄이 줄 전체로 일치하는 가장 최근 commit 을 찾는다."""
    wanted = f"Intake-From: KiwoomAX/{repo_name}"
    for record in git(central, "log", "origin/main", "--format=%H%x00%B%x01").split("\x01"):
        sha, _, body = record.strip("\n").partition("\0")
        lines = [line.strip() for line in body.splitlines()]
        if wanted not in lines:
            continue
        fields = dict(line.split(": ", 1) for line in lines if line.startswith("Intake-") and ": " in line)
        return {"commit": sha.strip(), "head": fields.get("Intake-Head", ""), "history": fields.get("Intake-History", "")}
    return None


def structure_verdicts(central: Path, ref: str = "origin/main") -> list[dict]:
    """구조 파일마다 템플릿 main 과 비교한 판정을 낸다. fetch_template 을 먼저 실행해야 한다."""
    verdicts = []
    for path in STRUCTURE_FILES:
        latest = blob(central, TEMPLATE_REF, path)
        current = blob(central, ref, path)
        if current is None:
            verdict = "add"
        elif current == latest:
            verdict = "same"
        else:
            history = {blob(central, sha, path) for sha in git(central, "rev-list", TEMPLATE_REF, "--", path).split()}
            verdict = "update" if current in history else "modified"
        verdicts.append({"path": path, "verdict": verdict})
    return verdicts


def emit(payload: dict) -> int:
    print(json.dumps(payload, ensure_ascii=False))
    return 0


# ---- 자체 시험(--check) 도구 ----

def make_repo(root: Path, files: dict[str, str], message: str = "init") -> Path:
    """fixture 레포를 만든다. 파일 내용은 주어진 글자 그대로(LF) 쓴다."""
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q", "-b", "main")
    commit_files(root, files, message)
    return root


def commit_files(repo: Path, files: dict[str, str], message: str) -> None:
    for path, text in files.items():
        target = repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8", newline="") as f:
            f.write(text)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)


def _isolate_git(tmp: Path) -> None:
    """이 PC 의 전역 git 설정(신원, 줄바꿈 변환, 기본 branch 이름)을 읽지 않게 한다."""
    empty = tmp / "empty.gitconfig"
    empty.write_text("", encoding="utf-8")
    os.environ.update({
        "GIT_CONFIG_GLOBAL": str(empty),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "fixture", "GIT_AUTHOR_EMAIL": "fixture@example.com",
        "GIT_COMMITTER_NAME": "fixture", "GIT_COMMITTER_EMAIL": "fixture@example.com",
    })


def _force_remove(func, path, _exc):
    os.chmod(path, stat.S_IWRITE)  # Windows 에서 git 객체 파일은 읽기 전용이다
    func(path)


def run_checks(checks: list) -> int:
    """시험 함수마다 새 임시 폴더를 주어 실행하고 결과를 JSON 하나로 낸다. 실패가 있으면 1 을 돌려준다."""
    base = Path(tempfile.mkdtemp(prefix="kw-intake-check-"))
    failures = []
    try:
        _isolate_git(base)
        for fn in checks:
            tmp = base / fn.__name__
            tmp.mkdir()
            try:
                fn(tmp)
            except Exception:
                failures.append({"name": fn.__name__, "error": traceback.format_exc(limit=3)})
    finally:
        shutil.rmtree(base, onexc=_force_remove)
    emit({"check": "failed" if failures else "ok", "failures": failures})
    return 1 if failures else 0
