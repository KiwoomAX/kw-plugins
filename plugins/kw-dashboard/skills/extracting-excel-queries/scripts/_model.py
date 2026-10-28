"""엑셀 외부 데이터 연결 하나를 나타내는 공통 데이터 형식과 고정 값."""
from dataclasses import dataclass, field

# spec 「결과물 형식」 의 연결 종류 값. 마지막 넷은 연결이 아니라 읽기 실패와 파일 상태를 알리는 행이다.
KINDS = (
    "ODBC 쿼리 테이블", "OLE DB 쿼리 테이블", "VBA ADODB SQL", "VBA 쿼리 테이블 생성",
    ".xls 연결 레코드", "Power Query", "외부 통합문서 링크", "DDE 링크", "VBA 파일 읽기",
    "VBA 웹 호출", "VBA 외부 프로그램 실행", "수식 외부 함수", "기타 연결 흔적",
    "VBA 읽기 실패", "엑셀 형식 아님", "열기 암호", "처리 오류",
)
FILE_STATE_KINDS = ("엑셀 형식 아님", "열기 암호", "처리 오류")
# 파일이나 VBA 프로젝트를 읽지 못했다는 행. 이 행이 있으면 연결 목록이 빠졌을 수 있다
READ_FAILURE_KINDS = ("VBA 읽기 실패", *FILE_STATE_KINDS)
# DB 를 읽는 연결 종류. 엑셀 분석기가 출처 대응표로 판정하지 못한 이 종류를 「DB 쿼리 연결」로 보인다
DB_KINDS = ("ODBC 쿼리 테이블", "OLE DB 쿼리 테이블", "VBA ADODB SQL", "VBA 쿼리 테이블 생성", ".xls 연결 레코드", "Power Query")


@dataclass
class Connection:
    kind: str
    location: str
    sql: str | None = None
    target: str = ""
    inputs: str = ""
    output_range: str = ""
    notes: list[str] = field(default_factory=list)
    origin: str = ""


def _selfcheck() -> None:
    assert ".xls 연결 레코드" in KINDS and not any("`" in k for k in KINDS)
    assert set(FILE_STATE_KINDS) <= set(READ_FAILURE_KINDS) <= set(KINDS) and set(DB_KINDS) <= set(KINDS)


if __name__ == "__main__":
    _selfcheck()
    print("selfcheck ok")
