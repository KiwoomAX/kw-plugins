"""입력 양식을 받아 검사하고, WINUS 를 준비하고, 계산한 뒤 저장한다.

표 사이에는 트랜잭션이 없으므로 쓰기 전에 계산까지 끝내고, 쓰기 직전에 업로드 이력에 「진행 중」을 남긴다.
그 기준일의 가장 최근 이력이 완료가 아니면 화면이 다시 계산하라고 알린다.
"""
import datetime as dt
import threading
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation

import httpx

import input_form
import winus as winus_errors
from store import SandboxRefused

WAITING = "WINUS 쿼리 연결을 기다리고 있습니다"
RECALC = "이 기준일의 결과를 다시 계산해야 합니다"
BUSY = "다른 업로드가 진행 중입니다"
NO_DATA = "이 기준일의 WINUS 데이터가 없습니다"
REFUSED = "WINUS 연결 권한이 없습니다. 담당 개발자에게 문의해 주십시오"
OVERWRITE = "기존 수기 입력이 덮어씌워집니다. 그래도 진행하시겠습니까?"
TRANSFORMS = {"same": lambda x: x, "/1e8": lambda x: x / 1e8, "round(/1e8)": lambda x: round(x / 1e8), "*100": lambda x: x * 100, "/100": lambda x: x / 100}

_guard = threading.Lock()
_held = set()


class Busy(Exception):
    pass


@contextmanager
def lock(base_date):
    """같은 기준일의 동시 쓰기를 거절한다. 샌드박스에 잠금 요청이 없어 프로세스 안에서 막는다(uvicorn 단일 프로세스 전제)."""
    with _guard:
        if base_date in _held:
            raise Busy
        _held.add(base_date)
    try:
        yield
    finally:
        with _guard:
            _held.discard(base_date)


def result(status, message, errors=()):
    return {"status": status, "message": message, "errors": list(errors)}


def by_stage(plan, *stages):
    return [t for t in plan["tables"] if t["stage"] in stages]


def waiting(plan):
    return any(t["waiting_query"] for t in plan["tables"])


def stamp(rows, base_date, base_time, loaded_at):
    return [{**r, "base_date": base_date, "base_time": base_time, "loaded_at": loaded_at} for r in rows]


def _mapped(table, rows):
    """쿼리 응답을 표의 열 이름으로 바꾼다. query_map 이 없으면 응답 열 이름을 그대로 쓴다."""
    query_map = table.get("query_map")
    if not query_map:
        return rows
    out = []
    for row in rows:
        item = {}
        for db, spec in query_map.items():
            value = row.get(spec["column"])
            item[db] = value if spec["transform"] == "same" or value is None else str(TRANSFORMS[spec["transform"]](float(value)))
        out.append(item)
    return out


def _each_values(each, lists):
    """query_each 의 목록 표에서 호출할 값. 빈 값과 중복은 빼고, 처음 나온 순서를 지킨다."""
    out = []
    for row in lists.get(each["table"], []):
        value = str(row.get(each["column"]) or "").strip()
        value = value.zfill(each["pad"]) if value and each.get("pad") else value
        if value and value not in out:
            out.append(value)
    return out


def _arg_sets(t, args, lists):
    each = t.get("query_each")
    return [{**args, each["arg"]: v} for v in _each_values(each, lists)] if each else [args]


def fetch_winus(plan, winus, base_date, parameters, lists=None):
    """(표별 행, 실패 응답). 하나라도 실패하면 그 기준일은 저장하지 않는다.
    query_each 가 있는 표는 lists({표 이름: 행 목록})의 그 열 값마다 한 번씩 순서대로 호출하고 응답을 합친다."""
    out = {}
    values = {"base_date": base_date, "yyyymmdd": base_date.replace("-", ""), **{k: str(v) for k, v in (parameters or {}).items()}}
    for t in by_stage(plan, "raw_winus"):
        args = {k: v.format(**values) for k, v in t.get("query_args", {}).items()}
        rows = []
        for one in _arg_sets(t, args, lists or {}):
            try:
                rows += winus.fetch(t["query_id"], one)
            except winus_errors.WinusRefused:
                return None, result("failed", REFUSED)
            except winus_errors.WinusStopped:
                return None, result("failed", f"{t['name'].rsplit('__', 1)[-1]} 데이터를 받지 못했습니다. 아무것도 저장하지 않았습니다. 잠시 뒤 다시 올려 주십시오")
        if not rows:  # 값 하나의 0건은 넘어가고, 합친 결과가 0건일 때만 멈춘다
            return None, result("failed", NO_DATA)
        out[t["name"]] = _mapped(t, rows)
    return out, None


def list_tables(plan):
    """query_each 가 목록으로 읽는 표 이름."""
    return {t["query_each"]["table"] for t in by_stage(plan, "raw_winus") if t.get("query_each")}


