"""결과표 조회 화면의 API. table_plan.json 의 표만 열고, 화면 입력을 표 이름으로 그대로 쓰지 않는다."""
import io

import openpyxl
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response

import input_form
import refetch as refetch_module
import upload as upload_module

ORIGIN = {"raw_winus": "WINUS", "raw_wfs": "WFS", "raw_external": "외부", "raw_manual": "수기"}
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
HIDDEN = {"base_date", "base_time", "loaded_at"}


def _target(name):
    return name.split("__", 2)[2]


def make_router(plan, store_for, winus, calculate, user_of, review=False):
    """기능 하나의 API. store_for(request) 는 그 요청을 보낸 사람의 권한으로 읽고 쓰는 Store 를, user_of(request) 는 로그인한 사람의 이름을 돌려준다.
    review 는 스킬의 임시 실행만 켠다(upload.run 참고). 대시보드에 복사한 화면은 create_router 를 쓰므로 언제나 꺼져 있다."""
    router = APIRouter()
    source = [t for t in plan["tables"] if t["stage"] in ORIGIN]
    result = [t for t in plan["tables"] if t["stage"] == "calc" and not t["name"].endswith("_dates")]
    allowed = {t["name"]: t for t in source + result}

    @router.get("/tables")
    def tables():
        return {"source": [{"name": t["name"], "label": f"[{ORIGIN[t['stage']]}] {_target(t['name'])}", "origin": ORIGIN[t["stage"]]} for t in source],
                "result": [{"name": t["name"], "label": _target(t["name"])} for t in result],
                "waiting": upload_module.waiting(plan), "settings": plan["settings"]}

    @router.get("/dates")
    def dates(request: Request):
        found = store_for(request).dates()
        return {"dates": found, "default": found[0] if found else None}

    @router.get("/table")
    def table(request: Request, date: str, name: str):
        t = allowed.get(name)
        if t is None:
            raise HTTPException(status_code=404, detail="없는 표입니다")
        store = store_for(request)
        rows = store.read(name, date)
        dates_name = f"{name}_dates"
        return {"columns": [c for c in t["columns"] if c["name"] not in HIDDEN], "rows": rows, "summaries": t.get("summaries", []),
                "dates": store.read(dates_name, date) if dates_name in store.tables else [],
                "base_time": rows[0].get("base_time") if rows else None, "loaded_at": rows[0].get("loaded_at") if rows else None, "state": store.state(date)}

    @router.get("/form")
    def form(request: Request, date: str):
        store = store_for(request)
        values = {t["name"]: store.read(t["name"], date) for t in plan["tables"] if t.get("editable")}
        return Response(input_form.make(plan, values, {"기준일": date}), media_type=XLSX)

    @router.post("/upload")
    def upload(request: Request, file: UploadFile = File(...), date: str = Form(...), confirm: bool = Form(False)):
        return upload_module.run(store_for(request), winus, plan, calculate, file.file.read(), date, user_of(request), confirm, review=review)

    @router.post("/refetch")
    def refetch(request: Request, date: str):
        return refetch_module.run(store_for(request), winus, plan, calculate, date, user_of(request))

    @router.get("/export")
    def export(request: Request, date: str):
        store = store_for(request)
        wb = openpyxl.Workbook()
        wb.remove(wb.active)
        for t in source + result:
            ws = wb.create_sheet(_target(t["name"])[:31])
            names = [c["name"] for c in t["columns"] if c["name"] not in HIDDEN]
            ws.append(names)
            for row in store.read(t["name"], date):
                ws.append([row.get(n) for n in names])
        out = io.BytesIO()
        wb.save(out)
        return Response(out.getvalue(), media_type=XLSX)

    return router
