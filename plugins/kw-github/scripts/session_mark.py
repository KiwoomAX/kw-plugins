"""기능 레포와 공유 대시보드 레포에서 작업 중인 세션을 표시한다.

세션마다 `.git/kiwoom-sessions/<세션 ID>` 파일 하나를 두고 수정 시각을 마지막 활동 시각으로 쓴다.
세션 시작 저장은 다른 세션이 작업 중이면 그 세션의 미완성 코드를 커밋하지 않도록 건너뛴다.
가드 훅이 셸 명령마다 부르므로 git 을 부르지 않고 폴더만 거슬러 올라가 레포를 찾는다.

세션이 도중에 다른 폴더로 옮겨도 끝날 때 모두 지우도록, 이 PC 의 임시 폴더에 세션마다 표시한 폴더 목록을 적는다.
"""
import re
import tempfile
import time
from pathlib import Path

MARKER = ".kiwoom-feature"
MARK_DIR = "kiwoom-sessions"
# 이 시간 안에 활동한 세션을 작업 중으로 본다. 비정상 종료로 남은 표시도 이 시간이 지나면 무시된다.
ACTIVE_SECONDS = 10 * 60 * 60
# 세션 ID 파일마다 그 세션이 표시를 남긴 표시 폴더를 한 줄에 하나씩 적는다.
REGISTRY_DIR = Path(tempfile.gettempdir()) / "kiwoom-sessions"
_SAFE_ID = re.compile(r"[^A-Za-z0-9_-]")
# shared_repo.repo_kind 와 같은 판정을 git 없이 .git/config 의 url 줄로 한다.
DASHBOARD_URL = re.compile(r"github\.com[/:]kiwoomax/[^/\s]*dashboard(\.git)?\s*$", re.I)


def _dashboard(git):
    try:
        text = (git / "config").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return any(line.strip().startswith("url = ") and DASHBOARD_URL.search(line.strip()[len("url = "):])
               for line in text.splitlines())


def _mark_dir(start):
    """기능 레포나 공유 대시보드 레포의 표시 폴더를 돌려준다. 둘 다 아니면 None 이다."""
    path = Path(start).resolve()
    for folder in (path, *path.parents):
        git = folder / ".git"
        if git.is_dir() and ((folder / MARKER).is_file() or _dashboard(git)):
            return git / MARK_DIR
    return None


def _name(session_id):
    # 세션 ID 를 파일 이름으로 쓰므로 경로를 벗어나는 글자를 지운다.
    return _SAFE_ID.sub("", str(session_id)) or None


def touch(start, session_id):
    marks, name = _mark_dir(start), _name(session_id)
    if marks is None or name is None:
        return
    marks.mkdir(exist_ok=True)
    (marks / name).write_text(str(time.time()), encoding="utf-8")
    _register(marks, name)


def _registered(name):
    try:
        return (REGISTRY_DIR / name).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []


def _register(marks, name):
    if str(marks) in _registered(name):
        return
    REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
    with open(REGISTRY_DIR / name, "a", encoding="utf-8") as handle:
        handle.write(f"{marks}\n")


def others_active(start, session_id, now=None):
    marks = _mark_dir(start)
    if marks is None or not marks.is_dir():
        return []
    now = time.time() if now is None else now
    own = _name(session_id)
    return sorted(mark.name for mark in marks.iterdir()
                  if mark.name != own and now - mark.stat().st_mtime <= ACTIVE_SECONDS)


def clear(start, session_id):
    """이 세션이 이 PC 에 남긴 표시를 모두 지운다. start 의 레포 표시도 함께 지운다. git 은 실행하지 않는다."""
    name = _name(session_id)
    if name is None:
        return
    marks = _mark_dir(start)
    folders = set(_registered(name)) | ({str(marks)} if marks is not None else set())
    for folder in folders:
        (Path(folder) / name).unlink(missing_ok=True)
    (REGISTRY_DIR / name).unlink(missing_ok=True)
