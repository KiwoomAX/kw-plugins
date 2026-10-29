"""기본 branch 를 main 으로 맞춘다(spec 「기본 branch 를 main 으로 맞추기」). 개발자에게 묻지 않는다.

옛 기본 branch 에 main 에 없는 commit 이 있을 때만 needs-decision 으로 멈추고, Claude 가 개발자에게
반영(merge_old)할지 버릴지(discard_old) 묻는다.
"""
import gitcmd
import github_merge

MAIN = "main"
LOCAL_OLD = "master"
MAIN_REF = f"refs/remotes/origin/{MAIN}"
KEEP_PREFIXES = ("feat/", "fix/", "refactor/", "docs/", "local-history")
# GitHub 기본 branch 를 바꾸기 전의 이름이다. 바꾼 직후 멈춰도 다음 실행이 그 branch 를 다시 검사하게 남겨 둔다.
OLD_DEFAULT_KEY = "kw-github.old-default"


def _exists(top, ref, deadline):
    return gitcmd.git_try(top, "rev-parse", "--verify", "-q", ref, deadline=deadline)[0] == 0


def _sha(top, ref, deadline):
    return gitcmd.git(top, "rev-parse", ref, deadline=deadline).strip()


def _head(top, deadline):
    code, out, _ = gitcmd.git_try(top, "symbolic-ref", "--short", "-q", "HEAD", deadline=deadline)
    return out.strip() if code == 0 else None


def _is_old_name(name):
    return name != MAIN and not name.startswith(KEEP_PREFIXES)


def _recorded_old(top, deadline):
    code, out, _ = gitcmd.git_try(top, "config", "--get", OLD_DEFAULT_KEY, deadline=deadline)
    return out.strip() if code == 0 and out.strip() else None


def _forget_old(top, old, deadline):
    if _recorded_old(top, deadline) == old:
        gitcmd.git_try(top, "config", "--unset", OLD_DEFAULT_KEY, deadline=deadline)


def settled(top, deadline=None):
    """이미 main 으로 맞춘 레포면 참이다. 세션 시작이 GitHub 를 부르지 않고 넘어가는 기준이다."""
    code, out, _ = gitcmd.git_try(top, "symbolic-ref", "-q", "refs/remotes/origin/HEAD", deadline=deadline)
    if code != 0 or out.strip() != MAIN_REF or _recorded_old(top, deadline):
        return False
    return not any(_exists(top, ref, deadline) for ref in (f"refs/heads/{LOCAL_OLD}", f"refs/remotes/origin/{LOCAL_OLD}"))


def _result(status, old_branch=None, commits=(), reason="", detail=""):
    return {"status": status, "old_branch": old_branch, "commits": list(commits), "reason": reason, "detail": detail}


def local_rename(top, deadline=None):
    """main 이 없고 master 가 있으면 PC 의 이름만 바꾼다. 바꿨으면 참이다."""
    if _exists(top, f"refs/heads/{MAIN}", deadline):
        return False
    if _exists(top, f"refs/heads/{LOCAL_OLD}", deadline):
        gitcmd.git(top, "branch", "-m", LOCAL_OLD, MAIN, deadline=deadline)
        return True
    if _head(top, deadline) == LOCAL_OLD:
        # 첫 commit 전이라 master 가 아직 없다. HEAD 가 가리킬 이름만 바꾼다.
        gitcmd.git(top, "symbolic-ref", "HEAD", f"refs/heads/{MAIN}", deadline=deadline)
        return True
    return False


def _default_branch(full, deadline):
    """GitHub 레포의 기본 branch 이름이다. 레포가 없으면 None 이다."""
    code, out, err = gitcmd.gh_try("api", f"repos/{full}", "--jq", ".default_branch", deadline=deadline)
    if code != 0:
        if "HTTP 404" in err:
            return None
        raise gitcmd.GitError(f"gh api repos/{full} 실패: {err.strip()}")
    return out.strip() or None


def _remote_has(top, branch, deadline):
    out = gitcmd.git(top, "ls-remote", "--heads", "origin", branch, deadline=deadline)
    return bool(out.strip())


