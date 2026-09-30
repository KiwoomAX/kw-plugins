#Requires -Version 7.0
# Contract tests for the kw-doc-formats plugin.
#   pwsh -NoProfile -ExecutionPolicy Bypass -File .\tests\test_doc_formats.ps1
#
# The plugin moved into this repo on 2026-09-07. It used to live in
# KiwoomAX/KW-doc-formats and be published by its own marketplace; both plugins
# are shipped by kiwoom-ax now and the source is an in-repo path.

$ErrorActionPreference = 'Stop'
$Repo   = Split-Path -Parent $PSScriptRoot
# 폴더 경로를 $Plugin 으로 두면 안 된다. PowerShell 은 변수 이름의 대소문자를 안
# 가려서, 아래에서 plugin.json 을 담는 $plugin 과 같은 변수가 된다. 경로가 조용히
# JSON 객체로 덮이고 한참 뒤 Join-Path 에서 엉뚱한 오류로 터진다.
$PluginDir = Join-Path $Repo 'plugins/kw-doc-formats'

$script:Pass = 0
$script:Fail = 0
function Assert($label, $cond) {
    if ($cond) { $script:Pass++; Write-Host "PASS  $label" -ForegroundColor Green }
    else       { $script:Fail++; Write-Host "FAIL  $label" -ForegroundColor Red }
}
# Reads JSON if the file exists, else $null, so a missing file is a FAIL line
# and not a crash before the totals print.
function Read-JsonOrNull($path) {
    if (Test-Path $path) { return (Get-Content $path -Raw | ConvertFrom-Json) }
    return $null
}
function Read-TextOrEmpty($path) {
    if (Test-Path $path) { return [IO.File]::ReadAllText($path) }
    return ''
}

$PluginName = 'kw-doc-formats'
$PluginId   = 'kw-doc-formats@kiwoom-ax'

Write-Host '--- manifests ---'
$pluginJson   = Join-Path $PluginDir '.claude-plugin/plugin.json'
$mktJson      = Join-Path $Repo   '.claude-plugin/marketplace.json'
$manifestJson = Join-Path $Repo   'plugins/kw-control-tower/manifest.json'
Assert 'plugin.json exists' (Test-Path $pluginJson)
Assert 'marketplace.json exists' (Test-Path $mktJson)
$plugin   = Read-JsonOrNull $pluginJson
$mkt      = Read-JsonOrNull $mktJson
$manifest = Read-JsonOrNull $manifestJson

Assert "plugin.json name is $PluginName" ($plugin.name -eq $PluginName)

# The marketplace ships more than this plugin, so the entry is looked up by
# name rather than by position.
$entry = $null
if ($mkt -and $mkt.plugins) { $entry = @($mkt.plugins) | Where-Object { $_.name -eq $PluginName } | Select-Object -First 1 }
Assert "the marketplace ships $PluginName" ($null -ne $entry)

# An in-repo relative path is the only form used here. A cross-repo object
# source written as { source: github, repo: ... } resolves over SSH and dies on
# a machine with no key; see the comment in marketplace.json.
Assert 'the plugin source is an in-repo path' ($null -ne $entry -and $entry.source -eq './plugins/kw-doc-formats')
Assert 'both descriptions are the same text' ($null -ne $plugin.description -and $null -ne $entry -and $plugin.description -eq $entry.description)
Assert 'plugin.json carries no version (commit-based auto update)' ($null -ne $plugin -and $null -eq $plugin.PSObject.Properties['version'])

# The list that requires this plugin now lives in the same repo, so the id is
# cross-checked here instead of being pinned by hand against another one. The
# hand-pinned version went stale: kw_install stopped holding the list and
# nothing failed.
Assert "the control tower requires $PluginId" ($null -ne $manifest -and @($manifest.required) -contains $PluginId)

Write-Host '--- skills ---'
$skillDirs = @(Get-ChildItem -Path (Join-Path $PluginDir 'skills') -Directory -ErrorAction SilentlyContinue)
Assert 'at least one skill ships' ($skillDirs.Count -gt 0)
foreach ($d in $skillDirs) {
    $md = Join-Path $d.FullName 'SKILL.md'
    Assert "$($d.Name) has SKILL.md" (Test-Path $md)
    $text = Read-TextOrEmpty $md
    $name = ([regex]::Match($text, '(?m)^name:\s*(\S+)\s*$')).Groups[1].Value
    Assert "$($d.Name) frontmatter name matches the folder" ($name -eq $d.Name)
}

# Each rule must live in exactly one skill, and the skill that owns it must be
# reachable. These check placement, not wording: a body assertion says the rule
# is here, and its negative says the rule is not left behind somewhere else.
$Bodies = @{}
foreach ($d in $skillDirs) { $Bodies[$d.Name] = Read-TextOrEmpty (Join-Path $d.FullName 'SKILL.md') }
function Body($name) { if ($Bodies.ContainsKey($name)) { return $Bodies[$name] } return '' }
function Desc($name) { return ([regex]::Match((Body $name), '(?ms)^description:\s*(.+?)$')).Groups[1].Value }

foreach ($n in @('common', 'hwp', 'pdf', 'pptx', 'xlsx', 'docx')) {
    Assert "the $n skill ships" ($Bodies.ContainsKey($n))
}

