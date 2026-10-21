"""commit 과 push 의 유일한 경로다. 하위 명령마다 검사하고, 걸린 파일을 빼고, 결과 JSON 한 개를 낸다.

commit 은 로컬에서만 작업 브랜치에 커밋한다. push 는 개발자가 승인한 뒤 upload 로만 한다.
스킬과 훅은 이 파일만 부른다.
"""
import argparse
import json
import re
import shutil
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

import gitcmd
import rules

ORG = "KiwoomAX"
ORG_PREFIX = f"github.com/{ORG}/"
MARKER = ".kiwoom-feature"
BRANCH = "main"
TOPIC = "kiwoom-feature"
RULES_PATH = Path(__file__).resolve().parent / "upload_rules.json"

SAVE_SECONDS = 120
CATCH_UP_SECONDS = 45
ABORT_SECONDS = 15
CATCH_UP_TEMPLATE = "이전 세션에서 저장하지 못한 변경 ({stamp})"
LOCK_MAX_AGE = 10 * 60
REMOTE_REF = f"refs/remotes/origin/{BRANCH}"
GITIGNORE_SPECIAL = set("*?[]\\!# ")
# Claude 가 만드는 superpowers 설계 문서는 기능 레포에도 올리지 않는다(사용자 결정, 2026-10-07).
DESIGN_DOCS = "docs/superpowers/"
DEFAULT_GITIGNORE = [".env", ".venv/", "node_modules/", "__pycache__/", DESIGN_DOCS]

ROTATE = " 이미 GitHub 에 올라간 적이 있으니 그 비밀값은 폐기하고 새로 발급받으세요."
EXCLUDE_NOTES = {
    "secret-content": "비밀번호 같은 값이 들어 있어 이번에는 올리지 않았습니다. 값을 .env 로 옮기고 코드에서는 환경 변수로 읽으세요.",
    "secret-content-tracked": "이미 올라간 코드에 비밀번호 같은 값이 들어 있습니다. 값을 .env 로 옮기고 코드에서는 환경 변수로 읽으세요." + ROTATE,
    "secret-filename": "비밀값을 담는 파일이라 앞으로도 올리지 않습니다.",
    "secret-filename-tracked": "비밀값을 담는 파일이라 앞으로는 올리지 않습니다." + ROTATE,
    "data": "데이터는 GitHub 코드 저장소에 올리지 않습니다.",
}

# 작업 브랜치 후보 접두어다. local-history 처럼 그 밖의 브랜치는 후보가 아니다.
WORK_PREFIXES = ("feat/", "fix/", "refactor/", "docs/")
SESSION_BRANCH = "feat/session-{stamp}"
UPLOAD_STASH = "kiwoom-upload"
REMOTE_URL = "https://github.com/{full}.git"
TEMPLATE_API = "repos/KiwoomAM/.github/contents/.github/ISSUE_TEMPLATE/03_feature_request.md"
FRONTMATTER = re.compile(r"\A---\n.*?\n---\n", re.S)
HTML_COMMENT = re.compile(r"<!--.*?-->\n?", re.S)

# 개발자에게 그대로 보이는 문장이다. git_terms.md 의 규칙(commit·push·main·branch 만 영어로 쓴다)을 따른다.
MSG_NOT_FEATURE = "이 폴더는 작업 폴더로 준비되지 않았습니다."
MSG_NOTHING = "새로 저장할 변경이 없습니다."
MSG_COMMITTED = "작업을 commit 해 두었습니다. 이 시점으로 코드를 되돌릴 수 있습니다."
MSG_UPLOADED = "작업을 GitHub 에 push(업로드)해 팀이 함께 보는 main 에 합쳤습니다."
MSG_CONFLICT = "GitHub에 올라온 것과 지금 PC에 저장된 것이 달라 올리기를 멈췄습니다. 이어서 확인하겠습니다."
MSG_NO_UPLOAD = "GitHub에 올릴 새 작업이 없습니다."
MSG_OTHER_OWNER = "올리려는 곳이 회사 GitHub(KiwoomAX)가 아닙니다."
MSG_RULES = "저장 규칙을 읽지 못해 저장을 멈췄습니다. AX팀에 알려 주세요."
MSG_TIMEOUT = "저장이 오래 걸려 멈췄습니다. 다음에 다시 저장합니다."
MSG_FAILED = "저장하지 못했습니다. 원인을 확인해 이어서 처리합니다."

MERGE_DETAIL = (
    "앞선 upload 의 merge 가 충돌로 멈춘 채 남아 있다. 충돌한 파일을 saving-work 의 충돌 규칙대로 풀고 "
    "git add 한 뒤 save_work.py upload --continue --repo <폴더> 를 실행하라. 그 전에는 commit 하지 않는다."
)


class BranchChoiceError(Exception):
    """커밋할 작업 브랜치를 정하지 못했을 때 올린다. 메시지가 그대로 detail 이 된다."""


def commit_result(status, message, detail="", excluded=None, committed=False, branch=None, state=None):
    state = state or {}
    return {
        "status": status,
        "committed": committed,
        "branch": branch,
        "unpushed": state.get("unpushed", False),
        "first_push": state.get("first_push", False),
        "history_reset": state.get("history_reset", ""),
        "excluded": excluded or [],
        "message": message,
        "detail": detail,
    }


def locate(start):
    if not Path(start).is_dir():
        return None
    code, out, _ = gitcmd.git_try(start, "rev-parse", "--show-toplevel")
    top = out.strip()
    return Path(top).resolve() if code == 0 and top else None


def normalize_url(url):
    return url.strip().replace("\\", "/").replace("github.com:", "github.com/").lower()


REMOTE_PATTERN = re.compile(r"github\.com[/:]([^/]+)/([^/]+?)(?:\.git)?/?$", re.IGNORECASE)


def read_marker(top):
    """표식 파일을 {키: 값} 으로 읽는다. 파일이 없으면 빈 dict 다."""
    try:
        text = (Path(top) / MARKER).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    pairs = (line.strip().split("=", 1) for line in text.splitlines() if "=" in line)
    return {key.strip(): value.strip() for key, value in pairs}


def set_marker(top, key, value):
    """같은 키가 있으면 값을 바꾸고 없으면 끝에 붙인다. 줄 순서는 그대로 둔다."""
    values = read_marker(top)
    values[key] = str(value)
    text = "".join(f"{name}={item}\n" for name, item in values.items())
    (Path(top) / MARKER).write_text(text, encoding="utf-8", newline="\n")


def is_feature_repo(top):
    # 원격은 첫 push 때 생기므로 표식 파일만 본다.
    return (Path(top) / MARKER).is_file()


def origin_url(top):
    # 설정에 적힌 주소를 그대로 읽는다. remote get-url 은 url.<base>.insteadOf 로 바꾼 주소를 준다.
    code, url, _ = gitcmd.git_try(top, "config", "--get", "remote.origin.url")
    return url.strip() if code == 0 and url.strip() else None


