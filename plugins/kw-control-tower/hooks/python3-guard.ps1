# 도구를 부르기 전 훅. 이 PC 에서 python3 이 파이썬이 아닐 때만 그 호출을 거부한다.
#
# 마이크로소프트 스토어로 보내는 안내판은 'Python' 이라는 낱말만 찍고 종료 코드 49 로
# 끝난다. 출력이 있어 돌아간 것처럼 보이므로 여러 줄 스크립트가 통째로 안 돌아도 눈에
# 안 띈다. 세션 시작 알림으로는 못 잡는다. 환경이 갖춰졌는지가 아니라 부르는 순간의
# 문제라 그 명령을 세울 곳이 여기다.
#
# 판정 자체는 여기서 안 한다. 링크가 가리키는 실물을 읽으려면 fsutil 을 불러야 하고
# 그것이 이 PC 에서 48밀리초다. 도구를 부를 때마다 물 값이 아니다. /kw-sync 가 한 번
# 재서 상태 파일에 적어 두고 이 훅은 그 한 줄을 읽기만 한다.
#
# 세 곳에서 좁힌다. 판정이 '안내판'일 때만 돌고, 명령의 첫 낱말이 python3 일 때만 잡고,
# python312 나 python3.12 처럼 뒤에 글자가 붙은 이름은 안 잡는다. WSL 과 도커 안에서는
# python3 이 정확한 이름이라 `wsl python3` 과 `docker exec ... python3` 은 지나간다.

Set-StrictMode -Off
$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false) } catch { }

try {
    $userHome = $env:USERPROFILE
    if ([string]::IsNullOrEmpty($userHome)) { exit 0 }

    $statePath = Join-Path (Join-Path $userHome '.claude') 'kw-control-tower.state'
    if (-not (Test-Path -LiteralPath $statePath)) { exit 0 }

    $verdict = $null
    $target  = ''
    foreach ($line in (Get-Content -LiteralPath $statePath -Encoding UTF8)) {
        if ($line -like 'python3=*')       { $verdict = $line.Substring(8) }
        if ($line -like 'python3Target=*') { $target  = $line.Substring(14) }
    }
    if ($verdict -ne 'redirector') { exit 0 }   # 파이썬으로 풀리거나, 없거나, 아직 안 쟀다

    $raw = [Console]::In.ReadToEnd()
    if ([string]::IsNullOrWhiteSpace($raw)) { exit 0 }
    $payload = $raw | ConvertFrom-Json
    $cmd = $payload.tool_input.command
    if ([string]::IsNullOrWhiteSpace($cmd)) { exit 0 }

    # 따옴표 안을 공백으로 지운다. 문자열 안에 든 python3 은 부르는 것이 아니다.
    $sb = New-Object System.Text.StringBuilder
    $q = [char]0
    for ($i = 0; $i -lt $cmd.Length; $i++) {
        $c = $cmd[$i]
        if ($q -ne [char]0) {
            if ($c -eq '\') { $i++; [void]$sb.Append(' '); continue }
            if ($c -eq $q)  { $q = [char]0; continue }
            [void]$sb.Append(' '); continue
        }
        if ($c -eq "'" -or $c -eq '"') { $q = $c; continue }
        if ($c -eq '\') { $i++; [void]$sb.Append(' '); continue }
        [void]$sb.Append($c)
    }

    # 셸 구분자로 갈라 조각마다 첫 낱말을 본다. 앞에 붙은 VAR=값 은 걷어낸다.
    $hit = $false
    foreach ($seg in ([regex]::Split($sb.ToString(), '[\|&;\(\)`\r\n]'))) {
        $s = $seg.TrimStart()
        while ($s -match '^[A-Za-z_][A-Za-z0-9_]*=\S*\s+') { $s = $s -replace '^[A-Za-z_][A-Za-z0-9_]*=\S*\s+', '' }
        if ($s -match '^python3([^A-Za-z0-9\._\-]|$)') { $hit = $true; break }
    }
    if (-not $hit) { exit 0 }

    $reason = "이 PC 에서 python3 은 파이썬이 아닙니다. 마이크로소프트 스토어로 보내는 안내판이라 'Python' 이라는 낱말만 찍고 종료 코드 49 로 끝납니다. 출력이 있어 돌아간 것처럼 보이므로 스크립트가 통째로 안 돌아도 눈에 안 띕니다. python 이나 py -3 으로 부르십시오."
    if ($target) { $reason = "$reason python3 이 가리키는 실물: $target" }

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
    # 가드가 스스로 실패했다고 사용자의 명령을 막지 않는다. 자국만 남긴다.
    try {
        $log = Join-Path (Join-Path $env:USERPROFILE '.claude') 'kw-control-tower.error'
        "$(Get-Date -Format o) python3-guard $($_.Exception.Message)" | Out-File -LiteralPath $log -Encoding UTF8 -Append
    } catch { }
    exit 0
}
