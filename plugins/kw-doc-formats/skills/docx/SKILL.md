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

## 아직 재지 않은 것

`python-docx` 1.2.0 이 만드는 빈 문서를 열어 보면 테마의 로마자 글꼴 슬롯이 Calibri 이고
동아시아 슬롯이 비어 있으며, 스타일 기본값의 언어 태그가 동아시아까지 `en-US` 다. 발표자료에서
같은 종류의 기본값이 한글을 상하게 하는 것을 실측했으므로 워드에서도 그럴 수 있다.

**다만 그것이 실제로 어떻게 보이는지는 아직 재지 않았다.** 이 문서를 쓴 PC에 워드가 없어
만든 문서를 열어 견줄 수 없었다. 워드가 있는 PC에서 한글이 든 문서를 만들어 열고, 슬롯을
채운 것과 안 채운 것을 나란히 놓고 본 뒤에 규칙을 적는다. 그 전에는 짐작으로 적지 않는다.
