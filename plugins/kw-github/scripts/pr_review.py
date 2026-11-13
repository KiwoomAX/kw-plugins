"""열린 검토 요청(PR)에 commit 을 추가하는 명령이다. 공유 레포와 기능 레포에서 쓴다.

PR 작업은 PC 에만 있는 branch pr-review/<번호> 에서 한다. 이 이름은 일반 저장 흐름의 후보가 아니다.
save_work 를 맨 위에서 불러온다. save_work 는 이 파일을 함수 안에서만 불러온다.
"""
import json
from pathlib import Path

import gitcmd
import rules
import save_work
import shared_repo

PREFIX = "pr-review/"
ALLOWED_COMMANDS = ("commit", "pr-start", "pr-push", "pr-leave", "sync-main", "check-imports", "pr-merge",
                    "revert-paths")
MSG_PR_CHECK = "검토 요청을 확인하지 못했습니다. AX팀에 확인을 요청해 주세요."
MSG_PR_CLOSED = "이 검토 요청은 이미 닫혔습니다. AX팀에 확인을 요청해 주세요."
MSG_PR_MOVED = "다른 사람이 같은 검토 요청을 먼저 수정했습니다. AX팀에 확인을 요청해 주세요."
MSG_PR_PUSHED = "검토 요청에 수정을 올렸습니다."
MSG_PR_NOTHING = "검토 요청에 올릴 새 수정이 없습니다."
MSG_PR_LEFT = "검토 요청 수정을 마치고 이전 작업으로 돌아왔습니다."
MSG_PR_NOT_ALLOWED = ("다른 분이 연 검토 요청은 작성자나 AX팀이 반영합니다. 수정한 내용은 검토 요청에 올렸으니 작성자에게 "
                      "반영을 요청해 주세요.")
MSG_PR_MERGED = "검토 요청을 반영했습니다."
MSG_PR_SECRET = "검토 요청에 비밀값이나 데이터 파일이 있어 반영하지 않았습니다. 그 파일을 고친 뒤 다시 요청해 주세요."
MSG_PR_HEAD_MOVED = "검토 요청에 아직 올리지 않은 수정이 있어 반영하지 않았습니다."
AX_MEMBERSHIP = "orgs/KiwoomAX/teams/ax/memberships/{login}"
FETCH = ("fetch", "-q", "--prune", "origin")


def review_number(branch):
    """리뷰 branch 이름이면 PR 번호를, 아니면 None 을 돌려준다."""
    rest = branch[len(PREFIX):] if branch and branch.startswith(PREFIX) else ""
    return int(rest) if rest.isdigit() else None


def _failed(detail, message=save_work.MSG_FAILED, **extra):
    return save_work._shared_failed(message, detail, **extra)


def _top(repo):
    """기능 레포나 공유 레포의 최상위 폴더다. 그 밖의 폴더면 None 이다."""
    top = save_work.locate(Path(repo))
    if top is None or not (save_work.is_feature_repo(top) or shared_repo.repo_kind(top) == "shared"):
        return None
    return top


def unpushed_count(top, branch, deadline):
    out = gitcmd.git(top, "rev-list", "--count", branch, "--not", "--remotes=origin", deadline=deadline)
    return int(out.strip())


def refuse_on_review(repo, command):
    """리뷰 branch 에서 쓸 수 없는 명령이면 failed 결과를 돌려준다. 저장소를 바꾸지 않는다."""
    if command in ALLOWED_COMMANDS:
        return None
    try:
        top = _top(repo)
        number = review_number(save_work.current_branch(top)) if top is not None else None
    except save_work.GH_ERRORS:
        return None
    if number is None:
        return None
    return _failed(f"지금 branch 는 검토 요청 #{number} 을 고치는 리뷰 branch 다. pr-push 로 올리거나 pr-leave 로 나온 뒤 "
                   "다시 실행하라.")


