# 이 PC 를 manifest.json 에 맞춘다. /kw-sync 와 설치기 9단계가 부른다.
#
# 걸음은 저마다 독립이고 멱등이다. 한 걸음이 실패해도 나머지는 돈다.
# 무엇을 했는지 마지막에 요약하고, 사용자가 끈 것을 되켰으면 그것을 따로 적는다.
#
# 이행 첫째 걸음이라 CLAUDE.md 걸음(걸음 6)은 아직 없다. 설치기가 그 일을 하고 있어
# 둘이 같은 블록을 쓰게 되기 때문이다.

[CmdletBinding()]
param(
    [switch]$WhatIfOnly
)

Set-StrictMode -Off
$ErrorActionPreference = 'Continue'

$script:Did      = New-Object System.Collections.ArrayList
$script:Reenab   = New-Object System.Collections.ArrayList
$script:Failed   = New-Object System.Collections.ArrayList

function Say  { param([string]$m) Write-Host "  $m" }
function Note {
    # 미리보기에서는 한 일이 없으므로 한 일처럼 적지 않는다.
    param([string]$m)
    if ($WhatIfOnly) { $m = "[안 함 · 미리보기] $m" }
    [void]$script:Did.Add($m)
    Write-Host "  + $m" -ForegroundColor Green
}
function Fail { param([string]$step, [string]$m) [void]$script:Failed.Add("$step : $m"); Write-Host "  ! $m" -ForegroundColor Yellow }

try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false) } catch { }

function Get-CheapHash {
    # 알림 훅과 글자 그대로 같은 계산이어야 한다. 다르면 고쳐도 알림이 안 꺼진다.
    param([string]$Path)
    $md5 = [System.Security.Cryptography.MD5]::Create()
    try {
        $bytes = [System.IO.File]::ReadAllBytes($Path)
        return [System.BitConverter]::ToString($md5.ComputeHash($bytes)).Replace('-', '')
    } finally { $md5.Dispose() }
}

function Read-Json {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    try { return (Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json) } catch { return $null }
}
function Get-Prop {
    param($Object, [string]$Name)
    if ($null -eq $Object) { return $null }
    $p = $Object.PSObject.Properties[$Name]
    if ($null -eq $p) { return $null }
    return $p.Value
}
function Save-Json {
    # 남이 써 둔 것을 지우지 않으려고 통째로 읽어 고친 뒤 그대로 다시 쓴다.
    param($Object, [string]$Path)
    $tmp = "$Path.kwtmp"
    ($Object | ConvertTo-Json -Depth 30) | Out-File -LiteralPath $tmp -Encoding UTF8 -NoNewline
    Move-Item -LiteralPath $tmp -Destination $Path -Force
}
function Invoke-Claude {
    param([string[]]$ClaudeArgs)
    if ($WhatIfOnly) { Say "[미리보기] claude $($ClaudeArgs -join ' ')"; return $true }
    & claude @ClaudeArgs 2>&1 | ForEach-Object { Say $_ }
    return ($LASTEXITCODE -eq 0)
}

$userHome = $env:USERPROFILE
if ([string]::IsNullOrEmpty($userHome)) { Write-Error '윈도가 아닙니다. 이 스크립트는 윈도 전용입니다.'; exit 1 }

$root = $env:CLAUDE_PLUGIN_ROOT
if ([string]::IsNullOrEmpty($root)) { $root = Split-Path -Parent $PSScriptRoot }

$cfg          = Join-Path $userHome '.claude'
$pluginsDir   = Join-Path $cfg 'plugins'
$settingsPath = Join-Path $cfg 'settings.json'
$knownPath    = Join-Path $pluginsDir 'known_marketplaces.json'
$statePath    = Join-Path $cfg 'kw-control-tower.state'
$backupDir    = Join-Path $cfg 'kw-control-tower-backups'

$manifest = Read-Json (Join-Path $root 'manifest.json')
if ($null -eq $manifest) { Write-Error "목록 파일을 못 읽었습니다: $root\manifest.json"; exit 1 }

# 상태 파일은 두 가지만 담는다. 라이브러리 목록의 해시와, 이 PC 에서 맞춤이 한 번이라도
# 돌았는지다. 나머지 물음은 전부 이 PC 를 직접 읽어 판정하므로 적을 상태가 없다.
$state = @{}
if (Test-Path -LiteralPath $statePath) {
    foreach ($line in (Get-Content -LiteralPath $statePath -Encoding UTF8)) {
        $i = $line.IndexOf('=')
        if ($i -gt 0) { $state[$line.Substring(0, $i)] = $line.Substring($i + 1) }
    }
}
$firstRun = -not $state.ContainsKey('ranOnce')

