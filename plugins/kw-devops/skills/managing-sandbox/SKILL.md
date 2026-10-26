---
name: managing-sandbox
description: AX팀 데이터베이스의 샌드박스(kw_sandbox)에 표를 만들거나, 데이터를 저장·수정·삭제할 때 연다. 대시보드나 업무 도구가 여러 사람과 함께 쓸 데이터를 둘 곳이 필요할 때, "샌드박스에 표 만들어 줘"·"이 데이터를 DB에 저장"·"우리 본부 표 목록"·"/sandbox 호출 코드" 같은 말이 나올 때, DBGateway 샌드박스가 거절할 때 연다. WINUS 데이터 조회는 searching-winus 가 맡는다.
---

# managing-sandbox

샌드박스는 AX팀 데이터베이스 `kw_sandbox` 안의 본부별 공간이다. 직원은 자기 본부 스키마(예: 경영전략본부는 `BS`)에 표를 만들고, 같은 본부 사람과 함께 행을 조회·삽입·수정·삭제한다. 팀 전용 스키마가 있는 팀은 그 스키마도 쓴다. 다른 본부의 표는 DBGateway 와 데이터베이스가 두 번 차단한다.

```
[클로드 코드 · 서비스 백엔드] --접근 키 + /sandbox/*--> [DBGateway] --본부 권한으로 실행--> [kw_sandbox 본부 스키마]
```

알고 써야 할 점은 다음과 같다.
- 표의 주인은 만든 사람이 아니라 본부다. 같은 본부 사람은 누가 만든 표든 지우고, 비우고, 이름을 바꿀 수 있다.
- 지운 데이터를 되돌리는 기능은 없다. 누가 무엇을 했는지는 DBGateway 의 작업 기록에만 남는다.
- 평문 SQL 은 보내지 못한다. 요청은 정해진 모양의 JSON 이고, DBGateway 가 문장을 만든다.

> DBGateway 의 샌드박스 경로는 시험 단계다. 이 문서에 적힌 것과 실제 응답이 다르면 맞춰 넘기지 말고 사용자에게 알린다.

## 접근 키

샌드박스는 searching-winus 와 같은 접근 키(환경 변수 `KIWOOM_ACCESS_KEY`)를 쓰고, 키 없는 요청은 받지 않는다. 스크립트는 키가 없거나, DBGateway 가 키를 거절하거나, 키를 설정했지만 지금 창에 반영되지 않았으면 요청을 보내지 않고 멈춘다. 그때 출력의 `조치`·`설정 뒤` 줄이 할 일을 알려 준다.

클로드는 그 출력을 받으면 searching-winus SKILL.md 의 「접근 키」 절 순서대로 발급과 등록을 안내한다. 두 스킬은 같은 키를 쓰므로, 한 번 등록하면 두 스킬 모두에서 쓰인다.

## 명령

명령은 모두 `python "${CLAUDE_SKILL_DIR}/scripts/sandbox.py" <하위 명령>` 형태다. 표·컬럼 이름이 한글이라 요청 내용은 JSON 파일로 넘긴다. 클로드는 Write 도구로 임시 파일에 JSON 을 쓰고 그 경로를 넘긴다. PowerShell 은 명령 안의 큰따옴표를 지우고 파이프로 넘긴 한글을 깨뜨리므로, 명령 안에 JSON 을 직접 적지 않는다.

```
python "${CLAUDE_SKILL_DIR}/scripts/sandbox.py" schemas
python "${CLAUDE_SKILL_DIR}/scripts/sandbox.py" tables BS
python "${CLAUDE_SKILL_DIR}/scripts/sandbox.py" describe --schema BS --table 투자후보
python "${CLAUDE_SKILL_DIR}/scripts/sandbox.py" select --request <파일> [--all --out <결과 파일>]
python "${CLAUDE_SKILL_DIR}/scripts/sandbox.py" create --spec <파일> --purpose "<자세한 용도>"
python "${CLAUDE_SKILL_DIR}/scripts/sandbox.py" insert --request <파일> [--confirm <확인값>]
python "${CLAUDE_SKILL_DIR}/scripts/sandbox.py" update --request <파일> [--confirm <확인값>]
python "${CLAUDE_SKILL_DIR}/scripts/sandbox.py" delete --request <파일> [--confirm <확인값>]
python "${CLAUDE_SKILL_DIR}/scripts/sandbox.py" overwrite --request <파일> [--confirm <확인값>]
python "${CLAUDE_SKILL_DIR}/scripts/sandbox.py" alter --change <파일> [--confirm <확인값>]
python "${CLAUDE_SKILL_DIR}/scripts/sandbox.py" drop --schema BS --table 투자후보 [--confirm <확인값>]
python "${CLAUDE_SKILL_DIR}/scripts/sandbox.py" truncate --schema BS --table 투자후보 [--confirm <확인값>]
python "${CLAUDE_SKILL_DIR}/scripts/sandbox.py" index-create --spec <파일>
python "${CLAUDE_SKILL_DIR}/scripts/sandbox.py" index-drop --schema BS --table 투자후보 --name <인덱스>
python "${CLAUDE_SKILL_DIR}/scripts/sandbox.py" record list
python "${CLAUDE_SKILL_DIR}/scripts/sandbox.py" record add --schema BS --table 투자후보 --purpose "<용도>"
python "${CLAUDE_SKILL_DIR}/scripts/sandbox.py" record remove --schema BS --table 투자후보
python "${CLAUDE_SKILL_DIR}/scripts/sandbox.py" record rename --schema BS --table 투자후보 --to <새 이름>
```

