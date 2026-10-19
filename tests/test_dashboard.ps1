#Requires -Version 7.0
# Contract tests for the kw-dashboard plugin.
#   pwsh -NoProfile -ExecutionPolicy Bypass -File .\tests\test_dashboard.ps1
#
# The skill guides work inside repos made from KiwoomAX/dashboard-template. The
# template's code comments, types and console warnings already teach the shell;
# the skill carries only what the code cannot say.

$ErrorActionPreference = 'Stop'
$Repo      = Split-Path -Parent $PSScriptRoot
$PluginDir = Join-Path $Repo 'plugins/kw-dashboard'
$SkillDir  = Join-Path $PluginDir 'skills/building-kiwoom-dashboard'

$script:Pass = 0
$script:Fail = 0
function Assert($label, $cond) {
    if ($cond) { $script:Pass++; Write-Host "PASS  $label" -ForegroundColor Green }
    else       { $script:Fail++; Write-Host "FAIL  $label" -ForegroundColor Red }
}
function Read-JsonOrNull($path) {
    if (Test-Path $path) { return (Get-Content $path -Raw -Encoding UTF8 | ConvertFrom-Json) }
    return $null
}
function Read-TextOrEmpty($path) {
    if (Test-Path $path) { return [IO.File]::ReadAllText($path) }
    return ''
}

$PluginName = 'kw-dashboard'
$PluginId   = 'kw-dashboard@kiwoom-ax'

Write-Host '--- manifests ---'
$pluginJson = Read-JsonOrNull (Join-Path $PluginDir '.claude-plugin/plugin.json')
$mkt        = Read-JsonOrNull (Join-Path $Repo '.claude-plugin/marketplace.json')
$manifest   = Read-JsonOrNull (Join-Path $Repo 'plugins/kw-control-tower/manifest.json')

Assert "plugin.json name is $PluginName" ($pluginJson.name -eq $PluginName)
$entry = $null
if ($mkt -and $mkt.plugins) { $entry = @($mkt.plugins) | Where-Object { $_.name -eq $PluginName } | Select-Object -First 1 }
Assert "the marketplace ships $PluginName" ($null -ne $entry)
Assert 'the plugin source is an in-repo path' ($null -ne $entry -and $entry.source -eq './plugins/kw-dashboard')
Assert 'both descriptions are the same text' ($null -ne $pluginJson.description -and $null -ne $entry -and $pluginJson.description -eq $entry.description)
Assert 'plugin.json carries no version (commit-based auto update)' ($null -ne $pluginJson -and $null -eq $pluginJson.PSObject.Properties['version'])
Assert "the control tower suggests $PluginId" ($null -ne $manifest -and @($manifest.suggested) -contains $PluginId)

Write-Host '--- skill ---'
$md = Join-Path $SkillDir 'SKILL.md'
Assert 'SKILL.md ships' (Test-Path $md)
$text = Read-TextOrEmpty $md
$name = ([regex]::Match($text, '(?m)^name:\s*(\S+)\s*$')).Groups[1].Value
Assert 'frontmatter name matches the folder' ($name -eq 'building-kiwoom-dashboard')
$desc = ([regex]::Match($text, '(?m)^description:\s*(.+)$')).Groups[1].Value
Assert 'description says when to open the skill' ($desc -match '^Use when ')
# A plain YAML scalar ends at ": " or " #"; the rest of the description would be lost.
Assert 'description is a safe plain scalar' (-not ($desc -match ': | #'))

# A reference file that SKILL.md does not link is never opened.
$refs = @('moving-existing-dashboard.md')
foreach ($ref in $refs) {
    Assert "$ref ships" (Test-Path (Join-Path $SkillDir $ref))
    Assert "SKILL.md links $ref" ($text -match [regex]::Escape("]($ref)"))
}
$refText = @($refs | ForEach-Object { Read-TextOrEmpty (Join-Path $SkillDir $_) }) -join "`n"
$allText = $text + "`n" + $refText

Assert 'no skill file points at a personal skills folder' (-not ($allText -match '~/\.claude'))
Assert 'no skill file calls python3' (-not ($allText -match '\bpython3\b'))
Assert 'skill documents carry no build-history notes' (-not ($allText -match '\b20\d\d-\d\d-\d\d\b|\(실측|실측\)|쓰던 때|섞여 있던'))

# The skill starts people from the template repo and hands deploys to the
# deploy skill. Both names must stay real.
Assert 'the skill names the template repo' ($text -match 'KiwoomAX/dashboard-template')
Assert 'the deploy skill it hands off to ships in this marketplace' (
    ($allText -match 'deploying-kiwoom-service') -and
    (Test-Path (Join-Path $Repo 'plugins/kw-devops/skills/deploying-kiwoom-service/SKILL.md')))

