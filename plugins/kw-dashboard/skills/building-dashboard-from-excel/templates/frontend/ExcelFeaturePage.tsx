/* 결과표 조회 화면. 원천 표와 결과표를 기준일별로 나란히 보고, 입력 양식을 올리고, 엑셀로 내려받는다.
   표 목록과 열은 모두 API 가 알려 주므로 엑셀마다 이 파일을 고치지 않는다. */
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import DashboardLayout from '../../shell/DashboardLayout';
import './ExcelFeaturePage.css';

type Row = Record<string, unknown>;
type TableInfo = { name: string; label: string };
type Settings = { date_input: { on: boolean; default: string }; refresh_unit: string; allow_today: boolean };
type Column = { name: string; type: string; header?: string; levels?: string[] };
type TableData = { columns: Column[]; rows: Row[]; dates: Row[]; base_time: string | null; loaded_at: string | null; state: string };
type Reply = { status: string; message: string; errors: { sheet: string; cell: string; reason: string }[] };

const RECALC = '이 기준일의 결과를 다시 계산해야 합니다';
const WAITING = 'WINUS 쿼리 연결을 기다리고 있습니다';

/* 한국 날짜(YYYY-MM-DD). 브라우저 시간대와 상관없이 오늘에서 daysBack 일 앞의 날을 정한다 */
function koreanDay(daysBack = 0): string {
  return new Date(Date.now() - daysBack * 86400000).toLocaleDateString('sv-SE', { timeZone: 'Asia/Seoul' });
}

/* 실패하면 서버가 보낸 안내(detail)를 담은 오류를 낸다. 예: 로그인 토큰을 받지 못했다는 503 */
async function getJson<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, init);
  if (!r.ok) {
    const body = (await r.json().catch(() => null)) as { detail?: unknown } | null;
    throw new Error(typeof body?.detail === 'string' ? body.detail : `요청 실패(${r.status})`);
  }
  return r.json() as Promise<T>;
}

const message = (e: unknown) => (e instanceof Error ? e.message : String(e));

function shown(value: unknown, column?: Column): string {
  if (value === null || value === undefined) return '';
  if (column?.type !== 'numeric') return String(value);
  const n = Number(value);
  return Number.isNaN(n) ? String(value) : n.toLocaleString('en-US', { maximumFractionDigits: 6 }); // 코드 열은 글자라 쉼표가 붙지 않는다
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
              {table.rows.map((row, i) => (
                <tr key={i}>
                  <td className="rn">{i + 1}</td>
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
      try {
        const got = await getJson<NonNullable<typeof info>>(`${api}/tables`);
        setInfo(got);
        setRaw(got.source[0]?.name ?? '');
        setRes(got.result[0]?.name ?? '');
        setDate((await loadDates()).default ?? '');
      } catch (e) {
        setNotice(message(e));
      }
    })();
  }, [api, loadDates]);

  const need = useCallback(
    async (name: string, day: string, force = false) => {
      if (!name || !day) return;
      const key = `${day}|${name}`;
      if (asked.current.has(key) && !force) return; // 이미 받은 표는 다시 요청하지 않아 표를 바로 바꿀 수 있다
      asked.current.add(key);
      try {
        const data = await getJson<TableData>(`${api}/table?date=${encodeURIComponent(day)}&name=${encodeURIComponent(name)}`);
        setCache((old) => ({ ...old, [key]: data }));
      } catch (e) {
        asked.current.delete(key); // 실패한 표는 다시 고르면 다시 요청한다
        setNotice(message(e));
      }
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

  const lastDay = koreanDay(info?.settings.allow_today ? 0 : 1);
  /* 올리기 창의 기준일 첫 값. 분석 때 정한 기본값(오늘 · 어제)을 쓰고, 그 밖의 값이면 가장 최근 기준일을 쓴다 */
  const firstDay = useMemo(() => {
    const rule = info?.settings.date_input.default;
    const day = rule === '오늘' ? koreanDay(0) : rule === '어제' ? koreanDay(1) : latest ?? '';
    return day && day > lastDay ? lastDay : day;
  }, [info, latest, lastDay]);

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
    let got: Reply;
    try {
      got = await getJson<Reply>(`${api}/upload`, { method: 'POST', body });
    } catch (e) {
      setReply({ status: 'failed', message: message(e), errors: [] });
      return;
    }
    if (got.status === 'saved' || got.status === 'same') await done(got, day);
    else setReply(got);
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    void send(false);
  };

  const refetch = async () => {
    let got: Reply;
    try {
      got = await getJson<Reply>(`${api}/refetch?date=${encodeURIComponent(date)}`, { method: 'POST' });
    } catch (e) {
      got = { status: 'failed', message: message(e), errors: [] };
    }
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
          <button className="sv-btn" disabled={off} onClick={() => { setNewDate(firstDay); setFile(undefined); setReply(undefined); setDialog('upload'); }}>
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
                {info?.settings.date_input.on ? (
                  <input aria-label="기준일 선택" type="date" max={lastDay} value={newDate} onChange={(e) => setNewDate(e.target.value)} />
                ) : (
                  <b>{newDate}</b>
                )}
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