def _precondition(top, deadline, commit=False):
    """PR 명령을 시작할 수 없으면 그 결과를 돌려준다. commit 이 참이면 지원 구조와 MERGE_HEAD 만 본다."""
    if shared_repo.repo_kind(top) == "shared" and not shared_repo.supported(top):
        return {"status": "unsupported", "reason": "", "message": save_work.MSG_UNSUPPORTED, "detail": ""}
    names = ("MERGE_HEAD",) if commit else ("MERGE_HEAD", save_work.UPLOAD_STATE, save_work.SYNC_STATE)
    gdir = save_work.git_dir(top, deadline)
    busy = [name for name in names if (gdir / name).exists()]
    if busy:
        return _failed(f"앞선 작업이 끝나지 않았다({', '.join(busy)}). 그 작업을 끝낸 뒤 다시 실행하라.")
    return None


def _read_pr(top, number, deadline):
    out = gitcmd.gh("pr", "view", str(number), "-R", save_work._full_name(top), "--json",
                    "state,headRefName,isCrossRepository,url", deadline=deadline)
    return json.loads(out)


def _used_by_copy(top, branch, deadline):
    """다른 사본 작업 폴더가 그 branch 를 쓰는 중인가."""
    out = gitcmd.git(top, "worktree", "list", "--porcelain", deadline=deadline)
    own = str(Path(top).resolve()).casefold()
    folder = None
    for line in out.splitlines():
        if line.startswith("worktree "):
            folder = str(Path(line[len("worktree "):]).resolve()).casefold()
        elif line == f"branch refs/heads/{branch}" and folder != own:
            return True
    return False


def _switch_to_review(top, review, remote_ref, current, deadline):
    """리뷰 branch 로 옮긴다. 옮기지 못하면 멈출 결과를, 옮겼으면 None 을 돌려준다."""
    keep = save_work._ref_exists(top, f"refs/heads/{review}", deadline) and unpushed_count(top, review, deadline) > 0
    if keep and not save_work._is_ancestor(top, remote_ref, review, deadline):
        return {"status": "remote-moved", "reason": "", "message": MSG_PR_MOVED,
                "unpushed": unpushed_count(top, review, deadline),
                "detail": f"{review} 에 올리지 않은 commit 이 있고 GitHub 의 검토 요청도 바뀌었다."}
    if keep and current == review:
        return None
    args = (review,) if keep else ("-C", review, "--no-track", remote_ref)
    code, out, err = gitcmd.git_try(top, "switch", "-q", "--no-overwrite-ignore", *args, deadline=deadline)
    if code != 0:
        return _failed(f"{review} 로 옮기지 못했다. {(err or out).strip()}")
    return None


def _pr_start(top, number, deadline):
    stop = _precondition(top, deadline)
    if stop is not None:
        return stop
    try:
        pr = _read_pr(top, number, deadline)
    except (*save_work.GH_ERRORS, ValueError) as exc:
        return _failed(str(exc), MSG_PR_CHECK)
    if pr.get("state") != "OPEN":
        return _failed(f"검토 요청 #{number} 의 상태는 {pr.get('state')} 다.", MSG_PR_CLOSED)
    if pr.get("isCrossRepository"):
        return _failed(f"검토 요청 #{number} 은 다른 레포의 branch 에서 왔다. 이 레포에서 commit 을 추가할 수 없다.")
    review, current = f"{PREFIX}{number}", save_work.current_branch(top, deadline)
    # commit 이 빼는 규칙 해당 파일은 commit 해도 남으므로 보지 않는다.
    if current != review and save_work.plain_changes(top, rules.load(save_work.RULES_PATH), deadline):
        return _failed("commit 하지 않은 변경이 있다. 먼저 commit 한 뒤 다시 실행하라.")
    gitcmd.git(top, *FETCH, deadline=deadline)
    remote_ref = f"refs/remotes/origin/{pr['headRefName']}"
    if not save_work._ref_exists(top, remote_ref, deadline):
        return _failed(f"GitHub 에 {pr['headRefName']} 이 없다.", MSG_PR_CHECK)
    if _used_by_copy(top, review, deadline):
        return _failed(f"다른 사본 작업 폴더가 {review} 를 쓰고 있다. 그 폴더에서 이어 가라.")
    stop = _switch_to_review(top, review, remote_ref, current, deadline)
    if stop is not None:
        return stop
    return {"status": "started", "reason": "", "message": "", "detail": "", "branch": review, "url": pr.get("url", "")}


