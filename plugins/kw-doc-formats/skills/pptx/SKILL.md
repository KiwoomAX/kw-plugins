---
name: pptx
description: 한국어 발표자료(.pptx)를 만들거나 고칠 때 document-skills:pptx와 함께 반드시 연다. 증상이 보이지 않아도 연다. 한국어 슬라이드는 기본값이 틀려 있어 사용자가 알아차린 뒤에는 늦다. 글자 윤곽선과 fontFace와 테마의 로마자 슬롯이 그것이다.
---

# 한국어 발표자료를 만들고 고칠 때

**`kw-doc-formats:common` 을 함께 본다.** 파일을 열고 쓸 때의 인코딩과, 어떤 형식이 바로
읽히는지가 거기 있다.

일반적인 발표자료 다루기는 `document-skills:pptx` 에 있다. 여기는 이 PC에서 그 기본값이 틀리거나
그 도구가 없는 자리만 적는다.

## PPT를 만들 때 항상 지킬 것

`.pptx` 를 새로 만든다면 아래 셋은 **증상이 보이기 전에 미리** 지킨다. 사용자가 "글자가
이상해 보인다"고 말해 준 다음에 고치는 것이 아니다. 한국어 슬라이드에서는 셋 다 기본값이
틀려 있으므로, 만드는 그 자리에서 지키지 않으면 그대로 잘못된 파일이 나간다.

| 만들 때 지킬 것 | 안 지키면 어떻게 되나 |
|---|---|
| 글자에 윤곽선(`outline`)을 주지 않는다 — 언어 불문 | 획이 깎여 가늘고 들쭉날쭉해 보인다 |
| `fontFace` 를 쓰지 않는다 | 슬라이드마다 글꼴이 박혀 사내 표준 테마가 안 먹는다 |
| 다 만든 뒤 테마의 로마자 슬롯을 맑은 고딕으로 바꾼다 | 영문과 숫자가 Calibri 로 나온다 |

셋에는 공통점이 하나 있다. **로마자로 확인하면 셋 다 멀쩡해 보인다.** 확인은 반드시 한글로
한다. 영문 예시만 띄워 놓고 괜찮다고 판단하는 것이 이 셋을 놓치는 전형적인 경로다.

다만 확인이 어려운 것과 규칙에 예외를 두는 것은 다르다. 셋 다 **언어와 무관하게 항상**
지킨다. "이 줄은 영문이니 예외로 해도 되겠다"는 판단은 넣지 않는다.

### 글자에 윤곽선을 주지 마라

**`pptxgenjs` 의 `outline` 옵션을 쓰지 마라. 한글이든 영문이든 예외가 없다.**

```js
// 쓰지 말 것
s.addText("자산운용본부 실적", { outline: { size: 1, color: "FFFFFF" } });
```

언어를 가리지 않는 금지로 두는 이유가 있다. 조건을 붙이면 "이 줄은 영문이니 괜찮겠다"는
판단이 매번 끼어드는데, 한 장의 슬라이드에 한글과 영문이 섞이는 것이 보통이라 그 판단은
거의 항상 틀린다. 게다가 나중에 그 자리에 한글이 들어오면 조용히 깨진다. 조건이 없으면
틀릴 자리도 없다.

**한글에서 특히 심한 것은 사실이다.** 이 옵션은 글자 속성에 `<a:ln w="12700">` 을 박는데,
한글은 획이 촘촘해서 1pt 선이 획 두께의 상당 부분을 먹는다. 그 결과 획이 양쪽에서 깎여 나가
**가늘고 들쭉날쭉해 보인다.** 같은 색 윤곽선을 주면 반대로 획이 부풀어 속공간이 막힌다.
로마자는 획이 굵고 성겨서 덜 티가 날 뿐, 안 상하는 것이 아니다.

실측으로 확인했다. 윤곽선 없는 줄, 같은 색 윤곽선 줄, 흰색 윤곽선 줄을 나란히 만들어
파워포인트로 렌더링하니 셋이 뚜렷이 달랐고, 아래 제거기를 돌린 뒤에는 셋이 똑같아졌다.

