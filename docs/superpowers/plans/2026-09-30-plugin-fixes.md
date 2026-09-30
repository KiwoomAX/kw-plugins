# 휘하 플러그인 결함 수정 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** kw-doc-formats·kw-devops 의 예제와 설명과 검사가 이 PC 에서 그대로 따라도 깨지지 않게 하고, 금지어 워크플로가 PR 을 하나만 유지하게 한다.

**Architecture:** 스킬 문서(SKILL.md)의 예제 코드와 설명을 고치고, 각 플러그인의 계약 검사(`tests/test_*.ps1`)에 그 규칙을 못 박는다. 스크립트는 `pick_port.py`·`fetch_manifest.py` 두 개만 고친다.

**Tech Stack:** PowerShell 7, Python 3.12, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-30-review-followups-design.md`

## Global Constraints

- `docs/superpowers/plans/2026-09-30-control-tower-followups.md` 를 먼저 끝낸 뒤 진행한다. 그 계획의 Task 12 가 `tests/test_doc_formats.ps1`·`test_devops.ps1` 의 validate 절을 지운다.
- 행 번호는 모두 origin/main `c75a44f` 기준이다. 앞 Task 가 같은 파일을 바꾼 뒤에는 번호가 밀리므로, 함께 적은 코드 문자열과 검사 이름으로 위치를 찾는다.
- kw-devops 스킬 파일에 날짜(`20\d\d-\d\d-\d\d`)와 「실측」을 쓰지 않는다. `tests/test_devops.ps1` 이 검출한다. kw-doc-formats 에는 이 검사가 없으나 새로 넣는 문장에도 쓰지 않는다.
- 스킬 파일에 `python3` 을 쓰지 않는다. 호출은 `python` 이다.
- PowerShell 파일에 BOM 을 붙이지 않는다. 이미 BOM 이 있는 `tests/test_devops.ps1` 은 그대로 둔다.
- 공개 저장소의 AX 팀 메일과 `/home/chshin84/opt` 경로와 서버 주소는 건드리지 않는다.
- Task 마다 실패 확인은 그 Task 에 적은 검사 파일로 하고, 커밋 전 통과 확인은 README 「손으로 고칠 때 지킬 것」대로 검사 넷(`test_control_tower.ps1`·`test_doc_formats.ps1`·`test_devops.ps1`·`test_dashboard.ps1`)을 모두 실행한다. 기대는 `실패 없음` 또는 `FAIL=0` 이다.

## Review Focus

- 한/글이 파일을 못 여는 문서(암호, 손상)를 hwp 예제대로 변환한 실행 — 빈 PDF 를 만들지 않고 멈추고 한/글이 남지 않아야 한다. Task 1 의 검사가 예제의 구조(반환값 확인과 `finally`)를 확인한다. 한/글 `Open` 이 암호 문서에서 `False` 를 돌려주는지는 확인하지 못했다.
- `koreanize_theme(p, p)` 처럼 같은 파일을 입력과 출력으로 준 호출(`Z:\` 와 `\\cifs\` 처럼 표기가 달라도) — 원본을 비우지 않고 오류로 멈춰야 한다. Task 1 의 검사가 확인한다.
- 엑셀·파워포인트·워드를 켜 둔 채 공식 스킬의 LibreOffice 단계를 만난 세션 — COM 대체 경로로 가되 켜진 프로그램을 닫게 하지 않고 사용자에게 요청해야 한다. Task 2 의 검사 세 개가 확인한다.
- `file_path` 에 공백·`#` 이 든 리포트, 같은 이름의 PDF 가 이미 있는 폴더 — 요청이 잘리지 않고, 기존 파일을 덮지 않아야 한다. Task 5 의 검사가 확인한다.
- 등록부 조회와 삽입 사이에 남이 같은 포트를 넣은 경합 — 「남이 먼저 잡았다」로 알아봐야 한다. Task 6 의 자체 검사가 확인한다.

---

### Task 1: 문서 형식 COM 예제가 원본과 사용자 프로그램을 지킨다

**Files:**
- Modify: `plugins/kw-doc-formats/skills/xlsx/SKILL.md:61`
- Modify: `plugins/kw-doc-formats/skills/hwp/SKILL.md:32-38`
- Modify: `plugins/kw-doc-formats/skills/pptx/SKILL.md` (81행 `import`, `koreanize_theme` docstring 뒤, 137행 `import`, `strip_text_outline` docstring 뒤)
- Test: `tests/test_doc_formats.ps1` (「skills」 절 끝)

**Interfaces:**
- Produces: `tests/test_doc_formats.ps1` 의 `# The monolith is gone` 절 바로 위에 넣는 검사 묶음. Task 2 가 그 아래에 이어 넣는다.

- [ ] **Step 1: 실패하는 검사를 넣는다**

`tests/test_doc_formats.ps1` 의 `# The monolith is gone` 절 바로 위에 넣는다.

