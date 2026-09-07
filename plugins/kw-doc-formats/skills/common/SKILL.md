---
name: common
description: 문서 파일을 파이썬으로 읽거나 쓰는 모든 작업에서 반드시 연다. .pptx .xlsx .docx .pdf .csv 어느 형식이든 파일을 열거나 저장하는 코드를 쓰기 전에 연다. 사내 파일은 cp949이고 엑셀로 열 CSV는 utf-8-sig여야 하며, 인코딩을 안 적으면 한글이 깨진다. **오피스 프로그램을 COM으로 부르기 전에도 반드시 연다** — 그냥 부르면 사용자가 열어 둔 무관한 문서가 저장 확인 창도 없이 전부 닫힌다.
---

# 문서 파일의 인코딩과 형식 길잡이

## 무엇이 바로 읽히는가

| 형식 | 바로 읽히나 | 안 되면 무엇을 하나 |
|---|---|---|
| `.xlsx` `.docx` `.pptx` `.pdf` `.csv` | 된다 | — |
| `.xls` (구형 엑셀) | 된다 | — |
| `.doc` `.ppt` (구형 워드·PPT) | **안 된다** | `kw-doc-formats:hwp` 에 최신 형식으로 바꾸는 법이 있다 |
| `.hwp` `.hwpx` (한글) | **안 된다** | `kw-doc-formats:hwp` 가 한/글을 조종해 바꾸는 법을 담고 있다 |

`.csv` 에는 단서가 하나 붙는다. **사내에서 오가는 CSV는 대개 cp949 로 저장되어 있다.** 파이썬이나
pandas 의 기본값인 UTF-8 로 읽으면 글자가 전부 깨지거나 아예 열리지 않는다. 그 화면은 사용자
눈에 "클로드가 잘못했다"로 보이므로, 인코딩을 짐작하지 말고 `chardet` 으로 판별한 뒤 그 값으로
열어라. 이 PC에는 정확히 그 용도로 깔려 있다.

```python
import chardet, pandas as pd

raw = open(path, "rb").read(100_000)          # 앞부분만 봐도 판별된다
enc = chardet.detect(raw)["encoding"]          # 사내 파일은 대개 cp949 로 나온다
df  = pd.read_csv(path, encoding=enc)
```

`chardet` 은 판별만 하고 파일을 고치지 않으므로 원본에 아무 영향이 없다. 판별에 실패하면
`encoding=None` 이 나오니 그때는 `cp949` 로 한 번, `utf-8` 로 한 번 시도해 보고 사용자에게
어느 쪽이 맞는지 물어라.

## 파이썬으로 파일을 열 때는 인코딩을 반드시 적는다

`kw-doc-formats:pptx` 에 실린 테마 슬롯 교체와 윤곽선 제거는 `.pptx` 를 풀어 그 안의 XML을
손본다. 거기 한글이 들어 있으므로 이 규칙이 먼저 온다. PPT만의 이야기가 아니라 이 PC에서
파이썬으로 파일을 읽고 쓸 때 전부 해당한다.

**파이썬이 파일을 열 때 쓰는 기본 인코딩은 PC마다 다르다.** 윈도의 로케일과 `PYTHONUTF8` 환경변수가
함께 정한다. 지금 이 PC의 값은 `python -c "import locale;print(locale.getpreferredencoding(False))"`
로 확인한다. 기본값이 cp949 인 PC에서는 UTF-8 로 저장된 한글 파일을
`encoding=` 없이 열면 이렇게 멈춘다.

```
UnicodeDecodeError: 'cp949' codec can't decode byte 0x9d in position 23
```

파일이 깨진 것이 아니라 여는 쪽이 틀린 것이다. 이 오류를 보고 원본을 의심하기 시작하면
한참을 헤맨다.

```python
open(path, encoding="utf-8")          # 코드에서는 이렇게 명시한다
data.decode("utf-8")                  # zipfile 에서 꺼낸 바이트도 마찬가지다
```

**코드에는 항상 명시한다.** `kw-doc-formats:pptx` 의 XML 예제가 `.decode("utf-8")` 과 `.encode("utf-8")` 을
빠짐없이 달고 있는 것이 그 때문이다. 한 줄짜리 명령을 급히 돌릴 때는 환경변수
`PYTHONUTF8=1` 로도 같은 효과를 낸다. 다만 그 변수는 PC마다 있을 수도 없을 수도 있으므로, 남길 코드에는
`encoding=` 을 적는 쪽이 맞다.

