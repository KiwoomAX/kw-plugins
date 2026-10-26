"""여러 개발자가 함께 쓰는 KiwoomAX 대시보드 레포(공유 레포)를 알아보고 기능 폴더 경계를 판정한다.

git 을 읽기만 한다. save_work 를 import 하지 않는다(save_work 가 이 모듈을 쓰기 때문이다).
"""
import json
import re
from pathlib import Path

import gitcmd

MARKER = ".kiwoom-feature"
REMOTE_REF = "refs/remotes/origin/main"
FRONT = "src/frontend/src/features/"
BACK = "src/backend/features/"
INTAKE_FILES = ("pyproject.toml", "uv.lock", "src/frontend/package.json", "src/frontend/package-lock.json",
                "docker-compose.yml", "Jenkinsfile")
STRUCTURE_FILES = ("src/backend/feature_loader.py", "src/backend/main.py", "src/backend/tests/test_health.py",
                   "src/frontend/src/feature-menu.ts", "src/frontend/src/routes.tsx")
RESERVED = {"src", "docs", "frontend", "backend", "shell", "features"}
WINDOWS_RESERVED = {"con", "nul", "aux", "prn"} | {f"com{n}" for n in range(1, 10)} | {f"lpt{n}" for n in range(1, 10)}
NAME = re.compile(r"[A-Za-z0-9_-]+")
ORIGIN = re.compile(r"github\.com[/:]([^/]+)/([^/]+?)(?:\.git)?/?$", re.IGNORECASE)
DOC = re.compile(r"docs/([^/]+)\.(pdf|docx)")


def _has_head(top):
    return gitcmd.git_try(top, "rev-parse", "--verify", "-q", "HEAD")[0] == 0


def _merging(top):
    code, out, _ = gitcmd.git_try(top, "rev-parse", "--git-path", "MERGE_HEAD")
    return code == 0 and (Path(top) / out.strip()).is_file()


def marker_tracked(top):
    """기능 레포 표식이 있는가. 진행 중 merge 가 작업 트리에 가져온 표식 파일은 보지 않는다."""
    if _has_head(top) and gitcmd.git_try(top, "cat-file", "-e", f"HEAD:{MARKER}")[0] == 0:
        return True
    return (Path(top) / MARKER).is_file() and not _merging(top)


def _origin(top):
    code, url, _ = gitcmd.git_try(top, "config", "--get", "remote.origin.url")
    match = ORIGIN.search(url.strip()) if code == 0 else None
    return (match.group(1), match.group(2)) if match else None


def repo_kind(top):
    if marker_tracked(top):
        return "feature"
    origin = _origin(top)
    if origin and origin[0].casefold() == "kiwoomax" and origin[1].casefold().endswith("dashboard"):
        return "shared"
    return "other"


def _feature_tree(top, ref):
    code, out, _ = gitcmd.git_try(top, "ls-tree", "-r", "--name-only", ref, "--", FRONT.rstrip("/"),
                                  BACK.rstrip("/"))
    return out.splitlines() if code == 0 else []


def supported(top, ref=REMOTE_REF):
    paths = _feature_tree(top, ref)
    return any(p.startswith(FRONT) for p in paths) and any(p.startswith(BACK) for p in paths)


def _valid_name(feature):
    if not isinstance(feature, str) or not NAME.fullmatch(feature):
        return False
    folded = feature.casefold()
    return folded not in RESERVED and folded not in WINDOWS_RESERVED


def feature_status(top, feature, ref=REMOTE_REF):
    if not _valid_name(feature):
        return "invalid"
    folders = set()
    for path in _feature_tree(top, ref):
        for prefix in (FRONT, BACK):
            rest = path[len(prefix):] if path.startswith(prefix) else ""
            if "/" in rest:
                folders.add(rest.split("/", 1)[0])
    if feature in folders:
        return "existing"
    if any(name.casefold() == feature.casefold() for name in folders):
        return "invalid"
    return "new"


def is_feature_doc(path, feature):
    return path in (f"docs/{feature}.pdf", f"docs/{feature}.docx")