```powershell
# Worked examples are copied as they are, so an unsafe example is an unsafe run.
# DisplayAlerts is off in the Excel example, so a Save() there overwrites the original silently.
Assert 'xlsx COM example does not save over the original' (-not ((Body 'xlsx') -match '\$wb\.Save\(\)'))
# A failed Open must not leave a windowless Hwp.exe behind; the next run would stop at the "already running" check.
Assert 'hwp COM example cleans up in finally' ((Body 'hwp') -match '(?s)try \{.*?\$h\.Open.*?\} finally \{.*?\$h\.Quit\(\)')
Assert 'hwp COM example stops when Open fails' ((Body 'hwp') -match 'if \(-not \$h\.Open\(')
# zipfile opens dst for writing before it reads src; the same file empties the deck. samefile also
# catches the same file written two ways (a mapped drive and its UNC path).
Assert 'pptx zip rewriters refuse to write over their source' ([regex]::Matches((Body 'pptx'), 'os\.path\.exists\(dst\) and os\.path\.samefile\(src, dst\)').Count -eq 2)
```

- [ ] **Step 2: 실패를 확인한다**

Run: `pwsh -NoProfile -ExecutionPolicy Bypass -File tests\test_doc_formats.ps1`
Expected: `xlsx COM example does not save over the original`, `hwp COM example cleans up in finally`, `hwp COM example stops when Open fails`, `pptx zip rewriters refuse to write over their source` 가 `FAIL`

- [ ] **Step 3: xlsx 주석을 고친다**

61행을 바꾼다.

```powershell
    if ($wb) { $wb.Close($false) }   # 원본에 저장하지 않는다. 결과가 필요하면 앞에서 $wb.SaveAs(스크래치패드 경로) 로 새 파일에 낸다
```

- [ ] **Step 4: hwp 예제를 finally 로 감싼다**

32–38행(`$h = New-Object …` 부터 `ReleaseComObject($h)` 까지)을 바꾼다.

```powershell
$h = New-Object -ComObject HWPFrame.HwpObject
try {
    $h.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule") | Out-Null
    # 못 열었는데 계속하면 빈 문서가 PDF 로 저장된다.
    if (-not $h.Open($src, "HWP", "forceopen:true")) { throw "한/글이 파일을 열지 못했습니다: $src" }
    $h.SaveAs($out, "PDF", "") | Out-Null      # 텍스트로 뽑을 때는 "UNICODE"
} finally {
    # 중간에 실패해도 한/글을 닫는다. 안 닫으면 창 없는 Hwp.exe 가 남아 다음 실행이 위 검사에서 멈춘다.
    try { $h.Clear(1) } catch {}
    try { $h.Quit() } catch {}
    [Runtime.InteropServices.Marshal]::ReleaseComObject($h) | Out-Null
}
```

- [ ] **Step 5: pptx 두 함수에 같은 파일 검사를 넣는다**

81행 `import re, zipfile` 을 `import os, re, zipfile` 로 바꾸고, `def koreanize_theme(...)` 의 docstring 바로 아래에 넣는다.

```python
    # 표기가 달라도(Z:\ 와 \\cifs\) 같은 파일이면 거부한다. 쓰기 모드가 원본을 먼저 비운다.
    if os.path.exists(dst) and os.path.samefile(src, dst):
        raise ValueError("src 와 dst 가 같은 파일이다. 다른 경로로 낸다")
```

두 번째 코드 블록의 `import re, zipfile`(원래 137행) 을 `import os, re, zipfile` 로 바꾸고, `def strip_text_outline(...)` 의 docstring 바로 아래에 같은 세 줄을 넣는다.

- [ ] **Step 6: 통과를 확인한다**

Run: 검사 넷. Expected: 모두 실패 없음

- [ ] **Step 7: 커밋한다**

```bash
git add plugins/kw-doc-formats/skills tests/test_doc_formats.ps1
git commit -m "fix: 문서 형식 COM 예제가 원본을 덮지 않고 실패해도 프로그램을 닫는다"
```

---

### Task 2: 문서 형식 설명을 바로잡고 LibreOffice 단계를 COM 으로 잇는다

공식 document-skills 는 LibreOffice(`soffice`)로 엑셀 수식을 계산하고 결과를 PDF 로 확인하는데, 설치기가 LibreOffice 를 깔지 않아 사내 PC 에서 실패한다. kw 보정 스킬에 COM 대체 경로를 적는다.

**Files:**
- Modify: `plugins/kw-doc-formats/skills/hwp/SKILL.md:3`
- Modify: `plugins/kw-doc-formats/skills/xlsx/SKILL.md` (44행 절 머리, COM 예제의 확인 주석)
- Modify: `plugins/kw-doc-formats/skills/docx/SKILL.md` (17행, 31–32행)
- Modify: `plugins/kw-doc-formats/skills/pptx/SKILL.md` (COM 확인 예제의 코드 블록 뒤)
- Modify: `plugins/kw-doc-formats/skills/common/SKILL.md:114`
- Modify: `plugins/kw-doc-formats/.claude-plugin/plugin.json:5`, `.claude-plugin/marketplace.json` (kw-doc-formats 항목의 description)
- Test: `tests/test_doc_formats.ps1` (101·111행과 새 검사)

