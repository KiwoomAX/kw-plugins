"""작업 branch 를 GitHub 에서 main 에 merge 한다(branch merge API). 원격 작업 branch 도 여기서 지운다."""
import json
import re

import gitcmd

STATUS_LINE = re.compile(r"^HTTP/\S+ (\d{3})", re.M)
STATUS_ERR = re.compile(r"\(HTTP (\d{3})\)")


def _message(out, err):
    body = out.split("\r\n\r\n", 1)[-1] if "\r\n\r\n" in out else out.split("\n\n", 1)[-1]
    try:
        return str(json.loads(body).get("message", "")) or err.strip()
    except (ValueError, AttributeError):
        return err.strip()


def merge(full, head_sha, message, deadline=None):
    """(응답 코드, 응답 메시지) 를 돌려준다. 시간 초과는 (None, "") 다.

    201 은 merge 함, 204 는 이미 merge 되어 있음, 409 는 충돌이다. 이 API 는 head 가 base 의 후손이어도
    fast-forward 하지 않고 merge commit 을 만든다.
    """
    try:
        code, out, err = gitcmd.gh_try("api", "-i", "-X", "POST", f"repos/{full}/merges", "-f", "base=main",
                                       "-f", f"head={head_sha}", "-f", f"commit_message={message}",
                                       deadline=deadline)
    except gitcmd.CommandTimeout:
        return None, ""
    found = STATUS_LINE.search(out) or STATUS_ERR.search(err)
    status = int(found.group(1)) if found else None
    if status is None and code != 0:
        return None, err.strip() or out.strip()
    return status, ("" if status in (201, 204) else _message(out, err))


def delete_remote(top, branch, sha, deadline=None):
    """push 한 SHA 를 기대값으로 원격 작업 branch 를 지운다. 같은 이름의 남의 branch 는 지우지 않는다."""
    code, _, _ = gitcmd.git_try(top, "push", "-q", "origin", "--delete",
                                f"--force-with-lease=refs/heads/{branch}:{sha}", branch, deadline=deadline)
    return code == 0
