---
name: searching-document
description: fnguide 증권사 리포트를 키워드로 찾아 대화에 보여 줘야 할 때 연다. "fnguide"라는 말과 함께 리포트·보고서·문서·자료를 찾거나 필요하다고 하면 로컬 파일을 뒤지기 전에 이 스킬을 먼저 연다. "fnguide 문서 필요해", "삼성전자 관련 보고서 찾아 줘", "HBM 리포트 검색", "최근 3개월 반도체 리포트 목록" 같은 요청에 쓴다. 키워드가 없으면 키워드만 묻는다. 조회 전용이며 원문 PDF 다운로드는 다루지 않는다.
---

# searching-document

사내 vdb-handler 의 하이브리드 검색 API 로 fnguide 리포트를 키워드와 기간으로 찾는다. 조회만 하고 LLM 은 쓰지 않는다. 결과는 키워드와 가까운 순서로 뽑은 상위 30건이다.

```
[pwsh] --POST /v1/search/hybrid--> [vdb-handler] --dense + sparse 검색--> [fnguide_reports_hybrid 컬렉션]
```

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
| `query` | 사용자가 말한 키워드 | 키워드 하나를 그대로 넣는다 |
| `collection_name` | `"fnguide_reports_hybrid"` | 고정 |
| `top_k` | `30` | 고정 |
| `use_rerank` | `false` | 서버 기본값이 `true` 라서 반드시 적는다. 켜면 ColBERT 리랭커가 산업 리포트보다 개별 종목 리포트를 위로 올린다 |
| `payload_filter` | 기간 조건 | 아래 형식을 따른다 |

기간은 `일자` 필드에 거는 범위 조건이다. `일자` 는 `20260804` 같은 YYYYMMDD **정수**라서 따옴표 없이 넣는다. 사용자가 기간을 말하지 않으면 오늘부터 3개월 전까지로 검색하고, 답에 그 기간을 적는다. `payload_filter` 를 빼면 전체 기간을 검색한다.

```json
{"must": [{"key": "일자", "range": {"gte": 20260629, "lte": 20260929}}]}
```

## 호출 예시

```powershell
$body = @{
    query           = 'HBM'
    collection_name = 'fnguide_reports_hybrid'
    top_k           = 30
    use_rerank      = $false
    payload_filter  = @{ must = @(@{ key = '일자'; range = @{ gte = 20260629; lte = 20260929 } }) }
} | ConvertTo-Json -Depth 6

$res = Invoke-RestMethod -Method Post -Uri 'http://192.7.9.45:8500/v1/search/hybrid' `
    -ContentType 'application/json' -Body $body -TimeoutSec 120

$res.results | ForEach-Object {
    [pscustomobject]@{ 일자 = $_.payload.'일자'; 종목 = $_.payload.'종목/분류명'; 제목 = $_.payload.'제목'; file_path = $_.payload.file_path }
} | Format-Table -AutoSize
```

- **`ConvertTo-Json -Depth 6` 을 빼지 않는다.** 기본 깊이는 2라서, 빼면 기간 조건이 `"System.Collections.Hashtable"` 이라는 문자열로 바뀌어 나간다.
- **슬래시가 든 키는 따옴표로 감싼다.** `$_.payload.'종목/분류명'`

## 응답

```json
{"results": [{"id": "…", "score": 0.53, "text": "…", "payload": {"제목": "…", "일자": 20260804, …}}], "count": 30, "collection": "fnguide_reports_hybrid"}
```

값은 항목의 `payload` 에서 읽는다. 최상위의 `file_name`·`category` 는 비어 있고 `page` 는 0이다.

| 필드 | 뜻 |
|---|---|
| `score` | 순위 점수. dense 와 sparse 검색의 등수로 계산해 0에서 1 사이 값이 나오고, 관련도를 뜻하지 않는다. 관련 없는 키워드로 찾아도 1등은 0.5 이상이라 조회끼리 비교하거나 기준값으로 자르지 않는다 |
| `payload.제목` | 리포트 제목 |
| `payload.일자` | 발행일, YYYYMMDD 정수 |
| `payload.종목/분류명` | 종목명이나 산업 분류명 |
| `payload.주내용` | 리포트 요약 |
| `payload.테마`·`섹터`·`지역`·`드라이버`·`정책` | 문자열 목록. 예: `["HBM", "AI", "반도체 장비"]` |
| `payload.source_pdf` | 원문 PDF 파일 이름 |
| `payload.file_path` | file-manager 의 파일 식별자. AX팀 인프라에 원문 PDF 를 요청할 때 필요한 값이다. 먼저 보여 주지 않고, 사용자가 원문을 받는 방법을 물으면 이 값과 함께 알려 준다 |
| `text` | 검색에 쓴 본문. 제목·종목·일자·5축·요약을 이은 글이다. `payload.text` 도 같은 값이다 |

30건 응답은 약 130KB 다. 대화에는 순위·일자·종목/분류명·제목을 표로 보이고, 요약·5축·`file_path` 는 사용자가 원할 때 꺼낸다.

## 사용자에게 알릴 것

결과 표 아래에 늘 적는 문장과 조건에 따라 적는 문장이 있다.

- **늘 적는다: 관련 없는 리포트가 섞일 수 있다.** 가까운 순서로 30건을 채우므로, 관련 리포트가 적은 기간이나 영문 약어 키워드에서는 무관한 리포트가 올라온다. 예를 들어 `HBM` 은 철자가 비슷한 HMM·에이치브이엠 리포트를 함께 가져온다.
- **늘 적는다: 표에 없는 정보가 더 있다.** 각 리포트에는 요약(`주내용`)과 원문 파일 이름(`source_pdf`)이 함께 있다.
- **30건 중 관련 리포트가 하나도 없을 때만 적는다: 그 기간에는 해당 리포트가 없는 것으로 본다.** 기간을 넓혀 다시 찾을지 묻는다.

## 실패

| 상태 | 뜻 |
|---|---|
| 연결 실패 | 사내망이나 VPN 밖이다 |
| 422 | 본문 형식 오류. `powershell.exe`(5.1)로 보냈거나 필드 이름·타입이 틀렸다 |
| 응답 지연 | 서버가 막 재시작되면 모델을 올리는 데 2분 가까이 소요된다. `-TimeoutSec 120` 을 둔다 |
