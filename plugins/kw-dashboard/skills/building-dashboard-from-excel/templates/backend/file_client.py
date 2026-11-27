"""검토용 임시 저장소. 샌드박스와 같은 요청을 받아 PC 의 JSON 파일에 저장한다. 운영에서는 쓰지 않는다.

담당자가 결과표를 엑셀로 검토하는 동안에는 샌드박스에 아무것도 쌓지 않는다. 그동안 store.Store 에 이 클라이언트를 넘겨
같은 화면 코드를 PC 에서 실행한다. 표마다 <폴더>/<표 이름>.json 에 행 목록을 둔다.
"""
import datetime as dt
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

from store import SandboxRefused

NUMBER = {"numeric", "integer", "bigint"}


def _value(v, kind):
    """샌드박스가 돌려주는 모양으로 바꾼다. 소수는 글자, 날짜는 YYYY-MM-DD 글자, 정수는 정수다."""
    if v is None or v == "":
        return None if kind in NUMBER | {"date", "timestamptz"} else v
    if kind in ("integer", "bigint"):
        return int(Decimal(str(v)))
    if kind == "numeric":
        return str(Decimal(str(v)))
    if kind == "date":
        return v.isoformat()[:10] if isinstance(v, (dt.date, dt.datetime)) else str(v)[:10]
    return v


def _sort_key(v, kind):
    """빈 값은 맨 뒤로 보낸다. 숫자 열은 값의 크기로 비교한다."""
    if v is None:
        return (True, 0)
    if kind in NUMBER:
        try:
            return (False, Decimal(str(v)))
        except InvalidOperation:
            pass
    return (False, str(v))


class FileClient:
    def __init__(self, folder, plan):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.tables = {t["name"]: t for t in plan["tables"]}

    def _table(self, name):
        t = self.tables.get(name)
        if t is None:
            raise SandboxRefused("table_not_found", name)
        return t

    def _kinds(self, t):
        return {c["name"]: c["type"] for c in t["columns"]}

    def _load(self, name):
        path = self.folder / f"{name}.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []

    def _save(self, name, rows):
        (self.folder / f"{name}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")

    def _clean(self, t, row):
        kinds = self._kinds(t)
        return {k: _value(v, kinds.get(k, "text")) for k, v in row.items()}

    def _match(self, t, row, where):
        """where 는 같음 조건만 받는다. {"열": 값} 또는 {"열": {"=": 값}}."""
        kinds = self._kinds(t)
        for k, cond in (where or {}).items():
            want = cond["="] if isinstance(cond, dict) else cond
            if isinstance(cond, dict) and set(cond) != {"="}:
                raise SandboxRefused("invalid_request", f"같음 조건만 받음: {k}")
            if row.get(k) != _value(want, kinds.get(k, "text")):
                return False
        return True

    def post(self, path, body):
        t = self._table(body["table"])
        if body.get("where") == {}:  # 샌드박스는 빈 조건을 거절한다
            raise SandboxRefused("invalid_request", "빈 조건")
        name, rows = t["name"], self._load(t["name"])
        if path == "rows/select":
            return self._select(t, rows, body)
        if path == "rows/insert":
            sent = [self._clean(t, r) for r in body["rows"]]
            if body.get("mode") == "upsert":
                rows = self._upsert(t, rows, sent)
            else:
                rows += sent
            self._save(name, rows)
            return {"row_count": len(sent)}
        if path == "rows/overwrite":
            if body.get("all") or "where" not in body:
                raise SandboxRefused("invalid_request", "범위 교체는 where 가 있어야 함")
            sent = [self._clean(t, r) for r in body["rows"]]
            self._save(name, [r for r in rows if not self._match(t, r, body["where"])] + sent)
            return {"row_count": len(sent)}
        if path == "rows/update":
            if "where" not in body:
                raise SandboxRefused("invalid_request", "수정은 where 가 있어야 함")
            changes, count = self._clean(t, body["set"]), 0
            for r in rows:
                if self._match(t, r, body["where"]):
                    r.update(changes)
                    count += 1
            self._save(name, rows)
            return {"row_count": count}
        raise SandboxRefused("invalid_request", f"받지 않는 요청: {path}")

    def _select(self, t, rows, body):
        kinds = self._kinds(t)
        hit = [r for r in rows if self._match(t, r, body.get("where"))]
        for o in reversed(body.get("order_by") or []):
            col = o["column"]
            hit.sort(key=lambda r: _sort_key(r.get(col), kinds.get(col, "text")), reverse=bool(o.get("descending")))
        start, limit = body.get("offset", 0), body["limit"]
        columns = [c["name"] for c in t["columns"]]
        return {"columns": columns, "rows": [[r.get(c) for c in columns] for r in hit[start:start + limit]], "truncated": len(hit) > start + limit}

    def _upsert(self, t, rows, sent):
        key = t["primary_key"]
        if not key:
            raise SandboxRefused("invalid_request", f"primary key 없는 표는 upsert 를 받지 않음: {t['name']}")
        for new in sent:
            old = next((r for r in rows if all(r.get(k) == new.get(k) for k in key)), None)
            if old is None:
                rows.append(new)
            else:
                old.update(new)
        return rows