def calculated(plan, calculate, tables, base_date):
    """(표 이름별 결과 행, 실패 응답). 계산을 첫 쓰기 전에 끝내므로 실패하면 아무것도 저장되지 않는다."""
    try:
        got = calculate(tables, base_date)
    except Exception as e:  # 엑셀마다 다른 계산 코드의 오류를 화면에 알리고 멈춘다
        return None, result("failed", f"계산에 실패했습니다. 아무것도 저장하지 않았습니다({type(e).__name__})")
    out = {}
    for t in by_stage(plan, "calc"):
        target = t["name"].split("__", 2)[2]
        if not got.get(target):
            return None, result("failed", "계산 결과가 비어 있습니다. 아무것도 저장하지 않았습니다")
        out[t["name"]] = got[target]
    return out, None


def write_all(store, base_date, kind, user, base_time, writes):
    """writes 는 쓰는 순서대로 (표 이름, 행 목록). 시간 단위는 쌓고, 일자 단위는 기준일 범위를 교체한다."""
    loaded_at = dt.datetime.now(dt.timezone.utc).isoformat()
    try:
        upload_id = store.begin(base_date, base_time, kind, user)
        for name, rows in writes:
            full = stamp(rows, base_date, base_time, loaded_at)
            (store.append(name, full) if store.hourly else store.replace(name, base_date, full))
        store.finish(upload_id)
    except (SandboxRefused, httpx.HTTPError):
        return result("failed", RECALC)
    return result("saved", "저장했습니다")


def _value(v):
    if v in (None, ""):
        return Decimal(0)
    try:
        return Decimal(str(v))
    except InvalidOperation:
        return str(v).strip()


def _same_rows(table, stored, new):
    names = [c["name"] for c in table["columns"] if c["name"] not in input_form.SKIP]
    old = {r["row_id"]: r for r in stored}
    return set(old) == {r["row_id"] for r in new} and all(_value(old[r["row_id"]].get(n)) == _value(r.get(n)) for r in new for n in names)


def _refused_date(plan, base_date, today):
    day = dt.date.fromisoformat(base_date)
    if not plan["settings"]["allow_today"] and day >= today:
        return "오늘은 기준일로 올릴 수 없습니다"
    if not plan["settings"]["allow_holiday"] and (day.weekday() >= 5 or base_date in plan.get("holidays", [])):
        return "휴일은 기준일로 올릴 수 없습니다"
    return None


def _process(store, winus, plan, calculate, data, base_date, user, confirm):
    editable = by_stage(plan, "raw_manual", "raw_external")
    state = store.state(base_date)
    form_date = base_date if state != "없음" else store.latest_before(base_date)
    previous = {t["name"]: [r["row_id"] for r in store.read(t["name"], form_date)] if form_date else [] for t in editable}
    checked = input_form.check(plan, data, previous)
    if checked["errors"]:
        return result("rejected", "입력 양식이 다릅니다. 아무것도 저장하지 않았습니다", checked["errors"])
    stored = {t["name"]: store.read(t["name"], base_date) for t in editable} if state != "없음" else {}
    changed = [t["name"] for t in editable if store.hourly or state != "완료" or not _same_rows(t, stored[t["name"]], checked["tables"][t["name"]])]
    if not store.hourly and state == "완료" and not changed:
        return result("same", "바뀐 값이 없어 저장된 결과를 보입니다")
    if state != "없음" and not confirm:
        return result("needs_confirm", OVERWRITE)
    if not store.hourly and state == "완료" and not list_tables(plan) & set(changed):  # 호출 목록이 바뀌면 WINUS 를 다시 받는다
        winus_rows = {t["name"]: store.read(t["name"], base_date) for t in by_stage(plan, "raw_winus")}
        fresh = []
    else:
        winus_rows, failed = fetch_winus(plan, winus, base_date, checked["parameters"], checked["tables"])
        if failed:
            return failed
        fresh = list(winus_rows)
    inputs = {**checked["tables"], **winus_rows, **{t["name"]: store.read_all(t["name"]) for t in by_stage(plan, "fixed")}}
    results, failed = calculated(plan, calculate, inputs, base_date)
    if failed:
        return failed
    writes = [(n, checked["tables"][n]) for n in changed] + [(n, winus_rows[n]) for n in fresh] + list(results.items())
    return write_all(store, base_date, "업로드", user, dt.datetime.now(dt.timezone.utc).isoformat(), writes)


def run(store, winus, plan, calculate, form_bytes, base_date, user, confirm_overwrite, today=None):
    """입력 양식 하나를 처리한다. {"status": saved · same · needs_confirm · rejected · failed, "message", "errors"}."""
    if waiting(plan):
        return result("rejected", WAITING)
    refused = _refused_date(plan, base_date, today or dt.date.today())
    if refused:
        return result("rejected", refused)
    try:
        with lock(base_date):
            return _process(store, winus, plan, calculate, form_bytes, base_date, user, confirm_overwrite)
    except Busy:
        return result("rejected", BUSY)