**Interfaces:**
- Consumes: Task 1 이 넣은 검사 묶음(그 아래에 이어 넣는다).

- [ ] **Step 1: 실패하는 검사를 넣고 느슨한 검사 두 개를 조인다**

101행과 111행을 바꾼다. 지금 정규식은 `.docx` 와 아무 `ln` 에도 맞아 규칙이 지워져도 통과한다.

```powershell
Assert 'hwp covers legacy Office files' ((Body 'hwp') -match '(?m)^## 구형 워드·PPT')
```

```powershell
Assert 'pptx removes the glyph outline' ((Body 'pptx') -match 'def strip_text_outline')
```

Task 1 의 검사 아래에 넣는다.

```powershell
# .xls is read directly (common's table); only .doc and .ppt need converting.
Assert 'hwp does not claim legacy Excel' (-not ((Desc 'hwp') -match '\.xls'))
# The Python libraries come from the control tower's requirements.txt, not from kw_install.
Assert 'the plugin description names the control tower as the library installer' ($null -ne $plugin -and $plugin.description -match 'kw-control-tower')
Assert 'docx names the control tower as the library installer' (-not ((Body 'docx') -match '설치기가 깔아 주는 것은'))
# kw_install does not install LibreOffice, so the official skills' soffice steps fail here.
foreach ($n in @('xlsx', 'docx', 'pptx')) {
    Assert "$n routes the official LibreOffice step to COM" ((Body $n) -match 'LibreOffice')
}
# The Excel replacement for recalc.py reads error values, not display text: a narrow column shows ####.
Assert 'xlsx finds formula errors by value, not by display text' ((Body 'xlsx') -match 'SpecialCells\(-4123, 16\)')
Assert 'docx no longer says the rest of the official skill works as is' (-not ((Body 'docx') -match '나머지 조언은 그대로 쓸 수 있다'))
# Each COM example stops before touching an Office program the user has open.
Assert 'xlsx COM example checks for a running Excel first' ((Body 'xlsx') -match 'Get-Process EXCEL')
Assert 'pptx COM example checks for a running PowerPoint first' ((Body 'pptx') -match 'Get-Process POWERPNT')
Assert 'docx COM example checks for a running Word first' ((Body 'docx') -match 'Get-Process WINWORD')
```

- [ ] **Step 2: 실패를 확인한다**

Run: `pwsh -NoProfile -ExecutionPolicy Bypass -File tests\test_doc_formats.ps1`
Expected: `hwp does not claim legacy Excel`, `the plugin description names the control tower as the library installer`, `docx names the control tower as the library installer`, `xlsx·docx·pptx routes the official LibreOffice step to COM`(세 줄), `xlsx finds formula errors by value, not by display text`, `docx no longer says the rest of the official skill works as is`, `docx COM example checks for a running Word first` 가 `FAIL`. 조인 두 검사와 엑셀·파워포인트 실행 확인 검사는 통과한다.

- [ ] **Step 3: hwp 설명과 플러그인 설명과 docx 설치 주체를 고친다**

hwp 3행에서 `구형 오피스 파일(.doc, .ppt, .xls)` 을 `구형 오피스 파일(.doc, .ppt)` 로 바꾼다.

`plugin.json` 5행과 `marketplace.json` 의 kw-doc-formats description 에서 `kw_install이 깔아 주는 파이썬 라이브러리와 Poppler를 전제한다.` 를 아래로 바꾼다. 두 문장이 글자 그대로 같아야 기존 검사 `both descriptions are the same text` 가 통과한다.

```
kw-control-tower가 깔아 주는 파이썬 라이브러리와 kw_install이 깔아 주는 Poppler를 전제한다.
```

docx 17행 `설치기가 깔아 주는 것은 \`python-docx\` 와 \`markitdown\` 이므로` 를 `kw-control-tower 가 깔아 주는 것은 \`python-docx\` 와 \`markitdown\` 이므로` 로 바꾼다.

- [ ] **Step 4: xlsx 에 recalc.py 대체를 적는다**

44행 `### COM 을 꼭 써야 한다면` 바로 아래, 코드 블록 앞에 넣는다.

```markdown
공식 `document-skills:xlsx` 는 수식이 든 파일마다 `recalc.py` 로 LibreOffice 를 실행해 계산하고, 오류 값을
세고, 계산 결과를 파일에 다시 쓰라고 한다. **이 PC 에는 LibreOffice 가 없어 그 단계가 실패한다.** 셋 다
아래 COM 예제로 한다. 계산은 `CalculateFullRebuild()`, 오류 값은 수식 셀 가운데 오류인 셀만 고르는
`SpecialCells(-4123, 16)`, 결과는 `SaveAs` 로 스크래치패드의 새 파일에 쓴다. 표시 문자열로 오류를
판정하지 않는다. 열이 좁으면 숫자도 `####` 으로 보인다.
```

같은 절 코드 블록의 `    # ... 확인할 값을 여기서 Write-Output 한다` 줄을 아래로 바꾼다.

