---
name: register-corp-certs
description: 사내 SSL 검사 장비 환경의 인증서 처리. 인증서 등록이나 SSL 설정 요청, 도커·컨테이너·WSL 안에서 HTTPS 요청을 보내는 작업, 그리고 CERTIFICATE_VERIFY_FAILED·SSLCertVerificationError·self signed certificate in certificate chain 같은 검증 오류에 쓴다.
---

# 사내 SSL 인증서

사내 네트워크의 SSL 검사 장비가 일부 목적지의 TLS를 가로챈다. 가로채기는 선별적이다.
`data.krx.co.kr`과 `google.com`으로 가는 연결은 가로채고 `pypi.org`로 가는 연결은 가로채지 않는다.
어느 곳을 가로채는지 미리 알 수 없으므로 목적지별로 대응하지 않는다.

PC 자체는 한 번 등록해 두면 파이썬과 pip와 Node가 별도 설정 없이 동작한다. **컨테이너와 WSL은 예외다.**
윈도우 사용자 환경 변수를 물려받지 않으므로 그 안은 따로 설정해야 한다.

## PC에 등록하기

아래 명령 한 줄만 실행하면 된다. 스크립트가 판단과 검증을 모두 포함하고 있으니 다른 명령과 조합하거나 여러 단계로 나누어 실행하지 마라.

```
pwsh -NoProfile -ExecutionPolicy Bypass -File "\\cifs\ai\projects\kw_install\setup.ps1"
```

이 명령은 설치기 전체를 실행하며, 인증서 등록이 그 1단계다. 인증서만 다시 설정하고 싶으면 뒤에
`-SkipPrograms -SkipPythonLibs -SkipClaudeInstall -SkipPlugins`를 붙인다.

여러 번 실행해도 안전하다. 파이썬이 없어도 된다. 실행이 끝나면 사용자에게 **터미널과 클로드 코드와
VSCode를 다시 시작하라**고 알려라. 환경 변수는 이미 실행 중인 프로그램에는 적용되지 않는다.

| 종료 코드 | 뜻 | 할 일 |
|---|---|---|
| 0 | 등록과 검증이 끝났다. | 재시작을 안내한다. |
| 2 | 등록에 필요한 파일을 가져오지 못했다. | 공유 폴더 `\\cifs\ai\projects\kw_install` 접근을 확인한다. 기존 상태는 수정하지 않았다. |
| 3 | 환경 변수는 설정되었으나 접속 검증이 실패했다. | 사내망 연결과, 회사 루트 인증서가 윈도우 인증서 저장소에 배포되었는지 확인한다. 출력의 상세 내용을 그대로 전한다. |
| 1 | 그 밖의 오류다. | 출력을 그대로 전한다. |

## 컨테이너에는 실행할 때 인증서를 넣는 것이 기본이다

**기존 이미지도 Dockerfile도 수정하지 않는다.** 실행할 때 인증서 번들을 마운트하고 환경 변수를 지정하면 어떤
이미지든 그 안의 파이썬과 Node가 사내 인증서를 신뢰한다.

```powershell
docker run -v "$(Split-Path -Parent $env:SSL_CERT_FILE):/certs:ro" `
           -e SSL_CERT_FILE=/certs/ca-bundle.pem `
           -e REQUESTS_CA_BUNDLE=/certs/ca-bundle.pem `
           -e NODE_EXTRA_CA_CERTS=/certs/ca-bundle.pem `
           -e CURL_CA_BUNDLE=/certs/ca-bundle.pem `
           -e GIT_SSL_CAINFO=/certs/ca-bundle.pem `
           <이미지>
```

번들의 경로를 직접 적지 않고 `SSL_CERT_FILE`에서 읽어 오는 이유는, 설치기가 그 위치를 바꿔도
이 명령이 그대로 동작하게 하려는 것이다. 설치기 1단계가 번들을 만들면서 그 변수를 설정한다.

변수가 5개인 이유는 도구마다 읽는 변수 이름이 다르기 때문이다. 파이썬 표준 라이브러리는
`SSL_CERT_FILE`, requests는 `REQUESTS_CA_BUNDLE`, Node는 `NODE_EXTRA_CA_CERTS`, `curl`은
`CURL_CA_BUNDLE`, `git`은 `GIT_SSL_CAINFO`를 읽는다. 하나라도 빠지면 그 도구에서만 검증이 실패한다.

**환경 변수로 해결되지 않는 것이 2가지 있다.** `apt`를 https 소스로 쓰면 시스템 인증서 저장소만
읽고, 자바는 JVM 자체 truststore(`cacerts`)만 읽는다. 둘 중 하나라도 쓰는 이미지라면 실행
인자로는 해결할 수 없고 Dockerfile에서 시스템 인증서 저장소나 `keytool`로 넣어야 한다.

파일 하나가 아니라 **폴더를 마운트한다.** 도커 데스크톱에서 윈도우 경로의 단일 파일 마운트는
불안정하다. 무엇보다 `setup.ps1`이 번들을 다시 만들면 파일이 통째로 교체되기 때문에, 파일
하나를 마운트한 컨테이너는 이전 내용을 계속 읽게 된다. 폴더로 마운트하면 그런 일이 없다.

`REQUESTS_CA_BUNDLE`을 함께 지정하는 이유는 requests가 `SSL_CERT_FILE`을 읽지 않기 때문이다.
그 번들은 공용 루트 인증서를 모두 포함하므로 그대로 써도 안전하다.