글자를 강조하려면 윤곽선 대신 **굵기(`bold`), 크기, 색**을 쓴다. 배경 위에 글자를 얹어야 해서
대비가 필요하면 글자에 선을 두르지 말고 **글자 뒤에 반투명 판을 깐다.**

### `fontFace` 를 쓰지 마라

지정하면 `latin`·`ea`·`cs` **세 슬롯이 한꺼번에** 덮인다. 슬라이드마다 글꼴 이름이 박혀서
사내 표준 테마(`.potx`)를 씌워도 따라오지 않고, 나중에 디자인에서 글꼴을 바꿔도 안 바뀐다.

### 테마의 로마자 슬롯을 맑은 고딕으로 바꿔라

`pptxgenjs` 가 들고 있는 테마는 **영어권 테마**다. 그대로 두면 한국어 파워포인트가 만드는
파일과 다르게 나오고, 글꼴 상자에 `맑은 고딕(본문)` 대신 `Calibri (본문)` 이 뜬다.

파워포인트로 직접 새 파일을 만들어 테마를 뜯어 비교한 결과다.

| 누가 만든 파일인가 | 로마자 슬롯 (`latin`) | 동아시아 슬롯 (`ea`) | 한글 슬롯 (`script="Hang"`) |
|---|---|---|---|
| 한국어 파워포인트가 만든 것 | **맑은 고딕** | 비어 있음 | 맑은 고딕 |
| `pptxgenjs` 가 만든 것 | Calibri | 비어 있음 | 맑은 고딕 |

**한국어 파워포인트는 로마자 슬롯에도 맑은 고딕을 넣는다.** 그래서 네이티브 파일은 영문과
숫자까지 맑은 고딕으로 나온다. `ea` 는 양쪽 다 비워 두므로 건드리지 마라.

`fontFace` 를 빼는 것만으로는 부족하다. 테마가 영어권 그대로라 영문이 Calibri 로 나온다.
다 만든 뒤 테마를 고쳐라. `.pptx` 는 XML 이 든 압축 파일이다.

```python
import re, zipfile

def koreanize_theme(src, dst, font="맑은 고딕"):
    """테마의 제목·본문 로마자 슬롯을 한글 글꼴로 바꾼다. ea 는 비운 채로 둔다."""
    def fix(m):
        blk = m.group(0)
        blk = re.sub(r'<a:latin typeface="[^"]*"([^/>]*)/>', f'<a:latin typeface="{font}"\\1/>', blk, count=1)
        return re.sub(r'<a:ea typeface="[^"]*"\s*/>', '<a:ea typeface=""/>', blk, count=1)
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename.startswith("ppt/theme/") and item.filename.endswith(".xml"):
                data = re.sub(r"<a:(majorFont|minorFont)>.*?</a:\1>", fix,
                              data.decode("utf-8"), flags=re.S).encode("utf-8")
            zout.writestr(item, data)
```

고친 뒤 파워포인트가 실제로 그렇게 인식하는지 확인할 수 있다. COM 으로 물어보면 된다.

```powershell
# 파워포인트가 떠 있으면 실행하지 않는다. 아래 Quit 이 열어 둔 발표자료까지 닫는다.
# 왜 그런지는 kw-doc-formats:common 의 「오피스 프로그램을 COM 으로 부를 때」에 있다.
if (@(Get-Process POWERPNT -ErrorAction SilentlyContinue).Count -gt 0) {
    throw "파워포인트가 실행 중입니다. 닫아 달라고 요청한 뒤에 다시 실행하십시오."
}

$ppt  = New-Object -ComObject PowerPoint.Application
$deck = $null
try {
    $deck = $ppt.Presentations.Open($path, $true, $false, $false)    # 읽기 전용, 창 없이
    $deck.SlideMaster.Theme.ThemeFontScheme.MinorFont.Item(1).Name   # 맑은 고딕 이어야 한다
} finally {
    if ($deck) { $deck.Close() }
    $ppt.Quit()                     # 위 검사를 통과했으므로 내가 띄운 인스턴스다
    [Runtime.InteropServices.Marshal]::ReleaseComObject($ppt) | Out-Null
}
```

