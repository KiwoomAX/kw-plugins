# AX 팀에 배포 등록 요청 메일을 보낸다. 언제 부르는지와 종료 코드를 읽는 법은
# SKILL.md 의 「AX 팀에 등록 요청 보내기」에 있다.
# 종료 코드: 2 입력 · 3 의존성 · 4 렌더링 · 5 아웃룩 호환 검사 · 6 발송 · 7 작업 폴더·첨부 쓰기 · 8 요청한 키가 원본에 없음
param(
    [string]$Subject = '',
    [string]$BodyPath = '',
    [string]$EnvSource = '',
    [string]$EnvKeys = ''
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$OutputEncoding = [Text.Encoding]::UTF8

# 받는 사람은 여기 하나다. 플러그인이 커밋 기준으로 갱신되므로 고치면 모든 PC 에 함께 반영된다.
$Recipient = 'sangeon.jeon@kiwoomam.com'
# 검사가 가짜 렌더러와 가짜 발송기로 바꿔 끼우는 환경변수다.
$Renderer = if ($env:KW_DEVOPS_MAIL_RENDERER) { $env:KW_DEVOPS_MAIL_RENDERER } else { '\\cifs\ai\projects\email_format\.claude\skills\outlook-email' }
$Sender   = if ($env:KW_DEVOPS_MAIL_SENDER)   { $env:KW_DEVOPS_MAIL_SENDER }   else { '\\cifs\ai\projects\email_format\.claude\skills\internal-email\scripts\send-mail.ps1' }

$Utf8NoBom = New-Object Text.UTF8Encoding $false
# 지금 처리 중인 단계의 종료 코드다. 그 단계에서 난 예외는 이 코드로 끝난다.
$script:Stage = 2
$code = 0
$work = $null

try {
    # 1. 인자 검사
    if (-not $Subject.Trim()) { throw '-Subject 가 비었다.' }
    if (-not $BodyPath -or -not (Test-Path -LiteralPath $BodyPath -PathType Leaf)) { throw "-BodyPath 파일이 없다: $BodyPath" }
    $BodyPath = (Resolve-Path -LiteralPath $BodyPath).ProviderPath
    if ($null -eq ([IO.File]::ReadAllText($BodyPath, $Utf8NoBom) | ConvertFrom-Json)) { throw '-BodyPath 가 비었다.' }
    $wantEnv = [bool]$EnvSource
    if ($wantEnv -ne [bool]$EnvKeys) { throw '-EnvSource 와 -EnvKeys 는 함께 줘야 한다.' }
    $keys = @()
    if ($wantEnv) {
        if (-not (Test-Path -LiteralPath $EnvSource -PathType Leaf)) { throw "-EnvSource 파일이 없다: $EnvSource" }
        $keys = @($EnvKeys.Split(',') | ForEach-Object { $_.Trim() } | Where-Object { $_ })
        if ($keys.Count -eq 0) { throw '-EnvKeys 에 키 이름이 없다.' }
        $envText = [IO.File]::ReadAllText((Resolve-Path -LiteralPath $EnvSource).ProviderPath, [Text.Encoding]::UTF8)
    }

    # 2. 의존성 확인
    $script:Stage = 3
    $missing = @()
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) { $missing += 'node' }
    if (-not (Test-Path -LiteralPath $Renderer -PathType Container)) { $missing += "렌더러 폴더 $Renderer" }
    if (-not (Test-Path -LiteralPath $Sender -PathType Leaf)) { $missing += "발송기 $Sender" }
    if ($missing.Count) { throw ('없는 것: ' + ($missing -join ', ')) }

    # 3. 작업 폴더 준비 — 강제 종료로 남은 첨부부터 치운다. 치우지 못해도 발송은 막지 않는다.
    $script:Stage = 7
    try {
        foreach ($d in @(Get-ChildItem -LiteralPath $env:TEMP -Directory -Filter 'kwdevops-mail-*' |
                         Where-Object { $_.LastWriteTime -lt (Get-Date).AddHours(-1) })) {
            try { Remove-Item -LiteralPath $d.FullName -Recurse -Force }
            catch { Write-Host "[경고] 지난 작업 폴더를 지우지 못했다: $($d.FullName)" }
        }
    } catch { Write-Host "[경고] 지난 작업 폴더를 살펴보지 못했다: $($_.Exception.Message)" }
    $work = Join-Path $env:TEMP ('kwdevops-mail-' + [guid]::NewGuid().ToString('N'))
    $null = New-Item -ItemType Directory -Path $work
    Copy-Item -LiteralPath $Renderer -Destination (Join-Path $work 'renderer') -Recurse
    $senderCopy = Join-Path $work 'send-mail.ps1'
    Copy-Item -LiteralPath $Sender -Destination $senderCopy

    # 4. 첨부 만들기 — 값은 파일에만 쓰고 화면에는 키 이름만 찍는다.
    $attach = $null
    if ($wantEnv) {
        $script:Stage = 2
        $found = @{}   # 대소문자를 가리지 않는 표다. 같은 키는 뒤 줄이 덮는다.
        foreach ($line in ($envText -split "`n")) {
            $line = $line.TrimEnd("`r")
            if ($line -match '^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
                $found[$Matches[1]] = @{ Name = $Matches[1]; Value = $Matches[2] }
            }
        }
        $lines = @()
        $absent = @()
        foreach ($k in $keys) {
            $e = $found[$k]
            if (-not $e -or $e.Value -eq '' -or $e.Value -eq '""' -or $e.Value -eq "''") { $absent += $k; continue }
            $v = $e.Value
            $q = $v.Substring(0, 1)
            if (($q -eq '"' -or $q -eq "'") -and $v.IndexOf($q, 1) -lt 0) {
                throw "따옴표가 같은 줄에서 닫히지 않는다: $($e.Name) — 여러 줄 값은 지원하지 않는다."
            }
            $lines += "$($e.Name)=$v"
        }
        if ($absent.Count) { Write-Host ('[첨부 제외] 원본에 없거나 값이 빈 키: ' + ($absent -join ', ')) }
        if ($lines.Count -eq 0) { $script:Stage = 8; throw '원본 .env 에 요청한 키가 하나도 없다. 보내지 않았다.' }
        $script:Stage = 7
        $attach = Join-Path $work '.env'
        [IO.File]::WriteAllText($attach, (($lines -join "`n") + "`n"), $Utf8NoBom)
    }

    # 5. 렌더링과 아웃룩 호환 검사
    $script:Stage = 4
    # 등록 요청 메일은 고딕 하나로 쓴다. 공유 렌더러의 명조(SERIF)를 작업 폴더 복사본에서만 고딕(SANS)으로 바꾼다.
    $tokens = Join-Path $work 'renderer\lib\tokens.js'
    $tokensText = [IO.File]::ReadAllText($tokens, $Utf8NoBom)
    $serifLine = [regex]'(?m)^const SERIF = .*$'
    if (-not $serifLine.IsMatch($tokensText)) { throw '렌더러 lib/tokens.js 에서 SERIF 줄을 찾지 못했다. 공유 렌더러의 모양이 바뀌었는지 확인하라.' }
    [IO.File]::WriteAllText($tokens, $serifLine.Replace($tokensText, 'const SERIF = SANS;', 1), $Utf8NoBom)
    $html = Join-Path $work 'body.html'
    & node (Join-Path $work 'renderer\formats\plain.js') $BodyPath $html
    if ($LASTEXITCODE -ne 0) { throw "렌더러가 종료 코드 $LASTEXITCODE 로 끝났다." }
    if (-not (Test-Path -LiteralPath $html) -or (Get-Item -LiteralPath $html).Length -eq 0) { throw '렌더링한 HTML 이 비었다.' }
    $script:Stage = 5
    & node (Join-Path $work 'renderer\scripts\verify-outlook.js') $html
    if ($LASTEXITCODE -ne 0) { throw '아웃룩 호환 검사를 통과하지 못했다. 보내지 않았다.' }

    # 6. 발송 — 보내는 주소는 발송기가 아웃룩 프로필에서 가져온다.
    $script:Stage = 6
    $send = @{ To = @($Recipient); Subject = $Subject; HtmlPath = $html }
    if ($attach) { $send.Attach = @($attach) }
    & $senderCopy @send
    Write-Host "발송 성공: $Recipient"
    $code = 0
} catch {
    $code = $script:Stage
    Write-Host "[request-ax] 실패 (종료 코드 $code): $($_.Exception.Message)"
} finally {
    # 메일이 이미 나간 뒤라 삭제 실패는 종료 코드를 바꾸지 않는다. 실패로 알리면 같은 요청이 다시 나간다.
    if ($work -and (Test-Path -LiteralPath $work)) {
        try { Remove-Item -LiteralPath $work -Recurse -Force }
        catch { Write-Host "[경고] 작업 폴더를 지우지 못했다. 첨부가 남았을 수 있다: $work" }
    }
}
exit $code