def parse_remote(url):
    """GitHub 주소에서 (소유자, 이름) 을 읽는다. GitHub 주소가 아니면 None 이다."""
    match = REMOTE_PATTERN.search(url.strip().replace("\\", "/"))
    return (match.group(1), match.group(2)) if match else None



def current_branch(top, deadline=None):
    # rev-parse --abbrev-ref HEAD 는 커밋이 없는 새 레포에서 오류로 끝난다. symbolic-ref 는 main 을 준다.
    code, out, _ = gitcmd.git_try(top, "symbolic-ref", "--short", "-q", "HEAD", deadline=deadline)
    return out.strip() if code == 0 else None


def git_dir(top, deadline=None, timeout=None):
    return Path(gitcmd.git(top, "rev-parse", "--absolute-git-dir", deadline=deadline, timeout=timeout).strip())


def rebase_in_progress(gdir):
    return (gdir / "rebase-merge").exists() or (gdir / "rebase-apply").exists()


def recover(top, deadline=None):
    """앞선 저장이 끊기며 남긴 상태를 치운다. rebase 를 취소하려면 lock 이 먼저 없어야 한다."""
    gdir = git_dir(top, deadline)
    lock = gdir / "index.lock"
    if lock.exists() and time.time() - lock.stat().st_mtime > LOCK_MAX_AGE:
        lock.unlink()
    if rebase_in_progress(gdir):
        gitcmd.git(top, "rebase", "--abort", deadline=deadline, check=False)


def _local_config(top, key, deadline):
    # --local 을 빼면 전역 설정까지 읽어, 이 레포에 작성자가 없는데도 있다고 본다.
    code, out, _ = gitcmd.git_try(top, "config", "--local", "--get", key, deadline=deadline)
    return out.strip() if code == 0 else ""


def ensure_author(top, deadline=None):
    """커밋 작성자 정보가 이 레포에 없으면 GitHub 계정에서 받아 이 레포에만 적는다."""
    if _local_config(top, "user.name", deadline) and _local_config(top, "user.email", deadline):
        return
    user = json.loads(gitcmd.gh("api", "user", deadline=deadline))
    gitcmd.git(top, "config", "--local", "user.name", user["login"], deadline=deadline)
    gitcmd.git(top, "config", "--local", "user.email",
               f"{user['id']}+{user['login']}@users.noreply.github.com", deadline=deadline)


def has_head(top, deadline=None):
    return gitcmd.git_try(top, "rev-parse", "--verify", "-q", "HEAD", deadline=deadline)[0] == 0


def reset_index(top, deadline=None):
    # 앞서 git add 로 올라간 파일이 검사를 건너 커밋되지 않도록 인덱스를 HEAD 와 같게 되돌린다.
    # 커밋할 경로를 지정하는 방식은 추적을 끊은 파일을 다시 올리므로 쓰지 않는다.
    if has_head(top, deadline):
        gitcmd.git(top, "reset", "-q", deadline=deadline)
    else:
        gitcmd.git(top, "read-tree", "--empty", deadline=deadline)


def changed_paths(top, deadline=None):
    entries = gitcmd.git_z(top, "status", "--porcelain=v1", "-z", "--untracked-files=all", deadline=deadline)
    paths, index = [], 0
    while index < len(entries):
        entry = entries[index]
        paths.append(entry[3:])
        if "R" in entry[:2] or "C" in entry[:2]:
            # 이름 변경과 복사는 다음 항목에 원래 경로가 따로 온다.
            index += 1
            if index < len(entries):
                paths.append(entries[index])
        index += 1
    return paths


def _size(full):
    return full.stat().st_size if full.is_file() else 0


def _read(full):
    try:
        return full.read_bytes()
    except OSError:  # 지워진 파일이나 읽을 수 없는 파일이다
        return b""


def ignore_line(path):
    return "/" + "".join("\\" + ch if ch in GITIGNORE_SPECIAL else ch for ch in path)