### 맞출 수 없는 차이 하나 — `lang` 속성

`lang` 속성은 못 맞춘다. 파워포인트는 한글과 영문을 다른 run 으로 쪼개 각각 `ko-KR` 과
`en-US` 를 붙이는데, pptxgenjs 는 전부 `en-US` 로 둔다. 맞춤법 검사와 줄바꿈 규칙에 영향이
있으나 겉모습은 같다. 손대려면 XML 을 직접 고쳐야 한다.

## 이미 만들어진 PPT에서 윤곽선을 걷어낼 때

여기는 남이 만든 파일이나 예전에 만든 파일을 넘겨받았을 때 쓴다. 새로 만드는 중이라면 위의
'PPT를 만들 때 항상 지킬 것'에서 애초에 윤곽선을 넣지 않는 쪽이 맞다.

사용자가 "글자가 삐뚤삐뚤해 보인다"고 말하지 않아도 된다. 받은 `.pptx` 를 손볼 일이 생기면
제거기를 한 번 돌려 보고 걷어낸 개수를 알려 주면 된다. 0이면 원래 깨끗한 파일이었다는 뜻이라
돌려서 손해 볼 것이 없다.

사람이 매번 Ctrl+A로 고치는 대신 파일을 고친다. `.pptx` 는 XML이 든 압축 파일이다.

```python
import re, zipfile

TEXT_PARTS = ("ppt/slides/", "ppt/slideLayouts/", "ppt/slideMasters/", "ppt/notesSlides/")

# (?<!/) 가 핵심이다. 이것이 없으면 자기닫힘 <a:rPr sz="2400"/> 를 여는 태그로 잘못 보고
# 한참 뒤의 </a:rPr> 까지를 한 구간으로 묶어 버린다. 그 사이에 도형 테두리가 있으면
# 글자 윤곽선인 줄 알고 같이 지워서 슬라이드 디자인이 망가진다. 실제로 그렇게 됐었다.
RE_RPR = re.compile(r"<a:(defRPr|rPr)\b([^>]*?)(?<!/)>(.*?)</a:\1>", re.S)
RE_LN  = re.compile(r"<a:ln\b[^>]*/>|<a:ln\b[^>]*>.*?</a:ln>", re.S)

def strip_text_outline(src, dst):
    """글자 속성 안의 윤곽선만 걷어낸다. 도형 테두리는 건드리지 않는다."""
    removed = 0
    def scrub(m):
        nonlocal removed
        inner, n = RE_LN.subn("", m.group(3))
        removed += n
        return f"<a:{m.group(1)}{m.group(2)}>{inner}</a:{m.group(1)}>"
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename.startswith(TEXT_PARTS) and item.filename.endswith(".xml"):
                data = RE_RPR.sub(scrub, data.decode("utf-8")).encode("utf-8")
            zout.writestr(item, data)
    return removed

print("걷어낸 윤곽선:", strip_text_outline(r"C:\...\발표.pptx", r"C:\...\발표_수정.pptx"))
```

**걷어낸 개수를 사용자에게 알려라.** 0이 나오면 이 파일에는 원래 문제가 없었다는 뜻이다.

검증한 것은 이렇다. 윤곽선을 준 덱에서 정확히 그것만 걷어냈고, 고친 파일은 그대로 열렸으며
한글도 남았고, 테마의 도형 선 정의는 보존됐다. 렌더링해서 비교하니 윤곽선을 줬던 줄이
안 준 줄과 똑같아졌다. 깨끗한 파일에 돌리면 0개이므로 두 번 돌려도 안전하다.

**이 제거기는 도형 테두리를 건드리지 않는다.** 글자 속성(`rPr`·`defRPr`) 안의 선만 지운다.
표 선, 도형 외곽선, 구분선은 그대로 남는다.

윤곽선이 어디서 들어왔는지는 두 갈래다. 위의 `outline` 옵션이 첫째이고, **쓰는 템플릿에
박혀 있는 경우**가 둘째다. 만든 기억이 없는데 계속 나온다면 템플릿을 확인해 보라 — 템플릿이
원인이면 템플릿 한 번만 고치면 영구히 끝난다.