def is_review(top, deadline=None):
    """기능 레포나 공유 레포이고 지금 branch 가 리뷰 branch 인가."""
    if top is None or not (save_work.is_feature_repo(top) or shared_repo.repo_kind(top) == "shared"):
        return False
    return review_number(save_work.current_branch(top, deadline)) is not None


def stage_review(top, data, deadline):
    """인덱스를 HEAD 로 되돌린 뒤 검사를 통과한 변경을 stage 하고 excluded 목록을 돌려준다.

    PR 은 AX팀이 보는 작업이라 기능 폴더 경계를 보지 않는다. .gitignore 와 이미 추적 중인 파일은 건드리지 않는다.
    """
    save_work.reset_index(top, deadline)
    tracked = set(gitcmd.git_z(top, "ls-files", "-z", deadline=deadline))
    trees = save_work._intake_trees(top, deadline)
    staged, excluded, hide = [], [], []
    for path in save_work.changed_paths(top, deadline):
        if path.startswith(save_work.DESIGN_DOCS):
            continue
        verdict = save_work.pr_file_verdict(top, data, path, deadline, trees)
        if verdict is None:
            staged.append(path)
            continue
        found, rule = verdict
        reason = f"{found}-tracked" if found == "secret-filename" and path in tracked else found
        excluded.append(save_work._excluded(path, reason, rule))
        # secret-content 는 고친 뒤 다시 올라가야 하므로 가리지 않는다.
        if found != "secret-content" and path not in tracked:
            hide.append(path)
    save_work.add_to_exclude(top, [save_work.ignore_line(path) for path in hide], deadline)
    if staged:
        save_work._pathspec(top, ("add", "-A"), staged, deadline)
    return excluded


def commit_review(top, message, wanted, feature, deadline, progress):
    """리뷰 branch 에 commit 한다. 결과에 pr_number 를 넣는다. 예외는 commit_work 가 결과로 바꾼다."""
    branch = progress["branch"] = save_work.current_branch(top, deadline)

    def result(*args, **kwargs):
        return {**save_work.commit_result(*args, branch=branch, **kwargs), "pr_number": review_number(branch)}

    stop = _precondition(top, deadline, commit=True)
    if stop is not None:
        return result(stop["status"], stop["message"], stop["detail"])
    if wanted or feature:
        return result("failed", save_work.MSG_FAILED, f"{branch} 는 검토 요청을 고치는 리뷰 branch 다. --feature 와 --branch 없이 "
                                                      "commit 하거나, 무관한 작업이면 pr-leave 로 나온 뒤 진행하라.")
    save_work.recover(top, deadline)
    # 끊긴 upload 가 남긴 stash 는 다른 작업의 수정이라 PR commit 에 넣지 않는다. 개발자가 내용을 보고 정리한다.
    excluded = progress["excluded"] = stage_review(top, rules.load(save_work.RULES_PATH), deadline)
    if not save_work.has_staged_changes(top, deadline):
        return result("nothing", save_work.with_notes(save_work.MSG_NOTHING, excluded), "", excluded)
    save_work.ensure_author(top, deadline)
    save_work.commit(top, message, excluded, deadline)
    progress["committed"] = True
    return result("committed", save_work.with_notes(save_work.MSG_COMMITTED, excluded), "", excluded, committed=True)


