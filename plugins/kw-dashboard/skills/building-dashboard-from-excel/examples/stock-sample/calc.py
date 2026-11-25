"""예시 화면의 계산 코드. 가짜 주가로 종목별 등락률을 내고, 수기 입력 메모를 종목코드로 붙인다.

calc-guide.md 의 약속대로 tables 는 {표 이름: 행 목록}, base_date 는 날짜이고, {대상: 행 목록} 을 돌려준다.
"""
from decimal import ROUND_HALF_UP, Decimal

PRICE, MEMO = "stock_sample__raw_winus__price", "stock_sample__raw_manual__memo"
CENT = Decimal("0.01")


def calculate(tables, base_date):
    memo = {r["종목코드"]: r["메모"] for r in tables[MEMO]}
    rows = []
    for i, p in enumerate(sorted(tables[PRICE], key=lambda r: r["종목코드"]), 1):
        start, end = Decimal(str(p["시가"])), Decimal(str(p["종가"]))
        rate = ((end - start) / start * 100).quantize(CENT, ROUND_HALF_UP)  # 등락률 = (종가 - 시가) / 시가 × 100, 소수 둘째 자리 사사오입
        rows.append({"row_seq": i, "종목명": p["종목명"], "등락률": str(rate), "변동성": p["변동성"], "메모": memo.get(p["종목코드"])})
    average = (sum(Decimal(r["등락률"]) for r in rows) / len(rows)).quantize(CENT, ROUND_HALF_UP) if rows else None
    return {"daily": rows, "daily_total": [{"row_seq": 1, "구분": "전체", "종목수": len(rows), "등락률평균": None if average is None else str(average)}]}