```powershell
    foreach ($s in $wb.Worksheets) {
        # -4123 은 수식 셀, 16 은 오류 값이다. 해당 셀이 없으면 예외가 난다.
        try { $e = $s.UsedRange.SpecialCells(-4123, 16) } catch { $e = $null }
        if ($e) { "오류: $($s.Name)!$($e.Address(0,0))" }
    }
    $wb.SaveAs($out)   # 계산 결과가 박힌 새 파일. $out 은 스크래치패드의 절대경로
```

- [ ] **Step 5: docx 에 워드 COM 대체를 적는다**

31–32행(`공식 스킬의 나머지 조언은 그대로 쓸 수 있다. …도구를 고르는 자리만 다르다.`)을 바꾼다.

````markdown
공식 스킬의 변경 추적·주석·`document.xml` 직접 수정 방법은 그대로 쓴다. 다만 공식 스킬이
LibreOffice(`soffice.py`·`accept_changes.py`)로 하는 단계는 **이 PC 에서 실패한다.** LibreOffice 가
없기 때문이다. 결과 확인과 변경 추적은 워드 COM 으로 하고, `.doc` 변환은 아래 표대로 한다.

| 공식 스킬의 단계 | 이 PC 의 대체 방법 |
|---|---|
| 결과를 PDF 로 바꿔 확인 | 아래 예제의 `ExportAsFixedFormat` |
| 변경 추적 받아들이기 | 아래 예제의 `Revisions.AcceptAll()` 뒤 새 이름으로 저장 |
| `.doc` 를 `.docx` 로 변환 | `kw-doc-formats:hwp` 의 「구형 워드·PPT를 넘겨받았을 때」(사용자가 워드로 열어 다른 이름으로 저장) |

```powershell
# 워드가 떠 있으면 실행하지 않는다. 아래 Quit 이 열어 둔 문서까지 닫는다.
# 왜 그런지는 kw-doc-formats:common 의 「오피스 프로그램을 COM 으로 부를 때」에 있다.
if (@(Get-Process WINWORD -ErrorAction SilentlyContinue).Count -gt 0) {
    throw "워드가 실행 중입니다. 사용자에게 닫아 달라고 요청한 뒤에 다시 실행하십시오."
}

# 경로는 셋 다 절대경로로 준다. 상대경로는 워드의 기본 폴더 기준으로 풀린다.
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
$doc = $null
try {
    $doc = $word.Documents.Open($path, $false, $true)   # 읽기 전용
    $doc.ExportAsFixedFormat($pdf, 17)                   # 17 은 PDF 다. $pdf 는 스크래치패드의 절대경로
    # 변경 추적을 받아들일 때: $doc.Revisions.AcceptAll(); $doc.SaveAs2($newPath)   # $newPath 는 원본이 아닌 새 절대경로
} finally {
    if ($doc) { $doc.Close(0) }                          # 0 은 저장하지 않음이다
    $word.Quit()                                          # 위 검사를 통과했으므로 이 스크립트가 시작한 인스턴스다
    [Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
}
```
````

- [ ] **Step 6: pptx 에 시각 확인 대체를 적는다**

COM 확인 예제의 코드 블록 끝(원래 117행, `if ($deck) { $deck.Close() }` 가 든 블록의 닫는 펜스) 뒤에 넣는다.

````markdown
### 결과를 눈으로 확인할 때

공식 `document-skills:pptx` 의 시각 확인은 `soffice.py` 로 PDF 를 만들고 `pdftoppm` 으로 이미지를
뽑는다. **이 PC 에는 LibreOffice 가 없어 앞 단계가 실패한다.** PDF 는 파워포인트 COM 으로 만들고
`pdftoppm` 은 그대로 쓴다(Poppler 는 설치기가 깐다). 위 예제의 `try` 안에서 한 줄이면 된다.

```powershell
    $deck.SaveAs($pdf, 32)    # 32 는 PDF 다. $pdf 는 스크래치패드의 절대경로
```

`.ppt` 를 `.pptx` 로 바꾸는 단계는 `kw-doc-formats:hwp` 의 「구형 워드·PPT를 넘겨받았을 때」를 따른다.
````

- [ ] **Step 7: common 의 COM 예제 목록에 docx 를 추가한다**

114행 `` `kw-doc-formats:xlsx` 와 `kw-doc-formats:pptx` 와 `kw-doc-formats:hwp` 의 COM 예제가 `` 를 `` `kw-doc-formats:xlsx` 와 `kw-doc-formats:pptx` 와 `kw-doc-formats:docx` 와 `kw-doc-formats:hwp` 의 COM 예제가 `` 로 바꾼다.

