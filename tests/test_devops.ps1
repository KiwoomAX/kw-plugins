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
# Suggested, not required: the skills reach only the internal server 192.7.9.45, so people
# off the company network turn the plugin off, and a required entry would turn it back on
# every session (decided 2026-09-29).
Assert "the control tower suggests $PluginId" ($null -ne $manifest -and @($manifest.suggested) -contains $PluginId)
Assert "the control tower does not require $PluginId" ($null -ne $manifest -and @($manifest.required) -notcontains $PluginId)

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
$refs = @('compose-and-env.md', 'jenkins-logs.md', 'jenkinsfile.md', 'local-verify.md', 'secrets.md', 'github-repo.md')
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
# env-<조직> reads as env-KiwoomAX; the real credential ids are env-ax and env-am.
$composeText = [IO.File]::ReadAllText((Join-Path $SkillDir 'compose-and-env.md'))
Assert 'the org credential is named env-ax or env-am where it is introduced' (($text -match 'env-ax') -and ($composeText -match 'env-ax'))
Assert 'reference files carry no CLAUDE_SKILL_DIR (not substituted there)' (-not ($refText -match 'CLAUDE_SKILL_DIR'))
# The control tower's python3 guard denies python3 on PCs where it is the Store
# redirector, so a python3 line in any skill file would be refused there.
Assert 'no skill file calls python3' (-not ($allText -match '\bpython3\b'))
# The skill carries what a deploy needs, not how each rule was found. Build
# history (dates, measurement notes, how things used to be) goes stale and is
# loaded on every run.
Assert 'skill documents carry no build-history notes' (-not ($allText -match '\b20\d\d-\d\d-\d\d\b|\(실측|실측\)|쓰던 때|섞여 있던'))

# AX 팀 요청은 플러그인 폴더의 문의 안내 한 곳으로 모은다. 메일로 보내던 스크립트와 메일 모양 문서는 없앴다.
$inquiryPath = Join-Path $PluginDir 'ax-inquiry.md'
Assert 'the AX inquiry guide ships at the plugin root' (Test-Path $inquiryPath)
Assert 'SKILL.md sends AX-team requests through the inquiry guide' ($text -match [regex]::Escape('${CLAUDE_PLUGIN_ROOT}/ax-inquiry.md'))
Assert 'no mail script or mail body document is left' (-not (Test-Path (Join-Path $SkillDir 'scripts/request-ax.ps1')) -and -not (Test-Path (Join-Path $SkillDir 'ax-requests.md')) -and -not ($allText -match 'request-ax|ax-requests'))
Assert 'env registration goes to the env inquiry type' ($text -match [regex]::Escape('「환경변수(env) 등록」'))
Assert 'schedule registration goes to the AX team by messenger' ($text -match '스케줄 등록' -and $text -match '메신저')
Assert 'a key file is still turned into a base64 env line' ($refText -match 'ToBase64String')
# 세 플러그인은 따로 설치될 수 있어 같은 안내를 플러그인마다 둔다. 한쪽만 고치면 안내가 갈라진다.
$copies = @('kw-devops', 'kw-dashboard', 'kw-github') | ForEach-Object { Join-Path $Repo "plugins/$_/ax-inquiry.md" }
Assert 'the three plugin copies of the inquiry guide are the same' (@($copies | Where-Object { Test-Path $_ }).Count -eq 3 -and @($copies | ForEach-Object { (Get-FileHash $_).Hash } | Select-Object -Unique).Count -eq 1)
Assert 'the inquiry guide names the service address and the env type' (([IO.File]::ReadAllText($inquiryPath)) -match [regex]::Escape('http://192.7.9.45:9999') -and ([IO.File]::ReadAllText($inquiryPath)) -match [regex]::Escape('환경변수(env) 등록'))

# The port is registered with the container_name the compose file actually carries, before push.
# Registering at step 5 left days between picking and registering, and two people could pick the same port.
Assert 'the port is registered right after compose is written' ($text -match '방금 쓴 compose 의 `container_name` 으로')
Assert 'an abandoned deploy tells the owner to ask for the row to be removed' ($text -match '배포를 그만두면 이 줄이\s+등록부에 남')
# A copy with no remote (a zip download) once got a fresh repo while the org already had one.
# Two repos with the same Jenkinsfile make two jobs that tear down each other's container.
Assert 'step 1 reads the existing origin before anything else' ($text -match '(?m)^git remote get-url origin')
Assert 'a new repo is created only in github-repo.md, and private' (-not ($text -match 'gh repo create') -and ($refText -match 'gh repo create \S+ --private'))
Assert 'no skill file force-pushes' (-not ($allText -match '(?m)^\s*git push\b.*(--force|-f\b)'))
# A copy that already has .git on master would track origin/main from master, and the step-4 push is refused.
Assert 'joining an existing repo points HEAD at main before reset' ($refText -match '(?s)git symbolic-ref HEAD refs/heads/main.*?git reset origin/main')

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

