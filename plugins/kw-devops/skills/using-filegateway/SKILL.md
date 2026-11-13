---
name: using-filegateway
description: 서버에서 실행되는 백엔드가 사내 파일 서버(네트워크 드라이브)의 파일을 읽어야 할 때 연다. 개발자 PC에서는 네트워크 경로로 열리는 파일을 서버 코드가 FileGateway로 받아 오게 만들 때, "네트워크 드라이브 파일을 서버에서 읽어야 해"·"공유 폴더 엑셀을 백엔드에서 가져와"·"FileGateway 호출 코드"·"/api/files" 같은 말이 나올 때, FileGateway가 401·404·503으로 거절할 때 연다. 파일을 올리거나 수정하는 작업, 폴더 안의 파일을 찾는 작업에는 쓰지 않는다.
---

# using-filegateway

FileGateway는 사내 파일 서버의 파일을 요청한 사람의 역할에 맞게 내려 주는 읽기 전용 서비스다. 개발자 PC에서는 네트워크 드라이브로 파일을 직접 열 수 있지만, 서버에서 실행되는 백엔드는 열 수 없다. 그래서 백엔드는 FileGateway에 파일 하나를 요청해 받는다.

```
[개발자 PC의 클로드 코드] --내 접근 키 + 네트워크 경로--> [FileGateway] : 경로와 권한을 미리 확인
[서비스 백엔드] --화면을 쓰는 사람의 로그인 토큰 + 공유 이름 + 상대 경로--> [FileGateway] --읽기 전용--> [파일 서버]
```

알고 써야 할 점은 다음과 같다.
- FileGateway는 파일 하나만 내려 준다. 폴더 목록과 파일 검색은 없다. 그래서 파일까지 적힌 경로를 사용자에게 받아야 한다.
- FileGateway는 네트워크 경로의 공유 이름과, 공유 폴더 기준의 상대 경로를 받는다. `\\파일서버\공유 이름\보고서\2월.xlsx`에서 공유 이름은 `공유 이름`이고 상대 경로는 `보고서/2월.xlsx`다.
- FileGateway는 어떤 공유가 연결돼 있는지 알려 주지 않는다. 연결되지 않은 공유와 권한이 없는 공유의 응답이 같다.
- 파일을 올리거나 수정할 수 없다.

> 이 문서에 적힌 것과 FileGateway의 실제 응답이 다르면 맞춰 넘어가지 말고 사용자에게 알린다.

## 접근 키

FileGateway는 searching-winus와 같은 접근 키(환경 변수 `KIWOOM_ACCESS_KEY`)를 받는다. 스크립트는 키가 없거나, FileGateway가 키를 거절하거나, 키를 설정했지만 지금 창에 반영되지 않았으면 멈춘다. 그때 출력의 `조치`·`설정 뒤` 줄이 할 일을 알려 준다.

클로드는 그 출력을 받으면 searching-winus SKILL.md의 「접근 키」 절 순서대로 발급과 등록을 안내하고, 키가 등록될 때까지 다음 단계를 진행하지 않는다. 한 번 등록한 키는 두 스킬 모두에서 쓰인다.

## 작업 순서

1. 파일 이름까지 적힌 네트워크 경로를 사용자에게 받는다. 형태는 `\\서버\공유 이름\폴더\파일`이나 `Z:\폴더\파일`이다.
2. 아래 「명령」의 `check`를 실행해 경로와 권한을 확인한다.
3. 아래 「결과」 표대로 출력을 읽고, `로컬 비교: 일치`가 나온 공유 이름과 상대 경로만 코드에 쓴다.
4. 아래 「백엔드 코드」의 규칙과 예시대로 백엔드 코드를 쓴다.
5. 서비스를 쓰는 사람의 역할로는 확인되지 않았다는 점을 아래 「권한」과 함께 사용자에게 알린다.

`check`는 네트워크 경로를 공유 이름과 상대 경로로 나누고, FileGateway로 그 파일을 받고, 이 PC에서 같은 경로로 읽은 파일과 크기·확인값을 비교한다. 이 확인은 개발자 본인의 역할로 한 결과다.

## 명령

```
python "${CLAUDE_SKILL_DIR}/scripts/filegw.py" check --path "<네트워크 경로>"
```

- 경로는 큰따옴표로 감싼다. 한글과 공백이 있어도 그대로 적는다.
- 받은 파일은 저장하지 않는다. 크기와 확인값만 계산한다. 확인값은 파일 내용의 SHA-256 앞 16자리다.
- 스크립트는 요청을 자동으로 다시 보내지 않는다.

## 결과

