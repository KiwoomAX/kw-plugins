---
name: extracting-excel-queries
description: Use when someone wants the queries and external data connections an Excel workbook uses (SQL inside VBA macros, ODBC query tables, Power Query, external workbook links) listed per file as index.xlsx and .sql files, or wants to know where an Excel workbook gets its data before moving the work to code or a dashboard. Reads VBA source even when the macro project is password-locked, and masks DB accounts and passwords in the results. Triggers on 엑셀 쿼리 뽑아 줘 · 엑셀에 연결된 쿼리 정리 · 매크로 안 SQL 보여 줘 · 엑셀 외부 연결 확인.
---

# extracting-excel-queries

엑셀 파일이 밖에서 데이터를 가져오는 연결을 찾아, 파일 단위로 목록(`index.xlsx`)과 `.sql` 파일로 남긴다. 스크립트는 DB 에 접속하지 않고 원본 엑셀을 읽기만 한다. 입력값은 `#변수명#` 으로 적는다. 엑셀 설명기(`explaining-excel-cell`)도 이 스킬의 코드로 값의 출처를 판정한다.

## 실행 명령

PowerShell 에서 실행한다. `<스킬>` 은 이 SKILL.md 가 있는 폴더다. 파일이나 폴더(하위 폴더 포함)를 받고, 결과는 현재 작업 폴더의 `excel-queries\` 에 쓴다.

```powershell
uv run --system-certs --no-project --with-requirements "<스킬>\scripts\requirements.txt" python "<스킬>\scripts\extract_queries.py" "<엑셀 또는 폴더 경로>" [--out <결과 폴더>] [--replace]
```

사용자가 저장 위치를 말하면 `--out` 으로 넘긴다.

## 종료 코드별 행동

| 종료 코드 | Claude 의 행동 |
|---|---|
| 0 | 아래 「결과 보고」 대로 알린다 |
| 1 | 출력된 설치 명령을 사용자에게 알리고 멈춘다 |
| 2 | `index.xlsx` 가 Excel 에 열려 있다고 알리고 닫아 달라고 한 뒤 멈춘다 |
| 3 | 출력된 원본이 이미 분석되어 있다고 알리고 결과를 바꿀지 묻는다. 승인하면 `--replace` 로 다시 실행한다 |
| 4 | 인자 오류다. 출력된 사용법을 보고 경로와 옵션을 고쳐 다시 실행한다 |

## 결과 보고

출력의 첫 줄은 출처 대응표 상태(「출처 대응표: 읽음」 또는 「출처 대응표: 읽기 실패」)다. 이어서 원본마다 `파일명, 연결 수, 미판별 수, 추출 미지원 수, 누출 처리 여부` 를 한 줄씩 출력한다. Claude 는 이 출력과 `index.xlsx` 를 읽고 아래를 알린다.

- 원본마다 찾은 연결의 종류와 수, 만든 `.sql` 의 수를 알린다.
- 출처 분류가 「미판별」 인 행과 비고가 「추출 미지원」 인 행을 이름으로 알린다. 출처 대응표가 「읽기 실패」이면 DB 연결이 모두 미판별이 된 이유가 그것이라고 함께 알린다.
- 비고에 「조립 분기 있음」, 「함수 항 바인드」, 「실행 호출 없음」 이 있는 SQL 은 사람이 원본 VBA 와 대조해야 한다고 알린다. 분기가 있으면 실행되는 SQL 이 분기에 따라 다르고, 함수 항은 `#EXPR1#` 같은 입력값으로 남기 때문이다.
- 「누출 처리」 가 있는 원본은 결과에 비밀번호가 남을 뻔해 `.sql` 을 지우고 「처리 오류」 행으로 바꿨다고 알린다.

Power Query 는 M 코드 안의 쿼리마다 행 하나다. `Odbc.Query`·`Value.NativeQuery` 등에 든 SQL 을 뽑고, 쿼리 결과를 불러오는 `Microsoft.Mashup` 연결은 따로 행을 만들지 않고 그 결과 범위를 쿼리 행에 적는다. 밖의 데이터를 읽지 않는 쿼리(셀 값을 읽는 날짜 쿼리 등)는 행을 만들지 않는다.

`index.xlsx` 의 행 하나가 연결 하나다. 열은 원본 엑셀 파일명, 원본 경로, 항목 번호, SQL 파일(누르면 열림), 저장 위치, 연결 종류, 접속 대상, 출처 분류, 입력, 결과를 쓰는 곳, 비고다. 결과에서 DB 아이디와 비밀번호는 `***` 로 가려진다.

## 출처 분류

출처 분류는 SQL 문장과 접속 문자열과 원본 경로만 보고 정한다. 값은 `WINUS`, `WFS`(우리펀드 서비스), `외부`, `미판별` 이다.

- WINUS 와 WFS 를 구분하는 서버 · 스키마 · DB 링크 · 폴더 이름은 사내 공용 폴더의 출처 대응표(`source_rules.json`)에서 읽는다. 대응표를 읽지 못하면(사내망 밖, 권한 없음) DB 연결은 모두 `미판별` 이다.
- 외부 통합문서 링크, DDE 링크, VBA 웹 호출, 수식 외부 함수는 대응표와 무관하게 `외부` 다.
- 열기 암호, 엑셀 형식 아님, 처리 오류 행은 출처 분류가 비어 있다.

DB 안의 동의어(synonym)가 다른 DB 링크를 숨기면 분류가 틀릴 수 있다. 결과를 알릴 때 이 한계를 함께 말한다.
