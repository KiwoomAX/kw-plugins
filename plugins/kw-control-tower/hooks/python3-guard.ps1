# 도구를 호출하기 전 훅. 이 PC 에서 python3 이 파이썬이 아닐 때만 그 호출을 거부한다.
#
# 마이크로소프트 스토어로 보내는 안내판은 'Python' 이라는 낱말만 찍고 종료 코드 49 로
# 끝난다. 출력이 있어 돌아간 것처럼 보이므로 여러 줄 스크립트가 통째로 안 돌아도 눈에
# 안 띈다. 세션 시작 알림으로는 못 잡는다. 환경이 갖춰졌는지가 아니라 호출하는 순간의
# 문제라 그 명령을 세울 곳이 여기다.
#
# 판정은 호출할 때 한다. hooks.json 의 if 가 python3 으로 시작하는 명령에서만 이 훅을 실행하므로
# fsutil 값(이 PC 에서 48밀리초)은 그 명령에만 든다. 맞춤이 적어 둔 값을 읽으면, 맞춤이 불일치한
# 단계만 실행하게 된 뒤로 판정을 적던 단계가 거의 실행되지 않아 판정이 굳는다.
#
# 세 곳에서 좁힌다. 판정이 '안내판'일 때만 돌고, 명령의 첫 낱말이 python3 일 때만 잡고,
# python312 나 python3.12 처럼 뒤에 글자가 붙은 이름은 안 잡는다. WSL 과 도커 안에서는
# python3 이 정확한 이름이라 `wsl python3` 과 `docker exec ... python3` 은 지나간다.

Set-StrictMode -Off
$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false) } catch { }

function Get-Python3Verdict {
    # 검사가 판정을 주입한다. 실제 PC 의 python3 에 기대면 PC 마다 결과가 달라진다.
    if ($env:KWCT_PYTHON3_PROBE) {
        return @{ Kind = $env:KWCT_PYTHON3_PROBE; Target = 'C:\stub\AppInstallerPythonRedirector.exe' }
    }
    $c = Get-Command python3 -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $c) { return @{ Kind = 'absent'; Target = '' } }
    $src = $c.Source
    $item = Get-Item -LiteralPath $src -Force
    if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -eq 0) { return @{ Kind = 'real'; Target = $src } }
    # 재지정 버퍼 안에 링크가 가리키는 실물의 경로가 UTF-16 으로 들어 있다.
    $dump = (& fsutil.exe reparsepoint query $src 2>&1 | Out-String)
    $bytes = New-Object System.Collections.Generic.List[byte]
    foreach ($line in ($dump -split "`n")) {
        if ($line -notmatch '^\s*[0-9a-fA-F]{4}:\s') { continue }
        $body = ($line -replace '^\s*[0-9a-fA-F]{4}:\s+', '')
        $hexPart = $body.Substring(0, [Math]::Min(48, $body.Length))
        foreach ($m in [regex]::Matches($hexPart, '\b[0-9a-fA-F]{2}\b')) { $bytes.Add([Convert]::ToByte($m.Value, 16)) }
    }
    $text = [System.Text.Encoding]::Unicode.GetString($bytes.ToArray())
    $exe = ($text -split "`0" | Where-Object { $_ -match '\.exe$' } | Select-Object -Last 1)
    $target = if ($exe) { $exe.Trim() } else { '' }
    # 경로에 WindowsApps 가 들었는지로 가르지 않는다. 스토어로 깐 진짜 파이썬도 거기 놓인다.
    $kind = if ($text -match 'AppInstallerPythonRedirector') { 'redirector' } else { 'real' }
    return @{ Kind = $kind; Target = $target }
}

try {
    $userHome = $env:USERPROFILE
    if ([string]::IsNullOrEmpty($userHome)) { exit 0 }

    $verdict = Get-Python3Verdict
    if ($verdict.Kind -ne 'redirector') { exit 0 }   # 파이썬으로 풀리거나 없다
    $target = $verdict.Target

    # 표준입력을 UTF-8 로 직접 읽는다. [Console]::In 은 콘솔 코드페이지로 해석하는데
    # 한국어 윈도에서는 949 라, 클로드가 보내는 UTF-8 한글이 깨지고 따옴표 짝이 틀어져
    # JSON 이 무너진다. 그러면 가드가 판정을 못 하고 통과시켜, 한글이 든 명령만 골라
    # 샌다. 2026-09-19 에 코드페이지 949 와 65001 로 각각 돌려 확인했다.
    $stdin  = [Console]::OpenStandardInput()
    $reader = New-Object System.IO.StreamReader($stdin, (New-Object System.Text.UTF8Encoding($false)))
    try { $raw = $reader.ReadToEnd() } finally { $reader.Dispose() }
    if ([string]::IsNullOrWhiteSpace($raw)) { exit 0 }
    $payload = $raw | ConvertFrom-Json
    $cmd = $payload.tool_input.command
    if ([string]::IsNullOrWhiteSpace($cmd)) { exit 0 }

    # 따옴표 안을 공백으로 지운다. 문자열 안에 든 python3 은 호출하는 것이 아니다.
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

    # 셸 구분자로 나눠 조각마다 첫 낱말을 본다. 앞에 붙은 VAR=값 은 걷어낸다.
    $hit = $false
    foreach ($seg in ([regex]::Split($sb.ToString(), '[\|&;\(\)`\r\n]'))) {
        $s = $seg.TrimStart()
        while ($s -match '^[A-Za-z_][A-Za-z0-9_]*=\S*\s+') { $s = $s -replace '^[A-Za-z_][A-Za-z0-9_]*=\S*\s+', '' }
        if ($s -match '^python3([^A-Za-z0-9\._\-]|$)') { $hit = $true; break }
    }
    if (-not $hit) { exit 0 }

    $reason = "이 PC 에서 python3 은 파이썬이 아닙니다. 마이크로소프트 스토어로 보내는 안내판이라 'Python' 이라는 낱말만 찍고 종료 코드 49 로 끝납니다. 출력이 있어 돌아간 것처럼 보이므로 스크립트가 통째로 안 돌아도 눈에 안 띕니다. python 이나 py -3 으로 실행하십시오."
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
        # 예외 메시지를 그대로 적지 않는다. 5.1 의 ConvertFrom-Json 은 예외 메시지에
        # 입력 전체를 포함한다. 그래서 이 자국에 명령 전문과 세션 기록 경로가 통째로
        # 쌓여 있었다. 종류와 앞머리만 남긴다.
        $msg = "$($_.Exception.GetType().Name): $($_.Exception.Message)"
        if ($msg.Length -gt 120) { $msg = $msg.Substring(0, 120) + " …(줄임)" }
        "$(Get-Date -Format o) python3-guard $msg" | Out-File -LiteralPath $log -Encoding UTF8 -Append
    } catch { }
    exit 0
}
