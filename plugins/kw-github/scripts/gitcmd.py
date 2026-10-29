"""git 과 gh 를 부르는 곳이다. 인코딩과 제한 시간과 프로세스 종료를 여기서만 다룬다."""
import os
import shutil
import subprocess
import time

GH_SECONDS = 20
KILL_WAIT_SECONDS = 5
# 콘솔이 없는 훅 프로세스가 git 을 띄울 때 검은 창이 번쩍이지 않게 한다.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class GitError(Exception):
    """명령이 0 이 아닌 종료 코드로 끝났을 때 올린다. 메시지에 명령과 표준 오류를 담는다."""


class CommandTimeout(Exception):
    """제한 시간 안에 명령이 끝나지 않았을 때 올린다."""


class ToolMissing(Exception):
    """git 이나 gh 실행 파일을 찾지 못했을 때 올린다."""


class Deadline:
    """전체 실행에 거는 제한 시간이다. 세션 시작 저장은 45초, 일반 저장은 120초로 준다."""

    def __init__(self, seconds):
        self.seconds = seconds
        self.started = time.monotonic()

    def remaining(self):
        return max(0.0, self.seconds - (time.monotonic() - self.started))

    def expired(self):
        return self.remaining() <= 0


def _env():
    env = dict(os.environ)
    # 훅 안에서는 로그인 질문에 답할 사람이 없어 시간만 흐른다. 묻지 말고 실패하게 한다.
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "never"
    # 경로에 든 * ? [ 를 패턴으로 읽지 않고 글자 그대로 다룬다.
    env["GIT_LITERAL_PATHSPECS"] = "1"
    return env


def _show(args):
    return " ".join(str(arg) for arg in args)


def _limit(args, deadline, timeout):
    if deadline is None:
        return timeout
    if deadline.expired():
        raise CommandTimeout(f"{_show(args)} 를 시작하기 전에 제한 시간이 지났다")
    left = deadline.remaining()
    return left if timeout is None else min(left, timeout)


def _kill_tree(proc):
    # Windows 의 git 은 git-remote-https 같은 자식을 띄운다. 부모만 죽이면 자식이 출력 파이프를
    # 쥔 채 남아 결과를 읽는 쪽이 자식이 끝날 때까지 멈춘다. 그래서 프로세스 트리째 끝낸다.
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                       capture_output=True, creationflags=_NO_WINDOW)
    else:
        proc.kill()


def run(args, cwd=None, deadline=None, timeout=None, stdin=None):
    """명령을 실행해 (종료 코드, 표준 출력 bytes, 표준 오류 문자열) 을 돌려준다."""
    limit = _limit(args, deadline, timeout)
    try:
        proc = subprocess.Popen(
            args, cwd=cwd, env=_env(),
            stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=_NO_WINDOW,
        )
    except FileNotFoundError as exc:
        if shutil.which(args[0]) is None:
            raise ToolMissing(f"{args[0]} 실행 파일을 찾지 못했다") from exc
        raise
    try:
        out, err = proc.communicate(stdin, timeout=limit)
    except subprocess.TimeoutExpired as exc:
        _kill_tree(proc)
        try:
            proc.communicate(timeout=KILL_WAIT_SECONDS)
        except subprocess.TimeoutExpired:
            pass
        raise CommandTimeout(f"{_show(args)} 가 {limit:.0f}초 안에 끝나지 않았다") from exc
    return proc.returncode, out, err.decode("utf-8", "replace")


def _git_args(args):
    # core.quotepath 를 꺼야 한글 경로가 8진수 이스케이프로 나오지 않는다.
    return ["git", "-c", "core.quotepath=off", *args]


def _fail(args, code, out, err):
    return GitError(f"{_show(args)} 실패(종료 코드 {code}): {err.strip() or out.strip()}")


def git_try(repo, *args, deadline=None, timeout=None, stdin=None):
    code, out, err = run(_git_args(args), cwd=str(repo), deadline=deadline, timeout=timeout, stdin=stdin)
    return code, out.decode("utf-8", "replace"), err


def git(repo, *args, deadline=None, timeout=None, stdin=None, check=True):
    code, out, err = git_try(repo, *args, deadline=deadline, timeout=timeout, stdin=stdin)
    if check and code != 0:
        raise _fail(_git_args(args), code, out, err)
    return out


def git_bytes(repo, *args, deadline=None, timeout=None):
    code, out, err = run(_git_args(args), cwd=str(repo), deadline=deadline, timeout=timeout)
    if code != 0:
        raise _fail(_git_args(args), code, "", err)
    return out


def git_z(repo, *args, deadline=None):
    return [entry for entry in git(repo, *args, deadline=deadline).split("\0") if entry]


def gh_try(*args, deadline=None, timeout=GH_SECONDS):
    code, out, err = run(["gh", *args], deadline=deadline, timeout=timeout)
    return code, out.decode("utf-8", "replace"), err


def gh(*args, deadline=None, timeout=GH_SECONDS):
    code, out, err = gh_try(*args, deadline=deadline, timeout=timeout)
    if code != 0:
        raise _fail(["gh", *args], code, out, err)
    return out
