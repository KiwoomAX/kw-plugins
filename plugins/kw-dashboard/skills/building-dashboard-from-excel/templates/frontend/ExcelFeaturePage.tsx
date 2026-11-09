/* 결과표 조회 화면. 원천 표와 결과표를 기준일별로 나란히 보고, 입력 양식을 올리고, 엑셀로 내려받는다.
   표 목록과 열은 모두 API 가 알려 주므로 엑셀마다 이 파일을 고치지 않는다. */
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import DashboardLayout from '../../shell/DashboardLayout';
import { evaluate, type Row } from './summary';
import './ExcelFeaturePage.css';

type TableInfo = { name: string; label: string };
type Settings = { date_input: { on: boolean; default: string }; refresh_unit: string; allow_today: boolean; allow_holiday: boolean };
type Column = { name: string; type: string; header?: string; levels?: string[] };
type Summary = { row: number; label: string; label_col: string | null; group_by: string | null; expr: Record<string, string | null> };
type TableData = { columns: Column[]; rows: Row[]; summaries: Summary[]; dates: Row[]; base_time: string | null; loaded_at: string | null; state: string };
type Reply = { status: string; message: string; errors: { sheet: string; cell: string; reason: string }[] };

const RECALC = '이 기준일의 결과를 다시 계산해야 합니다';
const WAITING = 'WINUS 쿼리 연결을 기다리고 있습니다';

async function getJson<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, init);
  if (!r.ok) throw new Error(`요청 실패(${r.status})`);
  return r.json() as Promise<T>;
}

function shown(value: unknown, column?: Column): string {
  if (value === null || value === undefined) return '';
  if (column?.type !== 'numeric') return String(value);
  const n = Number(value);
  return Number.isNaN(n) ? String(value) : n.toLocaleString('en-US', { maximumFractionDigits: 6 }); // 코드 열은 글자라 쉼표가 붙지 않는다
}

/* 데이터 행 사이에 소계 행을 끼운 표시 순서. 묶는 열이 있으면 그 값이 끝나는 곳 뒤, 없으면 표 끝이다 */
function withSummaries(table: TableData): { row: Row; summary?: Summary }[] {
  const known: Record<string, Row> = {};
  const line = (s: Summary, rows: Row[]) => {
    const row: Row = s.label_col ? { [s.label_col]: s.label } : {};
    const ordered = Object.entries(s.expr).sort(([, a], [, b]) => Number(a?.includes('ROW(')) - Number(b?.includes('ROW(')));
    known[s.label] = row;
    for (const [column, expr] of ordered) row[column] = expr ? evaluate(expr, rows, known) : null;
    return { row: { ...row }, summary: s };
  };
  const grouped = table.summaries.filter((s) => s.group_by);
  const out: { row: Row; summary?: Summary }[] = [];
  let start = 0;
  table.rows.forEach((row, i) => {
    out.push({ row });
    for (const s of grouped) {
      const column = s.group_by as string;
      if (table.rows[i + 1]?.[column] !== row[column]) {
        const part = table.rows.slice(start).filter((r, j) => j + start <= i && r[column] === row[column]);
        out.push(line(s, part));
      }
    }
    if (grouped.some((s) => table.rows[i + 1]?.[s.group_by as string] !== row[s.group_by as string])) start = i + 1;
  });
  for (const s of table.summaries.filter((x) => !x.group_by)) out.push(line(s, table.rows));
  return out;
}

function headerText(column: Column, table: TableData): string | null {
  return column.name.startsWith('t_plus_') ? String(table.dates[0]?.[column.name] ?? '') : null;
}

function Head({ table }: { table: TableData }) {
  const depth = Math.max(1, ...table.columns.map((c) => c.levels?.length ?? 1));
  const lines = Array.from({ length: depth }, (_, d) => table.columns.map((c) => headerText(c, table) ?? c.levels?.[d] ?? c.header ?? c.name));
  return (
    <thead>
      {lines.map((line, d) => {
        const cells: { text: string; span: number }[] = [];
        line.forEach((text, i) => {
          if (i && text === line[i - 1] && d < depth - 1) cells[cells.length - 1].span += 1;
          else cells.push({ text: d > 0 && text === lines[d - 1][i] ? '' : text, span: 1 });
        });
        return (
          <tr key={d}>
            {d === 0 && <th className="rn" rowSpan={depth} />}
            {cells.map((c, i) => (
              <th key={i} colSpan={c.span}>
                {c.text}
              </th>
            ))}
          </tr>
        );
      })}
    </thead>
  );
}

