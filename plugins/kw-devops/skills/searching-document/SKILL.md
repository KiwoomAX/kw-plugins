---
name: searching-document
description: fnguide 증권사 리포트를 키워드로 찾아 대화에 보여 줘야 할 때 작동한다. "fnguide"라는 말과 함께 리포트·보고서·문서·자료를 찾거나 필요하다고 하면 로컬 파일을 뒤지기 전에 이 스킬을 먼저 작동한다. "fnguide 문서 필요해", "삼성전자 관련 보고서 찾아 줘", "HBM 리포트 검색", "최근 3개월 반도체 리포트 목록" 같은 요청에 사용한다. 검색한 리포트의 원문 PDF 를 받아 달라는 요청에도 사용한다.
---

# searching-document

사내 vdb-handler 의 하이브리드 검색 API 로 fnguide 리포트를 키워드와 기간으로 찾고, 사용자가 고른 리포트의 원문 PDF 를 file-handler 에서 받는다. 둘 다 읽기만 하고 LLM 은 쓰지 않는다. 검색 결과는 키워드와 가까운 순서로 뽑은 상위 30건이다.

```
[pwsh] --POST /v1/search/hybrid--> [vdb-handler] --dense + sparse 검색--> [fnguide_reports_hybrid 컬렉션]
[pwsh] --GET /v1/files/{file_path}--> [file-handler] --> 원문 PDF
```

## 사용자에게 쓰는 말

이 스킬을 쓰는 사람은 개발자가 아니다. 답에서는 이 기능을 「사내 리포트 검색」으로만 부르고, 아래 문서의 부품 이름(vdb-handler, file-handler, 컬렉션, 하이브리드 검색, 리랭커, 서버 주소, `file_path` 같은 필드 이름)은 쓰지 않는다. 필드는 요약·원문 파일 이름·원문 PDF 처럼 뜻으로 부르고, 날짜는 「발간일」이라고 부른다. 아래의 `일자` 는 서버가 받는 키 이름이라 요청에서만 그대로 쓴다.

순위 열은 「유사도 순위」라고 부른다. 키워드와 가까운 순서라는 뜻이다. 결과를 읽고 묶거나 빼거나 관련 여부를 적으면 「AI 판단」이라고 밝혀 유사도 순위와 구분한다.

키워드가 없으면 검색 방식을 설명하지 않고 키워드와 기간만 한 문장으로 묻는다. 괄호 안은 오늘과 그 1주 전 날짜로 채운다.

> 찾을 키워드와 기간을 알려 주세요. 키워드가 여러 개면 쉼표로 구분해 주세요. 기간을 말하지 않으면 최근 1주(1주 전 날짜~오늘 날짜)로 찾습니다.

키워드가 여러 개면 키워드마다 따로 검색한다. 서로 관련이 적은 단어를 한 검색어에 넣으면 정확도가 떨어지기 때문이다.

- **쉼표로 나눠 말했으면** 묻지 않고 키워드마다 따로 찾는다.
- **쉼표 없이 여러 키워드로 보이면**(`삼성전자 HBM`, `삼성전자랑 HBM`) 나눈 결과를 확인한 뒤 찾는다. 예: 「삼성전자」, 「HBM」 두 키워드로 따로 찾을까요? 한 검색어로 묶어 찾을 수도 있지만, 서로 관련이 적은 단어를 함께 넣으면 정확도가 떨어져 따로 찾기를 권합니다.
- **키워드가 하나로 분명하면** 묻지 않고 찾는다.

## 요청 형식

| 항목 | 값 |
|---|---|
| 주소 | `http://192.7.9.45:8500/v1/search/hybrid` (사내망) |
| 메서드 | `POST`, 본문은 JSON |
| 인증 | 없음 |
| 셸 | `pwsh` (PowerShell 7). `powershell.exe`(5.1)로 보내면 한글 키 `일자`가 깨져 422 로 거절되고, 응답의 한글 키도 깨진다 |

본문 필드는 아래 값으로 채운다.

