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
# Only the people who deploy need this skill, so it is suggested, not required.
Assert "the control tower suggests $PluginId" ($null -ne $manifest -and @($manifest.suggested) -contains $PluginId)
Assert "the control tower does not require $PluginId" ($null -ne $manifest -and @($manifest.required) -notcontains $PluginId)

Write-Host '--- skill ---'
$md = Join-Path $SkillDir 'SKILL.md'
$py = Join-Path $SkillDir 'pick_port.py'
Assert 'SKILL.md ships' (Test-Path $md)
Assert 'pick_port.py ships next to it' (Test-Path $py)
$text = if (Test-Path $md) { [IO.File]::ReadAllText($md) } else { '' }
$name = ([regex]::Match($text, '(?m)^name:\s*(\S+)\s*$')).Groups[1].Value
Assert 'frontmatter name matches the folder' ($name -eq 'deploying-kiwoom-service')

# The plugin cache path differs per PC and per commit. Claude Code substitutes
# ${CLAUDE_SKILL_DIR} in a skill body, so every call must go through it.
Assert 'the body does not point at a personal skills folder' (-not ($text -match '~/\.claude'))
$calls = [regex]::Matches($text, '(?m)^python\b.*pick_port\.py.*$')
Assert 'every pick_port.py call goes through CLAUDE_SKILL_DIR' ($calls.Count -gt 0 -and @($calls | Where-Object { $_.Value -notmatch '\$\{CLAUDE_SKILL_DIR\}/pick_port\.py' }).Count -eq 0)
# The control tower's python3 guard denies python3 on PCs where it is the Store
# redirector, so a python3 line in the body would be refused there.
Assert 'the body never calls python3' (-not ($text -match '\bpython3\b'))

Write-Host '--- pick_port.py --check ---'
# Offline self-check: band arithmetic and the enum values the DB constraint holds.
$null = & python $py --check 2>&1 | Out-String
Assert 'pick_port.py --check exits 0' ($LASTEXITCODE -eq 0)

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
