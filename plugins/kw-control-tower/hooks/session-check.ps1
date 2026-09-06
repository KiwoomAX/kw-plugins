# 세션 시작 알림. 이 PC가 manifest.json 과 어긋난 곳을 말하기만 한다.
#
# 계약 다섯을 지킨다. 세션 시작에 도는 훅은 이것 하나이고, 외부 프로세스를 안 부르고,
# 네트워크에 안 나가고, 파일 여덟과 레지스트리 값 하나만 읽고, 몸통이 200밀리초를
# 넘으면 그 값을 상태 파일에 남긴다.
#
# 아무것도 고치지 않는다. 세션을 막지 않는다. 스스로 실패하면 조용히 물러난다.
# Windows PowerShell 5.1 에서도 돌아야 하므로 7 전용 문법을 쓰지 않는다.

Set-StrictMode -Off
$ErrorActionPreference = 'Stop'

# 이 파일은 UTF-8 BOM 으로 저장한다. BOM 이 없으면 5.1 이 본문을 ANSI 로 읽어
# 한글 문자열이 깨진 채 출력된다. 나가는 쪽도 UTF-8 로 맞춘다.
try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false) } catch { }

$script:Budget = @{ Files = 0; Registry = 0 }

function Get-CheapHash {
    # MD5 를 직접 부른다. 이 PC 에서 8ms 이고 Get-FileHash 명령은 72ms 다. 아홉 배다.
    # 파일이 바뀌었는지만 가리므로 암호 강도는 필요 없다.
    # 손으로 FNV-1a 를 돌리는 길은 막혀 있다. 5.1 은 uint64 곱셈이 넘칠 때 감싸지
    # 않고 던진다. .NET 의 문자열 해시는 프로세스마다 시드가 달라 못 쓴다.
    param([string]$Path)
    $md5 = [System.Security.Cryptography.MD5]::Create()
    try {
        $bytes = [System.IO.File]::ReadAllBytes($Path)
        return [System.BitConverter]::ToString($md5.ComputeHash($bytes)).Replace('-', '')
    } finally { $md5.Dispose() }
}

function Read-Json {
    # 없거나 깨졌으면 $null 을 준다. 판정을 못 하겠으면 안 하는 것이 이 훅의 규칙이다.
    param([string]$Path)
    $script:Budget.Files++
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    try { return (Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json) }
    catch { return $null }
}

