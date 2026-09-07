---
name: hwp
description: 한글 파일(.hwp, .hwpx)이나 구형 오피스 파일(.doc, .ppt, .xls)을 받았을 때 반드시 연다. 클로드가 바로 읽지 못하는 형식들이라 한 단계를 거쳐야 한다. 담당자 PC에 깔린 한/글과 오피스를 조종해 최신 형식으로 바꾸는 방법이 여기 있다.
---

# 한글과 구형 오피스 파일을 넘겨받았을 때

**`kw-doc-formats:common` 을 함께 본다.** 파일을 열고 쓸 때의 인코딩과, 어떤 형식이 바로
읽히는지가 거기 있다.

## 한글 파일을 다루는 법

담당자 PC에 한/글이 깔려 있으면 **자동으로 바꿀 수 있다.** 사람이 파일을 하나씩 열 필요가 없다.

목적에 따라 형식을 고른다.

- **내용을 읽어야 한다** → `PDF` 로 바꾼다. 표와 배치가 살아 있는 채로 그대로 읽을 수 있다.
- **글자만 뽑아 가공한다** → `UNICODE` 로 바꾼다. `TEXT` 로 하면 구형 한국어 인코딩으로 나와서
  읽을 때 글자가 전부 깨진다. 반드시 `UNICODE` 를 쓴다.

```powershell
# 경로는 반드시 절대경로로 준다. 원본은 건드리지 말고 결과를 새 파일로 낸다.
$src = 'C:\...\문서.hwp'
$out = 'C:\...\문서.pdf'

# 한/글이 이미 떠 있으면 실행하지 않는다. 아래 Quit 이 담당자가 열어 둔 문서까지 닫는다.
# 왜 그런지는 kw-doc-formats:common 의 「오피스 프로그램을 COM 으로 부를 때」에 있다.
if (@(Get-Process Hwp -ErrorAction SilentlyContinue).Count -gt 0) {
    throw "한/글이 실행 중입니다. 닫아 달라고 요청한 뒤에 다시 실행하십시오."
}

$h = New-Object -ComObject HWPFrame.HwpObject
$h.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule") | Out-Null
$h.Open($src, "HWP", "forceopen:true") | Out-Null
$h.SaveAs($out, "PDF", "") | Out-Null      # 텍스트로 뽑을 때는 "UNICODE"
try { $h.Clear(1) } catch {}
try { $h.Quit() } catch {}
[Runtime.InteropServices.Marshal]::ReleaseComObject($h) | Out-Null
```

`Open` 은 인자를 셋 받는다. 하나만 주면 실패한다. `RegisterModule` 이 `False` 를 돌려줘도
그대로 진행하면 된다.

**주의할 것.** 한/글 2010에서 확인한 방법이다. 최신 한/글은 파일을 열 때 승인 창을 띄울 수
있고, 그러면 사람이 눌러 줄 때까지 멈춘다. 응답이 없으면 화면에 창이 떠 있는지 확인하고,
사용자에게 눌러 달라고 요청한다.

여러 파일을 한 번에 바꿀 때는 한/글을 한 번만 띄우고 `Open` 과 `SaveAs` 만 반복한다.
파일마다 새로 띄우면 몹시 느리다.

**한/글이 없는 PC라면** 이 길이 막힌다. 문서를 가진 사람에게 PDF로 다시 받는 것이 가장 빠르다.

## 구형 워드·PPT를 넘겨받았을 때

`.doc` 와 `.ppt` 는 읽는 도구가 없다. 워드나 파워포인트로 열어 **다른 이름으로 저장**해서
`.docx` · `.pptx` 로 바꾸면 그다음부터는 다 된다. 한 번 바꿔 두면 계속 쓸 수 있으니
매번 변환하는 절차를 만들 필요는 없다.