Write-Host ''
Write-Host 'KW 컨트롤 타워 맞춤' -ForegroundColor Cyan
Write-Host ''

# ---------------------------------------------------------------- 걸음 1
Write-Host '1. 배포처를 등록합니다.'
try {
    $settings = Read-Json $settingsPath
    if ($null -eq $settings) { throw "settings.json 을 못 읽었습니다." }
    $known = Read-Json $knownPath

    foreach ($mk in @($manifest.marketplaces)) {
        $name = Get-Prop $mk 'name'
        $repo = Get-Prop $mk 'repo'
        $ours = ((Get-Prop $mk 'ours') -eq $true)

        $inSettings = ($null -ne (Get-Prop (Get-Prop $settings 'extraKnownMarketplaces') $name))
        $knownRoot  = Get-Prop $known 'marketplaces'
        if ($null -eq $knownRoot) { $knownRoot = $known }
        $inKnown    = ($null -ne (Get-Prop $knownRoot $name))

        if (-not $inSettings -and -not $inKnown) {
            if (Invoke-Claude @('plugin', 'marketplace', 'add', $repo)) { Note "배포처를 등록했습니다: $name" }
            else { Fail '1' "배포처 등록에 실패했습니다: $name" }
            continue
        }

        # 자동 갱신은 우리 배포처만 켠다. 남의 배포처의 그 값은 언제나 사용자의 것이다.
        if (-not $ours) { continue }

        $settings = Read-Json $settingsPath
        $known    = Read-Json $knownPath
        $a = Get-Prop (Get-Prop $settings 'extraKnownMarketplaces') $name
        $kr = Get-Prop $known 'marketplaces'; if ($null -eq $kr) { $kr = $known }
        $b = Get-Prop $kr $name

        $wrote = $false
        if ($null -ne $a -and (Get-Prop $a 'autoUpdate') -ne $true) {
            if (-not $WhatIfOnly) {
                $a | Add-Member -NotePropertyName 'autoUpdate' -NotePropertyValue $true -Force
                Save-Json $settings $settingsPath
            }
            $wrote = $true
        }
        if ($null -ne $b -and (Get-Prop $b 'autoUpdate') -ne $true) {
            if (-not $WhatIfOnly) {
                $b | Add-Member -NotePropertyName 'autoUpdate' -NotePropertyValue $true -Force
                Save-Json $known $knownPath
            }
            $wrote = $true
        }
        if ($wrote) { Note "자동 갱신을 켰습니다: $name" }
    }
} catch { Fail '1' $_.Exception.Message }

# ---------------------------------------------------------------- 걸음 2
Write-Host '2. 필수 플러그인을 맞춥니다.'
try {
    $installed = Read-Json (Join-Path $pluginsDir 'installed_plugins.json')
    $settings  = Read-Json $settingsPath
    $installedOf = Get-Prop $installed 'plugins'
    $enabled     = Get-Prop $settings 'enabledPlugins'

    foreach ($id in @($manifest.required)) {
        $entry = Get-Prop $installedOf $id
        $onDisk = $false
        if ($null -ne $entry) {
            foreach ($scope in @($entry)) {
                $p = Get-Prop $scope 'installPath'
                if ($p -and (Test-Path -LiteralPath $p)) { $onDisk = $true }
            }
        }

        if (-not $onDisk) {
            # 안 깔린 것에만 install 을 쓴다. install 은 사용자가 꺼 둔 값을 true 로 덮는다.
            if (Invoke-Claude @('plugin', 'install', $id)) { Note "플러그인을 깔았습니다: $id" }
            else { Fail '2' "설치에 실패했습니다: $id" }
            continue
        }

        if ((Get-Prop $enabled $id) -ne $true) {
            if (Invoke-Claude @('plugin', 'enable', $id)) {
                Note "꺼져 있던 필수 플러그인을 다시 켰습니다: $id"
                [void]$script:Reenab.Add($id)
            } else { Fail '2' "다시 켜지 못했습니다: $id" }
        }
    }

    # 권장 플러그인은 이 PC 에서 맞춤이 한 번도 안 돌았을 때만 깐다. 흔적을 세지 않는
    # 이유는 uninstall 이 두 파일의 흔적을 모두 지워, 일부러 지운 PC 와 처음 보는 PC 가
    # 구별되지 않기 때문이다.
    if ($firstRun) {
        foreach ($id in @($manifest.suggested)) {
            $entry = Get-Prop $installedOf $id
            if ($null -ne $entry) { continue }
            if (Invoke-Claude @('plugin', 'install', $id)) { Note "권장 플러그인을 깔았습니다: $id" }
            else { Fail '2' "권장 플러그인 설치에 실패했습니다: $id" }
        }
    } else {
        Say '권장 플러그인은 처음 한 번만 깝니다. 건너뜁니다.'
    }
} catch { Fail '2' $_.Exception.Message }

