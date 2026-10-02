# 세션 시작 알림. 이 PC가 manifest.json 과 불일치한 곳을 말하기만 한다.
#
# 계약 다섯을 지킨다. 세션 시작에 도는 훅은 이것 하나이고, 감지가 외부 프로세스를
# 새로 호출하려면 개발할 때 사용자에게 먼저 묻고, 네트워크에는 우리 배포처의 원격
# 커밋을 읽는 요청만 내보내고, 읽는 파일을 새로 늘리려면 개발할 때 사용자에게 먼저
# 묻고, 몸통이 200밀리초를 넘으면 그 값을 상태 파일에 남긴다. 네트워크 시간은 몸통에
# 안 센다.
#
# 승인된 외부 프로세스는 원격 커밋을 읽는 curl.exe 하나다. 2026-09-25 에 사용자가
# 승인했다. 묻는 시점은 훅이 돌 때가 아니라 개발할 때다.
#
# 아무것도 고치지 않는다. 세션을 막지 않는다. 스스로 실패하면 조용히 물러난다.
# PowerShell 7 을 전제한다. 설치기가 7 을 winget 으로 깔고, 그래도 없으면 아무것도
# 안 깔고 끝내므로, 7 이 없는 PC 에는 이 훅도 없다.
#
# 5.1 은 매 세션 204밀리초를 아꼈지만(357 대 561) 우회를 열한 군데 만들었다.
# 한국어를 ANSI 로 읽고, JSON 의 한글을 유니코드 이스케이프로 바꾸고, null 조건
# 연산자가 없다. 그중 하나는 문서와 코드를 대조하는 검사 넷을 한 번도 통과하지
# 못하게 하고 있었고 아무도 몰랐다. 2026-09-19 에 사용자가 7 로 정했다.

Set-StrictMode -Off
$ErrorActionPreference = 'Stop'

# BOM 을 붙이지 않는다. 7 은 BOM 없이도 UTF-8 로 읽는다. 붙이지 않는 편이 낫기까지
# 한데, BOM 이 없으면 5.1 로 돌렸을 때 한글이 조용히 깨지는 것이 아니라 파싱 오류로
# 죽어서 잘못 호출한 것이 그 줄에서 드러난다. 나가는 쪽 인코딩은 그대로 맞춘다.
# 콘솔 코드페이지는 7 에서도 윈도 기본을 따르는 때가 있기 때문이다.
try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false) } catch { }

$script:Budget = @{ Files = 0; Registry = 0 }

function Get-CheapHash {
    # MD5 를 직접 호출한다. 이 PC 에서 8ms 이고 Get-FileHash 명령은 72ms 다. 아홉 배다.
    # 파일이 바뀌었는지만 가리므로 암호 강도는 필요 없다.
    # .NET 의 문자열 해시는 프로세스마다 시드가 달라 못 쓴다.
    param([string]$Path)
    $md5 = [System.Security.Cryptography.MD5]::Create()
    try {
        $bytes = [System.IO.File]::ReadAllBytes($Path)
        return [System.BitConverter]::ToString($md5.ComputeHash($bytes)).Replace('-', '')
    } finally { $md5.Dispose() }
}

function Get-StuckPrint {
    # 실패한 원인이 같은지를 목록 파일 둘의 내용과 날짜와 단계 번호로 가른다. 목록이 바뀌거나
    # 날이 바뀌면 다시 시도한다. 알림 훅에도 같은 함수가 있다. 글자 그대로 같아야 한다.
    param([string]$Root, [int]$Step)
    $md5 = [System.Security.Cryptography.MD5]::Create()
    try {
        $bytes = New-Object System.Collections.Generic.List[byte]
        foreach ($f in @('manifest.json', 'requirements.txt')) {
            $p = Join-Path $Root $f
            if (Test-Path -LiteralPath $p) { $bytes.AddRange([System.IO.File]::ReadAllBytes($p)) }
        }
        $bytes.AddRange([System.Text.Encoding]::UTF8.GetBytes("step$Step " + (Get-Date -Format 'yyyy-MM-dd')))
        return [System.BitConverter]::ToString($md5.ComputeHash($bytes.ToArray())).Replace('-', '')
    } finally { $md5.Dispose() }
}

function Read-Json {
    # 없는 것과 못 읽는 것을 구분한다. 없으면 $null 이고 그것은 정상일 수 있다.
    # 못 읽으면 던진다. 사용자에게는 그래도 조용히 물러나지만, 삼키면 망가진
    # 설정을 가진 PC 와 아무 문제 없는 PC 가 구별되지 않는다. 던져서 catch 가
    # 자국을 남기게 한다.
    param([string]$Path)
    $script:Budget.Files++
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    try { return (Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json) }
    catch { throw "JSON 으로 안 읽힙니다: $Path" }
}

function Get-Prop {
    # PSCustomObject 에서 이름으로 값을 꺼낸다. 없는 이름이면 $null 이다.
    #
    # 7 의 null 조건 연산자로 한 줄로 줄이려다 되돌렸다. PowerShell 의 ?. 은 C# 과 달리
    # 사슬 전체를 건너뛰지 않고 바로 뒤의 멤버 접근 하나만 막는다. $Object?.PSObject 로
    # 쓰면 $Object 가 $null 일 때 그다음 .Properties[$Name] 이 그대로 돌아 "null 배열로
    # 인덱싱할 수 없습니다" 로 던진다. 검사가 그것을 잡았다.
    param($Object, [string]$Name)
    if ($null -eq $Object) { return $null }
    $p = $Object.PSObject.Properties[$Name]
    if ($null -eq $p) { return $null }
    return $p.Value
}

function Test-Marketplace {
    # 배포처가 두 파일 가운데 어디에 등록되어 있는지 센다.
    param($Settings, $Known, [string]$Name)
    $a = Get-Prop (Get-Prop $Settings 'extraKnownMarketplaces') $Name
    $b = Get-Prop (Get-Prop $Known   'marketplaces')            $Name
    if ($null -eq $b) { $b = Get-Prop $Known $Name }
    return @{ InSettings = ($null -ne $a); InKnown = ($null -ne $b); Settings = $a; Known = $b }
}

