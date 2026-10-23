"""기능 레포에서 작업 중인 세션을 표시한다.

세션마다 `.git/kiwoom-sessions/<세션 ID>` 파일 하나를 두고 수정 시각을 마지막 활동 시각으로 쓴다.
세션 시작 저장은 다른 세션이 작업 중이면 그 세션의 미완성 코드를 커밋하지 않도록 건너뛴다.
가드 훅이 셸 명령마다 부르므로 git 을 부르지 않고 폴더만 거슬러 올라가 레포를 찾는다.
"""
import re
import time
from pathlib import Path

MARKER = ".kiwoom-feature"
MARK_DIR = "kiwoom-sessions"
# 이 시간 안에 활동한 세션을 작업 중으로 본다. 비정상 종료로 남은 표시도 이 시간이 지나면 무시된다.
ACTIVE_SECONDS = 10 * 60 * 60
_SAFE_ID = re.compile(r"[^A-Za-z0-9_-]")


def _mark_dir(start):
    """기능 레포의 표시 폴더를 돌려준다. 기능 레포가 아니면 None 이다."""
    path = Path(start).resolve()
    for folder in (path, *path.parents):
        if (folder / MARKER).is_file() and (folder / ".git").is_dir():
            return folder / ".git" / MARK_DIR
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


def others_active(start, session_id, now=None):
    marks = _mark_dir(start)
    if marks is None or not marks.is_dir():
        return []
    now = time.time() if now is None else now
    own = _name(session_id)
    return sorted(mark.name for mark in marks.iterdir()
                  if mark.name != own and now - mark.stat().st_mtime <= ACTIVE_SECONDS)


def clear(start, session_id):
    marks, name = _mark_dir(start), _name(session_id)
    if marks is not None and name is not None:
        (marks / name).unlink(missing_ok=True)
