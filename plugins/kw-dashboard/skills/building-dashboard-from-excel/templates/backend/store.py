"""기능의 표를 읽고 쓴다. 화면 입력을 표 이름이나 조건으로 그대로 넘기지 않고, table_plan.json 에 있는 표만 연다.

저장 경로를 바꿀 때는 이 파일의 SandboxClient 만 바꾼다.
"""
import datetime as dt
import os
import uuid

import httpx

PAGE = 1000
UPLOAD = "excel_upload"


class SandboxRefused(Exception):
    def __init__(self, code, detail):
        super().__init__(f"{code}: {detail}")
        self.code = code


class SandboxClient:
    """샌드박스 요청 한 번을 보낸다. 실패해도 다시 보내지 않는다."""

    def __init__(self, url=None, key=None):
        self.url = url or os.environ["QUERY_GATEWAY_URL"]
        self.key = (key or os.environ["KIWOOM_ACCESS_KEY"]).strip()

    def post(self, path, body):
        r = httpx.post(f"{self.url}/sandbox/{path}", json=body, headers={"Authorization": f"Bearer {self.key}"}, timeout=60)
        if r.status_code == 200:
            return r.json()
        try:
            refusal = r.json()
        except ValueError:
            raise SandboxRefused(f"http_{r.status_code}", r.text[:200]) from None
        raise SandboxRefused(refusal.get("code", f"http_{r.status_code}"), str(refusal.get("detail")))


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


class Store:
    def __init__(self, client, schema, plan):
        self.client, self.schema, self.plan = client, schema, plan
        self.tables = {t["name"]: t for t in plan["tables"]}
        self.excel = plan["excel"]
        self.hourly = plan["settings"]["refresh_unit"] == "시간"

    def _table(self, name):
        return self.tables[name]  # 설계에 없는 표는 KeyError 로 끝낸다

    def _select(self, name, where):
        """조건에 맞는 행을 모두 받는다. 1,000행을 넘으면 페이지로 나눠 받는다."""
        t = self._table(name)
        keys = t["primary_key"] or [t["columns"][0]["name"]]
        out, offset = [], 0
        while True:
            page = self.client.post("rows/select", {"schema": self.schema, "table": name, "where": where, "limit": PAGE, "offset": offset,
                                                    "order_by": [{"column": k} for k in keys]})
            out += [dict(zip(page["columns"], row)) for row in page["rows"]]
            if not page.get("truncated"):
                return out
            offset += PAGE

    def _uploads(self, base_date=None):
        where = {"excel": self.excel} | ({"base_date": base_date} if base_date else {})
        return sorted(self._select(UPLOAD, where), key=lambda r: str(r.get("started_at")))

    def read(self, name, base_date):
        """그 기준일의 행. 시간 단위 엑셀은 완료된 가장 최근 기준 시각의 행만 돌려준다."""
        where = {"base_date": base_date}
        if self.hourly:
            times = [r["base_time"] for r in self._uploads(base_date) if r["status"] == "완료"]
            if times:
                where["base_time"] = times[-1]
        return self._select(name, where)

    def read_all(self, name):
        return self._select(name, {})

    def state(self, base_date):
        """그 기준일의 가장 최근 이력 행으로 정한다. 완료 · 미완료 · 없음 중 하나다."""
        rows = self._uploads(base_date)
        return "없음" if not rows else "완료" if rows[-1]["status"] == "완료" else "미완료"

    def dates(self):
        """결과가 있는 기준일을 최근 순으로 돌려준다."""
        return sorted({r["base_date"] for r in self._uploads() if r["status"] == "완료"}, reverse=True)

    def latest_before(self, base_date):
        return next((d for d in self.dates() if d < base_date), None)

    def _full(self, name, rows):
        columns = [c["name"] for c in self._table(name)["columns"]]
        return [{c: r.get(c) for c in columns} for r in rows]  # 보내지 않은 열은 비워지므로 모든 열을 보낸다

    def replace(self, name, base_date, rows):
        self.client.post("rows/overwrite", {"schema": self.schema, "table": name, "where": {"base_date": base_date}, "rows": self._full(name, rows)})

    def append(self, name, rows):
        self.client.post("rows/insert", {"schema": self.schema, "table": name, "mode": "append", "rows": self._full(name, rows)})

    def begin(self, base_date, base_time, kind, user):
        upload_id = uuid.uuid4().hex
        self.client.post("rows/insert", {"schema": self.schema, "table": UPLOAD, "mode": "append", "rows": [
            {"upload_id": upload_id, "excel": self.excel, "base_date": base_date, "base_time": base_time, "status": "진행 중", "kind": kind,
             "uploaded_by": user, "started_at": _now(), "finished_at": None}]})
        return upload_id

    def finish(self, upload_id):
        self.client.post("rows/update", {"schema": self.schema, "table": UPLOAD, "where": {"upload_id": upload_id}, "set": {"status": "완료", "finished_at": _now()}})