# 사내 문안 블록을 조립한다. 맞춤(sync.ps1)에도 같은 함수가 있다. 둘이 다르게
# 조립하면 맞춤이 쓴 블록을 훅이 다르다고 알린다.
function Get-AxBlock([string]$claudeMd) {
    $files = @('claude-md-ko.md')
    if ($claudeMd -notmatch '(?m)^#\s*BEGIN disciplined-coder\b') {
        $files += @('claude-md-ko-principles.md', 'korean-banned-words.md')
    }
    $lines = @('# BEGIN AX 설치 (자동 생성 블록 — 직접 고치지 마십시오)') + @($files | ForEach-Object { "@kw-ax/$_" }) + @('# END AX 설치')
    return $lines -join "`n"
}

# kw-ax 로 복사하고 대조할 템플릿이다. 블록이 싣는 파일과, 원칙이 근거로 가리키는 사본이다.
# 블록이 안 싣는 파일까지 대조하면 싣지도 않는 사본 하나 때문에 맞춤이 실행된다(2026-09-30 이 PC).
# 알림 훅에도 같은 함수가 있다. 둘이 다르면 맞춤이 복사한 것을 훅이 다르다고 알린다.
function Get-AxCopies([string]$claudeMd) {
    $files = @('claude-md-ko.md')
    if ($claudeMd -notmatch '(?m)^#\s*BEGIN disciplined-coder\b') {
        $files += @('claude-md-ko-principles.md', 'korean-banned-words.md', 'domain-korean_subset.md')
    }
    return $files
}

function Read-KwState([string]$Path) {
    # 상태 파일을 한 번만 읽는다. 질문마다 따로 열던 때에는 같은 파일을 세 번 열었다.
    $s = @{}
    $script:Budget.Files++
    if (Test-Path -LiteralPath $Path) {
        foreach ($line in (Get-Content -LiteralPath $Path -Encoding UTF8)) {
            $i = $line.IndexOf('=')
            if ($i -gt 0) { $s[$line.Substring(0, $i)] = $line.Substring($i + 1) }
        }
    }
    return $s
}

function Read-GitIdentity([string]$Path) {
    # ~/.gitconfig 에서 커밋 명의와, 그 메일을 사용자가 승인한 기록을 읽는다. git 을 실행하지
    # 않고 파일을 직접 읽는다. 감지가 외부 프로세스를 늘리지 않는다는 계약 때문이다.
    # git 처럼 섹션과 키의 대소문자를 가리지 않고, 따옴표와 줄 끝 주석을 값에서 뺀다.
    # include 로 다른 파일에 둔 값은 못 읽는다. 그런 PC 는 명의 스크립트가 승인한 값을 이
    # 파일에 다시 적으므로 한 번 확인하면 안내가 멈춘다.
    $id = @{ Name = $null; Email = $null; Approved = $null }
    $script:Budget.Files++
    if (-not (Test-Path -LiteralPath $Path)) { return $id }
    $section = ''
    foreach ($line in (Get-Content -LiteralPath $Path -Encoding UTF8)) {
        $t = $line.Trim()
        if ($t -match '^\[\s*([^\]\s"]+)') { $section = $Matches[1].ToLowerInvariant(); continue }
        if ($t -notmatch '^([A-Za-z][\w-]*)\s*=\s*(.*)$') { continue }
        $key = "$section.$($Matches[1].ToLowerInvariant())"
        $val = ($Matches[2] -replace '\s+[#;].*$', '').Trim().Trim('"')
        switch ($key) {
            'user.name'                      { $id.Name = $val }
            'user.email'                     { $id.Email = $val }
            'kw-control-tower.approvedemail' { $id.Approved = $val }
        }
    }
    return $id
}

function Get-MarketplaceHead {
    # 배포처 사본이 받아 둔 버전을 읽는다. 네트워크에 안 나간다. 디스크에 이미 있다.
    # git 사본은 HEAD 가 가리키는 ref 파일에 커밋이 있고, git 이 아닌 배포처는
    # .gcs-sha 파일 하나에 적어 둔다. 이 PC 에 둘 다 있어 둘 다 읽는다.
    param([string]$Dir)
    $g = Join-Path $Dir '.git'
    $h = Join-Path $g 'HEAD'
    $script:Budget.Files++
    if (Test-Path -LiteralPath $h) {
        $line = (Get-Content -LiteralPath $h -Raw -Encoding UTF8).Trim()
        if ($line.StartsWith('ref: ')) {
            $refFile = Join-Path $g ($line.Substring(5))
            $script:Budget.Files++
            if (Test-Path -LiteralPath $refFile) {
                return (Get-Content -LiteralPath $refFile -Raw -Encoding UTF8).Trim()
            }
            return $null
        }
        return $line
    }
    $gcs = Join-Path $Dir '.gcs-sha'
    $script:Budget.Files++
    if (Test-Path -LiteralPath $gcs) { return (Get-Content -LiteralPath $gcs -Raw -Encoding UTF8).Trim() }
    return $null
}

function Get-RemoteUrl {
    # 배포처 등록의 source 에서 원격 주소를 만든다. 원격을 읽을 수 없는 형식이면 $null 이다.
    # github 이면 저장소 이름으로 만들고, https 주소면 그대로 쓴다. 브랜치나 태그를 지정한
    # 배포처도 $null 이다. 원격 기본 브랜치와 비교하면 매 세션 다르다고 나와 맞춤이 되풀이된다.
    param($Source)
    if ($null -eq $Source -or (Get-Prop $Source 'ref')) { return $null }
    $repo = Get-Prop $Source 'repo'
    if ((Get-Prop $Source 'source') -eq 'github' -and $repo) { return "https://github.com/$repo.git" }
    $url = Get-Prop $Source 'url'
    if ($url -and $url.StartsWith('https://')) { return $url }
    return $null
}