function Get-Prop {
    # PSCustomObject 에서 이름으로 값을 꺼낸다. 5.1 에는 null 조건 연산자가 없다.
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

$sw = [System.Diagnostics.Stopwatch]::StartNew()
$notes = New-Object System.Collections.ArrayList

try {
    $userHome = $env:USERPROFILE
    if ([string]::IsNullOrEmpty($userHome)) { exit 0 }   # 윈도가 아니면 물러난다
    $root = $env:CLAUDE_PLUGIN_ROOT
    if ([string]::IsNullOrEmpty($root)) { exit 0 }

    $cfg     = Join-Path $userHome '.claude'
    $plugins = Join-Path $cfg 'plugins'

    $manifest = Read-Json (Join-Path $root 'manifest.json')
    if ($null -eq $manifest) { exit 0 }   # 목록을 못 읽으면 아무 말도 안 한다

    # 읽히는 것과 형식이 맞는 것은 다르다. 칸이 빠진 목록으로 판정하면 그 물음만
    # 조용히 사라져, 어긋난 PC 를 정상으로 본다. 맞춤은 이때 멈추고 말하지만 이
    # 훅은 세션을 어지럽히지 않는 쪽이라 자국만 남기고 물러난다.
    foreach ($k in @('marketplaces', 'required', 'suggested', 'retiredPlugins',
                     'retiredMarketplaces', 'retiredSkills', 'retiredHooks')) {
        if ($null -eq $manifest.PSObject.Properties[$k]) { throw "목록 파일에 '$k' 칸이 없습니다." }
    }

    $settings  = Read-Json (Join-Path $cfg     'settings.json')
    $installed = Read-Json (Join-Path $plugins 'installed_plugins.json')
    $known     = Read-Json (Join-Path $plugins 'known_marketplaces.json')

    $enabled     = Get-Prop $settings  'enabledPlugins'
    $installedOf = Get-Prop $installed 'plugins'

    # --- 물음 1과 2. 필수 플러그인이 깔려 있나, 켜져 있나 -------------------
    # 두 물음이 다른 파일에 답이 있고 고치는 명령도 다르다. install 은 사용자가
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
        [void]$notes.Add("필수 플러그인이 안 깔려 있습니다: $($missing -join ', ')")
    }
    if ($disabled.Count -gt 0) {
        [void]$notes.Add("필수 플러그인이 꺼져 있습니다: $($disabled -join ', ')")
    }

    # --- 물음 3. 정리하기로 한 플러그인이 남았나 ---------------------------
    $staleP = New-Object System.Collections.ArrayList
    foreach ($p in @($manifest.retiredPlugins)) {
        $id = Get-Prop $p 'id'
        if (-not $id) { continue }
        if ((Get-Prop $installedOf $id) -or ($null -ne (Get-Prop $enabled $id))) { [void]$staleP.Add($id) }
    }
    if ($staleP.Count -gt 0) {
        [void]$notes.Add("더 안 쓰는 플러그인이 남아 있습니다: $($staleP -join ', ')")
    }

    # --- 물음 4. 정리하기로 한 배포처가 남았나 -----------------------------
    $staleM = New-Object System.Collections.ArrayList
    foreach ($mk in @($manifest.retiredMarketplaces)) {
        $name = Get-Prop $mk 'name'
        if (-not $name) { continue }
        $m = Test-Marketplace $settings $known $name
        if ($m.InSettings -or $m.InKnown) { [void]$staleM.Add($name) }
    }
    if ($staleM.Count -gt 0) {
        [void]$notes.Add("더 안 쓰는 배포처가 남아 있습니다: $($staleM -join ', ')")
    }

    # --- 물음 5. 우리 배포처의 자동 갱신이 두 곳 다 켜져 있나 ---------------
    # 두 파일은 서로 값을 주고받지 않는다. 그래서 두 곳 다 본다.
    $offAuto = New-Object System.Collections.ArrayList
    foreach ($mk in @($manifest.marketplaces)) {
        if ((Get-Prop $mk 'ours') -ne $true) { continue }   # 남의 배포처는 안 잰다
        $name = Get-Prop $mk 'name'
        $m = Test-Marketplace $settings $known $name
        if (-not ($m.InSettings -or $m.InKnown)) { [void]$offAuto.Add("$name (등록 없음)"); continue }
        $a = Get-Prop $m.Settings 'autoUpdate'
        $b = Get-Prop $m.Known    'autoUpdate'
        if (($a -ne $true) -or ($b -ne $true)) { [void]$offAuto.Add($name) }
    }
    if ($offAuto.Count -gt 0) {
        [void]$notes.Add("자동 갱신이 꺼져 있습니다: $($offAuto -join ', ')")
    }

    # --- 물음 6. 파이썬 라이브러리 목록이 바뀌었나 -------------------------
    # 예산 안에서 이 PC 를 직접 못 읽는 것이 이 하나뿐이라 해시로 잰다.
    # 재는 것은 파일이다. JSON 의 부분 트리를 해시하면 프로세스마다 값이 달라진다.
    $stateFile = Join-Path $cfg 'kw-control-tower.state'
    $reqFile   = Join-Path $root 'requirements.txt'
    $script:Budget.Files++
    if (Test-Path -LiteralPath $reqFile) {
        $now = Get-CheapHash $reqFile
        $was = $null
        $script:Budget.Files++
        if (Test-Path -LiteralPath $stateFile) {
            foreach ($line in (Get-Content -LiteralPath $stateFile -Encoding UTF8)) {
                if ($line -like 'requirements=*') { $was = $line.Substring(13) }
            }
        }
        if ($now -ne $was) {
            [void]$notes.Add('파이썬 라이브러리 목록이 이 PC에 맞춰진 것과 다릅니다.')
        }
    }

    # --- 물음 7. PYTHONUTF8 이 세워졌나 ------------------------------------
    # 사용자가 일부러 0 으로 둔 것은 그대로 두는 것이 맞으므로 그때는 말하지 않는다.
    $script:Budget.Registry++
    $utf8 = [Environment]::GetEnvironmentVariable('PYTHONUTF8', 'User')
    if ($null -eq $utf8) {
        [void]$notes.Add('PYTHONUTF8 이 세워져 있지 않습니다. 한글이 깨질 수 있습니다.')
    }

    # --- 물음 8과 9. 정리하기로 한 스킬과 훅이 남았나 ----------------------
    $staleS = New-Object System.Collections.ArrayList
    foreach ($s in @($manifest.retiredSkills)) {
        $name = Get-Prop $s 'name'
        if (-not $name) { continue }
        if (Test-Path -LiteralPath (Join-Path (Join-Path $cfg 'skills') $name)) { [void]$staleS.Add($name) }
    }
    if ($staleS.Count -gt 0) {
        [void]$notes.Add("더 안 쓰는 스킬 사본이 남아 있습니다: $($staleS -join ', ')")
    }

    # 훅 배선은 파일 이름이 아니라 경로로 가른다. 이 플러그인이 거는 훅의 파일 이름이
    # 옛것과 같아서, 이름만 보면 자기 배선을 남의 것으로 센다.
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
        [void]$notes.Add("더 안 쓰는 훅 배선이 남아 있습니다: $($staleH -join ', ')")
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
            "$(Get-Date -Format o) $($sw.ElapsedMilliseconds)ms files=$($script:Budget.Files)`r`n",
            (New-Object System.Text.UTF8Encoding($false)))
    } catch { }
}

if ($notes.Count -eq 0) { exit 0 }   # 이상이 없으면 아무 말도 안 한다

Write-Output 'KW 컨트롤 타워: 이 PC가 사내 설정과 어긋난 곳이 있습니다.'
foreach ($n in $notes) { Write-Output "  - $n" }
# 플러그인이 나르는 명령은 언제나 '플러그인이름:명령이름' 으로 불린다. 짧은 이름을
# 적으면 사용자가 없는 명령을 치게 된다.
Write-Output '고치려면 /kw-control-tower:kw-sync 를 실행하십시오. 이 알림은 아무것도 바꾸지 않았습니다.'
exit 0
