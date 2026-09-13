#!/usr/bin/env python3
"""비어 있는 호스트 포트를 셈하고, 정한 포트를 등록부에 넣는다.

**등록부는 `kw_deploy.port` 테이블이고 `kiwoom-rdb-handler`(8700)를 거쳐 읽고 쓴다.**
전에는 `jenkins-shared-lib` README 의 마크다운 표였는데, 그 저장소가 private 이라 KiwoomAX 전용
개발자 15명이 아예 읽지 못했다. 지금은 사내망에 닿기만 하면 된다 — GitHub 권한도 ssh 계정도
필요 없다.

`kiwoom-rdb-manager` SDK 를 쓰지 않는 이유도 같다. 그 패키지가 사는 `KiwoomAM/Kiwoom-Manager`
가 private 이고 협업자 명단이 위와 똑같아서, SDK 를 쓰면 없앤 권한 벽이 되살아난다. 대신 그
계약은 그대로 지킨다 — 값은 `%(name)s` 로만 바인드하고 SQL 에 박지 않으며, 자격증명은 핸들러가
들고 있고 이쪽은 모른다.

**등록부와 실측은 서로 다른 것을 본다.** 등록부는 「잡아 둔 것」이고 TCP 프로브는 「실제로 듣고
있는 것」이다. 둘을 합쳐 점유를 정하고 어긋남을 먼저 알린다 — 등록만 되고 안 뜬 포트는
프로브가 빈 포트로 보고, 뜨는데 등록 안 된 포트는 등록부가 모른다.

    python pick_port.py --doctor    # 이 PC 가 스킬을 돌릴 수 있는지 본다
    python pick_port.py --find <저장소 이름> [<container_name> …]   # 이미 등록된 서비스인가
    python pick_port.py             # 차이와 빈 포트
    python pick_port.py --register <포트> <컨테이너> <service_type> [org [repo]]
    python pick_port.py --check     # 붙박이 예제로 자체 검사
"""
from __future__ import annotations

import concurrent.futures
import json
import socket
import sys
import urllib.error
import urllib.request

서버 = "192.7.9.45"
핸들러 = f"http://{서버}:8700"

# **대역 규약은 여기가 정본이다.** DB 에 두지 않는 이유는 성격이 달라서다 — 포트는 겹치는 순간
# 컨테이너가 죽으니 기계(기본키)가 막아야 하고, 대역은 어겨도 서비스는 뜨는 정책이다. 다섯 줄이
# 몇 달에 한 번 바뀌는 것에 표와 이관과 읽기 경로를 붙이는 것은 값보다 품이 크다.
#
# `3000`대와 `9000`대의 글자에 조직·역할을 모두 적는다. 전에는 「프론트엔드」와 「KiwoomAX 서비스」
# 라 축이 섞여 AX 프론트엔드가 어디로 갈지 정할 수 없었다.
# 이 스킬은 이 대역에서만 고른다. 다른 대역은 다른 팀 것이라 여기서 건드리지 않고,
# 우리가 고르는 자리가 여기뿐이라 겹칠 일도 없다. 그래서 셀 것도 이 대역 하나다.
대역 = [
    (9000, 9199, "KiwoomAX 서비스 — 프론트엔드·백엔드를 나누지 않는다"),
]

# `kw_deploy.port` 의 check 제약과 같은 값들. 어긋나면 DB 가 거부한다.
#
# **역할과 조직을 두 칸으로 갈라 둔다.** 전에는 `KiwoomAM-백엔드`·`KiwoomAX` 처럼 한 칸에 섞여
# 있어, AX 프론트엔드가 어느 값인지 정할 수 없었다. 이제 `frontend` + `KiwoomAX` 로 그냥 적는다.
# 핸들러는 남이 부르는 공용 설비라 `infra` 다 — 조직과 저장소는 그대로 갖는다.
구분 = ["infra", "backend", "frontend", "dashboard"]
조직 = ["KiwoomAM", "KiwoomAX"]


