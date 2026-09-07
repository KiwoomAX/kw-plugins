---
name: xlsx
description: 엑셀(.xlsx)을 읽거나 만들 때 document-skills:xlsx와 함께 반드시 연다. 셀 글자 크기를 11로 두는 규칙과, 수식 값이 필요할 때 엑셀 프로그램을 부르는 대신 무엇을 하는지가 여기 있다. **엑셀을 COM으로 부르기 전에는 증상이 보이지 않아도 반드시 연다** — 그냥 부르면 사용자가 열어 둔 무관한 문서가 저장 확인 창도 없이 전부 닫힌다. 엑셀로 열 CSV의 인코딩은 kw-doc-formats:common에 있다.
---

# 엑셀을 만들 때

**`kw-doc-formats:common` 을 함께 본다.** 파일을 열고 쓸 때의 인코딩과, 어떤 형식이 바로
읽히는지가 거기 있다.

일반적인 엑셀 다루기는 `document-skills:xlsx` 에 있다. 여기는 이 PC에서 그 기본값이 틀리거나
그 도구가 없는 자리만 적는다.

## 읽기만 하면 되는 일에 엑셀 프로그램을 부르지 않는다

`openpyxl` 과 `pandas` 로 파일을 직접 읽으면 되고, 그러면 사용자가 쓰고 있는 엑셀에는 아무 일도
일어나지 않는다. 프로그램을 부르는 순간 사용자가 열어 둔 문서가 위험해진다. 왜 그런지와 어느
프로그램에 같은 위험이 있는지는 `kw-doc-formats:common` 의 「오피스 프로그램을 COM 으로 부를
때」에 있다.

| 하려는 일 | 어떻게 하나 |
|---|---|
| 값·서식·시트 구조를 읽는다 | `openpyxl` 로 파일을 직접 연다. 프로그램을 부르지 않는다 |
| 새 파일을 만들거나 시트를 고친다 | `openpyxl` 로 쓴다. 원본을 직접 덮어쓰지 않는다 |
| 수식을 실제로 계산시켜야 한다 | COM 말고는 길이 없다. 아래 방어를 반드시 건다 |

### 수식 값이 필요할 때

openpyxl 은 수식을 **계산하지 않는다.** 그냥 열면 `=SUM(A1:A9)` 라는 글자가 나오고,
`data_only=True` 로 열면 **엑셀이 마지막으로 저장하면서 넣어 둔 값**이 나온다. 그 파일을
엑셀로 한 번도 연 적이 없거나 내가 openpyxl 로 만든 파일이면 그 자리가 `None` 이다.

```python
from openpyxl import load_workbook

wb = load_workbook(path, data_only=True)   # 엑셀이 저장해 둔 계산 결과를 읽는다
ws = wb.active
print(ws["B10"].value)                      # None 이면 계산된 적이 없는 파일이다
```

`None` 이 나왔다고 곧바로 COM 으로 넘어가지 마라. 사용자에게 그 파일을 엑셀로 한 번 열었다
저장해 달라고 하면 값이 박힌다. 그쪽이 사용자의 다른 문서를 위험에 빠뜨리지 않는다.

### COM 을 꼭 써야 한다면

```powershell
# 남의 엑셀에 붙는 것을 원천 차단한다. 이 검사 없이 아래를 실행하지 마라.
if (@(Get-Process EXCEL -ErrorAction SilentlyContinue).Count -gt 0) {
    throw "엑셀이 실행 중입니다. 사용자에게 닫아 달라고 요청한 뒤에 다시 실행하십시오."
}

$excel = New-Object -ComObject Excel.Application
$excel.Visible = $false
$excel.DisplayAlerts = $false
$wb = $null
try {
    $wb = $excel.Workbooks.Open($path)
    $excel.CalculateFullRebuild()
    # ... 확인할 값을 여기서 Write-Output 한다
} finally {
    if ($wb) { $wb.Close($false) }   # 저장해야 하면 앞에 $wb.Save() 를 둔다
    $excel.Quit()                     # 위 검사를 통과했으므로 내가 띄운 인스턴스다
    [Runtime.InteropServices.Marshal]::ReleaseComObject($excel) | Out-Null
}
```

### 열려 있는 파일을 덮어쓰지 마라

사용자가 엑셀로 열어 둔 파일을 openpyxl 로 덮어쓰면 엑셀이 그 충격을 견디지 못하고 죽는다.
내 컴퓨터 디스크라면 윈도가 "다른 프로그램이 쓰는 중"이라며 막아 주지만, **`\\cifs\...` 같은
네트워크 공유는 잠금이 헐거워서 막아 주지 않는다.** 사내 파일은 대개 공유 드라이브에 있으므로
이 보호막이 없다고 보는 편이 맞다.

열려 있는지는 잠금 파일로 안다. 엑셀은 문서를 열면 같은 폴더에 `~$` 를 붙인 숨김 파일을 만든다.

```python
import os

lock = os.path.join(os.path.dirname(path), "~$" + os.path.basename(path))
if os.path.exists(lock):
    raise SystemExit("이 파일은 지금 열려 있다. 사용자에게 닫아 달라고 알린다.")
```

결과물은 원본을 직접 고치지 말고 **스크래치패드에 새 파일로 만들어 보여 준 뒤 옮긴다.**
원본이 열려 있어도 사고가 없고, 결과가 잘못돼도 되돌릴 수 있다.

## 엑셀을 만들 때 항상 지킬 것

셀 글자 크기는 **11**로 둔다. 엑셀의 기본값이 11이고, `openpyxl`이 새로 만드는 통합 문서의
`Normal` 스타일도 11이다. 셀마다 크기를 따로 지정하지 않는다. 지정해야 하는 자리가 있어도
11로 적는다. 머리글을 돋보이게 하려면 크기가 아니라 굵기와 채우기 색으로 한다. 글꼴 이름은
이 규칙이 다루지 않는다.

```python
from openpyxl.styles import Font
ws["A1"].font = Font(bold=True)             # 크기를 적지 않는다. 11을 물려받는다
ws["A1"].font = Font(size=11, bold=True)    # 적어야 한다면 11이다
```