# ---------------------------------------------------------------- 걸음 3
Write-Host '3. 더 안 쓰는 플러그인과 배포처를 정리합니다.'
try {
    # 플러그인을 먼저 걷고 배포처를 나중에 걷는다. 배포처를 먼저 지우면 그 플러그인을
    # 이름으로 못 부른다.
    $installed = Read-Json (Join-Path $pluginsDir 'installed_plugins.json')
    $settings  = Read-Json $settingsPath
    $installedOf = Get-Prop $installed 'plugins'
    $enabled     = Get-Prop $settings 'enabledPlugins'

    foreach ($id in @($manifest.retiredPlugins)) {
        if ((Get-Prop $installedOf $id) -or ($null -ne (Get-Prop $enabled $id))) {
            if (Invoke-Claude @('plugin', 'uninstall', $id)) { Note "플러그인을 걷었습니다: $id" }
            else { Fail '3' "걷지 못했습니다: $id" }
        }
    }

    foreach ($name in @($manifest.retiredMarketplaces)) {
        $settings = Read-Json $settingsPath
        $known    = Read-Json $knownPath
        $kr = Get-Prop $known 'marketplaces'; if ($null -eq $kr) { $kr = $known }
        $present = ($null -ne (Get-Prop (Get-Prop $settings 'extraKnownMarketplaces') $name)) -or ($null -ne (Get-Prop $kr $name))
        if ($present) {
            if (Invoke-Claude @('plugin', 'marketplace', 'remove', $name)) { Note "배포처를 걷었습니다: $name" }
            else { Fail '3' "배포처를 걷지 못했습니다: $name" }
        }
    }
} catch { Fail '3' $_.Exception.Message }

# ---------------------------------------------------------------- 걸음 4
Write-Host '4. 파이썬 라이브러리를 맞춥니다.'
try {
    $req = Join-Path $root 'requirements.txt'
    if (-not (Test-Path -LiteralPath $req)) { throw "라이브러리 목록이 없습니다: $req" }
    $py = (Get-Command python -ErrorAction SilentlyContinue)
    if ($null -eq $py) { throw '파이썬을 못 찾았습니다. python 이 PATH 에 있어야 합니다.' }

    if ($WhatIfOnly) {
        Say "[미리보기] $($py.Source) -m pip install -r $req"
    } else {
        & $py.Source -m pip install --disable-pip-version-check -r $req 2>&1 | ForEach-Object { Say $_ }
        if ($LASTEXITCODE -ne 0) { throw "pip 이 코드 $LASTEXITCODE 로 끝났습니다." }
        # 이 걸음이 성공했을 때만 이 걸음의 해시를 적는다.
        $state['requirements'] = Get-CheapHash $req
        Note '파이썬 라이브러리를 목록에 맞췄습니다.'
    }
} catch { Fail '4' $_.Exception.Message }

# ---------------------------------------------------------------- 걸음 5
Write-Host '5. PYTHONUTF8 을 봅니다.'
try {
    # 설치기의 갈래를 그대로 들고 온다. 사용자가 0 으로 둔 것은 건드리지 않는다.
    $now = [Environment]::GetEnvironmentVariable('PYTHONUTF8', 'User')
    if ($now -eq '1') {
        Say '이미 1 입니다.'
    } elseif ($now -eq '0') {
        Say '0 입니다. 사용자가 끈 것이므로 그대로 둡니다.'
    } elseif ($null -ne $now) {
        Fail '5' "값이 '$now' 입니다. 손으로 1 이나 0 으로 고쳐 주십시오."
    } else {
        $py = (Get-Command python -ErrorAction SilentlyContinue)
        if ($null -eq $py) { throw '파이썬을 못 찾아 기본 인코딩을 재지 못했습니다.' }
        $enc = (& $py.Source -c "import sys; print(sys.getdefaultencoding())" 2>$null)
        if ([string]::IsNullOrEmpty($enc)) { throw '파이썬 기본 인코딩을 못 쟀습니다.' }
        if ($enc.Trim() -ne 'utf-8') {
            if (-not $WhatIfOnly) { [Environment]::SetEnvironmentVariable('PYTHONUTF8', '1', 'User') }
            Note "파이썬 기본이 $($enc.Trim()) 이라 PYTHONUTF8 을 1 로 세웠습니다."
        } else {
            Say '파이썬이 이미 utf-8 이라 세울 필요가 없습니다.'
        }
    }
} catch { Fail '5' $_.Exception.Message }