def pr_start(repo, number):
    """열린 PR 의 branch 를 pr-review/<번호> 로 받아 옮긴다."""
    deadline = gitcmd.Deadline(save_work.SAVE_SECONDS)
    try:
        top = _top(repo)
        if top is None:
            return _failed("기능 레포나 공유 대시보드 레포가 아니다.")
        return _pr_start(top, number, deadline)
    except save_work.GH_ERRORS as exc:
        return _failed(save_work.COMMAND_DETAIL.format(exc=exc))


def _return_target(top, deadline):
    """돌아갈 곳의 git switch 인자다."""
    if shared_repo.repo_kind(top) == "shared":
        return ("--detach", save_work.REMOTE_REF)
    waiting = [name for name in save_work.work_branches(top, deadline)
               if save_work._count(top, f"{save_work.REMOTE_REF}..{name}", deadline)]
    return (waiting[0],) if len(waiting) == 1 else (save_work.BRANCH,)


LEFT_STASH = "끊긴 올리기가 임시 보관한 수정이 남아 있다(stash: {ref}). saving-work 의 「남은 임시 보관」 절을 따르라."


def _go_back(top, deadline):
    """리뷰 branch 를 떠난다. 남은 규칙 해당 변경은 치웠다가 되돌린다. {"moved", "note"} 를 돌려준다."""
    target = _return_target(top, deadline)
    progress = {}
    save_work._stash_leftovers(top, deadline, progress)
    # 이 PC 에서만 가린 파일은 stash 에 들어가지 않으므로 덮어쓰지 않게 한다.
    code, out, err = gitcmd.git_try(top, "switch", "-q", "--no-overwrite-ignore", *target, deadline=deadline)
    # 이번에 치운 변경만 되돌린다. 끊긴 upload 가 남긴 stash 는 개발자가 내용을 보고 고른다.
    restored = (save_work.restore_upload_stash(top, deadline) or "") if progress.get("stashed") else ""
    if code != 0:
        return {"moved": False, "note": f"리뷰 branch 에서 옮기지 못했다. {(err or out).strip()} {restored}".strip()}
    left = save_work.upload_stash_ref(top, deadline)
    return {"moved": True, "note": restored or (LEFT_STASH.format(ref=left) if left else "")}


def _delete_review(top, branch, deadline):
    gitcmd.git(top, "branch", "-q", "-D", branch, deadline=deadline)


def _on_review(repo, deadline):
    """(최상위 폴더, 리뷰 branch, 멈출 결과) 다. 멈출 결과가 있으면 앞의 두 값은 쓰지 않는다."""
    top = _top(repo)
    if top is None:
        return None, None, _failed("기능 레포나 공유 대시보드 레포가 아니다.")
    stop = _precondition(top, deadline)
    if stop is not None:
        return top, None, stop
    branch = save_work.current_branch(top, deadline)
    if review_number(branch) is None:
        return top, None, _failed("지금 branch 가 리뷰 branch 가 아니다. pr-start 로 먼저 옮겨라.")
    return top, branch, None


def _plain_stop(top, deadline):
    left = save_work.plain_changes(top, rules.load(save_work.RULES_PATH), deadline)
    return _failed(f"commit 하지 않은 변경이 있다: {', '.join(left)}. 먼저 commit 하라.") if left else None


def _push(top, head, deadline):
    """force 없이 올린다. 올렸으면 None, 아니면 멈출 결과다."""
    code, out, err = gitcmd.git_try(top, "push", "-q", "origin", f"HEAD:{head}", deadline=deadline)
    if code == 0:
        return None
    text = (err or out).strip()
    if "non-fast-forward" in text or "(fetch first)" in text:
        return {"status": "remote-moved", "reason": "", "message": MSG_PR_MOVED, "detail": text}
    return _failed(f"push 하지 못했다. {text}")