function Get-RemoteHead {
    # 원격 저장소의 기본 브랜치 커밋을 읽는다. 못 읽으면 $null 이다.
    #
    # REST API 가 아니라 git 이 쓰는 info/refs 를 읽는다. REST 는 로그인 없이 IP 하나에
    # 시간당 60회라서, 외부 IP 하나를 나눠 쓰는 사내 PC 들이 금방 다 쓴다. info/refs 는
    # 그 한도가 없고 2KB 다. git ls-remote 는 같은 값을 읽지만 530~650밀리초 걸린다.
    #
    # curl.exe 로 읽는다. 감지가 외부 프로세스를 호출하지 않는다는 계약의 유일한 예외다.
    # 2026-09-25 에 새 pwsh 프로세스에서 다섯 번씩 재니 Invoke-WebRequest 가 평균 459ms,
    # curl.exe 가 377ms 였다. 훅은 매번 새 프로세스라 Invoke-WebRequest 의 첫 호출 준비
    # 값이 프로세스 하나 띄우는 값보다 컸다. disciplined-coder 도 같은 명령을 쓴다.
    # 'curl' 로 적으면 Invoke-WebRequest 의 별칭이 되므로 반드시 curl.exe 로 적는다.
    # 둘 다 Schannel 이라 사내 SSL 검사 장비 아래 성공 조건이 같다. 다른 점은 curl.exe 가
    # 시스템 프록시를 안 읽는 것이고, 명시적 프록시만 있는 망에서는 실패해 사본과 비교한다.
    #
    # 응답의 첫 ref 줄은 '<길이 4자><sha> HEAD\0<기능 목록>' 이다. ' HEAD' 바로 앞의
    # 40자를 잡으므로 길이 접두사가 sha 에 섞이지 않는다. 비공개 저장소의 401 은 -f 가
    # 실패로 돌려주고 그때도 $null 이다.
    param([string]$Url)
    try {
        $text = (& curl.exe -s -f -m 2 "$Url/info/refs?service=git-upload-pack" 2>$null) -join "`n"
        if ($LASTEXITCODE -ne 0) { return $null }
        $m = [regex]::Match($text, '([0-9a-f]{40}) HEAD')
        if ($m.Success) { return $m.Groups[1].Value }
    } catch { }
    return $null
}

$sw = [System.Diagnostics.Stopwatch]::StartNew()
$notes = New-Object System.Collections.ArrayList   # 맞춤이 고칠 수 있는 것
$noteSteps = New-Object System.Collections.ArrayList   # $notes 와 같은 순서로 맞춤 단계 번호
function Add-Note([int[]]$Step, [string]$Text) {
    [void]$notes.Add($Text)
    [void]$noteSteps.Add($Step)
}
$asks  = New-Object System.Collections.ArrayList   # 사용자가 직접 해야 하는 것
$askHints = New-Object System.Collections.ArrayList   # $asks 와 같은 순서로 클로드에게만 주는 지시
function Add-Ask([string]$Text, [string]$Hint) {
    [void]$asks.Add($Text)
    [void]$askHints.Add($Hint)
}
$stuckSay = New-Object System.Collections.ArrayList   # 같은 원격 커밋으로 실패해 다시 안 한 것
$remoteOf = @{}          # 배포처 이름 → 원격 커밋. 맞춤에 넘긴다
$script:NetMs = 0        # 몸통에 안 세는 네트워크 시간

