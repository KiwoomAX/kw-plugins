# Node.js 를 winget 으로 최신 LTS 로 업데이트하고 결과를 기록 파일에 남긴다. 동기화 단계 10 이 별도 프로그램으로
# 띄우고 기다리지 않는다. 그래서 이 스크립트가 끝날 때까지 세션 시작이 멈추지 않는다.
#
#   pwsh -NoProfile -ExecutionPolicy Bypass -File update-node.ps1 -Log <기록 파일>
#
# 성공했는지는 다음 세션에 세션 점검 훅이 node.exe 의 버전을 다시 읽어 판정한다. 이 스크립트는 사람이 원인을
# 찾을 수 있도록 winget 의 출력과 종료 코드와 실행 뒤의 버전을 남기기만 한다.

param([Parameter(Mandatory)][string]$Log)

$ErrorActionPreference = 'Continue'
try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false) } catch { }
$lines = New-Object System.Collections.ArrayList
[void]$lines.Add("$(Get-Date -Format o) 시작")
$wg = (Get-Command winget -ErrorAction SilentlyContinue | Select-Object -First 1).Source
if (-not $wg) {
    [void]$lines.Add('winget 찾기 실패: PATH 에 winget 없음')
} else {
    # Node.js 는 모든 사용자용으로 설치되므로 winget 이 관리자 승인 창을 띄운다. 승인을 거부하면 종료 코드로 남는다.
    $out = & $wg install --id OpenJS.NodeJS.LTS --exact --source winget --silent `
        --accept-source-agreements --accept-package-agreements --disable-interactivity 2>&1
    $rc = $LASTEXITCODE
    foreach ($l in $out) { [void]$lines.Add("$l") }
    [void]$lines.Add("winget 종료 코드: $rc")
}
$node = "$env:ProgramFiles\nodejs\node.exe"
if (Test-Path -LiteralPath $node) {
    $fv = [System.Diagnostics.FileVersionInfo]::GetVersionInfo($node)
    [void]$lines.Add("실행 뒤 버전: $($fv.FileMajorPart).$($fv.FileMinorPart).$($fv.FileBuildPart) ($node)")
}
[void]$lines.Add("$(Get-Date -Format o) 끝")
[System.IO.File]::WriteAllLines($Log, [string[]]@($lines), (New-Object System.Text.UTF8Encoding($false)))