def _finish_push(top, branch, deadline):
    """push 뒤 정리다. 이미 올라갔으므로 실패해도 결과를 바꾸지 않고 문장만 돌려준다."""
    try:
        back = _go_back(top, deadline)
        if back["moved"]:
            _delete_review(top, branch, deadline)
        return back["note"]
    except save_work.GH_ERRORS as exc:
        return f"리뷰 branch 를 정리하지 못했다. pr-leave 로 나와라. {exc}"


def _pr_push(repo, allow_other_owner, deadline):
    top, branch, stop = _on_review(repo, deadline)
    stop = stop or _plain_stop(top, deadline)
    if stop is not None:
        return stop
    url = None if allow_other_owner else save_work.other_owner_url(top, deadline)
    if url:
        return {"status": "other-owner", "reason": "", "message": save_work.MSG_OTHER_OWNER,
                "detail": save_work.OTHER_OWNER_DETAIL.format(url=url)}
    gitcmd.git(top, *FETCH, deadline=deadline)
    number = review_number(branch)
    try:
        pr = _read_pr(top, number, deadline)
    except (*save_work.GH_ERRORS, ValueError) as exc:
        return _failed(str(exc), MSG_PR_CHECK)
    if pr.get("state") != "OPEN":
        return _failed(f"검토 요청 #{number} 의 상태는 {pr.get('state')} 다.", MSG_PR_CLOSED)
    head = pr["headRefName"]
    remote_ref = f"refs/remotes/origin/{head}"
    if not save_work._ref_exists(top, remote_ref, deadline):
        return _failed(f"GitHub 에 {head} 이 없다.", MSG_PR_CHECK)
    hits = save_work.pr_content_hits(top, remote_ref, "HEAD", deadline)
    if hits:
        return _failed(f"올릴 commit 에 비밀값·데이터 파일이 있어 push 하지 않았다: {', '.join(hits)}. 그 파일을 고치는 commit 을 "
                       "만든 뒤 다시 실행하라.")
    status, message = "nothing", MSG_PR_NOTHING
    if save_work._count(top, f"{remote_ref}..HEAD", deadline):
        stop = _push(top, head, deadline)
        if stop is not None:
            return stop
        status, message = "pushed", MSG_PR_PUSHED
    note = _finish_push(top, branch, deadline)
    return {"status": status, "reason": "", "message": message, "detail": note, "url": pr.get("url", "")}


def _left(detail="", unpushed=0):
    return {"status": "left", "reason": "", "message": MSG_PR_LEFT, "detail": detail, "unpushed": unpushed}


def _discard(top, number, deadline):
    branch = f"{PREFIX}{number}"
    note = ""
    if save_work.current_branch(top, deadline) == branch:
        back = _go_back(top, deadline)
        if not back["moved"]:
            return _failed(back["note"])
        note = back["note"]
    if save_work._ref_exists(top, f"refs/heads/{branch}", deadline):
        _delete_review(top, branch, deadline)
    return _left(note)


def _pr_leave(repo, discard, number, deadline):
    if discard:
        top = _top(repo)
        if top is None:
            return _failed("기능 레포나 공유 대시보드 레포가 아니다.")
        if number is None:
            return _failed("--discard 에는 --number 가 필요하다.")
        return _precondition(top, deadline) or _discard(top, number, deadline)
    top, branch, stop = _on_review(repo, deadline)
    stop = stop or _plain_stop(top, deadline)
    if stop is not None:
        return stop
    back = _go_back(top, deadline)
    if not back["moved"]:
        return _failed(back["note"])
    left = unpushed_count(top, branch, deadline)
    if not left:
        _delete_review(top, branch, deadline)
    return _left(back["note"], left)


def _guarded(run):
    """저장소 명령의 예외를 결과로 바꾼다."""
    try:
        return run()
    except rules.RulesError as exc:
        return _failed(rules.failure_detail(exc), save_work.MSG_RULES)
    except save_work.GH_ERRORS as exc:
        return _failed(save_work.COMMAND_DETAIL.format(exc=exc))