| 필드 | 값 | 설명 |
|---|---|---|
| `query` | 사용자가 말한 키워드 | 요청 하나에 키워드 하나를 넣는다. 여러 개면 아래 「키워드 여러 개」처럼 따로 보낸다 |
| `collection_name` | `"fnguide_reports_hybrid"` | 고정 |
| `top_k` | `30` | 고정 |
| `use_rerank` | `false` | 서버 기본값이 `true` 라서 반드시 적는다. 켜면 ColBERT 리랭커가 산업 리포트보다 개별 종목 리포트를 위로 올린다 |
| `payload_filter` | 기간 조건 | 아래 형식을 따른다 |

기간은 `일자` 필드에 거는 범위 조건이다. `일자` 는 `20260804` 같은 YYYYMMDD **정수**라서 따옴표 없이 넣는다. 사용자가 기간을 말하지 않으면 오늘부터 1주 전까지로 검색하고, 답에 그 기간을 적는다. `payload_filter` 를 빼면 전체 기간을 검색한다. 조건이 없을 때 `{"must": []}` 처럼 빈 필터를 보내면 422 로 거절되므로 필드 자체를 뺀다.

```json
{"must": [{"key": "일자", "range": {"gte": 20260922, "lte": 20260929}}]}
```

## 호출 예시

```powershell
$body = @{
    query           = 'HBM'
    collection_name = 'fnguide_reports_hybrid'
    top_k           = 30
    use_rerank      = $false
    payload_filter  = @{ must = @(@{ key = '일자'; range = @{ gte = 20260922; lte = 20260929 } }) }
} | ConvertTo-Json -Depth 6

$res = Invoke-RestMethod -Method Post -Uri 'http://192.7.9.45:8500/v1/search/hybrid' `
    -ContentType 'application/json' -Body $body -TimeoutSec 120

$res.results | ForEach-Object {
    [pscustomobject]@{ 발간일 = $_.payload.'일자'; 종목 = $_.payload.'종목/분류명'; 제목 = $_.payload.'제목'; file_path = $_.payload.file_path }
} | Format-Table -AutoSize
```

- **`ConvertTo-Json -Depth 6` 을 빼지 않는다.** 기본 깊이는 2라서, 빼면 기간 조건이 `"System.Collections.Hashtable"` 이라는 문자열로 바뀌어 나간다.
- **슬래시가 든 키는 따옴표로 감싼다.** `$_.payload.'종목/분류명'`

## 키워드 여러 개

키워드마다 요청을 하나씩 동시에 보낸다.

```powershell
$keywords = @('삼성전자', 'HBM')
$filter = @{ must = @(@{ key = '일자'; range = @{ gte = 20260922; lte = 20260929 } }) }

