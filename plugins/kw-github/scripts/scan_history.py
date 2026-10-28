"""기존 이력을 처음 GitHub 에 올리기 전에 과거 커밋 전체를 검사한다.

판정은 저장과 같은 rules.judge 를 쓴다. 텍스트 파일만 내용을 꺼내 읽는다.
"""
import argparse
import json
import sys
from pathlib import Path

import gitcmd
import rules
import shared_repo

RULES_PATH = Path(__file__).resolve().parent / "upload_rules.json"
SCAN_SECONDS = 120
ZERO_OID = set("0")
SUBMODULE_MODE = "160000"


class _NeedContent(Exception):
    """rules.judge 가 내용을 읽으려 할 때 올린다. 내용은 모아서 한 번에 읽는다."""


def _need_content():
    raise _NeedContent


def judge_blobs(top, data, entries, deadline=None):
    """(blob, path) 목록을 판정해 (blob, path, size, 판정) 을 돌려준다. git 프로세스는 둘까지만 띄운다.

    크기는 cat-file --batch-check 로, 내용은 이름과 크기로 판정이 끝나지 않은 텍스트 파일만 cat-file --batch 로 읽는다.
    """
    sizes = gitcmd.blob_sizes(top, [blob for blob, _ in entries], deadline)
    judged, waiting = [], []
    for blob, path in entries:
        if blob not in sizes:
            continue
        try:
            judged.append((blob, path, sizes[blob], rules.judge(data, path, sizes[blob], _need_content)))
        except _NeedContent:
            waiting.append((blob, path))
    contents = gitcmd.blob_contents(top, [blob for blob, _ in waiting], deadline)
    for blob, path in waiting:
        raw = contents.get(blob, b"")
        judged.append((blob, path, sizes[blob], rules.judge(data, path, sizes[blob], lambda raw=raw: raw)))
    return judged


def _history_blobs(top, ref, deadline):
    for line in gitcmd.git(top, "rev-list", "--objects", ref, deadline=deadline).splitlines():
        yield line.split(" ", 1)[0]


def _changed_blobs(top, commits, deadline):
    """commit 마다 부모와 비교해 새로 들어온 (blob, path) 와 그 commit 을 git log 프로세스 하나로 모은다.

    부모와 같은 파일은 부모 commit 에서 이미 나온다. 부모가 검사 대상 밖이면 그 내용은 skip_ref 이력에 있다.
    """
    args = ["log", "--raw", "-z", "-m", "--root", "--no-renames", "--no-abbrev", "--format=%x00%H"]
    if commits is None:
        out = gitcmd.git(top, *args, "--all", deadline=deadline)
    else:
        out = gitcmd.git(top, *args, "--no-walk", "--stdin", deadline=deadline,
                         stdin="".join(f"{commit}\n" for commit in commits).encode("ascii"))
    tokens, commit, found, index = out.split("\0"), "", {}, 0
    while index < len(tokens):
        token = tokens[index].lstrip("\n")
        index += 1
        if not token.startswith(":"):
            if token:
                commit = token
            continue
        # :<옛 mode> <새 mode> <옛 blob> <새 blob> <상태> 다음 토큰이 경로다.
        meta, path = token[1:].split(), tokens[index] if index < len(tokens) else ""
        index += 1
        if set(meta[3]) == ZERO_OID or meta[1] == SUBMODULE_MODE:
            continue  # 지운 파일과 하위 모듈이다
        found.setdefault((meta[3], path), commit)
    return found


def scan(top, data, deadline=None, commits=None, skip_ref=None, doc_feature=None):
    """commits 가 없으면 모든 commit 을 본다. skip_ref 의 이력에 있는 내용(blob)은 보지 않는다.

    기능 이전 merge 뒤 다른 개발자가 고친 파일의 옛 내용은 skip_ref 이력에 있으므로 검출하지 않는다.

    doc_feature 가 있으면 그 기능의 설명 문서(docs/<기능>.pdf·docx)는 크기 상한 안에서 보지 않는다.
    """
    if commits is not None and not commits:
        return []
    known = set(_history_blobs(top, skip_ref, deadline)) if skip_ref else set()
    found = _changed_blobs(top, commits, deadline)
    entries = [(blob, path) for blob, path in found if blob not in known]
    doc_limit = data["data"]["file_max_mib"] * 1024 * 1024
    hits = []
    for blob, path, size, verdict in judge_blobs(top, data, entries, deadline):
        if doc_feature and shared_repo.is_feature_doc(path, doc_feature) and size <= doc_limit:
            continue
        if verdict is not None:
            hits.append({"path": path, "reason": verdict[0], "rule": verdict[1], "commit": found[(blob, path)][:8]})
    return hits


def run_scan(repo, rules_path=RULES_PATH, ref=None):
    try:
        data = rules.load(rules_path)
        deadline = gitcmd.Deadline(SCAN_SECONDS)
        commits = gitcmd.git(repo, "rev-list", ref, deadline=deadline).split() if ref else None
        hits = scan(repo, data, deadline, commits=commits)
    except rules.RulesError as exc:
        return {"status": "failed", "hits": [],
                "detail": f"규칙 파일 오류다. 개발자가 풀 일이 아니니 멈추고 AX팀에 알리라고 전하라. {exc}"}
    except gitcmd.CommandTimeout as exc:
        return {"status": "timeout", "hits": [],
                "detail": (f"{SCAN_SECONDS}초 안에 검사를 끝내지 못했다. 끝까지 확인하지 못한 이력은 올리지 "
                           f"않는다. 걸린 것과 같게 보고 reset_history.py 를 불러라. {exc}")}
    except Exception as exc:  # noqa: BLE001 — 스킬은 어떤 경우에도 JSON 을 받아야 한다
        return {"status": "failed", "hits": [], "detail": f"{exc.__class__.__name__}: {exc}"}
    if hits:
        return {"status": "hits", "hits": hits,
                "detail": "과거 커밋에 올리면 안 되는 파일이 있다. 개발자에게 묻지 말고 reset_history.py 를 불러라."}
    return {"status": "clean", "hits": [], "detail": "과거 커밋에 걸리는 파일이 없다. 이력을 그대로 둔다."}


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="과거 커밋 전체를 업로드 규칙으로 검사한다.")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--ref", help="이 branch 에 닿는 commit 만 검사한다(기능 이전은 main)")
    args = parser.parse_args(argv)
    payload = run_scan(Path(args.repo), ref=args.ref)
    # ASCII 로만 내보낸다. cp949 로 설정된 PowerShell 이 출력을 담아도 한글이 깨지지 않는다.
    print(json.dumps(payload))
    return 0 if payload["status"] == "clean" else 1


if __name__ == "__main__":
    raise SystemExit(main())