def pr_push(repo, allow_other_owner=False):
    """리뷰 branch 의 commit 을 PR 에 올리고 돌아간다. 개발자가 동의한 뒤에만 실행한다."""
    deadline = gitcmd.Deadline(save_work.SAVE_SECONDS)
    return _guarded(lambda: _pr_push(repo, allow_other_owner, deadline))


def _is_ax_member(login, deadline=None):
    """login 이 KiwoomAX 의 ax 팀 활성 구성원인가. 조회하지 못하면 아니라고 본다."""
    try:
        code, out, _ = gitcmd.gh_try("api", AX_MEMBERSHIP.format(login=login), deadline=deadline)
        return code == 0 and json.loads(out).get("state") == "active"
    except (*save_work.GH_ERRORS, ValueError, AttributeError):
        return False


def _merge_body(top, task, close):
    """merge commit 본문이다. save_work._merge_message 에서 제목 줄만 뺀 형식이다. 제목은 commit_title 로 보낸다."""
    numbers = ([task] if task is not None else []) + list(close)
    lines = [f"closes #{number}" for number in numbers]
    issue = save_work.read_marker(top).get("issue")
    if issue and int(issue) not in close:
        lines.append(f"#{issue}")
    return "\n".join(lines)


def _head_moved(top, number, head_ref, sha, deadline):
    """PC 에 PR head 에 없는 commit 이 있는가. 있으면 pr-push 를 먼저 해야 한다."""
    review = f"{PREFIX}{number}"
    if save_work.current_branch(top, deadline) == review and unpushed_count(top, review, deadline):
        return True
    local = f"refs/heads/{head_ref}"
    return save_work._ref_exists(top, local, deadline) and not save_work._is_ancestor(top, local, sha, deadline)


def _stop(status, message, detail="", **extra):
    return {"status": status, "reason": "", "message": message, "detail": detail, **extra}


def _merge_cleanup(top, number, head_ref, sha, shared, deadline):
    """merge 뒤 정리다. 이미 반영했으므로 실패해도 결과를 바꾸지 않고 문장만 돌려준다."""
    notes = []
    try:
        if not save_work.github_merge.delete_remote(top, head_ref, sha, deadline):
            notes.append(f"GitHub 의 {head_ref} 를 지우지 못했다.")
        gitcmd.git(top, *FETCH, deadline=deadline)
        review = f"{PREFIX}{number}"
        if save_work.current_branch(top, deadline) == review:
            back = _go_back(top, deadline)
            notes.append(back["note"])
            if back["moved"]:
                _delete_review(top, review, deadline)
        local = f"refs/heads/{head_ref}"
        if save_work._ref_exists(top, local, deadline) and save_work._contains(top, local, deadline):
            if save_work.current_branch(top, deadline) == head_ref:
                if shared:
                    gitcmd.git(top, "switch", "-q", "--detach", save_work.REMOTE_REF, deadline=deadline)
                else:
                    notes.append(save_work._move_head(top, deadline))
            gitcmd.git(top, "branch", "-q", "-D", head_ref, deadline=deadline)
    except save_work.GH_ERRORS as exc:
        notes.append(f"반영한 뒤 branch 를 정리하지 못했다. {exc}")
    return " ".join(note for note in notes if note)