- [ ] **Step 8: 통과를 확인한다**

Run: 검사 넷. Expected: 모두 실패 없음

- [ ] **Step 9: 커밋한다**

```bash
git add plugins/kw-doc-formats .claude-plugin/marketplace.json tests/test_doc_formats.ps1
git commit -m "fix: 문서 형식 설명을 바로잡고 공식 스킬의 LibreOffice 단계를 오피스 COM 으로 잇는다"
```

---

### Task 3: 배포 스킬의 메일 스크립트를 pwsh 로 호출하고 조직 자격증명 이름을 적는다

**Files:**
- Modify: `plugins/kw-devops/skills/deploying-kiwoom-service/SKILL.md:86, 184`
- Modify: `plugins/kw-devops/skills/deploying-kiwoom-service/compose-and-env.md:61`
- Test: `tests/test_devops.ps1:71-72` 과 새 검사

**Interfaces:**
- 없음.

- [ ] **Step 1: 검사를 고치고 넣는다**

71–72행을 바꾼다. 지금 검사는 `powershell`(5.1)로 호출하는 줄만 찾아, 결함을 통과 조건으로 못 박고 있다.

```powershell
# request-ax.ps1 has no BOM on purpose, so Windows PowerShell 5.1 would read its Korean as cp949.
$axCalls = [regex]::Matches($text, '(?m)^(pwsh|powershell)\b.*request-ax\.ps1.*$')
Assert 'every request-ax.ps1 call goes through CLAUDE_SKILL_DIR' ($axCalls.Count -gt 0 -and @($axCalls | Where-Object { $_.Value -notmatch '"\$\{CLAUDE_SKILL_DIR\}/scripts/request-ax\.ps1"' }).Count -eq 0)
Assert 'every request-ax.ps1 call runs in PowerShell 7' ($axCalls.Count -gt 0 -and @($axCalls | Where-Object { $_.Value -notmatch '^pwsh\b' }).Count -eq 0)
# env-<조직> reads as env-KiwoomAX; the real credential ids are env-ax and env-am.
$composeText = [IO.File]::ReadAllText((Join-Path $SkillDir 'compose-and-env.md'))
Assert 'the org credential is named env-ax or env-am where it is introduced' (($text -match 'env-ax') -and ($composeText -match 'env-ax'))
```

- [ ] **Step 2: 실패를 확인한다**

Run: `pwsh -NoProfile -ExecutionPolicy Bypass -File tests\test_devops.ps1`
Expected: `every request-ax.ps1 call runs in PowerShell 7` 와 `the org credential is named env-ax or env-am where it is introduced` 가 `FAIL`

- [ ] **Step 3: 구현한다**

SKILL.md 184행 맨 앞 `powershell -NoProfile` 을 `pwsh -NoProfile` 로 바꾼다.

SKILL.md 86행 셋째 칸을 바꾼다.

```markdown
| 소속 조직 | GitHub remote | 등록부 `org` 칸, `envCredIds` 의 조직 자격증명(KiwoomAX 는 `env-ax`, KiwoomAM 은 `env-am`) |
```

compose-and-env.md 61행의 `` `env-<조직>`(조직 공통) `` 을 `` `env-ax`·`env-am`(조직 공통) `` 으로 바꾼다.

- [ ] **Step 4: 통과를 확인한다**

Run: 검사 넷. Expected: 모두 실패 없음

- [ ] **Step 5: 커밋한다**

```bash
git add plugins/kw-devops/skills/deploying-kiwoom-service tests/test_devops.ps1
git commit -m "fix: 배포 스킬이 메일 스크립트를 pwsh 로 호출하고 조직 자격증명을 실제 이름으로 적는다"
```

---

### Task 4: 로컬 검증 명령과 매니페스트 스크립트의 출력을 고친다

**Files:**
- Modify: `plugins/kw-devops/skills/deploying-kiwoom-service/local-verify.md:22`
- Modify: `plugins/kw-devops/skills/searching-winus/scripts/fetch_manifest.py` (`main`)
- Test: `tests/test_devops.ps1`

**Interfaces:**
- 없음.

`fetch_manifest.py --selfcheck` 는 ASCII 만 출력해 경고 출력 경로에 닿지 않는다. 그래서 실행 검사를 두지 않고, 출력 인코딩을 고정하는 두 줄이 있는지만 본다.

- [ ] **Step 1: 실패하는 검사를 넣는다**

`--- searching-winus ---` 절 끝(`fetch_manifest.py asks for no document TTL` 아래)에 넣는다.

```powershell
# The stale-copy warning carries an em dash that cp949 lacks; without these two lines the fallback dies while printing it.
Assert 'fetch_manifest.py pins its output to UTF-8' ($fetText -match 'sys\.stdout\.reconfigure\(encoding="utf-8"\)' -and $fetText -match 'sys\.stderr\.reconfigure\(encoding="utf-8"\)')
```