def _change_default(full, old, has_main, deadline):
    """GitHub 의 기본 branch 를 main 으로 바꾼다. 실패하면 그 결과 dict, 성공하면 None 이다."""
    if has_main:
        args = ("api", "-X", "PATCH", f"repos/{full}", "-f", f"default_branch={MAIN}")
    else:
        args = ("api", "-X", "POST", f"repos/{full}/branches/{old}/rename", "-f", f"new_name={MAIN}")
    code, out, err = gitcmd.gh_try(*args, deadline=deadline)
    if code == 0:
        return None
    if "HTTP 403" in err:
        return _result("failed", old, reason="no-permission",
                       detail=f"GitHub 의 기본 branch({old})를 main 으로 바꿀 권한이 없다. AX팀 문의를 안내하라.")
    raise gitcmd.GitError(f"gh {' '.join(args)} 실패: {(err or out).strip()}")


def _track_main(top, deadline):
    if _exists(top, f"refs/heads/{MAIN}", deadline) and _exists(top, MAIN_REF, deadline):
        gitcmd.git(top, "branch", "-q", "-u", f"origin/{MAIN}", MAIN, deadline=deadline)
    gitcmd.git_try(top, "remote", "set-head", "origin", MAIN, deadline=deadline)


def _main_ref(top, deadline):
    return MAIN_REF if _exists(top, MAIN_REF, deadline) else f"refs/heads/{MAIN}"


def _old_tips(top, old, deadline):
    return [ref for ref in (f"refs/heads/{old}", f"refs/remotes/origin/{old}") if _exists(top, ref, deadline)]


def _extra_commits(top, old, deadline):
    """옛 branch 에만 있는 commit 의 제목이다."""
    base = _main_ref(top, deadline)
    titles = []
    for ref in _old_tips(top, old, deadline):
        for title in gitcmd.git(top, "log", "--format=%s", f"{base}..{ref}", deadline=deadline).splitlines():
            if title not in titles:
                titles.append(title)
    return titles


def _delete_old(top, old, deadline):
    """옛 branch 를 GitHub 와 PC 에서 지운다. GitHub 는 PC 가 본 끝을 기대값으로 지정한다."""
    remote = f"refs/remotes/origin/{old}"
    if _exists(top, remote, deadline):
        sha = _sha(top, remote, deadline)
        gitcmd.git(top, "push", "-q", "origin", "--delete", f"--force-with-lease=refs/heads/{old}:{sha}", old,
                   deadline=deadline)
    if _exists(top, f"refs/heads/{old}", deadline):
        if _head(top, deadline) == old:
            gitcmd.git(top, "switch", "-q", MAIN, deadline=deadline)
        gitcmd.git(top, "branch", "-q", "-D", old, deadline=deadline)
    _forget_old(top, old, deadline)


def _candidates(top, remote_old, deadline):
    names = [name for name in (remote_old, _recorded_old(top, deadline), LOCAL_OLD) if name and _is_old_name(name)]
    return [name for name in dict.fromkeys(names) if _old_tips(top, name, deadline)]


def normalize(top, full=None, deadline=None):
    """1~3단계를 한다. full 이 None 이면 GitHub 를 부르지 않는다."""
    changed = local_rename(top, deadline)
    remote_old = None
    if full:
        default = _default_branch(full, deadline)
        if default and default != MAIN:
            gitcmd.git(top, "config", OLD_DEFAULT_KEY, default, deadline=deadline)
            failed = _change_default(full, default, _remote_has(top, MAIN, deadline), deadline)
            if failed:
                return failed
            changed = True
            gitcmd.git(top, "fetch", "-q", "--prune", "origin", deadline=deadline)
            if _exists(top, f"refs/heads/{default}", deadline) and not _exists(top, f"refs/heads/{MAIN}", deadline):
                gitcmd.git(top, "branch", "-m", default, MAIN, deadline=deadline)
            remote_old = default
        if default:
            _track_main(top, deadline)
    if not _exists(top, f"refs/heads/{MAIN}", deadline) and not _exists(top, MAIN_REF, deadline):
        return _result("normalized" if changed else "ok")
    candidates = _candidates(top, remote_old, deadline)
    recorded = _recorded_old(top, deadline)
    if recorded and recorded not in candidates:
        _forget_old(top, recorded, deadline)  # 옛 branch 가 이미 없다
    for old in candidates:
        extra = _extra_commits(top, old, deadline)
        if extra:
            return _result("needs-decision", old, extra,
                           detail=f"옛 기본 branch {old} 에 main 에 없는 commit 이 있다. 개발자에게 commits 를 보여 주고 "
                                  "main 에 반영할지(--merge-old) 버릴지(--discard-old) 물어라.")
        _delete_old(top, old, deadline)
        changed = True
    return _result("normalized" if changed else "ok")