def _pr_merge(repo, number, task, close, deadline):
    top = _top(repo)
    if top is None:
        return _failed("기능 레포나 공유 대시보드 레포가 아니다.")
    stop = _precondition(top, deadline)
    if stop is not None:
        return stop
    full = save_work._full_name(top)
    gitcmd.git(top, *FETCH, deadline=deadline)
    try:
        pr = json.loads(gitcmd.gh("pr", "view", str(number), "-R", full, "--json",
                                  "state,headRefName,headRefOid,author,title,url", deadline=deadline))
        me = gitcmd.gh_login(deadline)
    except (*save_work.GH_ERRORS, ValueError) as exc:
        return _failed(str(exc), MSG_PR_CHECK)
    url = pr.get("url", "")
    if pr.get("state") != "OPEN":
        return _stop("not-open", MSG_PR_CLOSED, f"검토 요청 #{number} 의 상태는 {pr.get('state')} 다.", url=url)
    author = (pr.get("author") or {}).get("login", "")
    if author != me and not _is_ax_member(me, deadline):
        return _stop("not-allowed", MSG_PR_NOT_ALLOWED, f"작성자는 {author} 이고 지금 계정 {me} 는 ax 팀 활성 구성원이 아니다.",
                     url=url)
    head_ref, sha = pr["headRefName"], pr["headRefOid"]
    gitcmd.git(top, "fetch", "-q", "origin", f"pull/{number}/head", deadline=deadline)
    if _head_moved(top, number, head_ref, sha, deadline):
        return _stop("head-moved", MSG_PR_HEAD_MOVED, "PC 에 검토 요청에 올리지 않은 commit 이 있다. pr-push 로 먼저 올려라.",
                     url=url)
    if not save_work._is_ancestor(top, save_work.REMOTE_REF, sha, deadline):
        return _stop("main-moved", save_work.MSG_MAIN_MOVED, "검토 요청이 최신 GitHub main 을 포함하지 않는다. pr-start 뒤 "
                     "sync-main 으로 반영하고 pr-push 한 뒤 다시 실행하라.", url=url)
    # 다른 사람이 GitHub 에 바로 올린 commit 도 반영 전에 검사한다(사용자 결정 2026-11-13).
    hits = save_work.pr_content_hits(top, save_work.REMOTE_REF, sha, deadline)
    if hits:
        return _stop("secret-found", MSG_PR_SECRET, f"비밀값·데이터 파일: {', '.join(hits)}", url=url)
    shared = shared_repo.repo_kind(top) == "shared"
    if shared:
        deploy = [path for path in shared_repo.changed_paths(top, save_work.REMOTE_REF, sha, deadline)
                  if shared_repo.is_deploy(path)]
        if deploy:
            return _stop("outside", save_work.MSG_OUTSIDE.format(files=", ".join(deploy)),
                         "배포 설정 파일은 개발자가 배포 절차로 직접 반영한다.", outside=deploy, deploy=deploy, url=url)
        found = save_work.check_imports(top, sha, deadline)
        if found["status"] == "broken":
            return _stop("broken-import", save_work.MSG_BROKEN_IMPORT, found["detail"],
                         broken_imports=found["broken_imports"], url=url)
        if found["status"] != "ok":
            return _failed(found["detail"])
    code, out, err = gitcmd.gh_try("api", "-X", "PUT", f"repos/{full}/pulls/{number}/merge", "-f", f"sha={sha}",
                                   "-f", "merge_method=merge", "-f", f"commit_title={pr.get('title', '')} (#{number})",
                                   "-f", f"commit_message={_merge_body(top, task, close)}", deadline=deadline)
    if code != 0:
        return _failed(f"GitHub 가 반영을 거부했다: {(err or out).strip()}", url=url)
    note = _merge_cleanup(top, number, head_ref, sha, shared, deadline)
    return _stop("merged", MSG_PR_MERGED, note, url=url)


def pr_merge(repo, number, task=None, close=(), deadline=None):
    """열린 PR 을 확인한 뒤 GitHub 에서 merge 한다. 작성자이거나 ax 팀 구성원일 때만 merge 한다."""
    deadline = deadline or gitcmd.Deadline(save_work.SAVE_SECONDS)
    return _guarded(lambda: _pr_merge(repo, number, task, tuple(close), deadline))


def pr_leave(repo, discard=False, number=None):
    """리뷰 branch 를 떠난다. gh 를 쓰지 않는다. discard 는 개발자가 동의한 뒤에만 쓴다."""
    deadline = gitcmd.Deadline(save_work.SAVE_SECONDS)
    return _guarded(lambda: _pr_leave(repo, discard, number, deadline))
