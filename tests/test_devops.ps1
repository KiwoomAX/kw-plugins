#Requires -Version 7.0
# Contract tests for the kw-devops plugin.
#   pwsh -NoProfile -ExecutionPolicy Bypass -File .\tests\test_devops.ps1
#
# deploying-kiwoom-service moved in from a personal copy under ~/.claude/skills
# on 2026-09-14. That copy called its script by that path and with python3;
# neither holds once the skill ships inside a plugin on a Windows PC.

$ErrorActionPreference = 'Stop'
$Repo      = Split-Path -Parent $PSScriptRoot
$PluginDir = Join-Path $Repo 'plugins/kw-devops'
$SkillDir  = Join-Path $PluginDir 'skills/deploying-kiwoom-service'

$script:Pass = 0
$script:Fail = 0
function Assert($label, $cond) {
    if ($cond) { $script:Pass++; Write-Host "PASS  $label" -ForegroundColor Green }
    else       { $script:Fail++; Write-Host "FAIL  $label" -ForegroundColor Red }
}
function Read-JsonOrNull($path) {
    if (Test-Path $path) { return (Get-Content $path -Raw | ConvertFrom-Json) }
    return $null
}

$PluginName = 'kw-devops'
$PluginId   = 'kw-devops@kiwoom-ax'

Write-Host '--- manifests ---'
$pluginJson = Read-JsonOrNull (Join-Path $PluginDir '.claude-plugin/plugin.json')
$mkt        = Read-JsonOrNull (Join-Path $Repo '.claude-plugin/marketplace.json')
$manifest   = Read-JsonOrNull (Join-Path $Repo 'plugins/kw-control-tower/manifest.json')

Assert "plugin.json name is $PluginName" ($pluginJson.name -eq $PluginName)
$entry = $null
if ($mkt -and $mkt.plugins) { $entry = @($mkt.plugins) | Where-Object { $_.name -eq $PluginName } | Select-Object -First 1 }
Assert "the marketplace ships $PluginName" ($null -ne $entry)
Assert 'the plugin source is an in-repo path' ($null -ne $entry -and $entry.source -eq './plugins/kw-devops')
Assert 'both descriptions are the same text' ($null -ne $pluginJson.description -and $null -ne $entry -and $pluginJson.description -eq $entry.description)
Assert 'plugin.json carries no version (commit-based auto update)' ($null -ne $pluginJson -and $null -eq $pluginJson.PSObject.Properties['version'])
Assert "the control tower requires $PluginId" ($null -ne $manifest -and @($manifest.required) -contains $PluginId)

Write-Host '--- skill ---'
$md = Join-Path $SkillDir 'SKILL.md'
$py = Join-Path $SkillDir 'scripts/pick_port.py'
Assert 'SKILL.md ships' (Test-Path $md)
Assert 'pick_port.py ships under scripts/' (Test-Path $py)
$text = if (Test-Path $md) { [IO.File]::ReadAllText($md) } else { '' }
$name = ([regex]::Match($text, '(?m)^name:\s*(\S+)\s*$')).Groups[1].Value
Assert 'frontmatter name matches the folder' ($name -eq 'deploying-kiwoom-service')

# The body was split so a port question does not load compose templates and log
# tables. A reference file that SKILL.md does not link is never opened.
$refs = @('compose-and-env.md', 'jenkins-logs.md', 'server-facts.md')
foreach ($ref in $refs) {
    Assert "$ref ships" (Test-Path (Join-Path $SkillDir $ref))
    Assert "SKILL.md links $ref" ($text -match [regex]::Escape("]($ref)"))
}
$refText = @($refs | ForEach-Object { $p = Join-Path $SkillDir $_; if (Test-Path $p) { [IO.File]::ReadAllText($p) } }) -join "`n"
$allText = $text + "`n" + $refText

# The plugin cache path differs per PC and per commit. Claude Code substitutes
# ${CLAUDE_SKILL_DIR} in SKILL.md only; a reference file opened with Read keeps
# the literal text. So every call lives in SKILL.md and goes through it.
Assert 'no skill file points at a personal skills folder' (-not ($allText -match '~/\.claude'))
$calls = [regex]::Matches($text, '(?m)^python\b.*pick_port\.py.*$')
Assert 'every pick_port.py call goes through CLAUDE_SKILL_DIR' ($calls.Count -gt 0 -and @($calls | Where-Object { $_.Value -notmatch '\$\{CLAUDE_SKILL_DIR\}/scripts/pick_port\.py' }).Count -eq 0)
Assert 'reference files carry no CLAUDE_SKILL_DIR (not substituted there)' (-not ($refText -match 'CLAUDE_SKILL_DIR'))
# The control tower's python3 guard denies python3 on PCs where it is the Store
# redirector, so a python3 line in any skill file would be refused there.
Assert 'no skill file calls python3' (-not ($allText -match '\bpython3\b'))

Write-Host '--- pick_port.py --check ---'
# Offline self-check: band arithmetic and the enum values the DB constraint holds.
$null = & python $py --check 2>&1 | Out-String
Assert 'pick_port.py --check exits 0' ($LASTEXITCODE -eq 0)

# A tool call reads stdout through a pipe. On a Korean Windows PC without
# PYTHONUTF8 that pipe is cp949, which has no en dash or em dash, and the script
# printed both and died after the network work was done. PYTHONIOENCODING forces
# the same encoding on any machine; --check prints the band label.
$env:PYTHONIOENCODING = 'cp949'
try {
    $null = & python $py --check 2>&1 | Out-String
    $cpCode = $LASTEXITCODE
} finally { Remove-Item Env:PYTHONIOENCODING }
Assert 'pick_port.py prints on a cp949 console' ($cpCode -eq 0)

Write-Host '--- claude plugin validate ---'
Push-Location $Repo
try {
    $null = & claude plugin validate ./ 2>&1 | Out-String
    $code = $LASTEXITCODE
} finally { Pop-Location }
Assert 'claude plugin validate exits 0 (warnings allowed)' ($code -eq 0)

Write-Host ''
Write-Host ("PASS={0} FAIL={1}" -f $script:Pass, $script:Fail)
if ($script:Fail -ne 0) { exit 1 }
