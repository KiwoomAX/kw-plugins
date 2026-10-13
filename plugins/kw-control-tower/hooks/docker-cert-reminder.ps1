# 도커 명령을 실행할 때만 사내 인증서 조치를 상기시킨다.
#
# Claude Code의 PreToolUse 훅으로 등록되며, 명령이 docker로 시작할 때만 실행되도록 설정의
# if 필터가 적용되어 있다. 조치가 이미 보이면 아무 말도 하지 않고, 어떤 상황에도 호출을 막지 않는다.
#
# 상세 지침은 register-corp-certs 스킬이 원본이다. 여기에는 그 순간에 바로 쓸 것만 둔다.

$ErrorActionPreference = 'Stop'

# 나가는 인코딩을 맞춘다. 콘솔 코드페이지가 949 면 한국어 안내가 cp949 로 나가 깨진다.
try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false) } catch { }

# 번들이 없는 PC 에서는 안내하지 않는다. 이 안내는 번들을 컨테이너에 마운트하라는 것이라,
# 없는 폴더를 가리키면 틀린 안내가 된다.
#
# 플러그인 훅은 연결이 목록 파일에 고정되어 PC 마다 다르게 등록할 수 없다. 그래서 번들이
# 있는지를 등록 시점이 아니라 호출할 때마다 훅이 직접 판정한다. 나중에 번들이 생긴 PC 에서는
# 따로 조치하지 않아도 안내가 동작한다.
#
# 번들 위치는 설치기가 1단계에서 설정하는 SSL_CERT_FILE 에서 읽는다(설계 문서
# 2026-09-06-control-tower-design.md 의 결정). 경로를 코드에 고정하면 설치기가 번들을 옮길 때
# 이 훅만 옛 위치를 가리킨다. 번들을 %LOCALAPPDATA%\corp-certs 에서 D:\corp-certs 로 옮겼을 때
# 새로 설치한 PC 에서 이 안내가 사라질 뻔했다.
$bundleFile = $env:SSL_CERT_FILE
if (-not $bundleFile -or -not (Test-Path -LiteralPath $bundleFile)) { exit 0 }
$bundleDir = Split-Path -Parent $bundleFile

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
[사내 인증서] 인증서를 넣어 직접 빌드한 이미지이거나 외부로 HTTPS 요청을 보내지 않는 컨테이너라면
이 안내는 무시하라. 남이 만든 이미지를 그대로 실행하는 상황에만 해당한다.

그 상황에서는 지금이 인증서를 넣을 마지막 기회다. 컨테이너가 실행된 뒤에는 마운트를 추가할 수 없어
docker exec 로도 고치지 못한다. 아래를 추가하라.

    -v "__BUNDLE_DIR__:/certs:ro"
    -e SSL_CERT_FILE=/certs/ca-bundle.pem
    -e REQUESTS_CA_BUNDLE=/certs/ca-bundle.pem
    -e NODE_EXTRA_CA_CERTS=/certs/ca-bundle.pem
    -e CURL_CA_BUNDLE=/certs/ca-bundle.pem
    -e GIT_SSL_CAINFO=/certs/ca-bundle.pem

파일 하나가 아니라 폴더를 마운트한다. 번들을 다시 만들면 파일이 교체되므로 파일을 마운트하면
옛 내용을 계속 보게 된다.
'@

$BuildAdvice = @'
[사내 인증서] 빌드 중의 HTTPS는 실행 인자로 못 고친다. 도커에는 빌드 단계에 CA를 밖에서 넣는
수단이 없으므로, 필요하다면 Dockerfile에 인증서를 넣는 수밖에 없다.

이 사내망에서 실측한 결과는 이렇다.
  인증서 없이도 되는 곳 : PyPI(pip), npm, GitHub, 도커 레지스트리, astral.sh
  인증서가 필요한 곳    : crates.io·rustup(Rust), proxy.golang.org(Go), poetry 설치 스크립트,
                          apt.llvm.org, packages.microsoft.com, https 로 바꾼 데비안 apt,
                          api.anthropic.com

빌드가 앞쪽만 쓴다면 조치할 필요가 없다. 뒤쪽을 하나라도 쓰면 register-corp-certs 스킬에 넣을
블록과 그 위치(FROM 바로 다음, 다른 설치 명령보다 먼저)가 적혀 있다.
'@

try {
    # 표준입력을 UTF-8 로 직접 읽는다. [Console]::In 은 콘솔 코드페이지로 해석하는데
    # 한국어 윈도에서는 949 라, 클로드가 보내는 UTF-8 한글이 깨지고 따옴표 짝이 어긋나
    # JSON 을 읽지 못한다. 그러면 판정을 못 해 한글이 든 명령에서만 안내가 빠진다.
    # 2026-09-19 에 코드페이지 949 와 65001 로 각각 실행해 확인했다.
    $stdin  = [Console]::OpenStandardInput()
    $reader = New-Object System.IO.StreamReader($stdin, (New-Object System.Text.UTF8Encoding($false)))
    try { $raw = $reader.ReadToEnd() } finally { $reader.Dispose() }
    if (-not $raw) { exit 0 }
    $j = $raw | ConvertFrom-Json

    $tiProp = $j.PSObject.Properties['tool_input']
    if ($null -eq $tiProp) { exit 0 }
    $cmd = Get-Field $tiProp.Value 'command'
    if (-not $cmd) { exit 0 }

    # 이미 인증서를 신뢰하게 하는 인자가 있으면 안내하지 않는다.
    $alreadyHandled = 'NODE_EXTRA_CA_CERTS|SSL_CERT_FILE|REQUESTS_CA_BUNDLE|ca-bundle\.pem'

    if ($cmd -match 'docker\s+(container\s+)?run\b|docker\s+compose\s+(up|run)\b') {
        if ($cmd -match $alreadyHandled) { exit 0 }
        # 안내 문안은 작은따옴표 here-string 이라 글자 그대로 쓰이고, 번들 폴더만 여기서
        # 넣는다. 문안에 $ 가 있어도 깨지지 않게 보간이 아니라 치환으로 넣는다.
        Write-Context $RunAdvice.Replace('__BUNDLE_DIR__', $bundleDir)
        exit 0
    }
    if ($cmd -match 'docker\s+(image\s+)?build\b|docker\s+compose\s+build\b|docker\s+buildx\s+build\b') {
        Write-Context $BuildAdvice
        exit 0
    }
} catch {
    # 훅이 클로드 코드를 막는 일은 없어야 한다. 조용히 종료한다.
    exit 0
}

exit 0
