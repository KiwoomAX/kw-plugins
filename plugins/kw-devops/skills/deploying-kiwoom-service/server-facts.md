# 서버 실측 근거

SKILL.md 의 규칙이 어디서 나왔는지를 담는다. 사용자가 「왜 그런가」를 묻거나, 서버 동작이 이 기록과
달라 보일 때 연다.

## 서버 실측 (2026-09-08, `ssh -p 2222 chshin84@192.7.9.45`)

아래는 문서가 아니라 서버에서 직접 확인한 값이다. **README 와 어긋나는 것이 있으므로 문서만
읽고 판단하지 않는다.**

| 무엇 | 실측값 |
|---|---|
| Jenkins | 컨테이너 `jenkins`, 호스트 `9090`→내부 8080. 서버는 WSL2 + Docker Desktop |
| 조직 폴더 | `Kiwoom-AX`(repoOwner `KiwoomAX`)가 있고 스캔이 돌고 있다 |
| 스캔 주기 | `H/15 * * * *` — 15분마다. AX 스캔은 실제로 돌고 있다(2026-09-08 07:24 KST, 12초, repo 7개) |
| 발견 브랜치 | `RegexSCMHeadFilterTrait regex=main` — **`main` 만 발견한다.** 다른 브랜치는 잡조차 안 생긴다 |
| AX repo 현황 | `kw_install`·`Executive_dashboard`·`email_db`·`KW-doc-formats`·`DIMA`·`kw-plugins`·`wholesale-dashboard` 일곱 개가 모두 `Jenkinsfile` 없음으로 제외됐다 |
| 공용 라이브러리 | `jenkins-shared-lib`, defaultVersion `main`, `implicit=false`. Jenkins 전역 등록이다 |
| 자격증명 | 루트에 `global-env` 등이 있고 모든 잡이 받는다. `Kiwoom-AX` 폴더 전용 자격증명은 아직 없다 |
| 로그인 | GitHub 계정(2026-09-10 실측). `KiwoomAX` 조직원이면 잡을 읽고 빌드할 수 있다 |

### 무엇이 빌드를 일으키는가 — push 가 아니다

조직 폴더의 **빌드 268개를 전수로 세었다.** cron 263 · 수동 5 · 브랜치 인덱싱 0 · 웹훅 0.

`NoTriggerOrganizationFolderProperty` 가 `branches=.*` `strategy=INDEXING` 으로 걸려 인덱싱이
일으키는 빌드를 막고, `github-plugin-configuration.xml` 은 비어 있어 웹훅도 없다. 남은 트리거는
`kiwoomDeploy` 의 `cron(TZ=Asia/Seoul H 0 * * *)` 하나다.

**그래서 배포는 push 한 순간이 아니라 그날 자정에 일어난다.** Gate 가 최근 24시간 커밋을 확인해
있으면 배포하고 없으면 `NOT_BUILT` 로 끝낸다. 실제 로그가 그렇다.

```
Started by timer
Gate: 스케줄 + 최근 24h 커밋 있음 → 진행
OK: kiwoom-chatbot-stream-backend is healthy
Finished: SUCCESS
```

**즉시 배포하려면 Jenkins 화면에서 수동 빌드를 누른다.** 사용자에게 이 사실을 반드시 알린다 —
모르면 push 해 놓고 오지 않을 배포를 기다린다.

이 실측은 `changedOnly` 파라미터에도 걸린다. 선별 빌드는 push·인덱싱 트리거에서만 켜지는데 그
트리거가 0이므로 **켜 두어도 항상 전량 빌드가 돈다.** `Kiwoom-Handler` 가 `changedOnly: true` 로
켜 두었지만 실제로 선별로 돈 빌드는 없다. 새 repo 에 이 값을 넣을 이유가 지금은 없다.

### 이미 되어 있는 것 — 셋업부터 하자고 접근하지 않는다

공용 라이브러리 등록·자격증명·조직 폴더 잡이 모두 구축돼 있다. **KiwoomAX 스캔도 켜져 있으므로
AX repo 의 `main` 에 `Jenkinsfile` 을 올리면 15분 안에 잡이 저절로 생긴다** — 잡을 손으로 만들지
않는다. 공용 라이브러리는 Jenkins 전역 등록이라 그대로 닿는다.
