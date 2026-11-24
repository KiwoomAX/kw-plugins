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

export type Summary = { row: number; label: string; label_col: string | null; group_by: string | null; expr: Record<string, string | null> };

/* 데이터 행 사이에 소계 행을 끼운 표시 순서. 묶는 열이 있으면 그 값이 끝나는 곳 뒤, 없으면 표 끝이다.
   분석기는 엑셀의 소계 행마다 항목을 하나씩 만들므로, 같은 열로 묶는 항목은 첫 항목 하나로 묶음마다 소계를 낸다.
   묶는 열이 둘 이상이면 값이 덜 자주 바뀌는 열을 바깥 묶음으로 보고, 같으면 엑셀에서 소계 항목이 나중에 나온 열을 바깥으로 본다(엑셀은 안쪽 소계 행을 먼저 둔다).
   안쪽 소계를 먼저 넣고, 바깥 묶음이 끝나면 안쪽 묶음도 끝난다. */
export function withSummaries(rows: Row[], summaries: Summary[]): { row: Row; summary?: Summary }[] {
  const known: Record<string, Row> = {};
  const line = (s: Summary, part: Row[]) => {
    const row: Row = s.label_col ? { [s.label_col]: s.label } : {};
    const ordered = Object.entries(s.expr).sort(([, a], [, b]) => Number(a?.includes('ROW(')) - Number(b?.includes('ROW(')));
    known[s.label] = row;
    for (const [column, expr] of ordered) row[column] = expr ? evaluate(expr, part, known) : null;
    return { row: { ...row }, summary: s };
  };
  const first = new Map<string, Summary>();
  for (const s of summaries) if (s.group_by && !first.has(s.group_by)) first.set(s.group_by, s);
  const changes = new Map([...first.keys()].map((c) => [c, rows.filter((r, i) => i > 0 && r[c] !== rows[i - 1][c]).length]));
  const columns = [...first.keys()].sort((a, b) => (changes.get(b) ?? 0) - (changes.get(a) ?? 0)); // 안쪽 묶음부터. 같으면 엑셀 순서
  const outer = (a: string, b: string) => columns.indexOf(a) > columns.indexOf(b); // a 가 b 의 바깥 묶음
  const start = new Map(columns.map((c) => [c, 0]));
  const out: { row: Row; summary?: Summary }[] = [];
  rows.forEach((row, i) => {
    out.push({ row });
    const changed = columns.filter((c) => i + 1 === rows.length || rows[i + 1][c] !== row[c]);
    const ended = columns.filter((c) => changed.includes(c) || changed.some((o) => outer(o, c)));
    for (const c of ended) {
      out.push(line(first.get(c) as Summary, rows.slice(start.get(c), i + 1)));
      start.set(c, i + 1);
    }
  });
  for (const s of summaries.filter((x) => !x.group_by)) out.push(line(s, rows));
  return out;
}
