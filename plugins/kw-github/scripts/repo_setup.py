"""레포를 만들기 전에 폴더와 폴더 상태와 규칙 파일을 확인한다. starting-feature-repo 스킬이 부른다."""
import argparse
import ctypes
import json
import os
import re
import sys
import uuid
from pathlib import Path

import save_work

# Windows 알려진 폴더 ID 다. [Environment]::GetFolderPath 에는 다운로드가 없어 이 API 를 직접 쓴다.
KNOWN_FOLDERS = {
    "Desktop": "B4BFCC3A-DB2C-424C-B029-7FE99A87C641",
    "Documents": "FDD39AD0-238F-46AF-ADB4-6C85480369C7",
    "Downloads": "374DE290-123F-4565-9164-39C4925E467B",
}
ONEDRIVE_ENV = ("OneDrive", "OneDriveCommercial", "OneDriveConsumer")
REPO_NAME = re.compile(r"github\.com[/:]([^/]+/[^/]+?)(?:\.git)?/?$", re.IGNORECASE)

FOLDER_DETAIL = (
    "사용자 홈·바탕화면·문서·다운로드·OneDrive·드라이브 최상위는 레포로 만들지 않는다. 레포 이름으로 "
    "하위 폴더를 만들고 그 폴더에서 Claude Code 를 다시 열라고 안내하라. 세션 시작 저장은 세션을 연 "
    "폴더에서만 돈다."
)


def _known_folder(guid):
    """SHGetKnownFolderPath 로 실제 경로를 받는다. OneDrive 로 옮겨진 폴더는 옮겨진 경로가 온다."""
    folder_id = (ctypes.c_char * 16).from_buffer_copy(uuid.UUID(guid).bytes_le)
    pointer = ctypes.c_wchar_p()
    if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(folder_id), 0, None, ctypes.byref(pointer)) != 0:
        return None
    try:
        return pointer.value
    finally:
        ctypes.windll.ole32.CoTaskMemFree(pointer)


def personal_folders():
    home = Path.home()
    found = {home, *(home / name for name in KNOWN_FOLDERS)}
    if os.name == "nt":
        for guid in KNOWN_FOLDERS.values():
            path = _known_folder(guid)
            if path:
                found.add(Path(path))
    for key in ONEDRIVE_ENV:
        if os.environ.get(key):
            found.add(Path(os.environ[key]))
    return {path.resolve() for path in found}


def check_folder(path):
    folder = Path(path).resolve()
    if folder == Path(folder.anchor) or folder in personal_folders():
        return {"ok": False, "folder": str(folder), "detail": FOLDER_DETAIL}
    return {"ok": True, "folder": str(folder), "detail": ""}


def _full_name(url):
    match = REPO_NAME.search(url.strip())
    return match.group(1) if match else None


def inspect(path):
    top = save_work.locate(path)
    if top is None:
        return {"ok": True, "state": "not-git", "top": None, "branch": None, "has_commits": False,
                "has_remote": False, "repo": None}
    url = save_work.origin_url(top)
    if save_work.is_feature_repo(top):
        state = "feature"
    elif url is None:
        state = "local-only"
    elif save_work.normalize_url(save_work.ORG_PREFIX) in save_work.normalize_url(url):
        state = "company-no-marker"
    else:
        state = "other-remote"
    return {
        "ok": True,
        "state": state,
        "top": str(top),
        "branch": save_work.current_branch(top),
        "has_commits": save_work.has_head(top),
        "has_remote": url is not None,
        "repo": _full_name(url) if url else None,
    }


def check_rules(path=None):
    """저장 규칙 파일을 읽을 수 있는지 본다. 레포와 이슈를 만들기 전에 규칙 오류를 거르기 위해서다."""
    try:
        save_work.rules.load(path or save_work.RULES_PATH)
    except save_work.rules.RulesError as exc:
        return {"ok": False, "detail": str(exc)}
    return {"ok": True, "detail": ""}


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="기능 레포를 만들기 전에 확인한다.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check-folder").add_argument("--path", required=True)
    commands.add_parser("inspect").add_argument("--path", required=True)
    commands.add_parser("check-rules")
    args = parser.parse_args(argv)
    try:
        if args.command == "check-rules":
            payload = check_rules()
        elif args.command == "check-folder":
            payload = check_folder(args.path)
        else:
            payload = inspect(args.path)
    except Exception as exc:  # noqa: BLE001 — 스킬은 어떤 경우에도 JSON 을 받아야 한다
        payload = {"ok": False, "detail": f"{exc.__class__.__name__}: {exc}"}
    # ASCII 로만 내보낸다. cp949 로 설정된 PowerShell 이 출력을 담아도 한글이 깨지지 않는다.
    print(json.dumps(payload))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