**마운트는 컨테이너를 실행할 때만 넣을 수 있다.** 컨테이너가 실행된 뒤에는 마운트를 추가할 수 없으므로
`docker exec`로는 바로잡을 수 없다. 반대로 위처럼 실행했다면 뒤이어 `docker exec`로 안에서 파이썬을 실행할 때는
아무것도 더 붙일 필요가 없다. `docker compose`를 쓴다면 같은 내용을 `volumes`와
`environment`에 적는다.

## Dockerfile을 고쳐야 하는 상황

2가지뿐이다. **빌드 중에** 검사 장비가 가로채는 곳으로 HTTPS 요청을 보내야 할 때, 또는 그 이미지를
다른 사람에게 전달해 실행 인자 없이도 동작하게 만들고 싶을 때다. 빌드 중에 인증서를 넣는 일은 실행 인자로
대신할 수 없다. 도커에는 빌드 단계에서 CA 인증서를 밖에서 넣는 방법이 없기 때문이다.

가로채기는 선별적이다. 허용 목록이 "개발 인프라 전부"가 아니라 특정한 곳만 포함하므로, 결과는 빌드가 무엇을
내려받느냐에 따라 달라진다. 이 사내망에서 직접 확인한 결과는 다음과 같다.

| 인증서 없이도 접속되는 곳 | 인증서가 필요한 곳 |
|---|---|
| `pypi.org`, `files.pythonhosted.org` (pip) | `crates.io`, `sh.rustup.rs` (Rust 전체) |
| `registry.npmjs.org` (npm) | `proxy.golang.org` (Go 모듈) |
| `github.com`, `raw.githubusercontent.com` | `install.python-poetry.org` |
| 도커 레지스트리, `get.docker.com` | `apt.llvm.org`, `packages.microsoft.com` |
| `astral.sh` (uv), `deb.nodesource.com` | `deb.debian.org` (https 소스로 바꿨을 때) |
| | `api.anthropic.com` |

즉 `pip`과 `npm`만 쓰는 빌드는 별도 조치 없이 성공하지만, `cargo build`나 `go mod download`를 포함한 빌드는
인증서 없이는 반드시 실패한다. 컨테이너 안에서 클로드나 Anthropic API를 쓰는 상황도 마찬가지다.

고쳐야 한다면 블록을 `FROM` 바로 다음, 다른 설치 명령보다 **먼저** 둔다.

```dockerfile
FROM python:3.12-slim

COPY certs/eprism-root.pem /usr/local/share/ca-certificates/eprism-root.crt
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && update-ca-certificates
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
ENV NODE_EXTRA_CA_CERTS=/usr/local/share/ca-certificates/eprism-root.crt

# 그다음에 apt·pip·npm 설치가 온다
```

인증서 원본은 `\\cifs\ai\projects\kw_install\certs\ePrism-SSL-ROOT-CA.crt`에 있다. 도커는 빌드
컨텍스트 밖의 파일을 `COPY`하지 못하므로 프로젝트 폴더 안에 복사해 두어야 한다. 이 인증서는
비밀이 아니라 모든 사내 PC에 배포된 공개 루트 인증서이므로 코드 저장소에 넣어도 된다. 알파인 등 데비안
계열이 아닌 베이스 이미지라면 그 배포판의 방식에 맞게 바꿔 넣는다.

이 블록으로 빌드하면 설정이 **이미지에 고정되어** 실행 인자가 필요 없어진다.

컨테이너 안의 `curl`이나 `git`에도 적용하려면 마운트 위치를 `/etc/ssl/certs/ca-certificates.crt`로
지정해 배포판의 번들을 대체한다. 다만 그 이미지가 실행 중에 `update-ca-certificates`를 호출하면
그 파일이 읽기 전용이라 실패한다.

## WSL 안에서

별개의 리눅스 환경이므로 같은 방식으로 인증서를 넣는다. `ePrism-SSL-ROOT-CA.crt`를
`/usr/local/share/ca-certificates/` 아래에 두고 `update-ca-certificates`를 호출한 뒤,
`~/.bashrc`에 `SSL_CERT_FILE`과 `REQUESTS_CA_BUNDLE`과 `NODE_EXTRA_CA_CERTS`를 설정한다.

## 인증서 오류를 만났을 때

**코드에 CA 처리를 넣지 마라.** 이 구조는 그런 코드를 없애려고 만든 것이다. 오류가 발생한 곳에 따라 구분한다.

| 오류가 발생한 곳 | 할 일 |
|---|---|
| 윈도우에서 실행한 파이썬·pip·Node | 등록되지 않았거나 번들이 오래된 것이다. 위 `setup.ps1`을 한 번 실행하고 터미널을 다시 연다. |
| 컨테이너 안 | 위의 Dockerfile 블록이나 마운트 인자를 넣는다. |
| WSL 안 | 위의 WSL 절을 따른다. |
| `curl.exe` | `CRYPT_E_NO_REVOCATION_CHECK`라면 인증서 신뢰 문제가 아니라 인증서 폐기 여부 확인 문제다. `%USERPROFILE%\_curlrc`에 `ssl-no-revoke` 한 줄을 넣는다. |

## 하지 말아야 할 것

- 스크립트 앞머리에 CA 번들 경로를 설정하는 코드를 넣지 마라.
- 인증서 파일을 프로젝트마다 복사해 두지 마라. 도커 빌드 컨텍스트만 예외다.
- `truststore`나 `pip-system-certs`를 설치하지 마라. 검토했고 기각했다. 이유는
  `\\cifs\ai\projects\backup\ssl_trust\docs\superpowers\specs\2026-08-06-corp-cert-setup-design.md`에 있다.