# ---------------------------------------------------------------- 걸음 7
Write-Host '7. 더 안 쓰는 스킬 사본과 훅 배선을 정리합니다.'
try {
    $skillsRoot = Join-Path $cfg 'skills'
    foreach ($s in @($manifest.retiredSkills)) {
        $name = Get-Prop $s 'name'
        $by   = Get-Prop $s 'replacedBy'
        if ([string]::IsNullOrEmpty($name)) { continue }
        # 이름은 허용 목록으로 막는다. 거부 목록이 아니라 허용 목록이라 예상 못 한 것이 안 샌다.
        if ($name -notmatch '^[A-Za-z0-9._-]+$' -or $name -eq '.' -or $name -eq '..') {
            throw "스킬 이름이 폴더 이름 하나가 아닙니다: '$name'"
        }
        $dir = Join-Path $skillsRoot $name
        if (-not (Test-Path -LiteralPath $dir)) { continue }

        # 대체가 확인된 뒤에만 지운다. 먼저 지우고 설치가 실패하면 그 스킬이 없는 PC 가 된다.
        if ($by) {
            $ip = Read-Json (Join-Path $pluginsDir 'installed_plugins.json')
            if ($null -eq (Get-Prop (Get-Prop $ip 'plugins') $by)) {
                Say "$name : 대체할 $by 가 아직 안 깔려 있어 그대로 둡니다."
                continue
            }
        }

        $files   = @(Get-ChildItem -LiteralPath $dir -Recurse -Force -File)
        $subdirs = @(Get-ChildItem -LiteralPath $dir -Recurse -Force -Directory)

        if ($subdirs.Count -eq 0 -and $files.Count -eq 0) {
            if (-not $WhatIfOnly) { Remove-Item -LiteralPath $dir -Recurse -Force }
            Note "$name : 빈 폴더라 지웠습니다. 뜰 사본이 없습니다."
            continue
        }
        # 판정은 셋을 함께 본다. 하위 폴더 없음과 파일 하나와 그 이름이 SKILL.md 인 것이다.
        $onlySkill = ($subdirs.Count -eq 0) -and ($files.Count -eq 1) -and ($files[0].Name -eq 'SKILL.md')
        if (-not $onlySkill) {
            Say "$name : SKILL.md 말고 다른 것이 있어 그대로 둡니다."
            continue
        }
        if ($WhatIfOnly) { Say "[미리보기] $dir 를 사본 뜬 뒤 지웁니다."; continue }
        if (-not (Test-Path -LiteralPath $backupDir)) { New-Item -ItemType Directory -Force -Path $backupDir | Out-Null }
        Copy-Item -LiteralPath $files[0].FullName -Destination (Join-Path $backupDir "$name.SKILL.md.bak") -Force
        Remove-Item -LiteralPath $dir -Recurse -Force
        Note "$name : 사본을 뜨고 지웠습니다."
    }

    # 훅 배선은 파일 이름이 아니라 경로로 가른다. 새로 거는 훅이 같은 파일 이름을 갖기
    # 때문에, 이름으로 걷으면 맞춤이 매번 자기 배선을 지운다.
    foreach ($h in @($manifest.retiredHooks)) {
        Say "훅 배선 정리는 이행 셋째 걸음에서 만듭니다: $h"
    }
} catch { Fail '7' $_.Exception.Message }

# ---------------------------------------------------------------- 마무리
if (-not $WhatIfOnly) {
    $state['ranOnce'] = (Get-Date -Format o)
    $lines = foreach ($k in $state.Keys) { "$k=$($state[$k])" }
    $lines | Out-File -LiteralPath $statePath -Encoding UTF8
}

Write-Host ''
Write-Host '요약' -ForegroundColor Cyan
if ($script:Did.Count -eq 0) { Write-Host '  바꾼 것이 없습니다. 이 PC 는 이미 목록과 같습니다.' }
else { foreach ($d in $script:Did) { Write-Host "  - $d" } }

if ($script:Reenab.Count -gt 0) {
    Write-Host ''
    Write-Host '되켠 것' -ForegroundColor Yellow
    Write-Host "  꺼져 있던 필수 플러그인을 다시 켰습니다: $($script:Reenab -join ', ')"
    Write-Host '  회사가 필수로 정한 것이라 되켭니다. 이 줄은 그것을 조용히 안 하려고 적습니다.'
}

if ($script:Failed.Count -gt 0) {
    Write-Host ''
    Write-Host '못 한 것' -ForegroundColor Yellow
    foreach ($f in $script:Failed) { Write-Host "  - $f" }
    Write-Host '  못 한 걸음만 다음 세션에 다시 알립니다. 나머지는 조용합니다.'
    exit 1
}
exit 0