# docker-compose.jenkins.yml is written only when there are bind mounts, so most new services have none.
$lvPath = Join-Path $SkillDir 'local-verify.md'
$lv = if (Test-Path $lvPath) { [IO.File]::ReadAllText($lvPath) } else { '' }
Assert 'local-verify adds the Jenkins override only when it exists' ($lv -match 'Test-Path docker-compose\.jenkins\.yml')

Write-Host '--- searching-winus ---'
# The manifest lives in DBGateway, not in this repo: fetch_manifest.py pulls the index at
# run time and caches it under ~/.claude/cache. This repo is public, so the publisher and the
# registry DDL are kept out of it entirely — they carry the kw_deploy table definitions and the
# SQL that reads them, and only someone who may register a query needs them.
$DbDir   = Join-Path $PluginDir 'skills/searching-winus'
$dbMd    = Join-Path $DbDir 'SKILL.md'
$dbFetch = Join-Path $DbDir 'scripts/fetch_manifest.py'
Assert 'searching-winus SKILL.md ships' (Test-Path $dbMd)
Assert 'fetch_manifest.py ships under scripts/' (Test-Path $dbFetch)
$dbStray = @(Get-ChildItem $Repo -Recurse -File -Include 'build_manifest.py','schema.sql' -ErrorAction SilentlyContinue | Where-Object { $_.FullName -notmatch '[\\/]\.git[\\/]' })
Assert 'the manifest publisher is nowhere in this public repo' (@($dbStray).Count -eq 0)
Assert 'no manifest copy ships in the repo' (-not (Test-Path (Join-Path $DbDir 'references/manifest.md')))
# fetch_manifest.py is the only thing the skill may carry: nothing else, and no kw_deploy SQL.
$dbShipped = @(Get-ChildItem (Join-Path $DbDir 'scripts') -File -ErrorAction SilentlyContinue)
Assert 'the skill ships fetch_manifest.py and nothing else' (@($dbShipped).Count -eq 1 -and $dbShipped[0].Name -eq 'fetch_manifest.py')
$dbText  = if (Test-Path $dbMd) { [IO.File]::ReadAllText($dbMd) } else { '' }
$fetText = if (Test-Path $dbFetch) { [IO.File]::ReadAllText($dbFetch) } else { '' }
$dbAll   = $dbText + "`n" + $fetText
$dbName  = ([regex]::Match($dbText, '(?m)^name:\s*(\S+)\s*$')).Groups[1].Value
Assert 'searching-winus frontmatter name matches the folder' ($dbName -eq 'searching-winus')
Assert 'searching-winus files point at no personal skills folder' (-not ($dbAll -match '~/\.claude/skills'))
Assert 'searching-winus files call no python3' (-not ($dbAll -match '\bpython3\b'))
Assert 'searching-winus files carry no build-history notes' (-not ($dbAll -match '\b20\d\d-\d\d-\d\d\b|실측'))
Assert 'nothing shipped to skill users names the registry tables' (-not ($dbText + "`n" + $fetText -match 'kw_deploy'))
# The skill reads the manifest and nothing else: publishing it is somebody else's job elsewhere.
Assert 'the skill says nothing about publishing the manifest' (-not ($dbAll -match '관리자|build_manifest'))
# Where the manifest comes from and how long a copy is kept is the script's business. The reader
# only needs the command and what to do with a warning line, so the skill must not describe either.
Assert 'the skill does not describe the cache or its source' (-not ($dbText -match 'MongoDB|\.claude|캐시|TTL'))
# The skill is read-only: every registered query is a SELECT. A query goes out as POST with its
# arguments in the body (DBGateway ADR-0040), so POST to /winus/query is a read; other write verbs are not.
Assert 'the skill asks for no write' (-not ($dbText -match '\bPUT\b|\bPATCH\b|\bDELETE\b|execute_dml|insert_one'))
# DBGateway is retiring the query-string GET (Kiwoom-DBgateway#99), so the code the skill teaches must not use it.
Assert 'the skill calls queries with POST, not the retiring GET' ($dbText -match 'httpx\.post\(' -and -not ($dbText -match 'GET /winus/query|httpx\.get\('))
# The response field truncated is always false and is being retired with the GET (Kiwoom-DBgateway#99);
# code that reads body["truncated"] would fail with KeyError once it is gone.
Assert 'the skill reads no truncated field' (-not ($dbText -match 'truncated'))
# Screen numbers and report names are internal detail; the manifest lists queries, not screens.
Assert 'the skill names no WINUS screen numbers' (-not ($dbText -match '\b0\d{5}\b'))
# The skill is installed as a plugin, so the run-time call must resolve through the skill dir.
$fetCalls = [regex]::Matches($dbText, '(?m)^python\b.*fetch_manifest\.py.*$')
Assert 'fetch_manifest.py is called through CLAUDE_SKILL_DIR' ($fetCalls.Count -gt 0 -and @($fetCalls | Where-Object { $_.Value -notmatch 'CLAUDE_SKILL_DIR' }).Count -eq 0)
# The in-house SDKs live in the private KiwoomAM/Kiwoom-Manager repo, which skill users cannot install
# from. fetch_manifest.py asks DBGateway with the standard library alone and declares no dependencies.
Assert 'searching-winus pulls nothing from the private Kiwoom-Manager repo' (-not ($dbAll -match 'Kiwoom-Manager|mdb[-_]manager'))
Assert 'fetch_manifest.py declares no script dependencies' (-not ($fetText -match '(?m)^# /// script'))
# Offline self-check: cache, access key refusals (incl. the key-set-but-not-applied branches), redirects,
# and on Windows the real HKCU read with a throwaway value name.
$fetSelf = & python $dbFetch --selfcheck 2>&1 | Out-String
Assert 'fetch_manifest.py --selfcheck passes' ($LASTEXITCODE -eq 0 -and $fetSelf -match 'selfcheck ok')
Assert 'SKILL.md tells the reader to fetch the manifest before writing code' ($dbText -match 'fetch_manifest\.py')
# The cache must not land in the plugin folder (replaced on update) or in the user's repo.
Assert 'fetch_manifest.py caches under the Claude config dir' ($fetText -match 'CLAUDE_CONFIG_DIR' -and $fetText -match '"cache"')
Assert 'fetch_manifest.py keeps a one hour TTL' ($fetText -match '(?m)^TTL_SECONDS = 3600\s*$')
Assert 'fetch_manifest.py defines no Korean identifiers' (-not ($fetText -match '(?m)^\s*(def|class)\s+[^\x00-\x7F]'))
# The stale-copy warning carries an em dash that cp949 lacks; without these two lines the fallback dies while printing it.
Assert 'fetch_manifest.py pins its output to UTF-8' ($fetText -match 'sys\.stdout\.reconfigure\(encoding="utf-8"\)' -and $fetText -match 'sys\.stderr\.reconfigure\(encoding="utf-8"\)')

