# kw-plugins

키움 AX 팀이 사내 PC에 나눠 주는 클로드 코드 플러그인의 마켓플레이스다. 여기서 배포하는
것은 **컨트롤 타워**와 **문서 형식 스킬** 둘이고, 남의 저장소에 있는 플러그인은 컨트롤
타워가 목록을 들고 끌어온다.

## 왜 이렇게 만들었나

전에는 "이 PC에 무엇을 깔지"가 설치기(`kw_install`) 코드 안에 적혀 있었다. 그래서 플러그인을
하나 더할 때마다 설치기를 고치고 **전 직원이 그것을 다시 돌려야** 했다.

목록을 설치기 밖으로 꺼내 여기 두었다. 이제 플러그인을 더하는 일은 `manifest.json`에 한 줄
더하고 커밋하는 것이고, 각 PC는 다음 세션에 그 변화를 듣는다.

## 새 사내 플러그인을 더하려면

**이 저장소 안에 둔다.** `plugins/이름/` 아래에 플러그인을 놓고 두 곳에 한 줄씩 더한다.

```jsonc
// .claude-plugin/marketplace.json — 무엇을 파는가
{ "name": "kw-infra", "source": "./plugins/kw-infra" }

// plugins/kw-control-tower/manifest.json — 각 PC가 그것을 갖춰야 하는가
"required": [ "kw-infra@kiwoom-ax" ]
```

배포처는 이미 등록돼 있으므로 `marketplaces`는 안 건드린다. 원본이 이 저장소 안의 경로라
마켓플레이스를 받을 때 파일이 함께 오고, 설치가 네트워크를 안 쓴다.

**원본을 `{ "source": "github", "repo": "소유자/저장소" }` 로 적지 마라.** 다섯 가지 원본
형식 가운데 이것만 프로토콜을 안 받아서 클로드 코드가 주소를 조립하는데, 플러그인 설치 쪽
조립기가 SSH를 골라 SSH 키가 없는 사내 PC에서 `Host key verification failed`로 끝난다.
저장소가 퍼블릭인지는 무관하다 — 그 오류는 인가 이전인 호스트 키 검증에서 난다.
2026-09-06에 재고 확인했다.

정말로 남의 저장소를 가리켜야 한다면 `{ "source": "url", "url": "https://…git" }` 처럼
**프로토콜이 든 완전한 주소**를 적는다. 공식 마켓플레이스가 외부 저장소 238곳을 그 형식으로
가리키고 있고, 그 가운데 `superpowers`가 사내 PC에서 매번 깔린다.

## 컨트롤 타워가 하는 일

두 가지이고, 그 둘을 일부러 갈라 놓았다.

**세션이 시작할 때 알린다.** 이 PC가 목록과 어긋난 곳을 말하기만 하고 **아무것도 고치지
않는다.** 매 세션 도는 자리라 사용자에게 묻지 않고 PC를 바꾸면 안 되기 때문이다. 이상이
없으면 아무 말도 하지 않는다.

**`/kw-control-tower:kw-sync` 를 부르면 고친다.** 걸음이 여덟이고 저마다 독립이라 하나가 실패해도 나머지는
돈다. 배포처 등록, 필수 플러그인 설치와 되켜기, 더 안 쓰는 것 정리, 파이썬 라이브러리,
`PYTHONUTF8`, `CLAUDE.md`의 사내 문안, 옛 스킬 사본과 훅 배선 정리, `python3` 판정이다.

무엇을 바꿨는지 마지막에 요약하고, **사용자가 꺼 둔 필수 플러그인을 되켰으면 그것을 따로
적는다.** 회사가 정한 것이라 되켜지만 사용자 결정을 뒤집은 것이므로 조용히 지나가지 않는다.

## 세션 시작이 느려지지 않게 한 것

이것이 이 플러그인의 첫째 제약이다. 알림이 느려지면 감지의 값이 얼마든 사용자가 그것을
끄게 된다. 계약이 다섯이다.

| 무엇 | 값 |
|---|---|
| 세션 시작에 도는 훅 | 하나뿐이다 |
| 외부 프로그램 | 안 부른다. `claude`도 `git`도 `python`도 |
| 네트워크 | 안 나간다. 디스크에 있는 것만 본다 |
| 읽는 것 | 파일 여덟과 레지스트리 값 하나. 이 PC에서 합쳐 25KB 미만 |
| 몸통 시간 | 200밀리초를 넘으면 그 값을 남기고 검사가 떨어진다 |

이 PC에서 여러 차례 재니 프로세스까지 합쳐 0.4초 안팎이고 몸통은 다 200밀리초 안이었다. 세션이 처음 열릴 때 한 번은 넘길 수 있는데, 그때는 알림에 안 섞고 자국만 남긴다. 훅을 `pwsh`가 아니라 `powershell.exe`로
거는 이유가 둘이다. 그쪽이 빠르고(7은 513밀리초), pwsh 7이 클로드가 찾는 세 자리에 없는
PC에서도 훅이 죽지 않는다.

## 이 저장소에 있는 것

| 경로 | 무엇 |
|---|---|
| `.claude-plugin/marketplace.json` | 마켓플레이스 `kiwoom-ax` 정의 |
| `plugins/kw-control-tower/manifest.json` | **목록의 정본.** 새 플러그인은 여기에 더한다 |
| `plugins/kw-control-tower/hooks/` | 세션 시작 알림, 도커 인증서 안내, `python3` 가드 |
| `plugins/kw-control-tower/scripts/sync.ps1` | 그 명령이 부르는 본체 |
| `plugins/kw-control-tower/commands/kw-sync.md` | `/kw-control-tower:kw-sync` 명령. 플러그인이 나르는 명령은 언제나 `플러그인이름:명령이름` 으로 불린다 |
| `plugins/kw-control-tower/skills/` | 사내 인증서 스킬 |
| `plugins/kw-doc-formats/skills/` | 문서 형식 스킬 여섯. `common`·`hwp`·`pdf`·`pptx`·`xlsx`·`docx` |
| `tests/test_control_tower.ps1` | 컨트롤 타워의 계약 검사 |
| `tests/test_doc_formats.ps1` | 문서 형식 스킬의 계약 검사 |
| `docs/superpowers/specs/` | 설계 문서. 왜 그렇게 만들었는지가 여기 있다 |
| `docs/superpowers/reviews/` | 그 설계를 검토한 기록 |

## 손으로 고칠 때 지킬 것

**PowerShell 파일은 UTF-8 BOM으로 저장한다.** BOM이 없으면 Windows PowerShell 5.1이 본문을
다른 인코딩으로 읽어 한국어가 깨진다.

**훅 스크립트는 5.1 문법만 쓴다.** `ConvertFrom-Json -AsHashtable`처럼 7에만 있는 것을 쓰면
pwsh 7이 없는 PC에서 훅이 죽는다. 그리고 5.1은 `uint64` 곱셈이 넘칠 때 감싸지 않고 던진다.

**고친 뒤에는 검사를 둘 다 돌린다.**

```
pwsh -NoProfile -File tests\test_control_tower.ps1
pwsh -NoProfile -File tests\test_doc_formats.ps1
```
