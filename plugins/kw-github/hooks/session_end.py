"""세션이 끝날 때 이 세션의 작업 중 표시를 지운다.

SessionEnd 훅은 기본 1.5초 안에 끝나야 하므로 저장은 하지 않고 표시 파일 하나만 지운다.
비정상 종료로 지우지 못한 표시는 session_mark.ACTIVE_SECONDS 가 지나면 무시된다.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import session_mark  # noqa: E402


def main():
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8") or "{}")
        session_mark.clear(payload.get("cwd") or os.getcwd(), payload.get("session_id"))
    except Exception:  # noqa: BLE001 — 지우지 못해도 표시는 시간이 지나면 무시된다
        pass


if __name__ == "__main__":
    main()