def add_to_gitignore(top, paths):
    ignore = top / ".gitignore"
    text = ignore.read_text(encoding="utf-8", errors="replace") if ignore.exists() else ""
    existing = set(text.splitlines())
    new = [line for line in dict.fromkeys(ignore_line(path) for path in paths) if line not in existing]
    if not new:
        return
    prefix = "" if not text or text.endswith("\n") else "\n"
    with open(ignore, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(prefix + "\n".join(new) + "\n")


def _pathspec(top, command, paths, deadline):
    # 경로를 표준 입력으로 넘긴다. Windows 명령줄 길이 제한에 걸리지 않게 하기 위해서다.
    gitcmd.git(top, *command, "--pathspec-from-file=-", "--pathspec-file-nul",
               deadline=deadline, stdin="\0".join(paths).encode("utf-8"))


def _excluded(path, reason, rule):
    return {"path": path, "reason": reason, "rule": rule}


def _judge(top, data, path):
    full = top / path
    return rules.judge(data, path, _size(full), lambda: _read(full))


def _pushed_has_secret(top, data, path, deadline):
    """HEAD 에 있는 판본의 내용이 비밀값 규칙에 해당하는지 본다."""
    raw = gitcmd.git_bytes(top, "cat-file", "blob", f"HEAD:{path}", deadline=deadline)
    verdict = rules.judge(data, path, len(raw), lambda: raw)
    return verdict is not None and verdict[0] == "secret-content"


def ensure_gitignore(top):
    """.gitignore 가 없으면 기본값으로 만들고, 있으면 설계 문서를 가리는 줄이 빠졌을 때만 더한다."""
    ignore = top / ".gitignore"
    if not ignore.exists():
        ignore.write_text("\n".join(DEFAULT_GITIGNORE) + "\n", encoding="utf-8", newline="\n")
        return
    text = ignore.read_text(encoding="utf-8", errors="replace")
    if {DESIGN_DOCS, "/" + DESIGN_DOCS} & {line.strip() for line in text.splitlines()}:
        return
    prefix = "" if not text or text.endswith("\n") else "\n"
    with open(ignore, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(prefix + DESIGN_DOCS + "\n")


def stage(top, data, deadline=None):
    """인덱스를 HEAD 로 되돌린 뒤 검사를 통과한 변경만 스테이징한다. excluded 목록을 돌려준다."""
    reset_index(top, deadline)
    ensure_gitignore(top)
    # 인덱스를 HEAD 로 되돌렸으므로 ls-files 는 이미 올라간 파일 목록이다.
    tracked = set(gitcmd.git_z(top, "ls-files", "-z", deadline=deadline))
    # 예전에 올라간 설계 문서는 추적만 끊는다. 파일은 PC 에 남고 개발자에게 알리지 않는다.
    design_docs = sorted(path for path in tracked if path.startswith(DESIGN_DOCS))
    if design_docs:
        _pathspec(top, ("rm", "-q", "--cached", "--ignore-unmatch"), design_docs, deadline)
        tracked -= set(design_docs)
    changed = [path for path in changed_paths(top, deadline) if not path.startswith(DESIGN_DOCS)]
    staged, excluded, ignore = [], [], []
    for path in changed:
        verdict = _judge(top, data, path)
        if verdict is None:
            staged.append(path)
            continue
        found, rule = verdict
        reason = found
        if found == "secret-filename" and path in tracked:
            reason = "secret-filename-tracked"
        elif found == "secret-content" and path in tracked and _pushed_has_secret(top, data, path, deadline):
            # 고친 파일이어도 이미 올라간 판본에 비밀값이 있으면 그 값은 밖에 나갔다.
            reason = "secret-content-tracked"
        excluded.append(_excluded(path, reason, rule))
        # 내용에 비밀값이 든 코드 파일은 고친 뒤 다시 올라가야 하므로 이번 저장에서만 뺀다.
        if found != "secret-content":
            ignore.append(path)
    # git status 는 이번에 바뀌지 않은 파일을 보여 주지 않는다. 이미 올라간 파일은 따로 본다.
    # 예전에 잘못 올라간 파일과 .gitignore 없이 올라가기 시작한 파일을 저장할 때마다 바로잡는다.
    for path in sorted(tracked - set(changed)):
        verdict = _judge(top, data, path)
        if verdict is None:
            continue
        reason, rule = verdict
        if reason == "secret-content":
            # 이미 올라간 코드다. 코드는 고친 뒤 다시 올라가야 하므로 추적은 그대로 두고 알린다.
            excluded.append(_excluded(path, "secret-content-tracked", rule))
            continue
        if reason == "secret-filename":
            reason = "secret-filename-tracked"
        excluded.append(_excluded(path, reason, rule))
        ignore.append(path)
    if ignore:
        add_to_gitignore(top, ignore)
        _pathspec(top, ("rm", "-q", "--cached", "--ignore-unmatch"), ignore, deadline)
    if (top / ".gitignore").exists():
        staged.append(".gitignore")
    if staged:
        _pathspec(top, ("add",), staged, deadline)
    return excluded


def has_staged_changes(top, deadline=None):
    code, _, err = gitcmd.git_try(top, "diff", "--cached", "--quiet", deadline=deadline)
    if code not in (0, 1):
        raise gitcmd.GitError(f"git diff --cached --quiet 실패(종료 코드 {code}): {err.strip()}")
    return code == 1


def commit(top, message, excluded, deadline=None):
    # 이슈 번호는 붙이지 않는다. 이슈는 upload 의 merge 커밋이 연결한다.
    lines = [message]
    if excluded:
        lines.append("")
        lines += [f"Excluded: {item['path']} ({item['reason']}, {item['rule']})" for item in excluded]
    gitcmd.git(top, "commit", "-q", "-F", "-", deadline=deadline,
               stdin=("\n".join(lines) + "\n").encode("utf-8"))


def with_notes(base, excluded):
    if not excluded:
        return base
    lines = [base, "아래 파일을 확인해 주세요."]
    lines += [f"- {item['path']}: {EXCLUDE_NOTES[item['reason']]}" for item in excluded]
    return "\n".join(lines)


def _count(top, spec, deadline):
    return int(gitcmd.git(top, "rev-list", "--count", spec, deadline=deadline).strip() or 0)


def _ref_exists(top, ref, deadline):
    return gitcmd.git_try(top, "rev-parse", "--verify", "-q", ref, deadline=deadline)[0] == 0


def _branches(top, deadline):
    out = gitcmd.git(top, "for-each-ref", "--format=%(refname:short)", "refs/heads/", deadline=deadline)
    return out.split()


def work_branches(top, deadline=None):
    return [name for name in _branches(top, deadline) if name.startswith(WORK_PREFIXES)]


def _base(top, deadline):
    """미반영 커밋을 세는 기준이다. 원격 main 이 없으면 로컬 main 의 첫 커밋이다."""
    if _ref_exists(top, REMOTE_REF, deadline):
        return REMOTE_REF
    if not _ref_exists(top, f"refs/heads/{BRANCH}", deadline):
        return None
    roots = gitcmd.git(top, "rev-list", "--max-parents=0", BRANCH, deadline=deadline).split()
    return roots[-1] if roots else None


def _ahead(top, ref, deadline):
    base = _base(top, deadline)
    return _count(top, f"{base}..{ref}", deadline) if base else 0


def unpushed(top, deadline=None):
    """origin/main 에 없는 커밋이 main 이나 작업 브랜치에 있으면 참이다. 로컬 정보로만 정한다."""
    if not _ref_exists(top, REMOTE_REF, deadline):
        return _ref_exists(top, f"refs/heads/{BRANCH}", deadline) or bool(work_branches(top, deadline))
    return any(_ahead(top, ref, deadline) for ref in [BRANCH, *work_branches(top, deadline)])


def local_state(top, deadline=None):
    return {
        "unpushed": unpushed(top, deadline),
        "first_push": not _ref_exists(top, REMOTE_REF, deadline),
        "history_reset": read_marker(top).get("history-reset", ""),
    }


def relocate_main(top, deadline=None):
    """작업 브랜치에 있을 때 로컬 main 의 미반영 커밋을 그 브랜치에 남기고 main 만 되돌린다."""
    current = current_branch(top, deadline)
    base = _base(top, deadline)
    if not current or not current.startswith(WORK_PREFIXES) or base is None:
        return
    if not _ahead(top, BRANCH, deadline):
        return
    contained = gitcmd.git_try(top, "merge-base", "--is-ancestor", BRANCH, "HEAD", deadline=deadline)[0] == 0
    # main 에만 있는 커밋이 앞선 업로드의 merge 커밋뿐이면 내용은 모두 이 작업 브랜치에 있다.
    only_merges = not gitcmd.git(top, "rev-list", "--no-merges", f"{base}..{BRANCH}", "^HEAD",
                                 deadline=deadline).strip()
    if not contained and not only_merges:
        raise BranchChoiceError(
            f"로컬 main 에 작업 브랜치 {current} 에 없는 미반영 커밋이 있다. 두 작업이 섞여 있으므로 "
            "개발자에게 어느 작업을 먼저 올릴지 묻고, git log main 과 git log 로 커밋을 확인해 정리하라.")
    gitcmd.git(top, "branch", "-f", BRANCH, base, deadline=deadline)


def check_head(top, deadline=None):
    """HEAD 가 main 이나 작업 브랜치가 아니면 멈춘다. 예전 기록 위에 작업 브랜치가 생기지 않게 하기 위해서다."""
    current = current_branch(top, deadline)
    if current != BRANCH and not (current or "").startswith(WORK_PREFIXES):
        raise BranchChoiceError(
            f"지금 브랜치가 {current or '분리된 HEAD(detached)'} 다. local-history 같은 예전 기록 위에서는 commit 과 "
            "업로드를 하지 않는다. git switch main 으로 옮긴 뒤 다시 실행하라.")


def choose_branch(top, wanted, catch_up, deadline=None):
    """spec 「작업 브랜치 정하기」대로 커밋할 브랜치로 옮기고 그 이름을 돌려준다."""
    check_head(top, deadline)
    if not _ref_exists(top, f"refs/heads/{BRANCH}", deadline):
        return BRANCH  # 첫 커밋은 main 에 둔다
    candidates = [name for name in work_branches(top, deadline) if _ahead(top, name, deadline)]
    if len(candidates) > 1:
        raise BranchChoiceError(
            f"미반영 커밋이 있는 작업 브랜치가 둘 이상이다: {', '.join(candidates)}. 개발자에게 어느 작업을 "
            "먼저 올릴지 묻고, 그 브랜치를 upload 로 올린 뒤 다시 commit 하라.")
    if candidates:
        target = candidates[0]
        if current_branch(top, deadline) != target:
            gitcmd.git(top, "switch", "-q", target, deadline=deadline)
    else:
        target = wanted
        if target is None and catch_up:
            target = SESSION_BRANCH.format(stamp=datetime.now().strftime("%Y%m%d-%H%M"))
        if target is None:
            raise BranchChoiceError(
                "새 작업 브랜치가 필요하다. 작업 내용에 맞게 feat/·fix/·refactor/·docs/ 뒤에 영문 요약을 붙인 "
                "이름을 --branch 로 넘겨 다시 실행하라.")
        if not target.startswith(WORK_PREFIXES):
            raise BranchChoiceError(f"--branch {target} 는 feat/·fix/·refactor/·docs/ 로 시작해야 한다.")
        # 같은 이름이 남아 있어도 미반영 커밋이 없는 브랜치이므로 지금 위치에서 다시 만든다.
        gitcmd.git(top, "switch", "-q", "-C", target, deadline=deadline)
    relocate_main(top, deadline)
    return target


def restore_upload_stash(top, deadline=None, timeout=None):
    """앞선 upload 가 남긴 kiwoom-upload stash 를 되돌린다. 되돌리지 못하면 detail 문장을 돌려준다."""
    listing = gitcmd.git(top, "stash", "list", "--format=%gd %gs", deadline=deadline, timeout=timeout)
    for line in listing.splitlines():
        ref, _, subject = line.partition(" ")
        if subject.endswith(f": {UPLOAD_STASH}"):
            code, out, err = gitcmd.git_try(top, "stash", "pop", "-q", ref, deadline=deadline, timeout=timeout)
            if code != 0:
                # 충돌 표식이 남은 파일이 다음 commit 에 들어가지 않도록 HEAD 상태로 되돌린다.
                gitcmd.git(top, "reset", "-q", "--merge", deadline=deadline, timeout=timeout, check=False)
                return (f"검사에서 뺀 파일의 수정을 담은 {UPLOAD_STASH} stash 를 되돌리다 충돌했다. stash 는 남아 "
                        f"있다. git stash list 로 확인해 충돌한 파일을 풀고 git stash drop 하라. {(err or out).strip()}")
            return None
    return None


def commit_work(repo, message, branch=None, catch_up=False):
    """로컬에서만 커밋하고 결과 JSON 을 돌려준다. 예외를 failed 로 바꾸는 곳은 여기 하나다."""
    if catch_up:
        message = CATCH_UP_TEMPLATE.format(stamp=datetime.now().strftime("%Y-%m-%d %H:%M"))
    deadline = gitcmd.Deadline(CATCH_UP_SECONDS if catch_up else SAVE_SECONDS)
    progress = {"committed": False, "excluded": [], "branch": None}
    try:
        return _commit_work(Path(repo), message, branch, catch_up, deadline, progress)
    except BranchChoiceError as exc:
        return _failed(progress, MSG_FAILED, str(exc))
    except rules.RulesError as exc:
        return _failed(progress, MSG_RULES,
                       f"규칙 파일 오류다. upload_rules.json 을 고쳐야 하며 개발자가 풀 일이 아니다. {exc}")
    except gitcmd.CommandTimeout as exc:
        return _failed(progress, MSG_TIMEOUT, f"제한 시간을 넘겨 멈췄다. 한 번만 다시 실행하라. {exc}")
    except gitcmd.ToolMissing as exc:
        return _failed(progress, MSG_FAILED, f"{exc}. 개발자에게 kw_install 을 다시 실행하라고 안내하라.")
    except gitcmd.GitError as exc:
        return _failed(progress, MSG_FAILED, f"명령이 실패했다. 출력을 읽고 원인을 처리한 뒤 다시 실행하라. {exc}")
    except Exception as exc:  # noqa: BLE001 — 훅과 스킬은 어떤 경우에도 JSON 을 받아야 한다
        return _failed(progress, MSG_FAILED, f"예상하지 못한 오류다: {exc.__class__.__name__}: {exc}")


def _failed(progress, message, detail):
    return commit_result("failed", message, detail, excluded=progress["excluded"],
                         committed=progress["committed"], branch=progress["branch"])


def _commit_work(repo, message, wanted, catch_up, deadline, progress):
    top = locate(repo)
    if top is None or not is_feature_repo(top):
        return commit_result("not-feature-repo", MSG_NOT_FEATURE)
    recover(top, deadline)
    if (git_dir(top, deadline) / "MERGE_HEAD").exists():
        return commit_result("failed", MSG_FAILED, MERGE_DETAIL, branch=current_branch(top, deadline))
    note = restore_upload_stash(top, deadline) or ""
    data = rules.load(RULES_PATH)
    excluded = stage(top, data, deadline)
    progress["excluded"] = excluded
    if not has_staged_changes(top, deadline):
        return commit_result("nothing", with_notes(MSG_NOTHING, excluded), note, excluded,
                             branch=current_branch(top, deadline), state=local_state(top, deadline))
    target = choose_branch(top, wanted, catch_up, deadline)
    progress["branch"] = target
    ensure_author(top, deadline)
    commit(top, message, excluded, deadline)
    progress["committed"] = True
    return commit_result("committed", with_notes(MSG_COMMITTED, excluded), note, excluded,
                         committed=True, branch=target, state=local_state(top, deadline))


class UploadStop(Exception):
    """업로드 준비나 업로드를 멈춰야 할 때 올린다. 메시지가 그대로 detail 이 된다."""


def origin_owner(top):
    url = origin_url(top)
    parsed = parse_remote(url) if url else None
    return parsed[0] if parsed else None


def remote_description(full, deadline=None):
    out = gitcmd.gh("repo", "view", full, "--json", "description", "--jq", ".description",
                    deadline=deadline)
    return out.strip()


def _create_remote(top, name, title, deadline):
    full = f"{ORG}/{name}"
    try:
        gitcmd.gh("repo", "create", full, "--private", "--description", title, deadline=deadline)
    except gitcmd.GitError as exc:
        # 볼 권한이 없는 같은 이름의 레포가 있을 수 있으므로, 이미 있는 레포를 이 폴더의 원격으로 쓰지 않는다.
        raise UploadStop(
            f"GitHub 코드 저장소를 만들지 못했다. 이름이 겹치면 다른 이름을 정해 표식 파일의 name 을 고친 뒤 "
            f"prepare-upload 를 다시 실행하라. {exc}") from exc
    gitcmd.git(top, "remote", "add", "origin", REMOTE_URL.format(full=full), deadline=deadline)


def _issue_body(title, deadline):
    code, out, _ = gitcmd.gh_try("api", "-H", "Accept: application/vnd.github.raw", TEMPLATE_API, deadline=deadline)
    if code != 0 or not out.strip():
        return title + "\n"
    template = HTML_COMMENT.sub("", FRONTMATTER.sub("", out.replace("\r\n", "\n")))
    return f"{title}\n\n{template.strip()}\n"


def _feature_issue(top, full, name, title, deadline, body_file=None):
    known = read_marker(top).get("issue")
    if known:
        return int(known)
    wanted = f"[{name}] {title}"
    found = json.loads(gitcmd.gh("issue", "list", "-R", full, "--state", "open", "--search", f"{wanted} in:title",
                                 "--json", "number,title", "--limit", "100", deadline=deadline) or "[]")
    numbers = [item["number"] for item in found if item.get("title") == wanted]
    if numbers:
        number = numbers[0]
    else:
        folder = Path(tempfile.mkdtemp(prefix="kiwoom-issue-"))  # 레포 밖에 쓴다
        try:
            body = folder / "body.md"
            # Claude 가 템플릿의 절을 채운 본문을 넘기면 그대로 쓴다. 없으면 빈 템플릿을 붙인다.
            text = Path(body_file).read_text(encoding="utf-8") if body_file else _issue_body(title, deadline)
            body.write_text(text, encoding="utf-8", newline="\n")
            url = gitcmd.gh("issue", "create", "-R", full, "--title", wanted, "--body-file", str(body),
                            "--assignee", "@me", deadline=deadline)
        finally:
            shutil.rmtree(folder, ignore_errors=True)
        number = int(url.strip().rstrip("/").rsplit("/", 1)[-1])
        gitcmd.gh_try("api", "-X", "PATCH", f"repos/{full}/issues/{number}", "-f", "type=Feature", deadline=deadline)
    set_marker(top, "issue", number)
    return number


OTHER_OWNER_DETAIL = (
    "origin 의 push 주소({url})가 KiwoomAX 레포가 아니다. 개발자에게 '올리려는 곳이 회사 GitHub(KiwoomAX)가 아닙니다. "
    "{url} 에 올려도 될까요?' 라고 묻고, 동의하면 같은 명령에 --allow-other-owner 를 붙여 다시 실행하라."
)


def other_owner_url(top, deadline=None):
    """origin 의 push 주소 중 KiwoomAX 레포가 아닌 주소를 돌려준다. 모두 KiwoomAX 면 None 이다."""
    code, out, _ = gitcmd.git_try(top, "config", "--get-all", "remote.origin.pushurl", deadline=deadline)
    urls = out.split() if code == 0 and out.strip() else [origin_url(top)]
    for url in urls:
        parsed = parse_remote(url) if url else None
        if parsed is None or parsed[0].lower() != ORG.lower():
            return url
    return None


def prepare_upload(repo, allow_other_owner=False, body_file=None):
    """원격 레포·topic·팀 권한·기능 이슈를 맞춘다. 예외를 failed 로 바꾸는 곳은 여기 하나다."""
    deadline = gitcmd.Deadline(SAVE_SECONDS)
    try:
        return _prepare_upload(Path(repo), deadline, allow_other_owner, body_file)
    except UploadStop as exc:
        return _ready_result("failed", MSG_FAILED, str(exc))
    except gitcmd.CommandTimeout as exc:
        return _ready_result("failed", MSG_TIMEOUT, f"제한 시간을 넘겨 멈췄다. 한 번만 다시 실행하라. {exc}")
    except gitcmd.ToolMissing as exc:
        return _ready_result("failed", MSG_FAILED, f"{exc}. 개발자에게 kw_install 을 다시 실행하라고 안내하라.")
    except gitcmd.GitError as exc:
        return _ready_result("failed", MSG_FAILED, f"명령이 실패했다. 출력을 읽고 원인을 처리한 뒤 다시 실행하라. {exc}")
    except Exception as exc:  # noqa: BLE001 — 스킬은 어떤 경우에도 JSON 을 받아야 한다
        return _ready_result("failed", MSG_FAILED, f"예상하지 못한 오류다: {exc.__class__.__name__}: {exc}")


def _ready_result(status, message, detail="", repo=None, feature_issue=None, team_shared=None):
    return {"status": status, "repo": repo, "feature_issue": feature_issue, "team_shared": team_shared,
            "excluded": [], "message": message, "detail": detail}


def _prepare_upload(repo, deadline, allow_other_owner, body_file=None):
    top = locate(repo)
    if top is None or not is_feature_repo(top):
        return _ready_result("failed", MSG_NOT_FEATURE, "표식 파일이 없는 폴더다. starting-feature-repo 로 준비하라.")
    marker = read_marker(top)
    url = origin_url(top)
    if url:
        # 원격이 있으면 실제로 올라갈 곳은 origin 이다. 표식의 name 보다 주소의 이름을 쓴다.
        parsed = parse_remote(url)
        if parsed is None:
            raise UploadStop(f"origin 주소({url})에서 GitHub 레포 이름을 읽지 못했다.")
        owner, name = parsed
        other = other_owner_url(top, deadline)
        if other and not allow_other_owner:
            return _ready_result("other-owner", MSG_OTHER_OWNER, OTHER_OWNER_DETAIL.format(url=other))
    elif not marker.get("name"):
        raise UploadStop("표식 파일에 name 이 없다. 영문 레포 이름을 정해 name=<이름> 줄을 넣고 다시 실행하라.")
    else:
        owner, name = ORG, marker["name"]
        _create_remote(top, name, marker.get("title") or name, deadline)
    full = f"{owner}/{name}"
    company = owner.lower() == ORG.lower()
    if marker.get("issue"):
        # 기능 이슈까지 마친 레포다. topic 과 팀 권한은 그때 이미 맞췄다.
        return _ready_result("ready", "", repo=full, feature_issue=int(marker["issue"]))
    team_shared = None
    if company:
        # topic 과 팀 권한은 회사 레포에만 단다.
        gitcmd.gh("repo", "edit", full, "--add-topic", TOPIC, deadline=deadline)
        if marker.get("team"):
            team_shared = gitcmd.gh_try("api", "-X", "PUT", f"orgs/{ORG}/teams/{marker['team']}/repos/{full}",
                                        "-f", "permission=pull", deadline=deadline)[0] == 0
    title = marker.get("title") or remote_description(full, deadline) or name
    number = _feature_issue(top, full, name, title, deadline, body_file)
    return _ready_result("ready", "", repo=full, feature_issue=number, team_shared=team_shared)


UPLOAD_STATE = "kiwoom-upload.json"
CONFLICT_DETAIL = (
    "GitHub 공유 코드와 작업 브랜치의 같은 줄이 겹쳐 merge 를 멈췄다. 충돌한 파일: {files}. 양쪽 동작이 같고 "
    "줄바꿈·공백·표기만 다르면 묻지 말고 풀어라. 동작이 다를 때만 개발자에게 'GitHub에 올라온 것'과 "
    "'지금 PC에 저장된 것'을 A 와 B 로 적어 묻는다. 풀고 git add 한 뒤 save_work.py upload --continue --repo <폴더> "
    "를 실행하라. 검사에서 뺀 파일의 수정은 kiwoom-upload stash 에 있고 --continue 가 끝날 때 되돌린다."
)


def _state_path(top, deadline=None):
    return git_dir(top, deadline) / UPLOAD_STATE


def _merge_message(top, state):
    lines = [state["title"], "", f"closes #{state['task']}"]
    lines += [f"closes #{number}" for number in state.get("close", [])]
    issue = read_marker(top).get("issue")
    # 닫는 기능 이슈는 closes 줄이 이미 연결한다.
    if issue and int(issue) not in state.get("close", []):
        lines.append(f"#{issue}")
    return "\n".join(lines) + "\n"


def _unmerged(top, deadline):
    return gitcmd.git_z(top, "diff", "--name-only", "-z", "--diff-filter=U", deadline=deadline)


def _work_branch_for_upload(top, deadline):
    """올릴 작업 브랜치로 옮기고 이름을 돌려준다. 원격 main 만 비어 있고 작업 브랜치가 없으면 None 이다."""
    try:
        check_head(top, deadline)
    except BranchChoiceError as exc:
        raise UploadStop(str(exc)) from exc
    current = current_branch(top, deadline)
    candidates = [name for name in work_branches(top, deadline) if _ahead(top, name, deadline)]
    if current and current.startswith(WORK_PREFIXES):
        candidates = [name for name in candidates if name != current]
        if candidates:
            raise UploadStop(f"미반영 커밋이 있는 작업 브랜치가 둘 이상이다: {current}, {', '.join(candidates)}. "
                             "개발자에게 어느 작업을 먼저 올릴지 묻고 그 브랜치로 옮긴 뒤 다시 실행하라.")
        relocate_main(top, deadline)
        return current
    if len(candidates) > 1:
        raise UploadStop(f"미반영 커밋이 있는 작업 브랜치가 둘 이상이다: {', '.join(candidates)}. "
                         "개발자에게 어느 작업을 먼저 올릴지 묻고 그 브랜치로 옮긴 뒤 다시 실행하라.")
    if candidates:
        gitcmd.git(top, "switch", "-q", candidates[0], deadline=deadline)
        relocate_main(top, deadline)
        return candidates[0]
    if not _ref_exists(top, REMOTE_REF, deadline):
        return None  # 첫 push 이고 main 만 있다
    # 이전 방식에서 push 하지 못한 main 의 커밋이나 main 위의 변경을 작업 브랜치로 옮긴다.
    name = SESSION_BRANCH.format(stamp=datetime.now().strftime("%Y%m%d-%H%M"))
    gitcmd.git(top, "switch", "-q", "-C", name, deadline=deadline)
    relocate_main(top, deadline)
    return name


def _stash_leftovers(top, deadline, progress):
    """검사에서 빠져 커밋되지 않은 수정을 치운다. 브랜치를 오가는 동안 작업 트리를 비워 두기 위해서다."""
    if gitcmd.git(top, "status", "--porcelain", "--untracked-files=all", deadline=deadline).strip():
        # gitcmd 가 거는 GIT_LITERAL_PATHSPECS=1 아래에서는 stash -u 가 추적되지 않는 파일을 stash 에 넣고도
        # 작업 트리에서 지우지 않는다(2026-10-20 이 PC 에서 재현). 이 호출에서만 끈다.
        gitcmd.git(top, "--no-literal-pathspecs", "stash", "push", "-q", "-u", "-m", UPLOAD_STASH, deadline=deadline)
        progress["stashed"] = True


def _merge(top, branch, state, deadline, progress):
    """5·6단계다. 원격 main 에 맞춘 main 에 작업 브랜치를 --no-ff 로 합친다. 충돌하면 충돌 파일 목록을 돌려준다."""
    gitcmd.git(top, "fetch", "-q", "origin", deadline=deadline)
    # git 은 체크아웃된 브랜치의 branch -f 를 거부하므로 작업 브랜치로 먼저 옮긴다.
    gitcmd.git(top, "switch", "-q", branch, deadline=deadline)
    gitcmd.git(top, "branch", "-f", BRANCH, REMOTE_REF, deadline=deadline)
    gitcmd.git(top, "switch", "-q", BRANCH, deadline=deadline)
    ensure_author(top, deadline)
    progress["merge_started"] = True
    code, out, err = gitcmd.git_try(top, "merge", "--no-ff", "--no-commit", branch, deadline=deadline)
    if code != 0:
        files = _unmerged(top, deadline)
        if files:
            return files
        raise gitcmd.GitError(f"git merge 실패: {(err or out).strip()}")
    gitcmd.git(top, "commit", "-q", "-F", "-", deadline=deadline, stdin=_merge_message(top, state).encode("utf-8"))
    progress["merge_started"] = False
    return None


def _push_main(top, deadline):
    return gitcmd.git_try(top, "push", "-q", "origin", BRANCH, deadline=deadline)[0] == 0


def upload(repo, task=None, title=None, close=(), resume=False, allow_other_owner=False):
    """승인받은 작업을 GitHub 공유 코드에 올린다. 예외를 failed 로 바꾸는 곳은 여기 하나다."""
    deadline = gitcmd.Deadline(SAVE_SECONDS)
    progress = {"top": None, "stashed": False, "merge_started": False, "pushed": False, "excluded": []}
    try:
        payload = _upload(Path(repo), task, title, list(close), resume, deadline, progress, allow_other_owner)
    except UploadStop as exc:
        payload = _upload_result("failed", MSG_FAILED, str(exc), progress)
    except rules.RulesError as exc:
        payload = _upload_result("failed", MSG_RULES, f"규칙 파일 오류다. upload_rules.json 을 고쳐야 한다. {exc}",
                                 progress)
    except gitcmd.CommandTimeout as exc:
        payload = _upload_result("failed", MSG_TIMEOUT, f"제한 시간을 넘겨 멈췄다. 한 번만 다시 실행하라. {exc}",
                                 progress)
        _abort_own_merge(progress)
    except gitcmd.ToolMissing as exc:
        payload = _upload_result("failed", MSG_FAILED, f"{exc}. 개발자에게 kw_install 을 다시 실행하라고 안내하라.",
                                 progress)
    except gitcmd.GitError as exc:
        payload = _upload_result("failed", MSG_FAILED,
                                 f"명령이 실패했다. 출력을 읽고 원인을 처리한 뒤 다시 실행하라. {exc}", progress)
    except Exception as exc:  # noqa: BLE001 — 스킬은 어떤 경우에도 JSON 을 받아야 한다
        payload = _upload_result("failed", MSG_FAILED, f"예상하지 못한 오류다: {exc.__class__.__name__}: {exc}",
                                 progress)
    note = " ".join(filter(None, [progress.get("note"), _restore_after_upload(progress, payload["status"] == "uploaded")]))
    if note:
        payload["detail"] = f"{payload['detail']} {note}".strip()
    return payload


def _upload_result(status, message, detail, progress):
    return {"status": status, "pushed": progress["pushed"], "excluded": progress["excluded"],
            "message": message, "detail": detail}


def _abort_own_merge(progress):
    """시간 초과 때 이번 실행이 시작한 merge 만 취소한다. --continue 가 이어받은 merge 는 개발자의 해결이 담겨 있다."""
    top = progress["top"]
    if top is None or not progress["merge_started"]:
        return
    try:
        if (git_dir(top, timeout=ABORT_SECONDS) / "MERGE_HEAD").exists():
            gitcmd.git(top, "merge", "--abort", timeout=ABORT_SECONDS, check=False)
    except Exception:  # noqa: BLE001 — 취소하지 못하면 다음 commit 이 merge 중이라고 알린다
        pass


def _restore_after_upload(progress, uploaded):
    """치운 수정을 되돌린다. merge 가 진행 중이면 그 수정이 merge 에 섞이지 않도록 stash 에 남긴다."""
    top = progress["top"]
    if top is None or not progress["stashed"]:
        return ""
    try:
        if (git_dir(top, timeout=ABORT_SECONDS) / "MERGE_HEAD").exists():
            return ""
        branch = progress.get("branch")
        if not uploaded and branch and current_branch(top) != branch:
            # 중간에 멈추면 main 에는 작업 브랜치의 파일이 없을 수 있다. stash 를 만든 작업 브랜치로 돌아가 되돌린다.
            gitcmd.git(top, "switch", "-q", branch, timeout=ABORT_SECONDS)
        return restore_upload_stash(top, timeout=ABORT_SECONDS) or ""
    except Exception as exc:  # noqa: BLE001
        return f"{UPLOAD_STASH} stash 를 되돌리지 못했다. git stash list 로 확인하라. {exc}"


def _upload(repo, task, title, close, resume, deadline, progress, allow_other_owner):
    top = locate(repo)
    if top is None or not is_feature_repo(top):
        return _upload_result("failed", MSG_NOT_FEATURE, "표식 파일이 없는 폴더다.", progress)
    progress["top"] = top
    if not origin_url(top):
        raise UploadStop("origin 이 없다. prepare-upload 를 먼저 실행하라.")
    other = other_owner_url(top, deadline)
    if other and not allow_other_owner:
        return _upload_result("other-owner", MSG_OTHER_OWNER, OTHER_OWNER_DETAIL.format(url=other), progress)
    state_path = _state_path(top, deadline)
    if resume:
        if not state_path.exists():
            raise UploadStop("이어서 할 업로드가 없다. upload --task --title 로 다시 실행하라.")
        state = json.loads(state_path.read_text(encoding="utf-8"))
        progress["stashed"] = True  # 첫 실행이 남긴 stash 가 있으면 끝날 때 되돌린다
        branch = progress["branch"] = state.get("branch")
        if not branch or not _ref_exists(top, f"refs/heads/{branch}", deadline):
            raise UploadStop("이어서 올릴 작업 브랜치를 알 수 없다. upload --task --title 로 처음부터 다시 실행하라.")
        if (git_dir(top, deadline) / "MERGE_HEAD").exists():
            files = _unmerged(top, deadline)
            if files:
                raise UploadStop(f"아직 풀리지 않은 충돌이 있다: {', '.join(files)}. 풀고 git add 한 뒤 다시 실행하라.")
            ensure_author(top, deadline)
            gitcmd.git(top, "commit", "-q", "-F", "-", deadline=deadline,
                       stdin=_merge_message(top, state).encode("utf-8"))
        if gitcmd.git_try(top, "merge-base", "--is-ancestor", branch, BRANCH, deadline=deadline)[0] != 0:
            # merge 를 취소했거나 merge 전에 멈췄다. 작업 브랜치를 다시 합친다.
            files = _merge(top, branch, state, deadline, progress)
            if files:
                return _upload_result("failed", MSG_CONFLICT, CONFLICT_DETAIL.format(files=", ".join(files)), progress)
    else:
        if task is None or not title:
            raise UploadStop("--task 와 --title 이 필요하다.")
        if (git_dir(top, deadline) / "MERGE_HEAD").exists():
            raise UploadStop("앞선 merge 가 진행 중이다. 풀고 git add 한 뒤 upload --continue 를 실행하라.")
        state = {"task": task, "title": title, "close": close}
        state_path.write_text(json.dumps(state), encoding="utf-8")
        recover(top, deadline)
        progress["note"] = restore_upload_stash(top, deadline) or ""
        gitcmd.git(top, "fetch", "-q", "origin", deadline=deadline)
        data = rules.load(RULES_PATH)
        excluded = stage(top, data, deadline)
        progress["excluded"] = excluded
        staged = has_staged_changes(top, deadline)
        branch = _work_branch_for_upload(top, deadline) if (staged or unpushed(top, deadline)) else None
        if staged:
            ensure_author(top, deadline)
            commit(top, title, excluded, deadline)
        if not unpushed(top, deadline):
            state_path.unlink()
            return _upload_result("nothing", with_notes(MSG_NO_UPLOAD, excluded), "", progress)
        _stash_leftovers(top, deadline, progress)
        state["branch"] = progress["branch"] = branch
        state_path.write_text(json.dumps(state), encoding="utf-8")
        if not _ref_exists(top, REMOTE_REF, deadline):
            # 빈 레포에 다른 브랜치를 먼저 올리면 GitHub 가 그 브랜치를 기본 브랜치로 정한다.
            gitcmd.git(top, "push", "-q", "-u", "origin", BRANCH, deadline=deadline)
            progress["pushed"] = True
        if branch is None:
            state_path.unlink()
            return _upload_result("uploaded", with_notes(MSG_UPLOADED, excluded), "", progress)
        gitcmd.git(top, "push", "-q", "-u", "origin", branch, deadline=deadline)
        files = _merge(top, branch, state, deadline, progress)
        if files:
            return _upload_result("failed", MSG_CONFLICT, CONFLICT_DETAIL.format(files=", ".join(files)), progress)
    if not _push_main(top, deadline):
        # 원격이 그사이 앞섰다. 5단계부터 한 번 다시 한다.
        files = _merge(top, branch, state, deadline, progress)
        if files:
            return _upload_result("failed", MSG_CONFLICT, CONFLICT_DETAIL.format(files=", ".join(files)), progress)
        if not _push_main(top, deadline):
            raise UploadStop("GitHub 공유 코드가 계속 앞서 main push 가 거부되었다. 잠시 뒤 다시 실행하라.")
    gitcmd.git(top, "fetch", "-q", "origin", deadline=deadline)
    if gitcmd.git_try(top, "merge-base", "--is-ancestor", branch, REMOTE_REF, deadline=deadline)[0] != 0:
        raise UploadStop(f"main push 뒤에도 GitHub 공유 코드에 {branch} 가 보이지 않는다. 작업 브랜치는 지우지 않았다. "
                         "upload --continue 로 다시 실행하라.")
    progress["pushed"] = True
    left = []
    if branch:
        if gitcmd.git_try(top, "push", "-q", "origin", "--delete", branch, deadline=deadline)[0] != 0:
            left.append(f"GitHub 의 {branch}")
        # -d 는 합쳐진 브랜치만 지운다. 합쳐지지 않은 커밋을 지우지 않기 위해서다.
        if gitcmd.git_try(top, "branch", "-q", "-d", branch, deadline=deadline)[0] != 0:
            left.append(f"이 PC 의 {branch}")
    state_path.unlink(missing_ok=True)
    detail = f"합친 작업 브랜치를 지우지 못했다: {', '.join(left)}. 다음 업로드 때 다시 지워도 된다." if left else ""
    return _upload_result("uploaded", with_notes(MSG_UPLOADED, progress["excluded"]), detail, progress)


BULLET = re.compile(r"^[-*]\s*(\[[ xX]?\]\s*)?")


def template_only(title, body):
    """본문에 제목과 양식(절 제목, 빈 항목, 안내 주석) 말고 적힌 내용이 없으면 참이다."""
    plain = title.split("] ", 1)[-1].strip()
    for line in HTML_COMMENT.sub("", body or "").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or text == plain:
            continue
        if BULLET.sub("", text).strip():
            return False
    return True


def _leaked(top, data, deadline):
    """GitHub 공유 코드에 올라간 파일 중 업로드 규칙에 해당하는 파일이다."""
    found = []
    for path in gitcmd.git_z(top, "ls-tree", "-r", "-z", "--name-only", REMOTE_REF, deadline=deadline):
        raw = gitcmd.git_bytes(top, "cat-file", "blob", f"{REMOTE_REF}:{path}", deadline=deadline)
        verdict = rules.judge(data, path, len(raw), lambda raw=raw: raw)
        if verdict is not None:
            found.append(_excluded(path, verdict[0], verdict[1]))
    return found


def review_upload(repo):
    """업로드 뒤 점검에 쓸 사실을 모은다. 판단과 처리는 saving-work 스킬의 Claude 가 한다."""
    deadline = gitcmd.Deadline(SAVE_SECONDS)
    payload = {"status": "failed", "uploaded": False, "leaked": [], "issues": [], "message": MSG_FAILED, "detail": ""}
    try:
        top = locate(Path(repo))
        if top is None or not is_feature_repo(top):
            payload.update(message=MSG_NOT_FEATURE, detail="표식 파일이 없는 폴더다.")
            return payload
        parsed = parse_remote(origin_url(top) or "")
        if parsed is None:
            payload["detail"] = "origin 주소에서 GitHub 레포 이름을 읽지 못했다."
            return payload
        gitcmd.git(top, "fetch", "-q", "origin", deadline=deadline)
        local = gitcmd.git(top, "rev-parse", BRANCH, deadline=deadline).strip()
        remote = gitcmd.git(top, "rev-parse", REMOTE_REF, deadline=deadline).strip()
        feature = read_marker(top).get("issue")
        listed = json.loads(gitcmd.gh("issue", "list", "-R", "/".join(parsed), "--state", "open", "--json",
                                      "number,title,body,assignees", "--limit", "100", deadline=deadline) or "[]")
        payload.update(
            status="ok", message="",
            uploaded=local == remote,
            leaked=_leaked(top, rules.load(RULES_PATH), deadline),
            # ours: 플러그인이 만든 이슈다. 제목이 "[<레포 이름>] " 으로 시작한다.
            issues=[{"number": item["number"], "title": item["title"], "feature": str(item["number"]) == feature,
                     "ours": item["title"].startswith(f"[{parsed[1]}] "),
                     "template_only": template_only(item["title"], item.get("body")),
                     "no_assignee": not item.get("assignees")} for item in listed],
        )
    except Exception as exc:  # noqa: BLE001 — 스킬은 어떤 경우에도 JSON 을 받아야 한다
        payload["detail"] = f"점검하지 못했다: {exc.__class__.__name__}: {exc}"
    return payload


def _print(payload):
    # ASCII 로만 내보낸다. cp949 로 설정된 PowerShell 이 출력을 담아도 한글이 깨지지 않는다.
    print(json.dumps(payload))
    return 1 if payload["status"] == "failed" else 0


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="기능 레포의 작업을 검사해 commit 하고, 승인받은 작업을 push 한다.")
    sub = parser.add_subparsers(dest="command", required=True)
    commit_cmd = sub.add_parser("commit", help="로컬에서만 작업 브랜치에 커밋한다")
    commit_cmd.add_argument("--repo", required=True)
    mode = commit_cmd.add_mutually_exclusive_group(required=True)
    mode.add_argument("--message")
    mode.add_argument("--catch-up", action="store_true")
    commit_cmd.add_argument("--branch")
    prepare_cmd = sub.add_parser("prepare-upload", help="원격 레포와 기능 이슈를 맞춘다")
    prepare_cmd.add_argument("--repo", required=True)
    prepare_cmd.add_argument("--allow-other-owner", action="store_true")
    prepare_cmd.add_argument("--body-file")
    upload_cmd = sub.add_parser("upload", help="승인받은 작업을 GitHub 공유 코드에 올린다")
    upload_cmd.add_argument("--repo", required=True)
    upload_cmd.add_argument("--continue", dest="resume", action="store_true")
    upload_cmd.add_argument("--task", type=int)
    upload_cmd.add_argument("--title")
    upload_cmd.add_argument("--close", type=int, action="append", default=[])
    upload_cmd.add_argument("--allow-other-owner", action="store_true")
    sub.add_parser("review-upload", help="업로드 뒤 점검에 쓸 사실을 모은다").add_argument("--repo", required=True)
    args = parser.parse_args(argv)
    if args.command == "review-upload":
        return _print(review_upload(args.repo))
    if args.command == "upload":
        return _print(upload(args.repo, task=args.task, title=args.title, close=args.close, resume=args.resume,
                             allow_other_owner=args.allow_other_owner))
    if args.command == "commit":
        return _print(commit_work(args.repo, args.message, branch=args.branch, catch_up=args.catch_up))
    if args.command == "prepare-upload":
        return _print(prepare_upload(args.repo, allow_other_owner=args.allow_other_owner, body_file=args.body_file))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
