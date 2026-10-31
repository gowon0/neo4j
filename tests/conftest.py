"""권한 테스트 공통 설정.

- 인증 테이블(app_roles, app_users, audit_logs)은 메모리 가짜 저장소로 대체한다.
- 그 외 테이블은 실제 Supabase를 읽기 전용으로 쓰고, 쓰기(발주 등록 등)는 스텁으로 막아
  운영 데이터가 바뀌지 않게 한다.
"""

import os
import sys
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import accounts, auth, erp, permissions, risk, store  # noqa: E402
from server.app import app  # noqa: E402

AUTH_TABLES = ("app_roles", "app_users", "audit_logs")
PASSWORD = "Passw0rd-test1"
ADMIN_PASSWORD = "Admin-pass1234"


def _ts(value):

    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _match(value, cond):

    op, _, arg = cond.partition(".")

    if op == "eq":
        return value is not None and str(value) == arg

    if op == "ilike":
        return value is not None and arg.strip("*").lower() in str(value).lower()

    if op == "in":
        return str(value) in arg.strip("()").split(",")

    raise AssertionError(f"가짜 저장소가 지원하지 않는 조건: {cond}")


class FakeDB:

    def __init__(self):

        self.tables = {t: [] for t in AUTH_TABLES}
        self.seq = {t: 0 for t in AUTH_TABLES}

    def select(self, table, params=None):

        params = dict(params or {})
        order = params.pop("order", None)
        limit = params.pop("limit", None)
        offset = int(params.pop("offset", 0))
        params.pop("select", None)
        and_expr = params.pop("and", None)

        rows = [dict(r) for r in self.tables[table]]

        for col, cond in params.items():
            rows = [r for r in rows if _match(r.get(col), cond)]

        if and_expr:
            for part in and_expr.strip("()").split(","):
                col, op, value = part.split(".", 2)
                bound = _ts(value)
                rows = [
                    r for r in rows
                    if (op == "gte" and _ts(r[col]) >= bound) or (op == "lte" and _ts(r[col]) <= bound)
                ]

        if order:
            for spec in reversed(order.split(",")):
                col, _, direction = spec.partition(".")
                rows.sort(key=lambda r: (r.get(col) is None, r.get(col)), reverse=direction == "desc")

        rows = rows[offset:]

        return rows[:int(limit)] if limit else rows

    def insert(self, table, row):

        unique = {"app_roles": "name", "app_users": "username"}.get(table)

        if unique:
            if any(r.get(unique) == row[unique] for r in self.tables[table]):
                error = store.StoreError("duplicate key")
                error.status_code = 409
                raise error

        self.seq[table] += 1
        stored = dict(row, id=self.seq[table])
        stored.setdefault("created_at", datetime.now(timezone.utc).isoformat())
        self.tables[table].append(stored)

        return dict(stored)

    def _matching(self, table, match):

        rows = self.tables[table]

        for col, cond in match.items():
            rows = [r for r in rows if _match(r.get(col), cond)]

        return rows

    def update(self, table, match, patch):

        rows = self._matching(table, match)

        for r in rows:
            r.update(patch)

        return [dict(r) for r in rows]

    def delete(self, table, match):

        rows = self._matching(table, match)
        self.tables[table] = [r for r in self.tables[table] if r not in rows]

        return [dict(r) for r in rows]


@pytest.fixture(autouse=True)
def fake_db(monkeypatch):

    db = FakeDB()
    real_select = store.select

    monkeypatch.setattr(store, "select", lambda t, p=None: db.select(t, p) if t in AUTH_TABLES else real_select(t, p))

    def guarded(name, impl):

        def wrapper(table, *args):

            if table not in AUTH_TABLES:
                raise AssertionError(f"테스트가 운영 테이블에 쓰려 했습니다: {table}")

            return impl(table, *args)

        monkeypatch.setattr(store, name, wrapper)

    guarded("insert", db.insert)
    guarded("update", db.update)
    guarded("delete", db.delete)

    # 쓰기·외부 호출 스텁
    monkeypatch.setattr(erp, "create_order", lambda *a, **k: "PO-TEST-001")
    monkeypatch.setattr(erp, "update_order_status", lambda *a, **k: True)
    monkeypatch.setattr(store, "refresh_all", lambda: None)
    monkeypatch.setattr(
        risk, "get_risks",
        lambda force=False: {"generated_at": "테스트", "summary": {}, "projects": []},
    )

    # 환경 값 고정
    for module in (accounts, auth):
        monkeypatch.setattr(module, "APP_ADMIN_PASSWORD", ADMIN_PASSWORD)
    monkeypatch.setattr(accounts, "APP_ADMIN_ID", "admin")
    monkeypatch.setattr(auth, "APP_ADMIN_ID", "admin")
    monkeypatch.setattr(auth, "APP_EMERGENCY_ID", "emergency")
    monkeypatch.setattr(auth, "APP_EMERGENCY_ENABLED", True)

    # 캐시·제한 초기화
    accounts.invalidate_roles()
    auth._attempts.clear()
    auth._env_fail.update(count=0, until=0.0)
    auth._denied_seen.clear()

    accounts.bootstrap()

    return db


@pytest.fixture
def client():

    return TestClient(app)


def login(client, username, password):

    response = client.post("/api/auth/login", json={"id": username, "password": password})

    return response


def headers_for(client, username, password):

    response = login(client, username, password)
    assert response.status_code == 200, response.text

    return {"Authorization": "Bearer " + response.json()["token"]}


@pytest.fixture
def role_users(fake_db):
    """기본 역할마다 사용자 1명(비밀번호 변경 완료 상태). {역할명: 아이디}"""

    result = {}

    for i, role in enumerate(accounts.list_roles(force=True)):
        username = f"user{i}"
        accounts.create_user(username, f"{role['name']} 사용자", role["id"], PASSWORD, must_change=False)
        result[role["name"]] = username

    return result


@pytest.fixture
def admin_headers(client, fake_db):
    """첫 관리자로 로그인(초기 비밀번호 변경까지 마친 상태)."""

    token = login(client, "admin", ADMIN_PASSWORD).json()["token"]
    response = client.post(
        "/api/account/password",
        headers={"Authorization": f"Bearer {token}"},
        json={"current_password": ADMIN_PASSWORD, "new_password": "NewAdmin-pass99"},
    )
    assert response.status_code == 200, response.text

    return {"Authorization": "Bearer " + response.json()["token"]}


def perms_of(role_name):

    for role in permissions.DEFAULT_ROLES:
        if role["name"] == role_name:
            return set(role["permissions"])

    raise KeyError(role_name)