- `schemas` 는 이 키로 쓸 수 있는 스키마와 사용량·상한(10 GB)을 낸다. "쓸 수 있는 스키마 없음"이 나오면 그 사람의 조직에는 샌드박스가 없으니, 클로드는 AX팀에 문의하라고 알린다.
- `tables` 는 표마다 추정 행 수·크기·설명을 내고, 내 표 기록에 있는 표에는 "내 표"를 붙인다.
- `select` 한 번은 기본 1,000행, 최대 30,000행을 받는다. 더 많으면 `--all --out <결과 파일>` 로 모든 페이지를 파일에 받는다. 표 전체가 대화로 들어오지 않게 `--all` 은 `--out` 없이 쓰지 못한다.
- `insert` 의 `upsert` 는 새로 삽입한 행 수와 수정한 행 수를 따로 낸다. 고치기만 하려고 보냈는데 새로 삽입한 행이 있으면 primary key 를 잘못 적은 것이니, 클로드는 그 사실을 사용자에게 알린다.
- `overwrite` 는 `where` 범위(전부면 `"all": true`)의 행을 모두 지우고 보낸 행을 넣는다. 보내는 행이 그 범위의 전부일 때 쓴다(예: 10월분을 다시 조회해 올리기). 보내지 않은 컬럼은 비워지고, 미리보기가 그 컬럼 이름을 알린다. 범위 밖 행이 섞이면 DBGateway 가 아무것도 반영하지 않고 거절한다. 범위의 행이 30,000행 이상이면 스크립트는 지워질 행 수를 셀 수 없어 실행하지 않으니, 범위를 나눠(예: 월별) 요청한다. 바뀐 일부 행만 고치려면 `upsert` 를 쓴다.
- `truncate` 는 컬럼·primary key·인덱스·설명을 남기고 행만 모두 지운다. `delete` 는 `where` 가 반드시 있어야 하고, 모든 행 삭제는 `truncate` 로 한다.
- 종료 코드는 0 성공, 1 거절·중단, 3 확인 필요다.

JSON 파일의 모양은 다음과 같다. `//` 줄은 설명이라 파일에 넣지 않는다. `where` 의 연산자는 `=`·`!=`·`>`·`>=`·`<`·`<=`·`between`·`in`·`like` 다.

```json
// create --spec
{"schema": "BS", "table": "리테일_월별판매", "description": "리테일 대시보드 월별 판매 집계",
 "columns": [{"name": "기준월", "type": "varchar", "length": 6, "nullable": false},
             {"name": "상품코드", "type": "varchar", "length": 20, "nullable": false},
             {"name": "판매금액", "type": "numeric"}],
 "primary_key": ["기준월", "상품코드"]}

// select --request
{"schema": "BS", "table": "리테일_월별판매", "columns": ["상품코드", "판매금액"],
 "where": {"기준월": {">=": "202601"}}, "order_by": [{"column": "판매금액", "descending": true}], "limit": 100}

// insert --request (mode: append 덧붙이기 · upsert 같은 primary key 는 보낸 컬럼만 덮어쓰기)
{"schema": "BS", "table": "리테일_월별판매", "mode": "append",
 "rows": [{"기준월": "202609", "상품코드": "A001", "판매금액": "1250000"}]}

// update --request (전부가 대상이면 where 대신 "all": true)
{"schema": "BS", "table": "리테일_월별판매", "where": {"상품코드": "A001"}, "set": {"판매금액": "1300000"}}

// delete --request (where 필수)
{"schema": "BS", "table": "리테일_월별판매", "where": {"기준월": "202609"}}

// overwrite --request (전부가 대상이면 where 대신 "all": true)
{"schema": "BS", "table": "리테일_월별판매", "where": {"기준월": "202609"},
 "rows": [{"기준월": "202609", "상품코드": "A001", "판매금액": "1250000"}]}

// alter --change (아래 다섯 가지 중 하나만)
{"schema": "BS", "table": "리테일_월별판매", "add_column": {"name": "비고", "type": "text"}}
{"schema": "BS", "table": "리테일_월별판매", "drop_column": "비고"}
{"schema": "BS", "table": "리테일_월별판매", "rename_column": {"from": "비고", "to": "메모"}}
{"schema": "BS", "table": "리테일_월별판매", "rename_table": "리테일_판매"}
{"schema": "BS", "table": "리테일_월별판매", "set_description": {"description": "월별 판매 집계"}}

// index-create --spec
{"schema": "BS", "table": "리테일_월별판매", "name": "ix_상품코드", "columns": ["상품코드"]}
```