try {
    $userHome = $env:USERPROFILE
    if ([string]::IsNullOrEmpty($userHome)) { exit 0 }   # 윈도가 아니면 물러난다
    $root = $env:CLAUDE_PLUGIN_ROOT
    if ([string]::IsNullOrEmpty($root)) { exit 0 }

    $cfg     = Join-Path $userHome '.claude'
    $plugins = Join-Path $cfg 'plugins'

    $manifest = Read-Json (Join-Path $root 'manifest.json')
    if ($null -eq $manifest) { exit 0 }   # 목록을 못 읽으면 아무 말도 안 한다

    # 읽히는 것과 형식이 맞는 것은 다르다. 칸이 빠진 목록으로 판정하면 그 질문만
    # 조용히 사라져, 불일치한 PC 를 정상으로 본다. 맞춤은 이때 멈추고 말하지만 이
    # 훅은 세션을 어지럽히지 않는 쪽이라 자국만 남기고 물러난다.
    foreach ($k in @('marketplaces', 'required', 'suggested', 'retiredPlugins',
                     'retiredMarketplaces', 'retiredSkills', 'retiredHooks')) {
        if ($null -eq $manifest.PSObject.Properties[$k]) { throw "목록 파일에 '$k' 칸이 없습니다." }
    }

    $settings  = Read-Json (Join-Path $cfg     'settings.json')
    $installed = Read-Json (Join-Path $plugins 'installed_plugins.json')
    $known     = Read-Json (Join-Path $plugins 'known_marketplaces.json')
    $kwState = Read-KwState (Join-Path $cfg 'kw-control-tower.state')

    $enabled     = Get-Prop $settings  'enabledPlugins'
    $installedOf = Get-Prop $installed 'plugins'

    # --- 질문 1과 2. 필수 플러그인이 깔려 있나, 켜져 있나 -------------------
    # 두 질문이 다른 파일에 답이 있고 고치는 명령도 다르다. install 은 사용자가
    # 꺼 둔 것을 true 로 덮으므로 깔린 것에는 절대 안 쓴다.
    $missing  = New-Object System.Collections.ArrayList
    $disabled = New-Object System.Collections.ArrayList

    foreach ($id in @($manifest.required)) {
        $entry = Get-Prop $installedOf $id
        $onDisk = $false
        if ($null -ne $entry) {
            foreach ($scope in @($entry)) {
                $p = Get-Prop $scope 'installPath'
                if ($p -and (Test-Path -LiteralPath $p)) { $onDisk = $true }
            }
        }
        if (-not $onDisk) { [void]$missing.Add($id); continue }

        $state = Get-Prop $enabled $id
        if ($state -ne $true) { [void]$disabled.Add($id) }
    }

    if ($missing.Count -gt 0) {
        Add-Note 2 "필수 플러그인이 안 깔려 있습니다: $($missing -join ', ')"
    }
    if ($disabled.Count -gt 0) {
        Add-Note 2 "필수 플러그인이 꺼져 있습니다: $($disabled -join ', ')"
    }

    # --- 질문 3. 정리하기로 한 플러그인이 남았나 ---------------------------
    $staleP = New-Object System.Collections.ArrayList
    foreach ($p in @($manifest.retiredPlugins)) {
        $id = Get-Prop $p 'id'
        if (-not $id) { continue }
        if ((Get-Prop $installedOf $id) -or ($null -ne (Get-Prop $enabled $id))) { [void]$staleP.Add($id) }
    }
    if ($staleP.Count -gt 0) {
        Add-Note 3 "더 안 쓰는 플러그인이 남아 있습니다: $($staleP -join ', ')"
    }

    # --- 질문 4. 정리하기로 한 배포처가 남았나 -----------------------------
    $staleM = New-Object System.Collections.ArrayList
    foreach ($mk in @($manifest.retiredMarketplaces)) {
        $name = Get-Prop $mk 'name'
        if (-not $name) { continue }
        $m = Test-Marketplace $settings $known $name
        if ($m.InSettings -or $m.InKnown) { [void]$staleM.Add($name) }
    }
    if ($staleM.Count -gt 0) {
        Add-Note 3 "더 안 쓰는 배포처가 남아 있습니다: $($staleM -join ', ')"
    }

    # --- 질문 5. 우리 배포처의 자동 갱신이 두 곳 다 켜져 있나 ---------------
    # 두 파일은 서로 값을 주고받지 않는다. 그래서 두 곳 다 본다.
    $offAuto = New-Object System.Collections.ArrayList
    foreach ($mk in @($manifest.marketplaces)) {
        if ((Get-Prop $mk 'ours') -ne $true) { continue }   # 남의 배포처는 안 측정한다
        $name = Get-Prop $mk 'name'
        $m = Test-Marketplace $settings $known $name
        if (-not ($m.InSettings -or $m.InKnown)) { [void]$offAuto.Add("$name (등록 없음)"); continue }
        $a = Get-Prop $m.Settings 'autoUpdate'
        $b = Get-Prop $m.Known    'autoUpdate'
        if (($a -ne $true) -or ($b -ne $true)) { [void]$offAuto.Add($name) }
    }
    if ($offAuto.Count -gt 0) {
        Add-Note 1 "자동 갱신이 꺼져 있습니다: $($offAuto -join ', ')"
    }

    # --- 질문 6. 파이썬 라이브러리 목록이 바뀌었나 -------------------------
    # 예산 안에서 이 PC 를 직접 못 읽는 것이 이 하나뿐이라 해시로 측정한다.
    # 재는 것은 파일이다. JSON 의 하위 트리를 해시하면 프로세스마다 값이 달라진다.
    $reqFile   = Join-Path $root 'requirements.txt'
    $script:Budget.Files++
    if (Test-Path -LiteralPath $reqFile) {
        $now = Get-CheapHash $reqFile
        $was = $kwState['requirements']
        if ($now -ne $was) {
            Add-Note 4 '파이썬 라이브러리 목록이 이 PC에 맞춰진 것과 다릅니다.'
        }
    }

    # --- 질문 7. PYTHONUTF8 이 설정해졌나 ------------------------------------
    # 사용자가 일부러 0 으로 둔 것은 그대로 두는 것이 맞으므로 그때는 말하지 않는다.
    $script:Budget.Registry++
    $utf8 = [Environment]::GetEnvironmentVariable('PYTHONUTF8', 'User')
    if ($null -eq $utf8) {
        Add-Note 5 'PYTHONUTF8 이 설정되어 있지 않습니다. 한글이 깨질 수 있습니다.'
    }

    # --- 질문 8. CLAUDE.md 의 사내 문안이 템플릿과 같나 ---------------------
    # 이것이 감지 표에 있는데 훅에 없었다. 사내 문안을 손으로 고쳐도 아무도 모르는
    # 상태였다. 버전이나 해시가 아니라 글자를 견준다. 줄바꿈은 두 파일이 서로 다를
    # 수 있고 그것은 다름이 아니므로 맞춘 뒤에 견준다.
    $tpl = Join-Path $root 'templates\claude-md-ko.md'
    $mem = Join-Path $cfg 'CLAUDE.md'
    $script:Budget.Files += 2
    $u8 = New-Object System.Text.UTF8Encoding($false)
    # 블록은 kw-ax 의 사본을 @import 로 싣는다. 사본이 없으면 @import 가 알리지 않고
    # 아무것도 싣지 않으며, 낡으면 옛 문안이 실린다. CLAUDE.md 만 보아서는 둘 다 안 드러난다.
    # 맞춤이 Get-AxCopies 목록을 복사하므로 여기서도 같은 목록을 대조한다.
    $memText = if (Test-Path -LiteralPath $mem) { [System.IO.File]::ReadAllText($mem, $u8) } else { '' }
    if (Test-Path -LiteralPath $tpl) {
        $stale = New-Object System.Collections.ArrayList
        $tplDir = Split-Path -Parent $tpl
        foreach ($name in @(Get-AxCopies $memText)) {
            $src  = Join-Path $tplDir $name
            $copy = Join-Path (Join-Path $cfg 'kw-ax') $name
            $script:Budget.Files += 2
            if (-not (Test-Path -LiteralPath $src)) { continue }
            if (-not (Test-Path -LiteralPath $copy) -or
                ([System.IO.File]::ReadAllText($copy, $u8) -ne [System.IO.File]::ReadAllText($src, $u8))) {
                [void]$stale.Add($name)
            }
        }
        if ($stale.Count -gt 0) {
            Add-Note 6 "CLAUDE.md 가 싣는 사내 문안 사본이 없거나 배포된 것과 다릅니다: $($stale -join ', ')"
        }
    }
    if ((Test-Path -LiteralPath $tpl) -and (Test-Path -LiteralPath $mem)) {
        $now   = $memText
        $block = Get-AxBlock $now
        $re    = '(?ms)^#\s*BEGIN AX\b.*?^#\s*END AX[^\r\n]*'
        $found = [regex]::Match($now, $re)
        $norm  = { param($t) ($t -replace "`r`n", "`n").Trim() }
        $howMany = @([regex]::Matches($now, $re)).Count
        if (-not $found.Success) {
            Add-Note 6 'CLAUDE.md 에 사내 문안 블록이 없습니다.'
        } elseif ($howMany -gt 1) {
            # 개수를 따로 세는 것은 위 정규식이 첫 블록만 잡기 때문이다. 개수를 안
            # 보면 같은 블록이 둘인 파일이 "이미 같다" 로 읽혀 조용히 남는다.
            Add-Note 6 "CLAUDE.md 에 사내 문안 블록이 $howMany 개 있습니다."
        } elseif ((& $norm $found.Value) -ne (& $norm $block)) {
            Add-Note 6 'CLAUDE.md 의 사내 문안 블록이 배포된 것과 다릅니다.'
        }
    }

    # --- 질문 9와 10. 정리하기로 한 스킬과 훅이 남았나 ---------------------
    $staleS = New-Object System.Collections.ArrayList
    foreach ($s in @($manifest.retiredSkills)) {
        $name = Get-Prop $s 'name'
        if (-not $name) { continue }
        if (Test-Path -LiteralPath (Join-Path (Join-Path $cfg 'skills') $name)) { [void]$staleS.Add($name) }
    }
    if ($staleS.Count -gt 0) {
        Add-Note 7 "더 안 쓰는 스킬 사본이 남아 있습니다: $($staleS -join ', ')"
    }

    # 훅 연결은 파일 이름이 아니라 경로로 구분한다. 이 플러그인이 거는 훅의 파일 이름이
    # 옛것과 같아서, 이름만 보면 자기 연결을 남의 것으로 센다.
    $staleH = New-Object System.Collections.ArrayList
    $hookBlob = ''
    try { $hookBlob = (Get-Prop $settings 'hooks' | ConvertTo-Json -Depth 20 -Compress) } catch { $hookBlob = '' }
    foreach ($h in @($manifest.retiredHooks)) {
        $file = Get-Prop $h 'file'
        $pathBit = Get-Prop $h 'pathContains'
        if ($file -and $pathBit -and $hookBlob -and $hookBlob.Contains($file) -and $hookBlob.Contains($pathBit)) {
            [void]$staleH.Add($file)
        }
    }
    if ($staleH.Count -gt 0) {
        Add-Note 7 "더 안 쓰는 훅 연결이 남아 있습니다: $($staleH -join ', ')"
    }

    # --- 질문 11. 우리 배포처에서 온 설치본이 사본보다 뒤처졌나 --------------
    # 자동 갱신이 사본을 새 커밋까지 받아 놓고도 설치본을 안 옮기는 것을 2026-09-19 에
    # 이 PC 에서 두 건 확인했다. 한쪽은 57 커밋 뒤처져 있었고 자동 갱신은 켜져 있었다.
    # 두 값이 다 디스크에 있으므로 네트워크에 안 나가고 비교할 수 있다.
    #
    # 남의 배포처는 안 본다. 회사가 필수로 정한 것만 최신이어야 하고, 남의 것을 언제
    # 올릴지는 사용자가 정한다.
    #
    # 2026-09-25 에 견주는 대상을 사본에서 원격으로 바꿨다. 사본은 자동 갱신이 받아 와야
    # 움직이는데, 자동 갱신은 세션 시작 몇 분 뒤에 도착하거나 아예 안 온다. 사본과만
    # 견주면 원격에 새 커밋이 있어도 설치본과 사본이 같아 보여 맞춤이 안 돈다. 이 PC 에서
    # 그렇게 설치본이 PR 하나만큼 뒤처진 채로 세션이 열렸다. 원격을 못 읽으면 사본과 견준다.
    #
    # 배포처가 브랜치나 태그를 지정했으면 원격 기본 브랜치와 견주면 안 된다. 매 세션
    # 다르다고 나와 맞춤이 되풀이된다. 그때는 사본과 견준다.
    #
    # 맞춤이 지난번에 같은 원격 커밋으로 옮기지 못했으면 다시 호출하지 않는다. 매 세션
    # 일 분씩 같은 실패를 되풀이하게 된다. 원격에 새 커밋이 생기면 다시 시도한다.
    $behind = New-Object System.Collections.ArrayList
    $cloneLate = $false
    foreach ($mk in @($manifest.marketplaces)) {
        if ((Get-Prop $mk 'ours') -ne $true) { continue }
        $mkName = Get-Prop $mk 'name'
        if (-not $mkName -or $null -eq $installedOf) { continue }
        $head = Get-MarketplaceHead (Join-Path (Join-Path $plugins 'marketplaces') $mkName)
        $m = Test-Marketplace $settings $known $mkName
        $src = Get-Prop $m.Known 'source'
        if ($null -eq $src) { $src = Get-Prop $m.Settings 'source' }
        $url = Get-RemoteUrl $src
        $remote = $null
        if ($url) {
            $sw.Stop()
            $net = [System.Diagnostics.Stopwatch]::StartNew()
            $remote = Get-RemoteHead $url
            $script:NetMs += $net.ElapsedMilliseconds
            $sw.Start()
        }
        $target = if ($remote) { $remote } else { $head }
        if (-not $target) { continue }
        if ($remote) { $remoteOf[$mkName] = $remote }
        # 사본이 원격보다 뒤일 때만 받아오기(단계 1)가 필요하다.
        if ($remote -and $head -and -not $remote.StartsWith($head) -and -not $head.StartsWith($remote)) { $cloneLate = $true }

        $late = New-Object System.Collections.ArrayList
        foreach ($pluginId in @($installedOf.PSObject.Properties.Name)) {
            if (-not $pluginId.EndsWith("@$mkName")) { continue }
            foreach ($scope in @(Get-Prop $installedOf $pluginId)) {
                $sha = Get-Prop $scope 'gitCommitSha'
                if (-not $sha) { continue }
                if (-not $target.StartsWith($sha) -and -not $sha.StartsWith($target)) {
                    [void]$late.Add(@{ Id = $pluginId; Sha = $sha })
                    break
                }
            }
        }
        if ($late.Count -eq 0) { continue }
        if ($remote -and $kwState["stuck-$mkName"] -eq $remote) {
            [void]$stuckSay.Add('  이미 갱신에 실패해 다시 시도하지 않았습니다. 원격에 새 커밋이 생기면 다시 시도합니다.')
            foreach ($l in $late) { [void]$stuckSay.Add("  - $($l.Id) : $($l.Sha.Substring(0, 7)) → $($remote.Substring(0, 7))") }
            [void]$stuckSay.Add('  지금 옮기려면 아래를 실행해 주십시오.')
            [void]$stuckSay.Add("      claude plugin marketplace update $mkName")
            foreach ($l in $late) { [void]$stuckSay.Add("      claude plugin update $($l.Id)") }
        } else {
            foreach ($l in $late) { [void]$behind.Add($l.Id) }
        }
    }
    if ($behind.Count -gt 0) {
        Add-Note $(if ($cloneLate) { @(1, 2) } else { @(2) }) "설치본이 원격보다 뒤처져 있습니다: $(($behind | Select-Object -Unique) -join ', ')"
    }

    # --- 질문 12. 배포처 사본을 오래 받아오지 않았나 ------------------------
    # 사본 자체가 낡았는지는 네트워크에 나가야 확실히 안다. 감지는 안 나가므로 대신
    # 마지막으로 받아온 시각을 본다. 맞춤이 받아올 때마다 그 시각을 적으므로, 저장소에
    # 새 커밋이 없어 사본이 안 움직이는 때에도 이 질문이 되풀이되지 않는다.
    $refreshed = $kwState['refreshed']
    $stale = $true
    if ($refreshed) {
        try { $stale = ([datetime]::Parse($refreshed) -lt (Get-Date).AddDays(-14)) } catch { $stale = $true }
    }
    if ($stale) {
        Add-Note 1 '배포처 사본을 열나흘 넘게 받아오지 않았습니다.'
    }

    # --- 질문 13. 사내 GitHub 로그인이 되어 있나 ---------------------------
    # 이것은 $asks 로 간다. 브라우저 승인이 필요해 맞춤이 대신 못 한다. $notes 에
    # 넣으면 로그인 안 한 PC 에서 매 세션 맞춤이 돌고도 아무것도 못 고친다.
    #
    # "고칠 수 있는 것만 확인한다" 는 규칙의 예외다. 그 규칙을 둔 이유는 못 고치는
    # 것을 알리면 끌 수 없는 소음이 되기 때문인데, 이것은 사용자가 고칠 수 있고
    # 고치면 멈춘다. 예전에는 이 안내가 CLAUDE.md 에 있어서 로그인을 끝낸 사람도
    # 매 세션 읽었고, 안 한 사람은 읽고 넘겨도 아무 일이 없었다.
    #
    # 파일이 말해 주는 것은 "로그인한 적 있다" 까지다. 토큰이 만료되거나 취소돼도
    # 파일은 남는다. 그것까지 보려면 gh 를 실행하고 네트워크에 나가야 한다.
    $script:Budget.Files++
    $ghHosts = Join-Path (Join-Path $env:APPDATA 'GitHub CLI') 'hosts.yml'
    $loggedIn = $false
    if (Test-Path -LiteralPath $ghHosts) {
        foreach ($line in (Get-Content -LiteralPath $ghHosts -Encoding UTF8)) {
            if ($line -match '^\s*github\.com\s*:') { $loggedIn = $true; break }
        }
    }
    # 클로드가 이 명령을 대신 실행하면 gh 의 입력이 터미널이 아니라서, gh 가 브라우저를 여는
    # 단계를 건너뛰고 코드와 주소만 출력한다(2026-10-02 이 PC 에서 확인). 코드 입력 페이지는
    # 늘 같은 주소라 먼저 연다. start 는 PowerShell 과 cmd 와 Git Bash 에서 모두 기본 브라우저를
    # 연다. 코드는 --clipboard 가 클립보드에 넣으므로 사용자는 열린 페이지에 붙여 넣기만 한다.
    # user:email 은 git 명의를 GitHub 계정의 메일로 맞추는 데 쓴다. 기본 로그인에는 없다.
    # 명의 스크립트(git-identity.ps1)에도 같은 명령이 있다. 글자 그대로 같아야 한다.
    $loginCommand = 'start https://github.com/login/device; gh auth login --web --git-protocol https --skip-ssh-key --clipboard --scopes user:email'

    # --- 질문 14. git 커밋 명의를 사용자가 확인했나 ------------------------
    # 명의가 비어 있으면 클로드가 대화 맥락에 있는 클로드 계정 메일로 채운다. 클로드 계정을
    # 여럿이 같이 쓰는 PC 에서 직원의 커밋이 AX 팀 직원 이름으로 올라갔다(이슈 #28). 비어
    # 있는지만 보면 이미 남의 메일이 든 PC 를 정상으로 보므로, 지금 메일이 사용자가 승인한
    # 메일과 같은지를 본다. 승인은 명의 스크립트가 같은 파일에 적는다.
    #
    # 이것도 $asks 로 간다. 무엇이 본인 메일인지는 사용자가 승인해야 해서 맞춤이 대신 못 한다.
    # 로그인 전에는 GitHub 에서 메일을 못 읽으므로 로그인 안내 하나만 내고, 클로드가 로그인
    # 뒤에 이어 간다. ~/.gitconfig 를 읽는 것은 2026-10-02 에 사용자가 승인했다.
    $gitId = Read-GitIdentity (Join-Path $userHome '.gitconfig')
    $idOk = $gitId.Name -and $gitId.Email -and ($gitId.Approved -eq $gitId.Email)
    $idScript = Join-Path (Split-Path -Parent $PSScriptRoot) 'scripts\git-identity.ps1'
    $idHint = "git 명의는 pwsh -NoProfile -File `"$idScript`" 로 제안을 받아 지금 값과 제안 값을 본문에 보이고, " +
              '사용자가 승인한 뒤에만 같은 스크립트를 -Apply -Name -Email 로 실행하라. 대화 맥락에 있는 이름이나 메일로 채우지 않는다.'

    if (-not $loggedIn) {
        # 한 줄로 낸다. 매 세션 뜨는 안내라 길면 그 아래의 다른 알림을 밀어낸다(2026-09-29 사용자 결정).
        # 로그인은 사람이 브라우저에서 승인할 때까지 끝나지 않아 도구의 기본 시간 제한 2분으로는 끊긴다.
        $hint = "로그인 명령을 대신 실행할 때는 먼저 '열리는 브라우저 페이지에 Ctrl+V 로 코드를 붙여 넣고 승인하십시오'라고 본문에 알리고, 시간 제한을 10분으로 두고 실행하라."
        if (-not $idOk) { $hint += " 로그인이 끝나면 git 명의 확인으로 이어 간다. $idHint" }
        Add-Ask "사내 GitHub 로그인이 필요합니다. 다음을 실행하고 열리는 페이지에 Ctrl+V 로 코드를 붙여 넣으십시오: $loginCommand" $hint
    } elseif (-not $idOk) {
        $text = if ($gitId.Email) { "git 커밋 명의를 아직 확인하지 않았습니다(user.email: $($gitId.Email))." }
                else { 'git 커밋 명의(user.name · user.email)가 비어 있습니다.' }
        Add-Ask "$text 클로드에게 「git 명의 맞춰 줘」라고 하십시오." $idHint
    }
}
catch {
    # 사용자에게는 조용히 물러난다. 세션 시작을 훅의 사정으로 어지럽히지 않는다.
    # 다만 자국은 남긴다. 조용한 실패가 개발 중에 버그 하나를 통째로 가렸다.
    # 여기는 덧붙인다. 같은 오류가 반복되는지가 원인을 가리기 때문이다. 다만 영원히
    # 실패하는 PC 에서 파일이 자라지 않게 마지막 스무 줄만 남긴다.
    try {
        $log = Join-Path (Join-Path $env:USERPROFILE '.claude') 'kw-control-tower.error'
        $line = "$(Get-Date -Format o) $($_.Exception.GetType().Name): $($_.Exception.Message) @ $($_.InvocationInfo.ScriptLineNumber)"
        $keep = @()
        if (Test-Path -LiteralPath $log) { $keep = @(Get-Content -LiteralPath $log -Encoding UTF8) }
        $keep = @($keep + $line)
        if ($keep.Count -gt 20) { $keep = $keep[($keep.Count - 20)..($keep.Count - 1)] }
        $keep | Out-File -LiteralPath $log -Encoding UTF8
    } catch { }
    exit 0
}

$sw.Stop()

# 예산을 넘겼으면 그 사실을 남긴다. 알림에는 안 섞는다. 사용자가 고칠 것이 아니다.
#
# 덧붙이지 않고 덮어쓴다. 알고 싶은 것은 "요즘도 넘기는가"이지 넘긴 역사가 아니고,
# 덧붙이면 찬 시작마다 한 줄씩 영원히 쌓인다. 세션이 처음 열릴 때 한 번은 넘길 수
# 있다. 이 PC 에서 여덟 번을 재니 몸통이 다 200밀리초 안이었고 넘긴 것은 디스크가
# 식어 있던 첫 회뿐이었다.
if ($sw.ElapsedMilliseconds -gt 200) {
    try {
        $over = Join-Path (Join-Path $env:USERPROFILE '.claude') 'kw-control-tower.slow'
        [System.IO.File]::WriteAllText($over,
            "$(Get-Date -Format o) $($sw.ElapsedMilliseconds)ms files=$($script:Budget.Files) net=$($script:NetMs)ms`r`n",
            (New-Object System.Text.UTF8Encoding($false)))
    } catch { }
}

# --- 출력 -------------------------------------------------------------------
#
# 할 말을 모아 두었다가 끝에 훅 JSON 하나로 낸다. 그냥 찍으면 Claude 의 맥락에만 실리고
# 사용자 화면에는 안 보인다. systemMessage 는 사용자에게 띄우고, 같은 문장을
# additionalContext 로도 넣어 Claude 가 첫 답에서 재시작이나 직접 할 일을 전하게 한다.
# disciplined-coder 와 2026-09-25 에 이 형식으로 맞췄다.
$say = New-Object System.Collections.ArrayList
$syncLog = $null   # 맞춤을 불렀으면 그 진행 기록 파일. Claude 에게만 알린다.
$restartLine = 'kw-control-tower: 다시 켜야 새 버전이 적용됩니다.'
function Send-Hook {
    if ($say.Count -eq 0) { return }
    $text = ($say -join "`n").TrimEnd()
    # 맞춤이 찍은 재시작 줄도 여기서 보므로 문구가 아니라 합의한 첫 줄 그대로를 찾는다.
    $ctx = $text + "`n`n이 알림을 사용자의 첫 요청에 답하기 전에 먼저 전하라."
    if ($text.Contains($restartLine)) { $ctx += ' 클로드 코드를 다시 켜 달라고 요구하라.' }
    if ($text -match '(?m)^\s+claude plugin ') { $ctx += ' 적힌 명령을 대신 실행할지 물어라.' }
    foreach ($hint in $askHints) { if ($hint) { $ctx += " $hint" } }
    if ($syncLog) { $ctx += " 맞춤의 진행 기록은 $syncLog 에 있다." }
    @{ systemMessage = $text; hookSpecificOutput = @{ hookEventName = 'SessionStart'; additionalContext = $ctx } } |
        ConvertTo-Json -Depth 4 -Compress
}

