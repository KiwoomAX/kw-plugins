"""쿼리 응답 값의 단위 변환. 쿼리 연결 단계가 고른 변환 이름을 읽어 그대로 계산한다.

이름은 same(그대로), 「*배수」 · 「/배수」(예: /1e6 은 백만으로 나누기, *100 은 100 곱하기), 그 둘에 사사오입을 씌운
「round(/1e8)」 모양이다. 배수는 정해 두지 않으므로 엑셀 단위가 달라도 이 파일은 고치지 않는다.
계산은 십진수로 해서 0.07 × 100 이 7 로 나온다.
"""
import re
from decimal import ROUND_HALF_UP, Decimal

NAME = re.compile(r"(round\()?([*/])(\d+(?:e\d+)?)(\))?")


def apply(name, value):
    """변환한 값(Decimal). same 이면 값을 그대로 돌려준다. 값의 쉼표는 빼고 읽는다."""
    if name == "same":
        return value
    m = NAME.fullmatch(name)
    if not m or bool(m[1]) != bool(m[4]):
        raise ValueError(f"모르는 변환 이름: {name}")
    x = Decimal(repr(value) if isinstance(value, float) else str(value).replace(",", "").strip())
    scale = Decimal(m[3])
    y = x * scale if m[2] == "*" else x / scale
    return y.quantize(Decimal(1), rounding=ROUND_HALF_UP) if m[1] else y


def text(value):
    """저장할 글자. 지수 표기와 끝의 0 을 뺀다(7.00 은 7, 1E+2 는 100)."""
    return format(value.normalize(), "f")