| 출력 | 뜻 | 클로드가 할 일 |
|---|---|---|
| `로컬 비교: 일치` | 공유 이름과 상대 경로, 이 키의 권한, 전송이 모두 맞다 | 출력의 `공유 이름`과 `상대 경로`로 코드를 쓴다 |
| `로컬 비교: 하지 못함` | FileGateway로는 받았지만 이 PC에서 그 경로를 읽지 못했다 | 받은 파일이 사용자가 가리킨 파일인지 확인되지 않았다고 알리고, 크기가 맞는지 사용자에게 묻는다. 사용자가 맞다고 답하면 그 공유 이름과 상대 경로로 코드를 쓴다 |
| `로컬 비교: 다름` | FileGateway가 같은 이름의 다른 공유를 열었다 | 그 값으로 코드를 쓰지 않고 사용자에게 알린다 |
| `FileGateway 거절(400)` | 아래 「받지 않는 경로」에 해당한다 | 해당하는 조건을 사용자에게 알린다 |
| `FileGateway 거절(404)` | FileGateway에 연결되지 않은 공유, 없는 파일·폴더, 또는 이 키의 역할에 권한이 없다. FileGateway는 이를 구분해 알려 주지 않는다 | 출력의 마지막 줄이 이 PC에서 그 파일이 열리는지 알려 준다. 열리면 공유 연결이나 권한 문제이므로 아래 「권한」대로 안내한다. 열리지 않으면 경로를 사용자에게 다시 확인한다 |
| `FileGateway 신원 거절(401)` | 접근 키가 틀렸거나 폐기되었다 | 위 「접근 키」대로 안내한다 |
| `FileGateway 거절(503)` | 공유 연결 이상이거나 FileGateway가 권한 정보를 읽지 못했다 | 잠시 뒤 사용자가 다시 요청하게 한다 |

## 받지 않는 경로

FileGateway는 아래 경로를 400으로 거절한다. 파일 서버가 같은 파일을 다른 이름으로도 열어 주는 경로를 차단하기 위해서다.

- 폴더나 파일 이름이 공백이나 `.`으로 끝나는 경로
- `~1`, `~2.xls`처럼 `~숫자`로 끝나는 이름(Windows의 짧은 이름)
- `.snapshot`, `~snapshot`, `~snapsht` 폴더와 `~`로 시작하는 폴더. 파일 이름이 `~`로 시작하는 경로는 받는다
- `:` 문자가 있는 이름과 `..`이 있는 경로

## 백엔드 코드

| 항목 | 값 |
|---|---|
| 주소 | 서버 `192.7.9.45`의 `kiwoom-infra` 네트워크 안에서는 `http://kiwoom-filegateway:9009`, 그 밖에서는 `http://192.7.9.45:9009`. 코드에서는 환경 변수 `FILE_GATEWAY_URL`로 받는다 |
| 메서드·경로 | `GET /api/files/{공유 이름}?path=<상대 경로>`. 공유 이름과 상대 경로는 URL 인코딩한다. 상대 경로는 `/`로 구분한다 |
| 인증 | 헤더 `Authorization: Bearer <로그인 토큰 또는 접근 키>` |
| 성공 응답 | 200과 파일 내용. `Content-Length`가 파일 크기다 |

백엔드는 FileGateway에 보낼 값을 아래 순서로 고른다.

1. 화면에서 온 요청의 헤더 `X-Auth-Access-Token`이 있으면 그 로그인 토큰을 쓴다. 운영에서는 항상 이 값이다.
2. 헤더가 없고 환경 변수 `FILEGW_DEV_ACCESS_KEY`가 있으면 그 접근 키를 쓴다. 개발자 PC에서 실행할 때만 해당한다.
3. 둘 다 없으면 요청을 실패로 처리한다.

지킬 규칙은 다음과 같다.

- 운영 `docker-compose.yml`과 서버의 환경 변수에는 `FILEGW_DEV_ACCESS_KEY`를 넣지 않는다.
- 받은 파일과 로그인 토큰은 그 요청을 보낸 사람에게만 쓰고, 여러 사람이 함께 쓰는 캐시나 폴더에 넣어 두지 않는다.
- 받은 크기가 `Content-Length`와 다르면 실패로 처리한다.
- 503은 횟수를 정해 잠시 기다렸다 다시 요청하고, 400·401·404는 다시 요청하지 않는다.
- 로그인 토큰은 15분 뒤 만료되므로, 긴 작업은 파일을 먼저 받고 처리한다.
- 키 원문을 코드·문서·대화에 적지 않는다.

