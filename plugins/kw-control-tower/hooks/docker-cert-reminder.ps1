# 도커 명령을 낼 때만 사내 인증서 조치를 상기시킨다.
#
# Claude Code의 PreToolUse 훅으로 등록되며, 명령이 docker로 시작할 때만 뜨도록 설정의
# if 필터가 걸려 있다. 조치가 이미 보이면 아무 말도 하지 않고, 어떤 경우에도 호출을 막지 않는다.
#
# 상세 지침은 register-corp-certs 스킬이 정본이다. 여기에는 그 순간에 바로 쓸 것만 둔다.

$ErrorActionPreference = 'Stop'

function Write-Context {
    param([string]$Text)
    $payload = @{
        hookSpecificOutput = @{
            hookEventName     = 'PreToolUse'
            additionalContext = $Text
        }
    }
    $payload | ConvertTo-Json -Depth 5 -Compress
}

function Get-Field {
    param($Object, [string]$Name)
    if ($null -eq $Object) { return '' }
    $prop = $Object.PSObject.Properties[$Name]
    if ($null -eq $prop) { return '' }
    if ($null -eq $prop.Value) { return '' }
    return [string]$prop.Value
}

$RunAdvice = @'
[사내 인증서] 인증서를 구워 직접 빌드한 이미지이거나 외부 HTTPS를 내지 않는 컨테이너라면
이 안내는 무시하라. 남이 만든 이미지를 그냥 띄우는 경우에만 해당한다.

그 경우 지금이 인증서를 넣을 마지막 기회다. 컨테이너가 뜨고 나면 마운트를 추가할 수 없어
docker exec 로도 고치지 못한다. 아래를 더하라.

    -v "%LOCALAPPDATA%\corp-certs:/certs:ro"
    -e SSL_CERT_FILE=/certs/ca-bundle.pem
    -e REQUESTS_CA_BUNDLE=/certs/ca-bundle.pem
    -e NODE_EXTRA_CA_CERTS=/certs/ca-bundle.pem
    -e CURL_CA_BUNDLE=/certs/ca-bundle.pem
    -e GIT_SSL_CAINFO=/certs/ca-bundle.pem

파일 하나가 아니라 폴더를 마운트한다. 번들을 다시 구우면 파일이 교체되므로 파일 마운트는
옛 내용에 묶인다.
'@

$BuildAdvice = @'
[사내 인증서] 빌드 중의 HTTPS는 실행 인자로 못 고친다. 도커에는 빌드 단계에 CA를 밖에서 넣는
수단이 없으므로, 필요하다면 Dockerfile에 인증서를 심는 수밖에 없다.

이 사내망에서 실측한 결과는 이렇다.
  인증서 없이도 되는 곳 : PyPI(pip), npm, GitHub, 도커 레지스트리, astral.sh
  인증서가 필요한 곳    : crates.io·rustup(Rust), proxy.golang.org(Go), poetry 설치 스크립트,
                          apt.llvm.org, packages.microsoft.com, https 로 바꾼 데비안 apt,
                          api.anthropic.com

빌드가 앞쪽만 쓴다면 그냥 두면 된다. 뒤쪽을 하나라도 쓰면 register-corp-certs 스킬에 넣을
블록과 그 위치(FROM 바로 다음, 다른 설치 명령보다 먼저)가 적혀 있다.
'@

try {
    $raw = [Console]::In.ReadToEnd()
    if (-not $raw) { exit 0 }
    $j = $raw | ConvertFrom-Json

    $tiProp = $j.PSObject.Properties['tool_input']
    if ($null -eq $tiProp) { exit 0 }
    $cmd = Get-Field $tiProp.Value 'command'
    if (-not $cmd) { exit 0 }

    # 이미 신뢰를 넣는 흔적이 있으면 잔소리하지 않는다.
    $alreadyHandled = 'NODE_EXTRA_CA_CERTS|SSL_CERT_FILE|REQUESTS_CA_BUNDLE|ca-bundle\.pem'

    if ($cmd -match 'docker\s+(container\s+)?run\b|docker\s+compose\s+(up|run)\b') {
        if ($cmd -match $alreadyHandled) { exit 0 }
        Write-Context $RunAdvice
        exit 0
    }
    if ($cmd -match 'docker\s+(image\s+)?build\b|docker\s+compose\s+build\b|docker\s+buildx\s+build\b') {
        Write-Context $BuildAdvice
        exit 0
    }
} catch {
    # 훅이 클로드 코드를 막는 일은 없어야 한다. 조용히 물러난다.
    exit 0
}

exit 0
