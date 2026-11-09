/* 소계 · 합계 식을 계산한다. 백엔드 summary_expr.py 와 같은 문법이고 같은 값을 낸다.

   식   := 항 (("+" | "-" | "*" | "/") 항)*
   항   := 숫자 | "(" 식 ")" | 함수
   함수 := SUM(열) | AVERAGE(열) | COUNT(열) | SUMIF(조건 열, "값", 합 열) | SUMPRODUCT(열, 열) | ROW("소계 이름", 열) */

export type Row = Record<string, unknown>;
type Token = { kind: 'num' | 'text' | 'name' | 'op'; value: string };

const TOKEN = /\s*(?:(\d+(?:\.\d+)?)|"([^"]*)"|([A-Za-z_가-힣][0-9A-Za-z_가-힣]*)|([()+\-*/,]))/y;

class Stop extends Error {}

function tokens(expr: string): Token[] {
  const out: Token[] = [];
  const text = expr.trimEnd();
  let i = 0;
  while (i < text.length) {
    TOKEN.lastIndex = i;
    const m = TOKEN.exec(text);
    if (!m) throw new Stop();
    i = TOKEN.lastIndex;
    if (m[1] !== undefined) out.push({ kind: 'num', value: m[1] });
    else if (m[2] !== undefined) out.push({ kind: 'text', value: m[2] });
    else if (m[3] !== undefined) out.push({ kind: 'name', value: m[3] });
    else out.push({ kind: 'op', value: m[4] });
  }
  return out;
}

/* 샌드박스의 소수는 글자로 온다. 숫자로 읽을 수 없으면 null */
function number(v: unknown): number | null {
  if (v === null || v === undefined || v === '' || typeof v === 'boolean') return null;
  const n = Number(v);
  return Number.isNaN(n) ? null : n;
}

function call(name: string, args: Token[], rows: Row[], summaries?: Record<string, Row>): number {
  const column = (i: number) => {
    if (args[i].kind !== 'name') throw new Stop();
    return args[i].value;
  };
  if (['SUM', 'AVERAGE', 'COUNT'].includes(name) && args.length === 1) {
    const seen = rows.map((r) => number(r[column(0)])).filter((n): n is number => n !== null);
    if (name === 'COUNT') return seen.length;
    const total = seen.reduce((a, b) => a + b, 0);
    if (name === 'SUM') return total;
    if (!seen.length) throw new Stop();
    return total / seen.length;
  }
  if (name === 'SUMIF' && args.length === 3 && (args[1].kind === 'text' || args[1].kind === 'num')) {
    const want = args[1].value.trim();
    return rows.filter((r) => String(r[column(0)]).trim() === want).reduce((a, r) => a + (number(r[column(2)]) ?? 0), 0);
  }
  if (name === 'SUMPRODUCT' && args.length === 2) {
    return rows.reduce((a, r) => a + (number(r[column(0)]) ?? 0) * (number(r[column(1)]) ?? 0), 0);
  }
  if (name === 'ROW' && args.length === 2 && args[0].kind === 'text') {
    const value = number(summaries?.[args[0].value]?.[column(1)]);
    if (value === null) throw new Stop();
    return value;
  }
  throw new Stop();
}

/* 식의 값. 문법에 없거나 0 으로 나누면 null */
export function evaluate(expr: string, rows: Row[], summaries?: Record<string, Row>): number | null {
  try {
    const list = tokens(expr);
    let i = 0;
    const peek = () => list[i];
    const isOp = (...ops: string[]) => peek()?.kind === 'op' && ops.includes(peek().value);
    const take = (kind?: Token['kind'], value?: string) => {
      const t = list[i];
      if (!t || (kind && t.kind !== kind) || (value && t.value !== value)) throw new Stop();
      i += 1;
      return t;
    };
    const factor = (): number => {
      if (isOp('-')) {
        take();
        return -factor();
      }
      if (isOp('(')) {
        take();
        const out = expression();
        take('op', ')');
        return out;
      }
      if (peek()?.kind === 'num') return Number(take().value);
      const name = take('name').value;
      take('op', '(');
      const args: Token[] = [];
      while (!isOp(')')) {
        if (args.length) take('op', ',');
        args.push(take());
      }
      take('op', ')');
      return call(name, args, rows, summaries);
    };
    const term = (): number => {
      let out = factor();
      while (isOp('*', '/')) {
        const op = take().value;
        const right = factor();
        if (op === '/' && right === 0) throw new Stop();
        out = op === '*' ? out * right : out / right;
      }
      return out;
    };
    const expression = (): number => {
      let out = term();
      while (isOp('+', '-')) {
        const op = take().value;
        const right = term();
        out = op === '+' ? out + right : out - right;
      }
      return out;
    };
    const out = expression();
    return i === list.length ? out : null;
  } catch (e) {
    if (e instanceof Stop) return null;
    throw e;
  }
}