# 다른 곳(클로드 코드의 자동 갱신, disciplined-coder)이 옮긴 설치본은 알리지 않는다. 갱신은
# 그것을 한 훅이 그 세션에서만 알린다(2026-09-29 사용자 결정). 알리면 disciplined-coder 가
# 이미 알린 갱신을 다음 세션에 한 번 더 알리게 된다. 맞춤이 같은 원격 커밋으로 실패한 것은
# 직접 실행할 명령이 있으므로 알린다. 첫 줄 형식은 disciplined-coder 와 2026-09-25 에 맞췄다.
if ($stuckSay.Count -gt 0) {
    [void]$say.Add('kw-control-tower: 플러그인 버전 알림')
    foreach ($s in $stuckSay) { [void]$say.Add($s) }
    [void]$say.Add('')
}

# 사용자가 직접 해야 하는 것을 먼저 말한다. 한 가지를 한 줄로 낸다. 직접 할 일은 맞춤을
# 부르는 이유가 아니므로 아래의 맞춤과 무관하게 뜬다.
foreach ($a in $asks) { [void]$say.Add("KW 컨트롤 타워: $a") }
if ($asks.Count -gt 0 -and $notes.Count -gt 0) { [void]$say.Add('') }

if ($notes.Count -eq 0) { Send-Hook; exit 0 }   # 맞춤이 고칠 것이 없으면 맞춤을 안 호출한다