`--- request-ax.ps1 ---` 절 바로 위에 넣는다.

```powershell
# docker-compose.jenkins.yml is written only when there are bind mounts, so most new services have none.
$lvPath = Join-Path $SkillDir 'local-verify.md'
$lv = if (Test-Path $lvPath) { [IO.File]::ReadAllText($lvPath) } else { '' }
Assert 'local-verify adds the Jenkins override only when it exists' ($lv -match 'Test-Path docker-compose\.jenkins\.yml')
```

- [ ] **Step 2: 실패를 확인한다**

Run: `pwsh -NoProfile -ExecutionPolicy Bypass -File tests\test_devops.ps1`
Expected: `fetch_manifest.py pins its output to UTF-8` 와 `local-verify adds the Jenkins override only when it exists` 가 `FAIL`

- [ ] **Step 3: 구현한다**

local-verify.md 22행을 두 줄로 바꾼다(코드 블록 들여쓰기 세 칸을 지킨다). 23행 `docker compose up` 은 그대로 둔다. 덮어쓰기 파일은 서버 경로를 마운트하므로 이 PC 의 실행에는 넣지 않고, 문법·병합 확인에만 쓴다.

```powershell
   $f = @('-f', 'docker-compose.yml'); if (Test-Path docker-compose.jenkins.yml) { $f += @('-f', 'docker-compose.jenkins.yml') }
   docker compose @f config | Out-Null                                                  # 문법·병합
```

fetch_manifest.py 의 `def main() -> None:` 첫 줄로 넣는다.

```python
    # 출력을 UTF-8 로 고정한다. 도구가 파이프로 받으면 한국어 윈도우의 기본은 cp949 이고,
    # 낡은 사본 경고에 든 — 가 거기 없어 경고를 출력하다가 멈춘다.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
```

- [ ] **Step 4: 통과를 확인한다**

Run: 검사 넷. Expected: 모두 실패 없음

- [ ] **Step 5: 커밋한다**

```bash
git add plugins/kw-devops/skills tests/test_devops.ps1
git commit -m "fix: 로컬 검증이 없는 덮어쓰기 파일을 안 쓰고 매니페스트 스크립트가 UTF-8 로 출력한다"
```

---

### Task 5: 리포트 원문을 받을 때 주소를 인코딩하고 기존 파일을 덮지 않는다

**Files:**
- Modify: `plugins/kw-devops/skills/searching-document/SKILL.md:140-141`
- Test: `tests/test_devops.ps1` (`--- searching-document ---` 절)

**Interfaces:**
- 없음.

- [ ] **Step 1: 실패하는 검사를 넣는다**

`searching-document names no write endpoint` 아래에 넣는다.

```powershell
# file_path is spliced into the URL; a space or # would cut the request short.
Assert 'searching-document escapes the file path' ($sdText -match 'EscapeDataString')
Assert 'searching-document does not overwrite an existing PDF' ($sdText -match 'Test-Path -LiteralPath \$dest')
```

- [ ] **Step 2: 실패를 확인한다**

Run: `pwsh -NoProfile -ExecutionPolicy Bypass -File tests\test_devops.ps1`
Expected: `searching-document escapes the file path` 와 `searching-document does not overwrite an existing PDF` 가 `FAIL`

- [ ] **Step 3: 구현한다**

140–141행(`Invoke-WebRequest -Uri "http://192.7.9.45:8600/v1/files/$($p.file_path)" \`` 와 다음 줄)을 바꾼다.

```powershell
$dest = Join-Path $dir $p.source_pdf
if (Test-Path -LiteralPath $dest) { throw "같은 이름의 파일이 이미 있습니다: $dest — 덮어쓸지 사용자에게 묻는다" }
# 경로의 / 는 그대로 두고 조각마다 인코딩한다. 공백이나 # 이 섞이면 요청이 잘린다.
$enc = ($p.file_path -split '/' | ForEach-Object { [uri]::EscapeDataString($_) }) -join '/'
Invoke-WebRequest -Uri "http://192.7.9.45:8600/v1/files/$enc" -OutFile $dest -TimeoutSec 120
```

- [ ] **Step 4: 통과를 확인한다**

Run: 검사 넷. Expected: 모두 실패 없음

- [ ] **Step 5: 커밋한다**

```bash
git add plugins/kw-devops/skills/searching-document/SKILL.md tests/test_devops.ps1
git commit -m "fix: 리포트 원문 주소를 인코딩하고 같은 이름의 파일을 덮지 않는다"
```

---

### Task 6: 포트를 고른 작업 안에서 바로 등록한다

지금은 2단계에서 고르고 빌드 뒤인 5단계에서 넣어, 그 사이 다른 담당자가 같은 포트를 고를 수 있다. 등록에는 컨테이너 이름이 필요한데 그 이름(`kiwoom-<이름>`)은 3단계에서 담당자와 짧은 서비스 이름을 정할 때 정해진다. 그래서 **3단계에서 이름을 정한 직후, 파일을 쓰기 전에** 등록한다. push·빌드·AX 팀 회신을 기다리는 구간이 등록 뒤로 간다.