컬럼 타입은 `text`·`varchar`(`length` 필수)·`integer`·`bigint`·`numeric`·`boolean`·`date`·`timestamptz`·`jsonb` 다. 이름은 한글·영문·숫자·`_` 만 쓰고 숫자로 시작하지 않는다. 소수와 날짜는 조회 결과에 문자열로 온다.

## 작업 순서

1. **스키마를 확인한다.** `schemas` 로 쓸 수 있는 스키마를 본다.
2. **내 표 기록과 대조한다.** 기록에 있는 표를 쓰기 전에 `record list` 를 실행한다. "DBGateway 목록에 없음"이 붙은 표는 동료가 지웠거나 이름을 바꾼 표다. 클로드는 그 사실을 사용자에게 알리고 기록에서 뺄지 묻는다. 새 이름의 표를 찾아 기록에 옮기는 일은 사용자가 정한다. DBGateway 에는 이름 변경과 삭제 뒤 다시 만들기를 구분할 정보가 없기 때문이다.
3. **표를 만든다.** `create` 의 `description` 에는 같은 본부 동료가 표 목록에서 보고 알아볼 짧은 요약(1,000자 이하)을 쓴다. `--purpose` 에는 사용자가 나중에 보고 알 수 있게 자세한 용도를 쓰고, 이 값은 내 표 기록에만 남는다.
4. **행을 넣고 읽는다.** `insert`(append)와 `select` 는 바로 실행한다.
5. **되돌릴 수 없는 동작은 아래 「확인 절차」를 따른다.**

## 확인 절차

표 삭제·비우기, `upsert` 삽입, 범위 교체, 행 수정·삭제, 컬럼 삭제, 표·컬럼 이름 변경은 데이터나 구조를 되돌릴 수 없게 바꾼다. 같은 본부 동료가 만든 표일 수도 있다. 그래서 스크립트는 `--confirm` 없이 실행되면 변경 요청을 보내지 않고, 미리보기와 `확인값:` 줄을 낸 뒤 종료 코드 3 으로 멈춘다.

```
대상: BS.투자후보
내 표 기록에 없음: 다른 사람이 만들었을 수 있는 표
조건에 맞는 행: 3
확인값: 3
실행하려면 --confirm 3
```

1. 클로드는 미리보기를 그대로 사용자에게 보이고 AskUserQuestion 으로 실행할지 묻는다. "내 표 기록에 없음" 줄이 있으면 그 사실을 질문 머리에 적는다.
2. 사용자가 실행을 고른 때에만 같은 명령에 `--confirm <확인값>` 을 붙여 다시 실행한다. 클로드가 스스로 확인값을 붙이지 않는다.
3. 그사이 대상이 바뀌어 확인값이 달라졌으면 스크립트는 "대상 규모가 바뀜"으로 멈춘다. 이때는 1번부터 다시 한다.

미리보기의 규모는 동작에 따라 다르다. 조건이 있는 수정·삭제·범위 교체는 실제로 센 행 수다. 범위 교체의 미리보기에는 보낼 행 수도 나온다.

표 전체가 대상인 동작(표 삭제·비우기, `"all": true`, 컬럼 삭제)은 데이터를 PC 로 가져오지 않으려고 통계의 추정 행 수를 쓴다. 추정치라 동료가 방금 바꾼 행은 반영되지 않을 수 있다. 이름 변경의 확인값은 새 이름이다.

- **확인 대상 동작은 이 스크립트로만 실행한다.** 스크립트가 실패하거나 원하는 동작이 없으면 즉석 코드나 백엔드 코드로 DBGateway 를 직접 호출하지 않고 사용자에게 알린다.
- 인덱스 삭제와 설명 변경은 다시 만들 수 있어 확인 없이 실행한다. 컬럼을 지우면 그 컬럼이 든 인덱스도 함께 지워지고, 미리보기가 그 이름을 알린다. primary key 에 든 컬럼은 지울 수 없다.

