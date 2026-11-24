"""화면의 「WINUS 다시 받기」. 보고 있는 기준일의 WINUS 값을 다시 받아 결과를 다시 계산한다."""
import datetime as dt

import upload


def _process(store, winus, plan, calculate, base_date, user):
    if store.state(base_date) == "미완료":  # 일부만 반영된 입력을 다시 받기로 확정하지 않는다
        return upload.result("rejected", upload.UNFINISHED)
    editable = {t["name"]: store.read(t["name"], base_date) for t in upload.by_stage(plan, "raw_manual", "raw_external")}
    fetched, failed = upload.fetch_winus(plan, winus, base_date, {}, editable)
    if failed:
        return failed  # 조회가 실패하거나 0건이면 저장된 값을 그대로 둔다
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    winus_rows = upload.as_stored(plan, fetched, base_date, now)
    inputs = {**editable, **winus_rows, **{t["name"]: store.read_all(t["name"]) for t in upload.by_stage(plan, "fixed")}}
    results, failed = upload.calculated(plan, calculate, inputs, base_date)
    if failed:
        return failed
    carried = list(editable.items()) if store.hourly else []  # 시간 단위는 수기 · 외부 값을 이어받아 새 기준 시각으로 쌓는다
    writes = carried + list(winus_rows.items()) + list(results.items())
    return upload.write_all(store, base_date, "다시 받기", user, now, writes, now)


def run(store, winus, plan, calculate, base_date, user):
    """{"status": saved · rejected · failed, "message", "errors"}."""
    if upload.waiting(plan):
        return upload.result("rejected", upload.WAITING)
    try:
        with upload.lock(base_date):
            return _process(store, winus, plan, calculate, base_date, user)
    except upload.Busy:
        return upload.result("rejected", upload.BUSY)