def _merge_on_pc(top, old, deadline):
    """PC 에서 옛 branch 를 main 에 합친다. 충돌이면 거짓이다. main 을 꺼내지 않아도 되게 merge-tree 를 쓴다.

    merge 가 시작하지 못한 실패(작업 폴더에 바뀐 파일, 오래된 Git)는 충돌이 아니므로 GitError 로 알린다.
    충돌로 알리면 개발자가 충돌하지 않는 작업을 버리게 될 수 있기 때문이다.
    """
    if _head(top, deadline) == MAIN:
        code, out, err = gitcmd.git_try(top, "merge", "-q", "--no-edit", old, deadline=deadline)
        if code == 0:
            return True
        merge_head = gitcmd.git(top, "rev-parse", "--git-path", "MERGE_HEAD", deadline=deadline).strip()
        if not (top / merge_head).exists():
            raise gitcmd.GitError(f"git merge {old} 실패: {(err or out).strip()}")
        gitcmd.git_try(top, "merge", "--abort", deadline=deadline)
        return False
    code, out, err = gitcmd.git_try(top, "merge-tree", "--write-tree", MAIN, old, deadline=deadline)
    if code == 1:
        return False
    if code != 0:
        raise gitcmd.GitError(f"git merge-tree 실패({code}): {(err or out).strip()}")
    tree, base = out.split()[0], _sha(top, f"refs/heads/{MAIN}", deadline)
    commit = gitcmd.git(top, "commit-tree", tree, "-p", base, "-p", _sha(top, f"refs/heads/{old}", deadline),
                        "-m", f"예전 기본 branch {old} 를 main 에 반영", deadline=deadline).strip()
    gitcmd.git(top, "update-ref", f"refs/heads/{MAIN}", commit, base, deadline=deadline)
    return True


def merge_old(top, full, old, deadline=None):
    """개발자가 반영하기로 한 옛 branch 를 main 에 merge 한 뒤 지운다."""
    if not _is_old_name(old):
        return _result("failed", old, detail=f"{old} 는 옛 기본 branch 가 아니라 반영하지 않았다.")
    remote = f"refs/remotes/origin/{old}"
    if full and _exists(top, remote, deadline):
        if _exists(top, f"refs/heads/{old}", deadline) and _sha(top, f"refs/heads/{old}", deadline) != _sha(
                top, remote, deadline):
            gitcmd.git(top, "push", "-q", "origin", old, deadline=deadline)
            gitcmd.git(top, "fetch", "-q", "origin", deadline=deadline)
        code, message = github_merge.merge(full, _sha(top, remote, deadline),
                                           f"예전 기본 branch {old} 를 main 에 반영", deadline)
        if code == 409:
            return _result("conflict", old, detail=f"{old} 를 main 에 합치면 충돌한다. 아무것도 지우지 않았다. {message}")
        if code not in (201, 204):
            raise gitcmd.GitError(f"GitHub merge 응답 {code}: {message}")
        gitcmd.git(top, "fetch", "-q", "origin", deadline=deadline)
        # PC 의 main 에 GitHub 에 없는 commit 이 있으면 옮기지 않고 옛 branch 정리로 넘어간다.
        # 옮기려다 멈추면 GitHub merge 만 끝난 채 다시 실행해도 같은 곳에서 멈추기 때문이다.
        if gitcmd.git_try(top, "merge-base", "--is-ancestor", MAIN, MAIN_REF, deadline=deadline)[0] == 0:
            if _head(top, deadline) == MAIN:
                gitcmd.git(top, "merge", "-q", "--ff-only", MAIN_REF, deadline=deadline)
            else:
                gitcmd.git(top, "update-ref", f"refs/heads/{MAIN}", _sha(top, MAIN_REF, deadline), deadline=deadline)
    elif not _merge_on_pc(top, old, deadline):
        return _result("conflict", old, detail=f"{old} 를 main 에 합치면 충돌한다. 아무것도 지우지 않았다.")
    _delete_old(top, old, deadline)
    return _result("normalized", old)


def discard_old(top, old, deadline=None):
    """개발자가 버리기로 한 옛 branch 를 GitHub 와 PC 에서 지운다."""
    if not _is_old_name(old):
        return _result("failed", old, detail=f"{old} 는 옛 기본 branch 가 아니라 지우지 않았다.")
    _delete_old(top, old, deadline)
    return _result("normalized", old)