Write-Host '--- explaining-code-flow ---'
# The flow skill runs a repo on this PC, captures its screens and renders a guide
# page. Its three scripts each carry a --check self test.
$FlowDir  = Join-Path $PluginDir 'skills/explaining-code-flow'
$flowMd   = Join-Path $FlowDir 'SKILL.md'
$flowText = Read-TextOrEmpty $flowMd
Assert 'explaining-code-flow SKILL.md ships' (Test-Path $flowMd)
Assert 'its frontmatter name matches the folder' (([regex]::Match($flowText, '(?m)^name:\s*(\S+)\s*$')).Groups[1].Value -eq 'explaining-code-flow')
$flowDesc = ([regex]::Match($flowText, '(?m)^description:\s*(.+)$')).Groups[1].Value
Assert 'its description says when to open the skill' ($flowDesc -match '^Use when ')
Assert 'its description is a safe plain scalar' (-not ($flowDesc -match ': | #'))
foreach ($ref in @('analysis-prompt.md', 'tips-prompt.md', 'areas-prompt.md')) {
    Assert "$ref ships" (Test-Path (Join-Path $FlowDir $ref))
    Assert "SKILL.md links $ref" ($flowText -match [regex]::Escape("]($ref)"))
}
foreach ($s in @('render.py', 'run_repo.py', 'capture.py', 'draw_boxes.py')) {
    $py = Join-Path $FlowDir "scripts/$s"
    Assert "$s ships" (Test-Path $py)
    Assert "SKILL.md calls $s through CLAUDE_SKILL_DIR" ($flowText -match [regex]::Escape('${CLAUDE_SKILL_DIR}/scripts/' + $s))
    $null = & python $py --check 2>&1 | Out-String
    Assert "$s --check passes" ($LASTEXITCODE -eq 0)
}
Assert 'movie_template.html ships' (Test-Path (Join-Path $FlowDir 'scripts/movie_template.html'))
Assert 'manual_template.html ships' (Test-Path (Join-Path $FlowDir 'scripts/manual_template.html'))
Assert 'SKILL.md renders both pages into the output folder' ($flowText -match [regex]::Escape('render.py" <레포>/docs/code-flow/flow.json --out-dir <레포>/docs/code-flow'))
Assert 'the flow skill matches items against scenes and tips' ($flowText -match '\| 설명 대조 검토 \|')
Assert 'the flow skill checks each scene against its captures' ($flowText -match '\| 장면 · 화면 대조 \|')
Assert 'the merge table carries step frames' ($flowText -match [regex]::Escape('scenes.<id>.frames'))
$analysisText = Get-Content -Raw -Encoding UTF8 (Join-Path $FlowDir 'analysis-prompt.md')
Assert 'analysis links flow actions to capture steps' ($analysisText -match '`step`')
Assert 'analysis picks the whole result range as the end target' ($analysisText -match '범위 전체')
Assert 'its description names the user manual' ($flowDesc -match '사용자 설명서')
Assert 'the plugin description names the user manual' ($pluginJson.description -match '사용자 설명서')
$flowAll = (Get-ChildItem $FlowDir -Filter *.md | ForEach-Object { [IO.File]::ReadAllText($_.FullName) }) -join "`n"
Assert 'no flow skill file calls python3' (-not ($flowAll -match '\bpython3\b'))
Assert 'no flow skill file points at a personal skills folder' (-not ($flowAll -match '~/\.claude'))
Assert 'flow skill documents carry no build-history dates' (-not ($flowAll -match '\b20\d\d-\d\d-\d\d\b'))
$flowTpl = (Get-ChildItem (Join-Path $FlowDir 'scripts') -Filter *_template.html | ForEach-Object { [IO.File]::ReadAllText($_.FullName) }) -join "`n"
Assert 'flow page templates load nothing from the network' (-not ($flowTpl -match '(href|src)="https?://|@import|url\(https?:'))
$flowPy = (Get-ChildItem (Join-Path $FlowDir 'scripts') -Filter *.py | ForEach-Object { [IO.File]::ReadAllText($_.FullName) }) -join "`n"
Assert 'no user-facing script message says Docker' (-not ($flowPy -match '(RepoError|print)\(f?"[^"]*[Dd]ocker'))
Assert 'the plugin description names the flow skill' ($pluginJson.description -match 'explaining-code-flow')
$tipsText = Read-TextOrEmpty (Join-Path $FlowDir 'tips-prompt.md')
Assert 'tips are graded core or ref' ($tipsText -match '`core`' -and $tipsText -match '`ref`')
Assert 'tips carry no fixed count per scene' (-not ($tipsText -match '\d개 (안팎|이하)'))
Assert 'the flow skill reviews the feature order' ($flowText -match '\| 순서 검토 \|')
Assert 'the flow skill reviews the tips' ($flowText -match '\| 알아 둘 점 검토 \|')
$tpl = Read-TextOrEmpty (Join-Path $FlowDir 'scripts/movie_template.html')
Assert 'the template shows chatbot features as in development' ($tpl -match '챗봇 기능 안내는 개발 중입니다')

# 마켓플레이스 전체 검증은 tests/test_control_tower.ps1 이 한 번 실행한다.

Write-Host ''
Write-Host ("PASS={0} FAIL={1}" -f $script:Pass, $script:Fail)
if ($script:Fail -ne 0) { exit 1 }
