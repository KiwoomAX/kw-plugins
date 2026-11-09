"""소계 · 합계 식을 계산한다. 화면의 summary.ts 와 같은 문법이고 같은 값을 낸다.

식   := 항 (("+" | "-" | "*" | "/") 항)*
항   := 숫자 | "(" 식 ")" | 함수
함수 := SUM(열) | AVERAGE(열) | COUNT(열) | SUMIF(조건 열, "값", 합 열) | SUMPRODUCT(열, 열) | ROW("소계 이름", 열)
"""
import re
from decimal import Decimal, InvalidOperation

TOKEN = re.compile(r'\s*(?:(\d+(?:\.\d+)?)|"([^"]*)"|([A-Za-z_가-힣][0-9A-Za-z_가-힣]*)|([()+\-*/,]))')


class _Stop(Exception):
    """식을 계산할 수 없을 때 쓴다. evaluate 는 None 을 돌려준다."""


def _tokens(expr):
    out, i = [], 0
    while i < len(expr.rstrip()):
        m = TOKEN.match(expr, i)
        if not m:
            raise _Stop
        i = m.end()
        out.append(("num", m[1]) if m[1] else ("text", m[2]) if m[2] is not None else ("name", m[3]) if m[3] else ("op", m[4]))
    return out


def _number(v):
    """숫자로 읽을 수 있으면 Decimal, 아니면 None. 샌드박스의 소수는 글자로 온다."""
    if v is None or isinstance(v, bool):
        return None
    try:
        return Decimal(str(v))
    except InvalidOperation:
        return None


def _call(name, args, rows, summaries):
    """함수 하나의 값. args 는 (종류, 글자) 목록이다."""
    def column(i):
        if args[i][0] != "name":
            raise _Stop
        return args[i][1]

    if name in ("SUM", "AVERAGE", "COUNT") and len(args) == 1:
        seen = [n for r in rows if (n := _number(r.get(column(0)))) is not None]
        if name == "COUNT":
            return Decimal(len(seen))
        if name == "SUM":
            return sum(seen, Decimal(0))
        return sum(seen, Decimal(0)) / len(seen) if seen else _raise()
    if name == "SUMIF" and len(args) == 3 and args[1][0] in ("text", "num"):
        want = args[1][1].strip()
        return sum((_number(r.get(column(2))) or Decimal(0) for r in rows if str(r.get(column(0))).strip() == want), Decimal(0))
    if name == "SUMPRODUCT" and len(args) == 2:
        return sum(((_number(r.get(column(0))) or Decimal(0)) * (_number(r.get(column(1))) or Decimal(0)) for r in rows), Decimal(0))
    if name == "ROW" and len(args) == 2 and args[0][0] == "text":
        value = _number((summaries or {}).get(args[0][1], {}).get(column(1)))
        return value if value is not None else _raise()
    raise _Stop


def _raise():
    raise _Stop


class _Parser:
    def __init__(self, tokens, rows, summaries):
        self.tokens, self.rows, self.summaries, self.i = tokens, rows, summaries, 0

    def peek(self):
        return self.tokens[self.i] if self.i < len(self.tokens) else (None, None)

    def take(self, kind=None, value=None):
        t = self.peek()
        if t[0] is None or (kind and t[0] != kind) or (value and t[1] != value):
            raise _Stop
        self.i += 1
        return t

    def expression(self):
        out = self.term()
        while self.peek() in (("op", "+"), ("op", "-")):
            op = self.take()[1]
            right = self.term()
            out = out + right if op == "+" else out - right
        return out

    def term(self):
        out = self.factor()
        while self.peek() in (("op", "*"), ("op", "/")):
            op = self.take()[1]
            right = self.factor()
            if op == "/" and right == 0:
                raise _Stop
            out = out * right if op == "*" else out / right
        return out

    def factor(self):
        kind, value = self.peek()
        if (kind, value) == ("op", "-"):
            self.take()
            return -self.factor()
        if (kind, value) == ("op", "("):
            self.take()
            out = self.expression()
            self.take("op", ")")
            return out
        if kind == "num":
            self.take()
            return Decimal(value)
        name = self.take("name")[1]
        self.take("op", "(")
        args = []
        while self.peek() != ("op", ")"):
            if args:
                self.take("op", ",")
            args.append(self.take())
        self.take("op", ")")
        return _call(name, args, self.rows, self.summaries)


def evaluate(expr, rows, summaries=None):
    """식의 값(Decimal). 문법에 없거나 0 으로 나누면 None. summaries 는 {소계 이름: {열: 값}} 이다."""
    try:
        parser = _Parser(_tokens(expr), rows, summaries)
        out = parser.expression()
        return out if parser.i == len(parser.tokens) else None
    except (_Stop, InvalidOperation):
        return None