function Pane({ label, table, result }: { label: string; table?: TableData; result: boolean }) {
  const lines = useMemo(() => (table ? withSummaries(table) : []), [table]);
  let seq = 0;
  return (
    <section className={`sv-pane ${result ? 'res' : ''}`}>
      <div className="sv-cap">
        <b>{label}</b>
      </div>
      <div className="sv-grid">
        {table && (
          <table>
            <Head table={table} />
            <tbody>
              {lines.map(({ row, summary }, i) => (
                <tr key={i} className={summary ? 'sum' : ''}>
                  <td className="rn">{summary ? '' : (seq += 1)}</td>
                  {table.columns.map((c) => (
                    <td key={c.name} className={c.type === 'numeric' ? 'n' : ''}>
                      {shown(row[c.name], c)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}

export default function ExcelFeaturePage({ api, title }: { api: string; title: string }) {
  const [info, setInfo] = useState<{ source: TableInfo[]; result: TableInfo[]; waiting: boolean; settings: Settings }>();
  const [dates, setDates] = useState<string[]>([]);
  const [date, setDate] = useState('');
  const [raw, setRaw] = useState('');
  const [res, setRes] = useState('');
  const [cache, setCache] = useState<Record<string, TableData>>({});
  const [notice, setNotice] = useState('');
  const [dialog, setDialog] = useState<'' | 'upload' | 'refetch'>('');
  const [newDate, setNewDate] = useState('');
  const [file, setFile] = useState<File>();
  const [reply, setReply] = useState<Reply>();
  const asked = useRef(new Set<string>());

  const loadDates = useCallback(async () => {
    const got = await getJson<{ dates: string[]; default: string | null }>(`${api}/dates`);
    setDates(got.dates);
    return got;
  }, [api]);

  useEffect(() => {
    void (async () => {
      const got = await getJson<NonNullable<typeof info>>(`${api}/tables`);
      setInfo(got);
      setRaw(got.source[0]?.name ?? '');
      setRes(got.result[0]?.name ?? '');
      setDate((await loadDates()).default ?? '');
    })();
  }, [api, loadDates]);

  const need = useCallback(
    async (name: string, day: string, force = false) => {
      if (!name || !day) return;
      const key = `${day}|${name}`;
      if (asked.current.has(key) && !force) return; // 이미 받은 표는 다시 요청하지 않아 표를 바로 바꿀 수 있다
      asked.current.add(key);
      const data = await getJson<TableData>(`${api}/table?date=${encodeURIComponent(day)}&name=${encodeURIComponent(name)}`);
      setCache((old) => ({ ...old, [key]: data }));
    },
    [api],
  );

  useEffect(() => {
    void need(raw, date);
    void need(res, date);
  }, [raw, res, date, need]);

  const rawTable = cache[`${date}|${raw}`];
  const resTable = cache[`${date}|${res}`];
  const state = (resTable ?? rawTable)?.state;
  const latest = dates[0];

  const lastDay = useMemo(() => {
    const d = new Date();
    if (!info?.settings.allow_today) d.setDate(d.getDate() - 1);
    return d.toISOString().slice(0, 10);
  }, [info]);

  const done = async (got: Reply, day: string) => {
    setReply(undefined);
    setDialog('');
    setNotice(got.message);
    await loadDates();
    asked.current.clear();
    setCache({});
    setDate(day);
    await Promise.all([need(raw, day, true), need(res, day, true)]);
  };

  const send = async (confirm: boolean) => {
    if (!file) return;
    const day = newDate || date;
    const body = new FormData();
    body.append('file', file);
    body.append('date', day);
    body.append('confirm', String(confirm));
    const got = await getJson<Reply>(`${api}/upload`, { method: 'POST', body });
    if (got.status === 'saved' || got.status === 'same') await done(got, day);
    else setReply(got);
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    void send(false);
  };

  const refetch = async () => {
    const got = await getJson<Reply>(`${api}/refetch?date=${encodeURIComponent(date)}`, { method: 'POST' });
    if (got.status === 'saved') await done(got, date);
    else {
      setDialog('');
      setNotice(got.message);
    }
  };

  const off = !info || info.waiting;
  const existing = dates.includes(newDate || date);
  const rawLabel = info?.source.find((t) => t.name === raw)?.label ?? '';
  const resLabel = info?.result.find((t) => t.name === res)?.label ?? '';

  return (
    <DashboardLayout title={title} asof={resTable?.loaded_at ? `기준일 ${date} · 적재 ${resTable.loaded_at}` : undefined}>
      <div className="sv">
        <div className="sv-bar">
          <label>
            기준일
            <select aria-label="기준일" value={date} onChange={(e) => setDate(e.target.value)}>
              {dates.map((d) => (
                <option key={d}>{d}</option>
              ))}
            </select>
          </label>
          <label>
            원본 데이터
            <select aria-label="원본 데이터" value={raw} onChange={(e) => setRaw(e.target.value)}>
              <option value="">보지 않음</option>
              {info?.source.map((t) => (
                <option key={t.name} value={t.name}>
                  {t.label}
                </option>
              ))}
            </select>
          </label>
          <span className="sv-arrow">→</span>
          <label>
            결과 표
            <select aria-label="결과 표" value={res} onChange={(e) => setRes(e.target.value)}>
              <option value="">보지 않음</option>
              {info?.result.map((t) => (
                <option key={t.name} value={t.name}>
                  {t.label}
                </option>
              ))}
            </select>
          </label>
          <span className="sv-sp" />
          <button className="sv-btn" disabled={off || !date} onClick={() => setDialog('refetch')}>
            WINUS 다시 받기
          </button>
          <button className="sv-btn" disabled={off} onClick={() => { setNewDate(latest ?? ''); setFile(undefined); setReply(undefined); setDialog('upload'); }}>
            수기 입력 · 외부 데이터 업로드
          </button>
          <a className="sv-btn" href={`${api}/export?date=${encodeURIComponent(date)}`}>
            엑셀 내려받기
          </a>
        </div>
        {info?.waiting && <div className="sv-ok">{WAITING}</div>}
        {state && state !== '완료' && <div className="sv-ok">{RECALC}</div>}
        {notice && <div className="sv-ok">{notice}</div>}
        <div className="sv-main">
          {raw && <Pane label={rawLabel} table={rawTable} result={false} />}
          {res && <Pane label={resLabel} table={resTable} result />}
          {!raw && !res && <div className="sv-empty">표를 골라 주세요</div>}
        </div>

        {dialog === 'refetch' && (
          <div className="sv-scrim open">
            <div className="sv-dlg" role="dialog" aria-modal="true">
              <h2>WINUS 값 갱신</h2>
              <div className="sv-date">
                <b>기준일 {date}</b> 이 기준일의 WINUS 값을 다시 받아 결과를 다시 계산합니다
              </div>
              <div className="sv-act">
                <button className="sv-btn" onClick={() => setDialog('')}>
                  취소
                </button>
                <button className="sv-btn primary" onClick={() => void refetch()}>
                  다시 받기
                </button>
              </div>
            </div>
          </div>
        )}

        {dialog === 'upload' && (
          <div className="sv-scrim open">
            <form className="sv-dlg" role="dialog" aria-modal="true" onSubmit={submit}>
              <h2>입력 양식 올리기</h2>
              <label className="sv-row">
                <span>기준일</span>
                <input aria-label="기준일 선택" type="date" max={lastDay} value={newDate} onChange={(e) => setNewDate(e.target.value)} />
              </label>
              <div className="sv-date">
                {existing ? '이 기준일에는 이미 수기 입력이 있습니다. 업데이트하려면 올려 주세요' : '새 기준일입니다. WINUS 데이터를 이 기준일로 받아 계산합니다'}
              </div>
              <div className="sv-step">
                <span>
                  입력 양식에는 지금 보고 있는 기준일(<b>{date}</b>)의 수기 입력 · 외부 데이터 값이 채워져 있습니다. 바꿀 값만 고쳐 업로드해 주세요
                </span>
                <a className="sv-btn" href={`${api}/form?date=${encodeURIComponent(date)}`}>
                  입력 양식 내려받기
                </a>
              </div>
              <label className="sv-row">
                <span>채운 입력 양식</span>
                <input aria-label="채운 입력 양식" type="file" accept=".xlsx" onChange={(e) => setFile(e.target.files?.[0])} />
              </label>
              {reply && (
                <div className="sv-date">
                  {reply.message}
                  {reply.errors.slice(0, 20).map((x) => (
                    <div key={`${x.sheet}${x.cell}`}>
                      {x.sheet} {x.cell}: {x.reason}
                    </div>
                  ))}
                </div>
              )}
              <div className="sv-act">
                <button className="sv-btn" type="button" onClick={() => setDialog('')}>
                  취소
                </button>
                {reply?.status === 'needs_confirm' ? (
                  <button className="sv-btn primary" type="button" onClick={() => void send(true)}>
                    진행
                  </button>
                ) : (
                  <button className="sv-btn primary" type="submit" disabled={!file}>
                    올리고 계산하기
                  </button>
                )}
              </div>
            </form>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