## 엑셀로 열 CSV는 BOM 있는 UTF-8로 쓴다

파이썬이 UTF-8로 쓴 CSV를 한국어 엑셀에서 더블클릭으로 열면 cp949로 해석해 한글이 전부 깨진다.
사용자 눈에는 "클로드가 파일을 망쳤다"로 보인다. `PYTHONUTF8=1`이 걸린 PC에서는 파이썬의 기본
쓰기 인코딩이 UTF-8이라 이 일이 더 잦다. 사용자가 엑셀로 열 CSV는 반드시 `utf-8-sig`로 쓴다.
BOM이 붙어 엑셀이 UTF-8로 읽는다. 표가 목적이면 CSV 대신 `.xlsx`로 바로 내보내는 편이 낫다.
인코딩 문제가 아예 없다.

```python
df.to_csv(path, encoding="utf-8-sig", index=False)   # 엑셀로 열 CSV
df.to_excel(path_xlsx, index=False)                  # 표가 목적이면 이쪽
```

읽을 때의 규칙은 위 「파이썬으로 파일을 열 때는 인코딩을 반드시 적는다」 절에 있다. 사내에서
받은 CSV는 대개 cp949라 `chardet`으로 판별해 읽고, 내가 쓰는 CSV는 `utf-8-sig`로 쓴다. 두 규칙은
방향이 반대이고 둘 다 지킨다.

## 오피스 프로그램을 COM 으로 부를 때

**부르기 전에 그 프로그램이 이미 떠 있는지 보고, 떠 있으면 실행하지 말고 멈춘다.** 사용자에게
닫아 달라고 알리는 것이 맞다. 몰래 진행하는 편이 훨씬 나쁘다.

엑셀도 파워포인트도 한/글도 **프로그램 하나가 열린 문서 전부를 담는 구조**다. 문서마다
프로그램이 하나씩 뜨지 않는다. 그래서 `New-Object -ComObject Excel.Application` 은 새 프로그램을
띄우는 것처럼 보이지만 **이미 켜져 있는 것에 그대로 붙을 때가 있고**, 마무리로 부르는 `Quit()`
한 번이 사용자가 열어 둔 문서를 전부 닫는다. 앞에 `DisplayAlerts = $false` 를 뒀다면 저장 확인
창도 뜨지 않으므로 **저장하지 않은 작업이 말없이 사라진다.**

실제로 겪은 일이다. 수식이 제대로 계산되는지 확인하려고 COM 으로 엑셀을 띄우고
`finally { $excel.Quit() }` 로 마무리한 세션에서, 사용자가 따로 열어 둔 무관한 문서가 함께
닫혔다. 사용자 눈에는 "건드리라고 하지도 않은 파일이 저절로 꺼진다"로 보인다. 원인을 찾기까지
한참 걸리는 종류의 사고이므로, 부르기 전에 막는 편이 훨씬 싸다.

| 부르는 프로그램 | 검사에 쓸 프로세스 이름 |
|---|---|
| 엑셀 | `EXCEL` |
| 파워포인트 | `POWERPNT` |
| 워드 | `WINWORD` |
| 한/글 | `Hwp` |

```powershell
# 남의 문서에 붙는 것을 원천 차단한다. 이 검사 없이 COM 을 부르지 마라.
if (@(Get-Process EXCEL -ErrorAction SilentlyContinue).Count -gt 0) {
    throw "엑셀이 실행 중입니다. 사용자에게 닫아 달라고 요청한 뒤에 다시 실행하십시오."
}
```

이 PC에서 넷 다 설치를 확인했고, `Get-Process <이름>` 으로 실행 여부가 잡히는 것도 확인했다.
새로 COM 을 부르는 코드를 쓸 때는 이 표에서 이름을 가져다 맨 앞에 검사를 건다. `Quit()` 이
안전한 것은 **그 검사를 통과했을 때뿐이다.** 검사를 빼고 아래 토막만 베껴 쓰면 원래 사고로
그대로 돌아간다.

`kw-doc-formats:xlsx` 와 `kw-doc-formats:pptx` 와 `kw-doc-formats:hwp` 의 COM 예제가 모두 이
검사를 달고 있는 것이 그 때문이다.

## 기존 오피스 문서의 내용을 뽑을 때

`python -m markitdown 파일경로` 로 내용을 뽑아낼 수 있다. 엑셀·워드·PPT·PDF에 모두 쓴다.
읽히지 않으면 위 표에서 그 형식이 바로 읽히는 것인지 먼저 확인한다.