# common owns encoding. Nothing else restates it.
Assert 'common carries the encoding section' ((Body 'common') -match '(?m)^## 파이썬으로 파일을 열 때는 인코딩을 반드시 적는다')
Assert 'common detects the encoding of incoming CSV' ((Body 'common') -match 'chardet')
Assert 'common writes CSV meant for Excel with a BOM' ((Body 'common') -match 'utf-8-sig')
Assert 'xlsx does not restate the CSV encoding rule' (-not ((Body 'xlsx') -match 'utf-8-sig'))

# xlsx owns the cell font size.
Assert 'xlsx fixes the cell font size at 11' ((Body 'xlsx') -match 'size=11')

# hwp owns the conversion of formats Claude cannot read.
Assert 'hwp drives the Hangul word processor' ((Body 'hwp') -match 'HWPFrame\.HwpObject')
Assert 'hwp covers legacy Office files' ((Body 'hwp') -match '(?m)^## 구형 워드·PPT')

# docx names the tools that exist on this PC.
Assert 'docx builds with python-docx' ((Body 'docx') -match 'python-docx')
Assert 'docx reads with markitdown' ((Body 'docx') -match 'markitdown')

# pdf owns page selection and PDF output.
Assert 'pdf prints through headless Edge' ((Body 'pdf') -match '--print-to-pdf')

# pptx owns the Korean deck defaults.
Assert 'pptx removes the glyph outline' ((Body 'pptx') -match 'def strip_text_outline')

# A skill is only read when its description matches what the user is doing, and
# skills never chain on their own. Each format skill must name its official
# counterpart in the description, and point at common in the body.
foreach ($n in @('pdf', 'pptx', 'xlsx', 'docx')) {
    Assert "$n names document-skills:$n in its description" ((Desc $n) -match [regex]::Escape("document-skills:$n"))
}
foreach ($n in @('hwp', 'pdf', 'pptx', 'xlsx', 'docx')) {
    Assert "$n points at kw-doc-formats:common" ((Body $n) -match 'kw-doc-formats:common')
}

# Worked examples are copied as they are, so an unsafe example is an unsafe run.
# DisplayAlerts is off in the Excel example, so a Save() there overwrites the original silently.
Assert 'xlsx COM example does not save over the original' (-not ((Body 'xlsx') -match '\$wb\.Save\(\)'))
# A failed Open must not leave a windowless Hwp.exe behind; the next run would stop at the "already running" check.
Assert 'hwp COM example cleans up in finally' ((Body 'hwp') -match '(?s)try \{.*?\$h\.Open.*?\} finally \{.*?\$h\.Quit\(\)')
Assert 'hwp COM example stops when Open fails' ((Body 'hwp') -match 'if \(-not \$h\.Open\(')
# zipfile opens dst for writing before it reads src; the same file empties the deck. samefile also
# catches the same file written two ways (a mapped drive and its UNC path).
Assert 'pptx zip rewriters refuse to write over their source' ([regex]::Matches((Body 'pptx'), 'os\.path\.exists\(dst\) and os\.path\.samefile\(src, dst\)').Count -eq 2)

# .xls is read directly (common's table); only .doc and .ppt need converting, by Save As in Word or PowerPoint.
Assert 'hwp does not claim legacy Excel' (-not ((Desc 'hwp') -match '\.xls'))
Assert 'hwp does not promise Office automation it does not carry' (-not ((Desc 'hwp') -match '오피스를 조종해'))
# The Python libraries come from the control tower's requirements.txt, not from kw_install.
Assert 'the plugin description names the control tower as the library installer' ($null -ne $plugin -and $plugin.description -match 'kw-control-tower')
Assert 'docx names the control tower as the library installer' (-not ((Body 'docx') -match '설치기가 깔아 주는 것은'))
# kw_install does not install LibreOffice, so the official skills' soffice steps fail here.
foreach ($n in @('xlsx', 'docx', 'pptx')) {
    Assert "$n routes the official LibreOffice step to COM" ((Body $n) -match 'LibreOffice')
}
# The Excel replacement for recalc.py reads error values, not display text: a narrow column shows ####.
Assert 'xlsx finds formula errors by value, not by display text' ((Body 'xlsx') -match 'SpecialCells\(-4123, 16\)')
# DisplayAlerts is off, so SaveAs overwrites an existing file without asking; the example checks first.
Assert 'xlsx example checks the result path before SaveAs' ((Body 'xlsx') -match 'Test-Path -LiteralPath \$out')
Assert 'docx no longer says the rest of the official skill works as is' (-not ((Body 'docx') -match '나머지 조언은 그대로 쓸 수 있다'))
# Each COM example stops before touching an Office program the user has open.
Assert 'xlsx COM example checks for a running Excel first' ((Body 'xlsx') -match 'Get-Process EXCEL')
Assert 'pptx COM example checks for a running PowerPoint first' ((Body 'pptx') -match 'Get-Process POWERPNT')
Assert 'docx COM example checks for a running Word first' ((Body 'docx') -match 'Get-Process WINWORD')

# The monolith is gone; no leftover may name it.
foreach ($d in $skillDirs) {
    Assert "$($d.Name) does not name the retired skill" (-not ((Body $d.Name) -match 'document-formats'))
}

# 마켓플레이스 전체 검증은 tests/test_control_tower.ps1 이 한 번 실행한다.

Write-Host ''
Write-Host ("PASS={0} FAIL={1}" -f $script:Pass, $script:Fail)
if ($script:Fail -ne 0) { exit 1 }
