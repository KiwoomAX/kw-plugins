# 도구를 호출하기 전 훅. 금융투자협회 홈페이지(kofia.or.kr 와 그 아래 주소 전체)로 가는 호출을 거부한다.
#
# 자동화 도구와 AI 도구가 이 홈페이지에 반복 접속하면 사내 접속이 차단되어 임직원의 실제 업무에
# 지장이 생긴다(PR #68, 2026-10-22 사용자 결정). 사내 지침의 문구는 권고라서 긴 대화에서는 지켜지지
# 않을 수 있다. 그래서 호출하는 순간에 여기서 멈춘다. 정당한 단건 조회도 같이 멈춘다. 필요하면
# 사용자가 브라우저로 직접 연다.
#
# 거르는 곳이 둘이다. WebFetch 는 주소의 호스트가 kofia.or.kr 이거나 그 아래 주소일 때 멈춘다.
# Bash 와 PowerShell 은 명령 안에 kofia.or.kr 가 있으면 멈춘다. hooks.json 의 if 가 명령에
# kofia.or.kr 가 있을 때만 이 훅을 실행하게 하지만, 판정은 여기서 다시 한다.
# 명령 안의 글자를 보므로 따옴표 안의 주소(예: 커밋 메시지)도 멈춘다. 호출하는지 적어 두는지를
# 가를 수 없고, 접속을 놓치는 쪽이 더 비싸다.

Set-StrictMode -Off
$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false) } catch { }

# kofia.or.kr 앞이 글자·숫자·하이픈이면 다른 이름(예: notkofia.or.kr)이다. 점이면 아래 주소다.
$kofiaPattern = '(?i)(?<![A-Za-z0-9\-])kofia\.or\.kr(?![A-Za-z0-9\-])'

function Test-KofiaHost([string]$Url) {
    $u = $null
    if (-not [System.Uri]::TryCreate($Url, [System.UriKind]::Absolute, [ref]$u)) {
        # 방식이 없는 주소(예: www.kofia.or.kr/a)도 호스트를 읽을 수 있게 http 를 붙여 다시 읽는다.
        if (-not [System.Uri]::TryCreate("http://$Url", [System.UriKind]::Absolute, [ref]$u)) { return ($Url -match $kofiaPattern) }
    }
    $h = $u.DnsSafeHost.ToLowerInvariant()
    return ($h -eq 'kofia.or.kr' -or $h.EndsWith('.kofia.or.kr'))
}

try {
    # 표준입력을 UTF-8 로 직접 읽는다. [Console]::In 은 콘솔 코드페이지(한국어 윈도우는 949)로
    # 해석해 한글이 깨지고, 그러면 JSON 을 읽지 못해 가드가 판정하지 못한다.
    $stdin  = [Console]::OpenStandardInput()
    $reader = New-Object System.IO.StreamReader($stdin, (New-Object System.Text.UTF8Encoding($false)))
    try { $raw = $reader.ReadToEnd() } finally { $reader.Dispose() }
    if ([string]::IsNullOrWhiteSpace($raw)) { exit 0 }
    $payload = $raw | ConvertFrom-Json

    $hit = $false
    $tool = [string]$payload.tool_name
    if ($tool -eq 'WebFetch') {
        $url = [string]$payload.tool_input.url
        if (-not [string]::IsNullOrWhiteSpace($url)) { $hit = Test-KofiaHost $url }
    }
    else {
        $cmd = [string]$payload.tool_input.command
        if (-not [string]::IsNullOrWhiteSpace($cmd)) { $hit = ($cmd -match $kofiaPattern) }
    }
    if (-not $hit) { exit 0 }

    $reason = "금융투자협회 홈페이지(kofia.or.kr 와 그 아래 주소 전체)는 사내 지침으로 접속을 금지했다. 자동화 도구와 AI 도구가 반복 접속하면 사내 접속이 차단되어 임직원의 실제 업무에 지장이 생긴다. 이 호출을 실행하지 말고, 필요한 자료는 사용자가 브라우저에서 직접 내려받거나 사내에 이미 있는 데이터 경로가 있는지 사용자에게 확인하라."
    $out = @{
        hookSpecificOutput = @{
            hookEventName            = 'PreToolUse'
            permissionDecision       = 'deny'
            permissionDecisionReason = $reason
        }
    }
    Write-Output ($out | ConvertTo-Json -Depth 5 -Compress)
    exit 0
}
catch {
    # 가드가 스스로 실패했다고 사용자의 명령을 막지 않는다. 기록만 남긴다.
    try {
        $log = Join-Path (Join-Path $env:USERPROFILE '.claude') 'kw-control-tower.error'
        # 예외 메시지를 그대로 적지 않는다. 5.1 의 ConvertFrom-Json 은 예외 메시지에 입력 전체를
        # 포함해 명령 전문이 기록에 쌓인다. 종류와 앞머리만 남긴다.
        $msg = "$($_.Exception.GetType().Name): $($_.Exception.Message)"
        if ($msg.Length -gt 120) { $msg = $msg.Substring(0, 120) + " …(줄임)" }
        "$(Get-Date -Format o) kofia-guard $msg" | Out-File -LiteralPath $log -Encoding UTF8 -Append
    } catch { }
    exit 0
}
