"""기능 이전 1단계에서 중앙 레포가 전제 조건을 만족하는지 확인한다.

    python check_central.py --central <중앙 레포 폴더>                     # 전제 조건과 구조 파일 판정
    python check_central.py --central <중앙 레포 폴더> --apply-structure   # 판정 뒤 낡은 구조 파일을 템플릿 최신으로 맞춤
    python check_central.py --check                                         # 가짜 레포(fixture)로 자체 시험

결과는 JSON 하나다. status 는 ok(모두 통과), stop(전제 조건을 만족하지 않아 멈춤), failed(git·gh 실행 실패)다.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import intake_common as common

def check(central: Path, apply_structure: bool = False) -> dict:
    common.git(central, "fetch", "-q", "origin")
    common.fetch_template(central)
    checks = []
    failed = False

    url = common.git(central, "config", "--get", "remote.origin.url").strip()
    try:
        owner, name = common.owner_name(url)
        perms = (common.gh_json("api", f"repos/{owner}/{name}") or {}).get("permissions", {})
        checks.append({"name": "push", "ok": bool(perms.get("push")), "detail": "" if perms.get("push") else "쓰기 권한이 없다"})
    except Exception as exc:
        failed = True
        checks.append({"name": "push", "ok": False, "detail": str(exc)})

    has_jenkins = common.blob(central, "origin/main", "Jenkinsfile") is not None
    checks.append({"name": "jenkinsfile", "ok": has_jenkins, "detail": "" if has_jenkins else "main 에 Jenkinsfile 이 없다"})

    tree = common.tree_files(central, "origin/main")
    missing = [d for d in (common.FE_FEATURES, common.BE_FEATURES) if not any(p.startswith(d) for p in tree)]
    checks.append({"name": "feature-dirs", "ok": not missing, "detail": ", ".join(missing)})

    verdicts = common.structure_verdicts(central)
    modified = [v["path"] for v in verdicts if v["verdict"] == "modified"]
    checks.append({"name": "structure", "ok": not modified, "detail": ", ".join(modified)})

    applied = []
    if apply_structure and not modified:
        for v in verdicts:
            if v["verdict"] in ("add", "update"):
                common.git(central, "checkout", common.TEMPLATE_REF, "--", v["path"])
                applied.append(v["path"])

    status = "failed" if failed else ("ok" if all(c["ok"] for c in checks) else "stop")
    return {"status": status, "checks": checks, "structure": verdicts, "applied": applied}


TEMPLATE_V1 = {
    **{path: f"{path} v1\n" for path in common.STRUCTURE_FILES},
    "src/frontend/src/shell/shell.css": ".shell {}\n",
    "src/frontend/src/shell/Rail.tsx": "export {}\n",
    "src/frontend/src/features/.gitkeep": "",
    "src/backend/features/.gitkeep": "",
}
ROUTES = "src/frontend/src/routes.tsx"
MENU = "src/frontend/src/feature-menu.ts"
SHELL_CSS = "src/frontend/src/shell/shell.css"
CENTRAL_URL = "https://github.com/KiwoomAX/x-dashboard.git"


def _fixture(tmp: Path, change: dict | None = None, message: str | None = None) -> Path:
    """템플릿(routes.tsx 를 v1·v2 두 번 commit)과, 템플릿 v2 에 Jenkinsfile 을 추가한 중앙 레포를 만든다.

    change 의 값이 None 이면 그 파일을 지운다. 중앙 레포의 origin 과 템플릿 주소는 실제 GitHub 주소로 두고,
    insteadOf 로 로컬 폴더를 가리키게 한다.
    """
    template = common.make_repo(tmp / "template", TEMPLATE_V1)
    common.commit_files(template, {ROUTES: f"{ROUTES} v2\n"}, "v2")
    files = {**TEMPLATE_V1, ROUTES: f"{ROUTES} v2\n", "Jenkinsfile": "kiwoomDeploy()\n"}
    for path, text in (change or {}).items():
        if text is None:
            files.pop(path, None)
        else:
            files[path] = text
    source = common.make_repo(tmp / "central-src", files)
    if message:
        common.git(source, "commit", "-q", "--allow-empty", "-m", message)
    bare = tmp / "central.git"
    common.git(tmp, "init", "-q", "--bare", "-b", "main", str(bare))
    common.git(source, "push", "-q", str(bare), "main")
    central = tmp / "중앙 레포"
    common.git(tmp, "clone", "-q", str(bare), str(central))
    common.git(central, "remote", "set-url", "origin", CENTRAL_URL)
    common.git(central, "config", f"url.{bare.as_posix()}.insteadOf", CENTRAL_URL)
    common.git(central, "config", f"url.{template.as_posix()}.insteadOf", common.TEMPLATE_URL)
    return central


def _fake_gh(push: bool | None):
    def fake(*args: str) -> object:
        if push is None:
            raise RuntimeError("gh: HTTP 401")
        return {"permissions": {"push": push}}
    return fake


def _run(central: Path, push: bool | None = True, apply: bool = False) -> dict:
    real = common.gh_json
    common.gh_json = _fake_gh(push)
    try:
        return check(central, apply)
    finally:
        common.gh_json = real


def _by_name(result: dict) -> dict:
    return {c["name"]: c for c in result["checks"]}


def check_all_ok(tmp: Path) -> None:
    result = _run(_fixture(tmp))
    assert result["status"] == "ok", result
    assert all(c["ok"] for c in result["checks"]), result
    assert set(_by_name(result)) == {"push", "jenkinsfile", "feature-dirs", "structure"}


def check_no_jenkinsfile(tmp: Path) -> None:
    result = _run(_fixture(tmp, {"Jenkinsfile": None}))
    failed = [c["name"] for c in result["checks"] if not c["ok"]]
    assert failed == ["jenkinsfile"], result
    assert result["status"] == "stop"


def check_one_features_dir(tmp: Path) -> None:
    result = _run(_fixture(tmp, {"src/frontend/src/features/.gitkeep": None}))
    assert not _by_name(result)["feature-dirs"]["ok"], result


def check_shell_changed(tmp: Path) -> None:
    # 이전 절차는 셸을 읽거나 고치지 않으므로, 상태바·사이드바를 고친 대시보드도 멈추지 않는다
    result = _run(_fixture(tmp, {SHELL_CSS: ".shell { color: red }\n"}))
    assert result["status"] == "ok" and "shell" not in _by_name(result), result


def check_shell_extra_file(tmp: Path) -> None:
    extra = "src/frontend/src/shell/Extra.tsx"
    result = _run(_fixture(tmp, {extra: "export {}\n"}))
    assert result["status"] == "ok" and "shell" not in _by_name(result), result


def check_no_push(tmp: Path) -> None:
    result = _run(_fixture(tmp), push=False)
    assert not _by_name(result)["push"]["ok"], result
    assert result["status"] == "stop"


def check_gh_error(tmp: Path) -> None:
    result = _run(_fixture(tmp), push=None)
    assert not _by_name(result)["push"]["ok"], result
    assert result["status"] == "failed"


def check_structure_verdicts(tmp: Path) -> None:
    result = _run(_fixture(tmp / "a", {ROUTES: f"{ROUTES} v1\n", MENU: None}))
    verdicts = {v["path"]: v["verdict"] for v in result["structure"]}
    assert verdicts[ROUTES] == "update" and verdicts[MENU] == "add", result
    assert verdicts["src/backend/main.py"] == "same"
    assert result["status"] == "ok"
    result = _run(_fixture(tmp / "b", {ROUTES: "export const manualMenu = []\n"}))
    verdicts = {v["path"]: v["verdict"] for v in result["structure"]}
    assert verdicts[ROUTES] == "modified", result
    assert result["status"] == "stop" and not _by_name(result)["structure"]["ok"]


def check_structure_crlf_worktree(tmp: Path) -> None:
    central = _fixture(tmp)
    common.git(central, "config", "core.autocrlf", "true")
    (central / ROUTES).unlink()
    common.git(central, "checkout", "--", ROUTES)
    assert b"\r\n" in (central / ROUTES).read_bytes()
    verdicts = {v["path"]: v["verdict"] for v in _run(central)["structure"]}
    assert verdicts[ROUTES] == "same", verdicts


def check_apply_structure(tmp: Path) -> None:
    central = _fixture(tmp, {ROUTES: f"{ROUTES} v1\n", MENU: None})
    result = _run(central, apply=True)
    assert sorted(result["applied"]) == sorted([ROUTES, MENU]), result
    for path in (ROUTES, MENU):
        staged = common.git(central, "rev-parse", f":{path}").strip()
        assert staged == common.blob(central, common.TEMPLATE_REF, path), path


def check_apply_refused(tmp: Path) -> None:
    central = _fixture(tmp, {ROUTES: "export const manualMenu = []\n", MENU: None})
    result = _run(central, apply=True)
    assert result["applied"] == [], result
    assert common.git_z(central, "status", "--porcelain", "-z") == []


def check_owner_name(tmp: Path) -> None:
    for url in (
        "https://github.com/KiwoomAX/x-dashboard.git",
        "https://github.com/KiwoomAX/x-dashboard",
        "https://someone@github.com/KiwoomAX/x-dashboard.git",
        "git@github.com:KiwoomAX/x-dashboard.git",
    ):
        assert common.owner_name(url) == ("KiwoomAX", "x-dashboard"), url


def check_intake_line_exact(tmp: Path) -> None:
    message = "기능 이전\n\nIntake-From: KiwoomAX/fund-aum-type-summary\nIntake-Head: abc123\nIntake-History: no"
    central = _fixture(tmp, message=message)
    common.git(central, "fetch", "-q", "origin")
    assert common.find_intake(central, "fund-aum") is None
    found = common.find_intake(central, "fund-aum-type-summary")
    assert found is not None and found["head"] == "abc123" and found["history"] == "no", found


CHECKS = [
    check_all_ok, check_no_jenkinsfile, check_one_features_dir, check_shell_changed, check_shell_extra_file,
    check_no_push, check_gh_error, check_structure_verdicts, check_structure_crlf_worktree,
    check_apply_structure, check_apply_refused, check_owner_name, check_intake_line_exact,
]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--central")
    ap.add_argument("--apply-structure", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if args.check:
        return common.run_checks(CHECKS)
    try:
        return common.emit(check(Path(args.central), args.apply_structure))
    except Exception as exc:  # 약속대로 JSON 하나와 종료 코드 0 으로 끝낸다
        return common.emit({"status": "failed", "detail": str(exc), "checks": [], "structure": [], "applied": []})


if __name__ == "__main__":
    sys.exit(main())