# --- 여기부터 예산 밖이다 ---------------------------------------------------
#
# 위의 감지까지가 예산 안이다. 불일치한 곳이 하나도 없으면 바로 위에서 끝나므로
# 평소 세션은 예산 그대로다. 아래는 불일치한 세션에서만 돌고, 맞춤은 외부 프로세스를
# 실행하고 네트워크에 나간다. 그 값을 치르기로 한 것은 사용자 결정이다.
#
# 알리기만 하던 때에는 사내 목록에 새 플러그인이 추가해진 것을 알고도 몇 주씩 안 깔린
# PC 가 남았다. 알림을 읽고 명령을 호출하는 사람이 없으면 감지는 아무것도 바꾸지 않는다.
#
# 맞춤은 멱등이다. 없거나 불일치한 것만 고치고 이미 맞는 것은 손대지 않는다. 실패해도
# 세션을 막지 않는다. 못 한 단계만 다음 세션에 다시 알리고 나머지는 조용하다.

# 같은 원인으로 이미 실패한 단계는 다시 호출하지 않는다. 호출해도 같은 실패가 되풀이될 뿐이다.
$runSteps = New-Object System.Collections.ArrayList
$held     = New-Object System.Collections.ArrayList
foreach ($n in @($noteSteps | ForEach-Object { $_ } | Sort-Object -Unique)) {
    if ($kwState["stuck-step$n"] -eq (Get-StuckPrint $root $n)) { [void]$held.Add($n) } else { [void]$runSteps.Add($n) }
}
if ($held.Count -gt 0) {
    [void]$say.Add("kw-control-tower: 맞춤이 단계 $($held -join ', ') 에서 같은 원인으로 이미 실패해 다시 시도하지 않았습니다. 기록: $(Join-Path $cfg 'kw-control-tower.sync.log')")
}
if ($runSteps.Count -eq 0) { Send-Hook; exit 0 }

