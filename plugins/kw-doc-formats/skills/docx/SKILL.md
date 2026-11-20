---
name: docx
description: 워드 문서(.docx)를 만들거나 읽을 때 document-skills:docx와 함께 반드시 연다. 공식 스킬이 쓰라는 npm docx 와 pandoc 은 이 PC에 없다. 여기서는 python-docx 로 만들고 markitdown 으로 읽는다.
---

# 워드 문서를 만들고 읽을 때

**`kw-doc-formats:common` 을 함께 본다.** 파일을 열고 쓸 때의 인코딩과, 어떤 형식이 바로
읽히는지가 거기 있다.

일반적인 워드 문서 다루기는 `document-skills:docx` 에 있다. 여기는 이 PC에서 그 기본값이 틀리거나
그 도구가 없는 자리만 적는다.

## 이 PC에서는 python-docx 로 만들고 markitdown 으로 읽는다

공식 `document-skills:docx` 는 만들 때 npm `docx` 를, 읽을 때 `pandoc` 을 쓰라고 한다.
**이 PC에는 둘 다 없다.** kw-control-tower 가 깔아 주는 것은 `python-docx` 와 `markitdown` 이므로
그 둘을 쓴다.

```python
import docx                        # 만들 때
d = docx.Document()
d.add_paragraph("보고서 본문")
d.save("보고서.docx")
```

```
python -m markitdown 보고서.docx    # 읽을 때
```

공식 스킬의 주석 달기와 `document.xml` 직접 수정 방법은 그대로 쓴다. 다만 공식 스킬이
LibreOffice(`soffice.py`·`accept_changes.py`)로 하는 단계는 **이 PC 에서 실패한다.** LibreOffice 가
없기 때문이다. 결과 PDF 확인과 변경 추적 받아들이기는 워드 COM 으로 하고, `.doc` 변환은 아래 표대로 한다.

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

## 제목 왼쪽에 작은 점이 보이면 단락 설정을 끈다

워드에서 서식 기호 보기(¶)를 켜면 제목 같은 단락 왼쪽에 작은 검은 점이 보인다. 인쇄되지는 않지만
문서를 받은 사람의 화면에도 보여서 사용자가 지워 달라고 한다. 이 점은 그 단락에 **다음 단락과 함께**,
**현재 단락을 나누지 않음**, **단락 앞에서 페이지 나누기** 중 하나가 켜져 있다는 표시다.

`python-docx` 1.2.0 의 빈 문서는 `Heading 1`·`Heading 2` 스타일에 앞의 두 설정을 켜 둔다(2026-11-20
확인, `Title` 은 꺼져 있다). 그래서 따로 설정하지 않아도 모든 제목에 점이 생긴다. 문서를 만들 때 제목
스타일에서 두 설정을 끄고, 단락에도 세 설정을 켜지 않는다.

```python
for name in ("Heading 1", "Heading 2", "Heading 3"):
    pf = d.styles[name].paragraph_format
    pf.keep_with_next = False
    pf.keep_together = False
# 단락마다 keep_with_next · keep_together · page_break_before 를 True 로 두지 않는다
```

두 설정을 끄면 제목이 페이지 맨 아래에 홀로 남거나 그림 설명이 그림과 다른 페이지로 갈 수 있다.
결과를 PDF 로 바꿔 그런 곳을 찾고, 그 제목 바로 앞 단락 끝에 페이지 나누기 문자를 넣어 고친다
(`run.add_break(WD_BREAK.PAGE)`). 페이지 나누기 문자는 단락 설정이 아니어서 점이 생기지 않는다.

## 아직 재지 않은 것

`python-docx` 1.2.0 이 만드는 빈 문서를 열어 보면 테마의 로마자 글꼴 슬롯이 Calibri 이고
동아시아 슬롯이 비어 있으며, 스타일 기본값의 언어 태그가 동아시아까지 `en-US` 다. 발표자료에서
같은 종류의 기본값이 한글을 상하게 하는 것을 실측했으므로 워드에서도 그럴 수 있다.

**다만 그것이 실제로 어떻게 보이는지는 아직 재지 않았다.** 이 문서를 쓴 PC에 워드가 없어
만든 문서를 열어 견줄 수 없었다. 워드가 있는 PC에서 한글이 든 문서를 만들어 열고, 슬롯을
채운 것과 안 채운 것을 나란히 놓고 본 뒤에 규칙을 적는다. 그 전에는 짐작으로 적지 않는다.