**Files:**
- Modify: `plugins/kw-devops/skills/deploying-kiwoom-service/SKILL.md` (3단계 110–123행, 5단계 142–155행)
- Modify: `plugins/kw-devops/skills/deploying-kiwoom-service/scripts/pick_port.py` (`등록`, `등록부검사`)
- Test: `tests/test_devops.ps1` (`pick_port.py --check exits 0` 가 자체 검사를 실행한다)

**Interfaces:**
- 없음.

- [ ] **Step 1: 자체 검사에 경합을 넣는다**

`pick_port.py` 의 `등록부검사` 에서 `바뀐줄 = {"수": 1}` 아래에 `경합 = {"켬": False}` 를 넣고, `가짜` 함수의 `기록.append((길, 몸))` 아래에 넣는다.

```python
        if 길 == "/v1/dml/insert" and 경합["켬"]:
            # 조회와 삽입 사이에 남이 같은 포트를 넣은 것을 흉내 낸다. 핸들러는 기본키 충돌로 거부한다.
            표.append({"port": 몸["params"]["port"], "container": "kw-rival", "service_type": "dashboard",
                      "org": "KiwoomAX", "repo": "r"})
            raise SystemExit("핸들러가 거부했다 (HTTP 409)\n  duplicate key")
```

`assert [r["port"] for r in 찾아모으기(...)] ...` 줄 아래에 넣는다.

```python
        경합["켬"] = True
        assert "남이 먼저" in 멈춤(lambda: 등록(9020, "kw-me", "dashboard", "KiwoomAX", "me")), "삽입이 경합으로 거부되면 남이 먼저 잡은 것으로 알린다"
        경합["켬"] = False
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python plugins\kw-devops\skills\deploying-kiwoom-service\scripts\pick_port.py --check`
Expected: `AssertionError: 삽입이 경합으로 거부되면 …`

- [ ] **Step 3: 등록이 거부를 다시 조회해 가린다**

`등록` 의 `_부르기("/v1/dml/insert", {…})` 호출을 `try` 로 감싼다.

```python
    try:
        _부르기("/v1/dml/insert", {
            "sql": "insert into kw_deploy.port (port, container, service_type, org, repo) "
                   "values (%(port)s, %(container)s, %(service_type)s, %(org)s, %(repo)s)",
            "params": {"port": 포트, "container": 컨테이너, "service_type": 종류,
                       "org": 소속, "repo": 저장소},
        })
    except SystemExit:
        # 위 조회와 이 삽입 사이에 남이 같은 포트를 넣으면 기본키 충돌로 거부된다. 다시 조회해 그것인지 가린다.
        나중 = 주인(등록조회(), 포트)
        if 나중 is not None and 나중["container"].lower() != 컨테이너.lower():
            raise SystemExit(f"남이 먼저 잡았다: {포트} {나중['container']}\n  2단계로 돌아가 다시 센다.")
        raise
```

- [ ] **Step 4: 스킬 절차를 옮긴다**

SKILL.md 3단계의 `답을 받으면 차례로 한다.` 목록 맨 앞에 한 항목을 넣고 뒤 번호를 하나씩 민다.

```markdown
1. 컨테이너 이름을 `kiwoom-<짧은 서비스 이름>` 으로 정하고, 처음 올리는 서비스면 2단계의 포트를 **지금 등록한다.**
   명령은 5단계의 `--register` 줄이다. 「남이 먼저 잡았다」고 하면 2단계로 돌아가 다시 고른다. 미루면 push 와
   빌드와 AX 팀 회신을 기다리는 동안 다른 사람이 같은 포트를 고른다.
```

5단계의 `1단계에서 이미 찾은 서비스도 쓸 포트로 한 번 돌린다 — 비어 있는 \`repo\` 칸이 채워진다.` 앞에 한 문장을 넣는다.

```markdown
3단계에서 넣었으면 「이미 등록돼 있다」고 나온다. 그대로 둔다.
```

- [ ] **Step 5: 통과를 확인한다**

Run: `python plugins\kw-devops\skills\deploying-kiwoom-service\scripts\pick_port.py --check` 와 검사 넷
Expected: `검사 통과 — …` 와 모두 실패 없음

- [ ] **Step 6: 커밋한다**

```bash
git add plugins/kw-devops/skills/deploying-kiwoom-service
git commit -m "fix: 배포 스킬이 포트를 이름을 정한 직후 등록하고 삽입 경합을 알아본다"
```

---

### Task 7: 금지어 워크플로가 PR 을 하나만 유지한다

spec 의 「현행 유지」 항목은 워크플로의 매일 실행이다. 이 Task 는 실행 주기를 그대로 두고, 열린 PR 이 있을 때 같은 내용의 PR 이 매일 하나씩 더 열리는 결함만 고친다.