Write-Host '--- managing-sandbox ---'
# Reads and writes the user's own tables in kw_sandbox through DBGateway /sandbox/*. Unlike
# searching-winus it writes, keeps a record under the Claude config dir, and ships two scripts,
# so the read-only checks above do not carry over.
$sbDir  = Join-Path $PluginDir 'skills/managing-sandbox'
$sbMd   = Join-Path $sbDir 'SKILL.md'
$sbBack = Join-Path $sbDir 'backend.md'
$sbPy   = Join-Path $sbDir 'scripts/sandbox.py'
$sbRec  = Join-Path $sbDir 'scripts/record.py'
Assert 'managing-sandbox ships SKILL.md, backend.md, sandbox.py and record.py' (@($sbMd, $sbBack, $sbPy, $sbRec | Where-Object { Test-Path $_ }).Count -eq 4)
$sbText = if (Test-Path $sbMd) { [IO.File]::ReadAllText($sbMd) } else { '' }
$sbBackText = if (Test-Path $sbBack) { [IO.File]::ReadAllText($sbBack) } else { '' }
$sbPyText = if (Test-Path $sbPy) { [IO.File]::ReadAllText($sbPy) } else { '' }
$sbRecText = if (Test-Path $sbRec) { [IO.File]::ReadAllText($sbRec) } else { '' }
$sbAll = $sbText + "`n" + $sbBackText + "`n" + $sbPyText + "`n" + $sbRecText
Assert 'managing-sandbox frontmatter name matches the folder' (([regex]::Match($sbText, '(?m)^name:\s*(\S+)\s*$')).Groups[1].Value -eq 'managing-sandbox')
Assert 'managing-sandbox files point at no personal skills folder' (-not ($sbAll -match '~/\.claude/skills'))
Assert 'managing-sandbox files call no python3' (-not ($sbAll -match '\bpython3\b'))
Assert 'managing-sandbox files carry no build-history notes' (-not ($sbAll -match '\b20\d\d-\d\d-\d\d\b|실측'))
Assert 'managing-sandbox pulls nothing from the private Kiwoom-Manager repo' (-not ($sbAll -match 'Kiwoom-Manager|mdb[-_]manager'))
Assert 'managing-sandbox scripts declare no script dependencies' (-not ($sbAll -match '(?m)^# /// script'))
$sbCalls = [regex]::Matches($sbText, '(?m)^python\b.*sandbox\.py.*$')
Assert 'sandbox.py is called through CLAUDE_SKILL_DIR' ($sbCalls.Count -gt 0 -and @($sbCalls | Where-Object { $_.Value -notmatch 'CLAUDE_SKILL_DIR' }).Count -eq 0)
Assert 'sandbox.py pins its output to UTF-8' ($sbPyText -match 'sys\.stdout\.reconfigure\(encoding="utf-8"\)' -and $sbPyText -match 'sys\.stderr\.reconfigure\(encoding="utf-8"\)')
# The record is the only copy of who made which table, so it lives outside the cache folder.
Assert 'record.py keeps the record under the Claude config dir, outside the cache' ($sbRecText -match 'CLAUDE_CONFIG_DIR' -and $sbRecText -match '"managing-sandbox"' -and -not ($sbRecText -match '"cache"'))
# The access-key handling is shared with searching-winus; both skills ship in this one plugin.
Assert 'sandbox.py imports fetch_manifest from searching-winus' ($sbPyText -match 'searching-winus' -and $sbPyText -match 'import fetch_manifest' -and (Test-Path $dbFetch))
Assert 'managing-sandbox docs use no em dash' (-not (($sbText + $sbBackText) -match '—'))
# Offline self-check: fake DBGateway, refusal codes, the confirm step, and the record. It replaces
# the registry reader and the browser opener, so a Windows run touches neither.
$sbSelf = & python $sbPy --selfcheck 2>&1 | Out-String
Assert 'sandbox.py --selfcheck passes' ($LASTEXITCODE -eq 0 -and $sbSelf -match 'selfcheck ok')