def allowed(path, feature):
    return path.startswith(f"{FRONT}{feature}/") or path.startswith(f"{BACK}{feature}/") or is_feature_doc(path, feature)


def feature_of(path):
    for prefix in (FRONT, BACK):
        rest = path[len(prefix):] if path.startswith(prefix) else ""
        if "/" in rest:
            return rest.split("/", 1)[0]
    match = DOC.fullmatch(path)
    return match.group(1) if match else None


# ---- 경계 판정 ----
TEMPLATE_TREE = "repos/KiwoomAX/dashboard-template/git/trees/main?recursive=1"


class TemplateUnavailable(Exception):
    """dashboard-template main 을 조회하지 못했다."""


def _paths_z(entries, renames=True):
    paths, index = [], 0
    while index < len(entries):
        status = entries[index]
        if renames and status[:1] in ("R", "C"):
            paths += [entries[index + 1], entries[index + 2]]
            index += 3
        else:
            paths.append(entries[index + 1])
            index += 2
    return paths


def changed_paths(top, base, head, deadline=None):
    entries = gitcmd.git_z(top, "diff", "--name-status", "-z", "-M", base, head, deadline=deadline)
    return _paths_z(entries)


def worktree_paths(top, deadline=None):
    entries = gitcmd.git_z(top, "status", "--porcelain=v1", "-z", "--untracked-files=all", deadline=deadline)
    paths, index = [], 0
    while index < len(entries):
        entry = entries[index]
        paths.append(entry[3:])
        if "R" in entry[:2] or "C" in entry[:2]:
            index += 1
            if index < len(entries):
                paths.append(entries[index])
        index += 1
    return paths


def _blob(top, ref, path, deadline=None):
    code, out, _ = gitcmd.git_try(top, "rev-parse", "-q", "--verify", f"{ref}:{path}", deadline=deadline)
    return out.strip() if code == 0 and out.strip() else None


def final_blob(top, head, path, dirty, deadline=None):
    """경로의 최종 내용 blob. commit 하지 않은 경로는 줄바꿈 변환을 거친 작업 트리 파일로 계산한다."""
    if path in dirty:
        full = Path(top) / path
        if not full.is_file():
            return None
        return gitcmd.git(top, "hash-object", f"--path={path}", "--", str(full), deadline=deadline).strip()
    return _blob(top, head, path, deadline)


def template_blobs(deadline=None):
    code, out, err = gitcmd.gh_try("api", TEMPLATE_TREE, deadline=deadline)
    if code != 0:
        raise TemplateUnavailable(err.strip() or out.strip())
    try:
        tree = json.loads(out)["tree"]
    except (ValueError, KeyError, TypeError) as exc:
        raise TemplateUnavailable(str(exc)) from exc
    return {item["path"]: item["sha"] for item in tree if item.get("path") in STRUCTURE_FILES}


def _result(status, reason="", new_feature=False, outside=(), why=None):
    return {"status": status, "reason": reason, "new_feature": new_feature, "outside": list(outside),
            "why": why or {}}


def boundary(top, feature, paths, head, dirty, intake=False, deadline=None):
    if not supported(top):
        return _result("unsupported")
    status = feature_status(top, feature)
    if status == "invalid":
        return _result("invalid-feature")
    new_feature = status == "new"
    if intake and not new_feature:
        return _result("invalid-feature")
    template = None
    outside, why = [], {}
    for path in dict.fromkeys(paths):
        blob = final_blob(top, head, path, dirty, deadline)
        if blob == _blob(top, REMOTE_REF, path, deadline):
            continue  # origin/main 과 같으면 변경이 아니다
        if allowed(path, feature):
            continue
        if intake and path in INTAKE_FILES:
            continue
        if intake and path in STRUCTURE_FILES:
            if template is None:
                try:
                    template = template_blobs(deadline)
                except TemplateUnavailable:
                    return _result("failed", "template-unavailable", new_feature)
            if blob == template.get(path):
                continue
            why[path] = "템플릿과 다르다"
        outside.append(path)
    return _result("outside" if outside else "inside", "", new_feature, outside, why)