# ── 등록부 ────────────────────────────────────────────────────────────
def _부르기(길: str, 몸: dict) -> dict:
    """핸들러 호출. 실패를 삼키지 않고 바로 멈춘다."""
    요청 = urllib.request.Request(
        핸들러 + 길, data=json.dumps(몸, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(요청, timeout=20) as 답:
            난것 = json.load(답)
    except urllib.error.HTTPError as 탈:
        # 망은 멀쩡하고 핸들러가 거부한 것이다. 둘을 뭉치면 중복 포트를 만난 사람이
        # 사내망을 의심하며 엉뚱한 데를 뒤진다.
        속 = 탈.read().decode("utf-8", "replace")
        try:
            속 = json.loads(속).get("detail") or json.loads(속).get("error") or 속
        except ValueError:
            pass
        raise SystemExit(f"핸들러가 거부했다 (HTTP {탈.code})\n  {속}")
    except urllib.error.URLError as 탈:
        raise SystemExit(f"핸들러에 못 붙었다: {핸들러}{길}\n  {탈}\n"
                         "  사내망에 있는지 먼저 본다. 포트를 문서 없이 짐작하지 않는다.")
    if "error" in 난것:
        raise SystemExit(f"핸들러가 거부했다: {난것.get('error')}\n  {난것.get('detail','')}")
    return 난것


def 등록조회() -> list[dict]:
    """등록부 전체. 포트 오름차순."""
    return _부르기("/v1/query/all-dict", {
        "query": "select port, container, service_type, org, repo "
                 "from kw_deploy.port order by port"
    })["rows"]


def 찾기(이름: str) -> list[dict]:
    """컨테이너나 저장소 이름으로 등록부를 찾는다.

    포트를 새로 고르기 전에 반드시 이것을 먼저 부른다. 안 부르면 이미 포트를 가진
    서비스에 새 포트를 쥐여 주고, 옛 줄은 등록부에 남아 썩는다. container 에 유일
    제약이 없어(한 컨테이너가 포트 여럿을 갖는 것이 실제로 있다) DB 가 안 막아 준다.
    """
    return _부르기("/v1/query/all-dict", {
        "query": "select port, container, service_type, org, repo from kw_deploy.port "
                 "where lower(container) = lower(%(이름)s) or lower(repo) = lower(%(이름)s) "
                 "order by port",
        "params": {"이름": 이름},
    })["rows"]


def 주인(줄들: list[dict], 포트: int) -> dict | None:
    """그 포트를 이미 가진 줄. 없으면 None."""
    return next((r for r in 줄들 if r["port"] == 포트), None)


def 등록(포트: int, 컨테이너: str, 종류: str,
        소속: str | None = None, 저장소: str | None = None) -> None:
    """포트 한 줄을 넣는다. 값은 바인드로만 넘긴다 — SQL 에 박으면 주입이다.

    같은 서비스로 이미 있으면 새로 넣지 않는다. 기본키 충돌로 거부당한 뒤 「2단계로 돌아가
    다시 센다」를 따르면 이미 포트를 가진 서비스가 새 포트를 받아 간다. 그 줄의 repo 칸이
    비어 있으면 채운다 — 비어 있으면 저장소 이름으로 찾을 때 안 나온다.
    """
    먼저 = 주인(등록조회(), 포트)
    if 먼저 is not None:
        if 먼저["container"].lower() != 컨테이너.lower():
            raise SystemExit(f"남이 먼저 잡았다: {포트} {먼저['container']}\n  2단계로 돌아가 다시 센다.")
        if 저장소 and not 먼저["repo"]:
            _부르기("/v1/dml/update", {
                "sql": "update kw_deploy.port set repo = %(repo)s "
                       "where port = %(port)s and repo is null",
                "params": {"repo": 저장소, "port": 포트},
            })
            print(f"이미 등록돼 있다: {포트} {먼저['container']} — 비어 있던 repo 칸을 {저장소} 로 채웠다")
        else:
            print(f"이미 등록돼 있다: {포트} {먼저['container']} — 넣을 것이 없다")
        return
    if 종류 not in 구분:
        raise SystemExit(f"service_type 이 틀렸다: {종류}\n  쓸 수 있는 것: {' · '.join(구분)}")
    if 소속 is not None and 소속 not in 조직:
        raise SystemExit(f"org 가 틀렸다: {소속}\n  쓸 수 있는 것: {' · '.join(조직)}")
    _부르기("/v1/dml/insert", {
        "sql": "insert into kw_deploy.port (port, container, service_type, org, repo) "
               "values (%(port)s, %(container)s, %(service_type)s, %(org)s, %(repo)s)",
        "params": {"port": 포트, "container": 컨테이너, "service_type": 종류,
                   "org": 소속, "repo": 저장소},
    })
    붙임 = " ".join(x for x in (소속, 저장소) if x)
    print(f"등록했다: {포트} {컨테이너} ({종류}{' · ' + 붙임 if 붙임 else ''})")


# ── 실측 ──────────────────────────────────────────────────────────────
def _열림(포트: int, 제한: float = 0.7) -> int | None:
    with socket.socket() as 통로:
        통로.settimeout(제한)
        return 포트 if 통로.connect_ex((서버, 포트)) == 0 else None


def 서버점유(볼것: set[int]) -> set[int]:
    """서버가 실제로 듣고 있는 포트. 사내망에서 붙어 보는 것으로 센다.

    사내망 밖에서는 연결이 모두 실패해 「전부 비었다」로 보인다. 그 상태로 포트를 내주면 남의
    서비스를 죽이므로, 반드시 열려 있는 핸들러(8700)를 함께 물어보고 그것마저 닫혀 있으면
    포트가 아니라 망을 의심하고 끝낸다.
    """
    표지 = 8700
    전부 = sorted(볼것 | {표지})
    with concurrent.futures.ThreadPoolExecutor(256) as 무리:
        열린것 = {p for p in 무리.map(_열림, 전부) if p}

    # 닫힌 것만 넉넉한 제한으로 한 번 더 본다. 1,011개를 0.7초로 한꺼번에 두드리면 서버가
    # 밀리는 순간 살아 있는 포트가 닫힌 것으로 세어졌다(실측: 8800 kiwoom-redis-handler 가
    # Up 9 hours (healthy) 인데 안 뜬다고 나왔다). 열린 것은 빨리 답하므로 다시 볼 이유가 없고,
    # 닫힌 것만 추리면 전체 시간이 거의 안 는다.
    닫힌것 = [p for p in 전부 if p not in 열린것]
    if 닫힌것:
        with concurrent.futures.ThreadPoolExecutor(256) as 무리:
            열린것 |= {p for p in 무리.map(lambda x: _열림(x, 2.0), 닫힌것) if p}

    if 표지 not in 열린것:
        raise SystemExit(f"{서버}:{표지}(rdb-handler) 에 못 붙었다 — 사내망에 있는지 먼저 본다.\n"
                         "여기서 멈춘다. 다 비어 보이는 것을 빈 포트로 착각하면 안 된다.")
    return 열린것 & 볼것


def 빈포트(쓰임: set[int], 몇개: int = 10) -> list[tuple[str, list[int]]]:
    """대역마다 앞에서부터 빈 포트. 계산만 하므로 망 없이 검사할 수 있다."""
    return [(f"{아래}–{위} {용도}",
             [p for p in range(아래, 위 + 1) if p not in 쓰임][:몇개])
            for 아래, 위, 용도 in 대역]


# ── 사전 점검 ─────────────────────────────────────────────────────────
def 사전점검() -> int:
    """이 PC 가 스킬을 돌릴 수 있는지 본다. 환경은 사람마다 다르므로 남이 대신 못 봐 준다."""
    import shutil
    막힌것 = 0
    print(f"파이썬        {sys.version.split()[0]}  (3.7 이상이면 된다)")

    try:
        줄수 = len(등록조회())
        print(f"포트 등록부    닿는다  {핸들러}  ({줄수}줄)")
    except SystemExit as 탈:
        print(f"포트 등록부    못 닿는다  {핸들러}")
        print(f"              → {str(탈).splitlines()[0]}")
        막힌것 += 1

    도커 = shutil.which("docker")
    print(f"도커          있다  {도커}  → 4단계 「빠른 길」의 조건을 본다" if 도커 else
          "도커          없다  → 4단계는 Jenkins 에서 검증한다(정상이다. 깔지 않아도 된다)")

    print()
    print("막는 것 없음. 스킬을 그대로 진행한다." if 막힌것 == 0
          else f"막는 것 {막힌것}개. 위 화살표대로 처리한 뒤 다시 돌린다.")
    return 1 if 막힌것 else 0


def 검사() -> None:
    """망 없이 도는 자체 검사. 대역 계산이 규약대로인지 본다."""
    assert [a for a, _, _ in 대역] == [9000], "이 스킬은 AX 대역에서만 고른다"
    난것 = dict(zip([f"{a}" for a, _, _ in 대역], [p for _, p in 빈포트(set())]))
    assert 난것["9000"] == list(range(9000, 9010)), 난것["9000"]
    assert 빈포트({9000, 9001})[0][1][0] == 9002, "찬 포트를 건너뛰어야 한다"
    assert 빈포트({p for p in range(9000, 9200)})[0][1] == [], "대역이 다 차면 빈칸이 없다"
    assert len(빈포트(set())[0][1]) == 10, "대역이 넓어 열 개까지만 보인다"
    assert 구분 == ["infra", "backend", "frontend", "dashboard"], 구분
    assert 조직 == ["KiwoomAM", "KiwoomAX"], 조직
    줄들 = [{"port": 8080, "container": "kw-dashboard-web", "repo": None}]
    assert 주인(줄들, 8080)["container"] == "kw-dashboard-web" and 주인(줄들, 9002) is None
    print("검사 통과")


if __name__ == "__main__":
    인자 = sys.argv[1:]
    if "--check" in 인자:
        검사()
    elif "--doctor" in 인자:
        sys.exit(사전점검())
    elif "--find" in 인자:
        # 저장소 이름과 container_name 을 함께 받는다. 옛 줄은 repo 칸이 비어 있어 저장소
        # 이름 하나로는 못 찾는다(실측: kw-dashboard-web 두 줄).
        남은 = 인자[인자.index("--find") + 1:]
        if not 남은:
            raise SystemExit("쓰임: --find <저장소 이름> [<container_name> …]")
        찾은 = sorted({r["port"]: r for n in 남은 for r in 찾기(n)}.values(),
                    key=lambda r: r["port"])
        묶음 = ", ".join(남은)
        if not 찾은:
            print(f"등록부에 없다: {묶음}")
            print("  처음 올리는 서비스다. 인자 없이 돌려 빈 포트를 고른다.")
        else:
            with concurrent.futures.ThreadPoolExecutor(8) as 무리:
                뜬것 = {p for p in 무리.map(lambda r: _열림(r["port"], 2.0), 찾은) if p}
            print(f"이미 등록돼 있다: {묶음} — {len(찾은)}줄")
            for r in 찾은:
                붙임 = " · ".join(x for x in (r["org"], r["repo"]) if x)
                print(f"  {r['port']}  {r['container']}  ({r['service_type']}"
                      f"{' · ' + 붙임 if 붙임 else ''})  "
                      f"{'뜬다' if r['port'] in 뜬것 else '안 뜬다'}")
            print("  **새 포트를 고르지 않는다.** 위 포트를 그대로 쓴다.")
            print("  줄이 둘 이상이면 어느 것을 쓸지 사람에게 묻는다.")
            if 뜬것:
                print("  **서버에서 이미 돌고 있다.** 3단계의 「이미 도는 서비스를 넘겨받을 때」를 따른다.")
    elif "--register" in 인자:
        남은 = 인자[인자.index("--register") + 1:]
        if not 3 <= len(남은) <= 5:
            raise SystemExit("쓰임: --register <포트> <컨테이너> <service_type> [org [repo]]\n"
                             f"  service_type: {' · '.join(구분)}\n"
                             f"  org         : {' · '.join(조직)} — 이미지를 그대로 띄운 인프라는 뺀다")
        등록(int(남은[0]), 남은[1], 남은[2],
            남은[3] if len(남은) > 3 else None,
            남은[4] if len(남은) > 4 else None)
    else:
        줄들 = 등록조회()
        등록됨 = {r["port"] for r in 줄들}
        이름 = {r["port"]: r["container"] for r in 줄들}
        볼것 = {p for 아래, 위, _ in 대역 for p in range(아래, 위 + 1)}
        실제 = 서버점유(볼것)

        # FAIL-LOUD — 어긋남을 합치고 끝내지 않고 사람에게 보인다.
        등록만 = sorted(p for p in 등록됨 - 실제 if p in 볼것)
        실측만 = sorted(실제 - 등록됨)
        if 등록만:
            print("[차이] 등록됐지만 안 뜬다: "
                  + ", ".join(f"{p} {이름[p]}" for p in 등록만))
        if 실측만:
            print(f"[차이] 뜨는데 등록이 없다: {실측만}  ← 등록부에 넣어야 한다")
        print(f"[등록부] {len(줄들)}줄 · {핸들러}\n" if not (등록만 or 실측만)
              else "위 차이를 사람에게 알린 뒤 포트를 고른다.\n")

        for 이름줄, 포트들 in 빈포트(등록됨 | 실제):
            print(f"{이름줄}\n  빈 포트: {', '.join(map(str, 포트들)) or '없다'} …\n")