Write-Host '--- searching-document ---'
# A reference skill: one SKILL.md and no scripts. The user's own Claude calls vdb-handler with it.
$sdDir  = Join-Path $PluginDir 'skills/searching-document'
$sdMd   = Join-Path $sdDir 'SKILL.md'
Assert 'searching-document SKILL.md ships' (Test-Path $sdMd)
Assert 'searching-document ships SKILL.md and nothing else' (@(Get-ChildItem $sdDir -Recurse -File -ErrorAction SilentlyContinue).Count -eq 1)
$sdText = if (Test-Path $sdMd) { [IO.File]::ReadAllText($sdMd) } else { '' }
$sdName = ([regex]::Match($sdText, '(?m)^name:\s*(\S+)\s*$')).Groups[1].Value
Assert 'searching-document frontmatter name matches the folder' ($sdName -eq 'searching-document')
Assert 'searching-document calls no python3' (-not ($sdText -match '\bpython3\b'))
Assert 'searching-document carries no build-history notes' (-not ($sdText -match '\b20\d\d-\d\d-\d\d\b|실측'))
# The server defaults use_rerank to true; the skill promises a search without the reranker.
Assert 'searching-document turns the reranker off' ($sdText -match 'use_rerank\s*=\s*\$false')
# ConvertTo-Json stops at depth 2 and turns the date filter into "System.Collections.Hashtable".
Assert 'searching-document serialises the body deep enough' ($sdText -match 'ConvertTo-Json -Depth [3-9]')
# Read-only: it names the search and the file GET, never a collection write or a file upload.
Assert 'searching-document names no write endpoint' (-not ($sdText -match '/upsert|/delete|/upload|set_payload|delete_points'))
# file_path is spliced into the URL; a space or # would cut the request short.
Assert 'searching-document escapes the file path' ($sdText -match 'EscapeDataString')
Assert 'searching-document does not overwrite an existing PDF' ($sdText -match 'Test-Path -LiteralPath \$dest')

# 마켓플레이스 전체 검증은 tests/test_control_tower.ps1 이 한 번 실행한다.

Write-Host ''
Write-Host ("PASS={0} FAIL={1}" -f $script:Pass, $script:Fail)
if ($script:Fail -ne 0) { exit 1 }