**Files:**
- Modify: `.github/workflows/sync-banned-words.yml` (「PR 을 연다」 단계)
- Test: `tests/test_control_tower.ps1` (「훅이 맞춤을 호출한다」 절의 워크플로 검사 옆)

**Interfaces:**
- 없음.

- [ ] **Step 1: 실패하는 검사를 넣는다**

`Check '목록을 받아 오는 워크플로가 있다'` 아래에 넣는다.

```powershell
# 비교 기준이 main 이라, 열린 PR 이 병합되기 전에는 매일 같은 내용의 PR 이 하나씩 더 열렸다.
# 브랜치를 하나로 고정하고, 그 브랜치가 이미 같은 내용이면 push 하지 않는다.
Check '금지어 워크플로가 브랜치 하나에 PR 하나를 유지한다' {
    $wfText = Get-Content (Join-Path $repo '.github\workflows\sync-banned-words.yml') -Raw -Encoding UTF8
    ($wfText -match 'BRANCH=chore/banned-words-sync') -and ($wfText -notmatch 'date -u') -and
    ($wfText -match 'gh pr list --head') -and ($wfText -match 'git fetch origin "\$BRANCH"')
}
```

- [ ] **Step 2: 실패를 확인한다**

Run: `pwsh -NoProfile -ExecutionPolicy Bypass -File tests\test_control_tower.ps1`
Expected: `금지어 워크플로가 브랜치 하나에 PR 하나를 유지한다` 가 `FAIL`

- [ ] **Step 3: 구현한다**

「PR 을 연다」 단계의 `run:` 을 바꾼다.

```yaml
        run: |
          set -euo pipefail
          # 브랜치를 하나로 고정한다. 이 브랜치는 워크플로만 쓴다. 목록을 고칠 것은 원본 저장소에서 고친다.
          # 날짜를 붙이던 때에는 병합 전까지 매일 같은 내용의 PR 이 하나씩 더 열렸다.
          BRANCH=chore/banned-words-sync
          # 브랜치가 이미 같은 내용이면 push 하지 않는다. 검토 중인 PR 의 head 를 바꾸지 않기 위해서다.
          if git fetch origin "$BRANCH" 2>/dev/null && git show "FETCH_HEAD:$TARGET" > /tmp/branch.md 2>/dev/null \
             && cmp -s /tmp/incoming.md /tmp/branch.md; then
            echo "열린 PR 브랜치가 이미 같은 내용입니다."
            exit 0
          fi
          cp /tmp/incoming.md "$TARGET"
          git config user.name  'github-actions[bot]'
          git config user.email 'github-actions[bot]@users.noreply.github.com'
          git switch -C "$BRANCH"
          git add "$TARGET"
          git commit -m 'chore: 금지어 목록을 원본에서 받아 온다' \
                     -m "원본: $SOURCE" \
                     -m '이 저장소는 만들지 않고 받기만 한다. 목록을 고치려면 KiwoomAX/korean-banned-words 의 데이터를 고친다.'
          git push --force -u origin "$BRANCH"
          if [ -n "$(gh pr list --head "$BRANCH" --state open --json number --jq '.[].number')" ]; then
            echo "열린 PR 이 있어 브랜치만 갱신했습니다."
            exit 0
          fi
          gh pr create \
            --title '금지어 목록을 원본에서 받아 온다' \
            --body "$(printf '%s\n' \
              '`KiwoomAX/korean-banned-words` 의 `dist/korean-banned-words.md` 가 바뀌어 받아 왔습니다.' '' \
              '이 파일은 생성물입니다. 여기서 고치지 마십시오. 고치려면 원본 저장소의 데이터를 고치면 다음 실행이 다시 받아 옵니다.' '' \
              '병합하면 사내 PC 들이 다음 세션에 새 목록을 물어 가고, 그 다음 세션부터 그것으로 돕니다.')"
```

- [ ] **Step 4: 통과를 확인한다**

Run: 검사 넷. Expected: 모두 실패 없음

- [ ] **Step 5: 열린 옛 PR 을 확인한다**

Run: `gh pr list --state open --search "head:chore/banned-words-"`
Expected: 날짜가 붙은 옛 브랜치의 PR 이 열려 있으면 그 목록을 사용자에게 알린다. 새 워크플로는 그 PR 을 보지 못해 첫 실행에 PR 이 하나 더 열리므로, 옛 PR 을 닫을지는 사용자가 정한다. 워크플로를 `workflow_dispatch` 로 실행해 확인하는 일도 원격 저장소에 브랜치를 만드므로 사용자 승인 뒤에 한다.

- [ ] **Step 6: 커밋한다**

```bash
git add .github/workflows/sync-banned-words.yml tests/test_control_tower.ps1
git commit -m "fix: 금지어 워크플로가 고정 브랜치 하나로 PR 을 하나만 유지한다"
```

<!-- spec-review: escalated -->