$byKeyword = $keywords | ForEach-Object -ThrottleLimit 5 -Parallel {
    $body = @{
        query           = $_
        collection_name = 'fnguide_reports_hybrid'
        top_k           = 30
        use_rerank      = $false
        payload_filter  = $using:filter
    } | ConvertTo-Json -Depth 6
    $res = Invoke-RestMethod -Method Post -Uri 'http://192.7.9.45:8500/v1/search/hybrid' `
        -ContentType 'application/json' -Body $body -TimeoutSec 120
    [pscustomobject]@{ 키워드 = $_; 결과 = $res.results }
}
```

- **결과는 끝난 순서로 돌아온다.** 보여 줄 때는 사용자가 말한 키워드 순서로 다시 맞춘다.

## 응답

```json
{"results": [{"id": "…", "score": 0.53, "text": "…", "payload": {"제목": "…", "일자": 20260804, …}}], "count": 30, "collection": "fnguide_reports_hybrid"}
```

값은 항목의 `payload` 에서 읽는다. 최상위의 `file_name`·`category` 는 비어 있고 `page` 는 0이다.

| 필드 | 뜻 |
|---|---|
| `score` | 순위 점수. dense 와 sparse 검색의 등수로 계산해 0에서 1 사이 값이 나오고, 관련도를 뜻하지 않는다. 관련 없는 키워드로 찾아도 1등은 0.5 이상이라 조회끼리 비교하거나 기준값으로 자르지 않는다 |
| `payload.제목` | 리포트 제목 |
| `payload.일자` | 발간일, YYYYMMDD 정수 |
| `payload.종목/분류명` | 종목명이나 산업 분류명 |
| `payload.주내용` | 리포트 요약 |
| `payload.테마`·`섹터`·`지역`·`드라이버`·`정책` | 문자열 목록. 예: `["HBM", "AI", "반도체 장비"]` |
| `payload.source_pdf` | 원문 PDF 파일 이름 |
| `payload.file_path` | 원문 PDF 의 식별자. 아래 「원문 받기」에 쓴다 |
| `text` | 검색에 쓴 본문. 제목·종목·일자·5축·요약을 이은 글이다. `payload.text` 도 같은 값이다 |

30건 응답은 약 130KB 다. 대화에는 유사도 순위·발간일·종목/분류명·제목을 표로 보이고(키워드가 여러 개면 키워드마다 제목을 달아 표를 따로 보인다), 요약·5축·`file_path` 는 사용자가 원할 때 꺼낸다.

## 사용자에게 알릴 것

결과 표 아래에 항상 쓰는 문장과 조건에 따라 쓰는 문장이 있다.

- **항상: 관련 없는 리포트가 섞일 수 있다.** 가까운 순서로 30건을 채우므로, 관련 리포트가 적은 기간이나 영문 약어 키워드에서는 무관한 리포트가 올라온다. 예를 들어 `HBM` 은 철자가 비슷한 HMM·에이치브이엠 리포트를 함께 가져온다.
- **항상: 표에 없는 정보가 더 있다.** 각 리포트에는 요약과 원문 파일 이름이 함께 있고, 원문 PDF 도 받을 수 있다.
- **30건 중 관련 리포트가 하나도 없을 때만 적는다: 그 기간에는 해당 리포트가 없는 것으로 본다.** 기간을 넓혀 다시 찾을지 묻는다.

## 원문 받기

사용자가 표에서 리포트를 골라 원문을 달라고 하면, 그 리포트의 `file_path` 로 file-handler 에서 PDF 를 받아 `source_pdf` 이름으로 저장한다. 저장할 폴더를 사용자가 말하지 않았으면 먼저 묻는다.

```powershell
$dir = 'C:\Users\me\Downloads\fnguide'          # 사용자가 정한 폴더
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$p = $res.results[0].payload                    # 사용자가 고른 리포트
$dest = Join-Path $dir $p.source_pdf
if (Test-Path -LiteralPath $dest) { throw "같은 이름의 파일이 이미 있습니다: $dest — 덮어쓸지 사용자에게 묻는다" }
# 경로의 / 는 그대로 두고 조각마다 인코딩한다. 공백이나 # 이 섞이면 요청이 잘린다.
$enc = ($p.file_path -split '/' | ForEach-Object { [uri]::EscapeDataString($_) }) -join '/'
Invoke-WebRequest -Uri "http://192.7.9.45:8600/v1/files/$enc" -OutFile $dest -TimeoutSec 120
```

- **여러 건은 한 건씩 차례로 받는다.** 응답은 파일 하나다.
- **저장한 뒤 경로와 크기를 알린다.** 받은 파일은 `%PDF-` 로 시작한다.

## 실패

| 상태 | 뜻 |
|---|---|
| 연결 실패 | 사내망이나 VPN 밖이다 |
| 404 (원문 받기) | 그 `file_path` 의 파일이 없다. 검색 결과에서 값을 다시 옮겼는지 확인한다 |
| 422 | 본문 형식 오류. `powershell.exe`(5.1)로 보냈거나, 필드 이름·타입이 틀렸거나, 모르는 키(`score_threshold` 등)나 빈 필터를 넣었다. 다시 보내도 같으므로 본문을 고친다 |
| 503 | 지금 요청을 받을 수 없다. 서버가 재시작 뒤 모델을 올리는 중(약 2분)이거나 동시 요청 한도를 넘었다. 몇 초 뒤 두세 번 다시 보내고, 계속 503 이면 사용자에게 잠시 뒤 다시 찾자고 알린다. 모델이 꺼진 상태라면 설정이 바뀌기 전까지 계속 503 이다 |
| 500 | 검색어를 임베딩하는 호출이 일시적으로 실패했다. 한두 번 다시 보낸다 |