## 내 표 기록

DBGateway 는 누가 표를 만들었는지 모른다. 그래서 스크립트는 이 PC 사용자가 만든 표를 사용자 폴더의 `managing-sandbox/tables.json` 에 적어 둔다. 항목은 스키마·표 이름·자세한 용도·만든 날짜다. 컬럼은 적지 않으니 필요하면 `describe` 로 본다.

- 스크립트는 요청이 성공했을 때만 기록을 고친다. 표를 만들면 추가하고, 표 이름을 바꾸면 고치고, 표를 지우면 뺀다.
- 다른 PC 나 서비스 백엔드로 만든 표는 사용자가 원하면 `record add` 로 기록한다. DBGateway 에 그 표가 있을 때만 기록된다.
- 결과를 모른다는 거절이나 "변경은 반영됨. 내 표 기록만 고치지 못함"이 나오면, 클로드는 `tables`·`describe` 로 반영 여부를 확인하고 `record` 명령으로 기록을 고친다. 같은 요청을 다시 보내지 않는다.
- 기록 파일을 읽지 못하면 스크립트는 파일을 덮어쓰지 않고, 표를 만들거나 지우는 요청도 보내지 않고 멈춘다. 클로드는 그 사실을 사용자에게 알린다.

## 실패

거절되면 스크립트는 `거절(<코드>): <사유>` 와 `- 조치: <다음 행동>` 두 줄을 내고 종료 코드 1 로 멈춘다. 스크립트는 어떤 요청도 자동으로 다시 보내지 않는다. 클로드는 `조치` 줄을 그대로 전하고 그대로 따른다.

- **`write_outcome_unknown`·`sandbox_undecided`:** 쓰기가 반영됐는지 모른다는 뜻이다. 같은 요청을 다시 보내지 않고 조회로 확인한다. primary key 없는 표에 append 했으면 조회로도 가릴 수 없으므로 다시 보낼지 사용자에게 묻는다.
- **`no_answer`:** 요청을 보낸 뒤 응답을 받지 못했다. 쓰기였으면 반영 여부를 모르므로 위와 같이 다시 보내지 않고 조회로 확인한다.
- **`sandbox_unreachable`:** 다시 시도하지 않고 사용자에게 알린다. DBGateway 쪽 설정 문제일 수도 있다.
- **"DBGateway 에 연결하지 못함":** 사내망인지, 환경 변수 `QUERY_GATEWAY_URL` 이 맞는지 확인한다.
- **`http_404`:** 연결한 DBGateway 에 샌드박스 경로가 없다. 사용자에게 알린다.

범위 교체(`overwrite`)에서 반영 여부를 모르면 클로드는 위와 같이 조회로 범위의 행을 확인한다. 다시 실행해야 하면 직전의 `--confirm` 명령을 쓰지 않고, 확인값 없이 실행해 미리보기부터 사용자에게 보인다. 그사이 동료가 그 범위에 쓴 행도 다시 지워질 수 있기 때문이다.

## 서비스 백엔드

대시보드 같은 서비스의 백엔드도 개발자의 같은 접근 키로 샌드박스를 호출할 수 있다. 백엔드 코드는 환경 변수 `KIWOOM_ACCESS_KEY` 에서 키를 읽는다. 서버에 키를 넣는 방법은 배포 작업이라 이 스킬이 다루지 않는다.

클로드는 이런 코드를 쓰기 전에 다음을 개발자에게 알린다.
- 서비스로 들어온 모든 요청은 개발자 권한으로 처리되고, DBGateway 의 작업 기록에도 개발자로 남는다.
- 같은 키는 샌드박스만이 아니라 개발자에게 허용된 WINUS 등록 쿼리도 연다. AX팀 직원의 키는 모든 본부 스키마를 쓸 수 있다.
- 키를 재발급하면 서버의 키도 바꿔야 서비스가 멈추지 않는다. 개발자가 다른 본부로 옮기면 서비스가 쓸 수 있는 스키마가 바뀌고, 퇴사해 키가 폐기되면 서비스가 멈춘다.
- 키를 넣은 파일은 체크포인트에 넣지 않고, 요청 헤더는 기록에 남기지 않는다.
- DBGateway 는 키 주인만 확인하므로, 서비스를 누가 쓰는지는 서비스가 직접 나눠야 한다. 접근을 나누지 않는 서비스에는 쓰기 기능을 두지 않는다.

코드 규칙과 예시는 [backend.md](backend.md) 에 있다.