서버에 접근 키를 넣으면 화면을 쓰는 모든 사람이 그 개발자의 역할로 파일을 받는다. 그래서 클로드는 그런 설정을 요청받으면 진행하지 않고 이 제한을 사용자에게 알린다. 받은 크기를 비교하는 이유는 전송 중에 파일이 바뀌면 FileGateway가 연결을 끊기 때문이다.

파일 서버에서 공유 이름이 바뀌면 코드의 공유 이름도 고쳐야 한다. 클로드는 코드를 쓸 때 이 점을 사용자에게 한 줄로 알린다.

개발자 PC에서 백엔드를 실행할 때는 그 터미널에서만 아래처럼 설정한다.

```powershell
$env:FILEGW_DEV_ACCESS_KEY = $env:KIWOOM_ACCESS_KEY
$env:FILE_GATEWAY_URL = 'http://192.7.9.45:9009'
```

코드 예시는 다음과 같다. 공유 이름과 상대 경로는 `check` 출력의 값을 쓴다.

```python
import os
import time
from urllib.parse import quote

import httpx

FILE_GATEWAY_URL = os.environ.get("FILE_GATEWAY_URL", "http://kiwoom-filegateway:9009")


def gateway_credential(user_token: str | None) -> str:
    """화면에서 온 로그인 토큰을 먼저 쓰고, 없으면 개발자 PC의 접근 키를 쓴다."""
    if user_token:
        return user_token
    dev_key = os.environ.get("FILEGW_DEV_ACCESS_KEY", "").strip()
    if dev_key:
        return dev_key
    raise PermissionError("로그인 토큰 없음: X-Auth-Access-Token 헤더와 FILEGW_DEV_ACCESS_KEY 가 모두 없음")


def fetch_file(share: str, path: str, user_token: str | None) -> bytes:
    """share 는 네트워크 경로의 공유 이름, path 는 공유 폴더 기준의 상대 경로다."""
    headers = {"Authorization": f"Bearer {gateway_credential(user_token)}"}
    for wait in (0, 2, 5):
        time.sleep(wait)
        r = httpx.get(f"{FILE_GATEWAY_URL}/api/files/{quote(share, safe='')}", params={"path": path},
                      headers=headers, timeout=60)
        if r.status_code != 503:
            break
    if r.status_code == 401:
        raise PermissionError("FileGateway 신원 거절(401): 로그인 토큰이 만료되었거나 틀림")
    if r.status_code == 404:
        raise FileNotFoundError(f"FileGateway 404: {share}/{path}. 없는 파일이거나 이 사람의 역할에 권한 없음")
    if r.status_code == 400:
        raise ValueError(f"FileGateway 가 받지 않는 경로 형식: {path}")
    r.raise_for_status()
    if len(r.content) != int(r.headers["Content-Length"]):
        raise IOError(f"받은 크기가 Content-Length 와 다름: {share}/{path}")
    return r.content


# FastAPI 라면 화면에서 온 요청의 헤더를 그대로 전달한다.
# @app.get("/report")
# def report(x_auth_access_token: str | None = Header(default=None)):
#     data = fetch_file("공유 이름", "보고서/2월.xlsx", x_auth_access_token)
```

- `async def` 안에서는 `httpx.AsyncClient`와 `asyncio.sleep`을 쓴다. 동기 호출은 다른 요청의 처리를 멈춘다.
- 수백 MB가 넘는 파일은 `httpx.stream`으로 나눠 받아 디스크에 쓰고, 쓴 크기를 `Content-Length`와 비교한다.

## 권한

FileGateway는 요청한 사람의 역할로 판정한다. 그래서 개발자의 `check`가 성공해도, 서비스를 쓰는 사람에게 그 공유의 권한이 없으면 그 사람의 요청은 404다.

- 권한은 공유와 폴더 단위로 역할(본부·팀)에 준다. 한 폴더에 따로 권한이 정해져 있으면 그 폴더는 상위 폴더의 권한을 따르지 않는다.
- 공유를 FileGateway에 연결하는 일과 권한을 주는 일은 AX팀이 한다. 클로드는 네트워크 경로의 공유 이름, 상대 경로의 폴더, 서비스를 쓸 본부·팀을 정리해 사용자에게 준다. 사용자는 그 정리를 AX팀 요청에 그대로 쓴다.
- 개발자 본인의 `check`가 404이면 개발자의 본부·팀도 그 정리에 넣는다. 개발자에게 권한이 없으면 `check`로 경로를 확인할 수 없다.
- 누가 어떤 파일을 받았는지는 FileGateway의 기록에 남는다. 개발자의 접근 키로 받은 요청은 그 개발자의 이름으로 남는다.