# 자식 프로세스로 부른다. 같은 프로세스에서 호출하면 맞춤의 Write-Host 가 성공 스트림에
# 안 실려 못 잡는다. 둘 다 출력을 UTF-8 로 맞춰 두어 한국어가 안 깨진다.
$sync = Join-Path (Split-Path -Parent $PSScriptRoot) 'scripts\sync.ps1'
if (-not (Test-Path -LiteralPath $sync)) {
    # 맞춤을 못 부를 때만 불일치 목록을 낸다. 맞춤이 돌면 그 결과가 무엇을 고쳤는지 말하므로
    # 목록을 함께 내면 같은 플러그인이 두 번 나온다.
    [void]$say.Add('KW 컨트롤 타워: 이 PC 가 사내 설정과 불일치합니다.')
    foreach ($n in $notes) { [void]$say.Add("  - $n") }
    [void]$say.Add('맞춤 스크립트를 못 찾아 고치지 못했습니다. 설치기를 다시 돌리십시오.')
    Send-Hook
    exit 0
}

try {
    # 감지가 읽은 원격 커밋을 넘긴다. 맞춤은 그 커밋까지 옮기지 못했으면 상태 파일에
    # 적고, 감지는 다음 세션에 그것을 보고 같은 실패로 맞춤을 다시 호출하지 않는다.
    $env:KWCT_REMOTE_HEAD = (@($remoteOf.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }) -join ';')
    # -Brief 로 부른다. 맞춤은 진행 출력을 로그 파일에 두고 결과만 낸다.
    $out = & pwsh -NoProfile -NonInteractive -File $sync -Brief -Steps ($runSteps -join ',') -BudgetSeconds 60 2>&1
    $syncLog = Join-Path $cfg 'kw-control-tower.sync.log'
    # 맞춤이 낸 결과를 그대로 흘린다. 다시 켜라는 안내도 맞춤이 낸다.
    #
    # 여기서 문구를 찾아 판정하던 것을 그만뒀다. 맞춤이 재시작을 호출하는 일을 다섯 가지
    # 하는데 이 정규식은 그중 둘만 잡고 있었다. 갱신과 되켜기와 걷어내기가 빠졌다.
    # 무엇이 재시작을 호출하는지는 그 일을 하는 곳이 안다.
    foreach ($line in $out) { [void]$say.Add("$line") }
} catch {
    [void]$say.Add("맞춤을 돌리지 못했습니다: $($_.Exception.Message)")
}
Send-Hook
exit 0
