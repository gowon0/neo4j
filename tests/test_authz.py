"""로그인·권한 동작 테스트."""

import re
from datetime import date, timedelta

import pytest

from conftest import ADMIN_PASSWORD, PASSWORD, headers_for, login, perms_of
from server import accounts, audit, auth, passwords, permissions, store

FUTURE = (date.today() + timedelta(days=30)).isoformat()
SIM = {"start": "2026-01", "end": "2026-12", "demand_change": 0, "delay_days": 0}

# (메서드, 경로, 본문, 필요한 권한)  — 로그인만 필요하면 빈 튜플
ENDPOINTS = [
    ("GET", "/api/materials", None, ()),
    ("GET", "/api/permissions", None, ()),
    ("GET", "/api/dashboard", None, ("dashboard.view",)),
    ("GET", "/api/risks", None, ("risks.view",)),
    ("GET", "/api/risks?refresh=true", None, ("risks.view", "risks.refresh")),
    ("GET", "/api/forecast", None, ("forecast.view",)),
    ("GET", "/api/forecast/series", None, ("forecast.view",)),
    ("GET", "/api/forecast/models", None, ("forecast.view",)),
    ("GET", "/api/orders", None, ("orders.view",)),
    ("POST", "/api/orders", {"material_id": 1, "quantity": 5, "due_date": FUTURE}, ("orders.create",)),
    ("PATCH", "/api/orders/PO-1", {"status": "진행중"}, ("orders.update",)),
    ("GET", "/api/inventory", None, ("inventory.view",)),
    ("GET", "/api/simulation/scenarios", None, ("simulation.run",)),
    ("POST", "/api/simulation", SIM, ("simulation.run",)),
    ("GET", "/api/export/orders?format=csv", None, ("orders.view", "orders.export")),
    ("GET", "/api/export/inventory?format=csv", None, ("inventory.view", "inventory.export")),
    ("GET", "/api/export/forecast?format=csv", None, ("forecast.view", "forecast.export")),
    ("POST", "/api/export/simulation", {**SIM, "format": "csv"}, ("simulation.run", "simulation.export")),
    ("GET", "/api/export/risks?format=csv", None, ("risks.view", "risks.export")),
    ("GET", "/api/data/status", None, ("data.view",)),
    ("POST", "/api/data/refresh", None, ("data.refresh",)),
    ("GET", "/api/settings", None, ("settings.view",)),
    ("GET", "/api/admin/users", None, ("users.manage",)),
    ("GET", "/api/admin/roles", None, ()),   # users.manage 또는 roles.manage (아래 별도 검증)
    ("GET", "/api/admin/audit", None, ("audit.view",)),
    ("GET", "/api/export/audit?format=csv", None, ("audit.view",)),
]


def call(client, method, path, body, headers):

    return client.request(method, path, json=body, headers=headers)


# ------------------------------------------------------------
# 로그인 · 계정
# ------------------------------------------------------------

def test_bootstrap_creates_roles_and_first_admin(fake_db, client):

    names = [r["name"] for r in accounts.list_roles(force=True)]
    assert names == [r["name"] for r in permissions.DEFAULT_ROLES]

    admin = accounts.get_user_by_username("admin")
    assert admin["must_change_password"] is True
    assert passwords.verify_password(ADMIN_PASSWORD, admin["password_hash"])
    assert ADMIN_PASSWORD not in admin["password_hash"]


def test_first_login_requires_password_change(client, fake_db):

    token = login(client, "admin", ADMIN_PASSWORD).json()["token"]
    h = {"Authorization": f"Bearer {token}"}

    me = client.get("/api/me", headers=h).json()
    assert me["must_change_password"] is True
    assert client.get("/api/dashboard", headers=h).status_code == 403   # 변경 전에는 업무 기능 차단

    weak = client.post("/api/account/password", headers=h, json={"current_password": ADMIN_PASSWORD, "new_password": "short1"})
    assert weak.status_code == 422

    ok = client.post("/api/account/password", headers=h, json={"current_password": ADMIN_PASSWORD, "new_password": "NewAdmin-pass99"})
    assert ok.status_code == 200
    new_h = {"Authorization": "Bearer " + ok.json()["token"]}

    assert client.get("/api/me", headers=h).status_code == 401      # 옛 토큰 무효
    assert client.get("/api/dashboard", headers=new_h).status_code != 403
    assert client.get("/api/me", headers=new_h).json()["must_change_password"] is False


def test_wrong_password_and_unknown_user_look_the_same(client, role_users):

    wrong = login(client, role_users["조회자"], "Wrong-pass123")
    unknown = login(client, "nobody", "Wrong-pass123")

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["detail"] == unknown.json()["detail"] == auth.GENERIC_LOGIN_ERROR


def test_lockout_after_five_failures_and_admin_unlock(client, role_users, admin_headers):

    user = role_users["조회자"]

    for _ in range(4):
        assert login(client, user, "bad").status_code == 401

    assert login(client, user, "bad").status_code == 429
    assert login(client, user, PASSWORD).status_code == 429          # 잠금 중에는 맞는 비밀번호도 거절

    target = accounts.get_user_by_username(user)
    assert client.post(f"/api/admin/users/{target['id']}/unlock", headers=admin_headers).status_code == 200
    assert login(client, user, PASSWORD).status_code == 200


def test_logout_invalidates_token(client, role_users):

    h = headers_for(client, role_users["조회자"], PASSWORD)

    assert client.get("/api/dashboard", headers=h).status_code != 401
    assert client.post("/api/auth/logout", headers=h).status_code == 200
    assert client.get("/api/dashboard", headers=h).status_code == 401


def test_deactivated_user_is_cut_off_immediately(client, role_users, admin_headers):

    h = headers_for(client, role_users["구매담당"], PASSWORD)
    assert client.get("/api/orders", headers=h).status_code != 401

    target = accounts.get_user_by_username(role_users["구매담당"])
    res = client.patch(f"/api/admin/users/{target['id']}", headers=admin_headers, json={"is_active": False})
    assert res.status_code == 200

    assert client.get("/api/orders", headers=h).status_code == 401
    assert login(client, role_users["구매담당"], PASSWORD).status_code == 401


def test_role_change_applies_immediately(client, role_users, admin_headers):

    viewer = headers_for(client, role_users["조회자"], PASSWORD)
    assert client.get("/api/orders", headers=viewer).status_code == 403

    roles = {r["name"]: r for r in client.get("/api/admin/roles", headers=admin_headers).json()["roles"]}
    perms = roles["조회자"]["permissions"] + ["orders.view"]
    assert client.patch(f"/api/admin/roles/{roles['조회자']['id']}", headers=admin_headers, json={"permissions": perms}).status_code == 200

    assert client.get("/api/orders", headers=viewer).status_code != 403


def test_emergency_admin_works_when_db_is_down(client, monkeypatch):

    def down(table, params=None):
        raise store.StoreError("DB 장애")

    monkeypatch.setattr(store, "select", down)

    res = login(client, "emergency", ADMIN_PASSWORD)
    assert res.status_code == 200
    assert res.json()["user"]["emergency"] is True
    assert set(res.json()["user"]["permissions"]) == permissions.ALL_SET

    assert login(client, "emergency", "wrong").status_code == 401

    monkeypatch.setattr(auth, "APP_EMERGENCY_ENABLED", False)
    assert login(client, "emergency", ADMIN_PASSWORD).status_code == 401


def test_ip_throttle(client, fake_db):

    for _ in range(auth.LOGIN_IP_LIMIT):
        client.post("/api/auth/login", json={"id": "x", "password": "y"}, headers={"X-Real-IP": "9.9.9.9"})

    blocked = client.post("/api/auth/login", json={"id": "x", "password": "y"}, headers={"X-Real-IP": "9.9.9.9"})
    assert blocked.status_code == 429


def test_invalid_or_forged_tokens_are_rejected(client, fake_db):

    assert client.get("/api/me").status_code == 401
    assert client.get("/api/me", headers={"Authorization": "Bearer abc.def"}).status_code == 401
    forged = auth.issue_token(1, 1)[:-4] + "0000"
    assert client.get("/api/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_audit_trail_records_key_events(client, role_users, admin_headers, fake_db):

    login(client, role_users["구매담당"], "bad")
    h = headers_for(client, role_users["구매담당"], PASSWORD)
    client.post("/api/orders", headers=h, json={"material_id": 1, "quantity": 5, "due_date": FUTURE})
    client.get("/api/export/orders?format=csv", headers=h)
    client.get("/api/settings", headers=h)    # 권한 없음 → access_denied

    actions = [r["action"] for r in fake_db.tables["audit_logs"]]
    for expected in ("login_failed", "login", "order_create", "export", "access_denied", "password_change"):
        assert expected in actions, expected

    created = next(r for r in fake_db.tables["audit_logs"] if r["action"] == "order_create")
    assert created["username"] == role_users["구매담당"] and created["target"] == "PO-TEST-001"


# ------------------------------------------------------------
# 역할 × 엔드포인트
# ------------------------------------------------------------

@pytest.mark.parametrize("role", [r["name"] for r in permissions.DEFAULT_ROLES])
def test_role_endpoint_matrix(client, role_users, role):

    h = headers_for(client, role_users[role], PASSWORD)
    granted = perms_of(role)

    for method, path, body, needed in ENDPOINTS:
        if path == "/api/admin/roles":
            allowed = bool({"users.manage", "roles.manage"} & granted)
        else:
            allowed = set(needed) <= granted

        status = call(client, method, path, body, h).status_code

        if allowed:
            assert status not in (401, 403), f"{role}: {method} {path} 가 허용돼야 하는데 {status}"
        else:
            assert status == 403, f"{role}: {method} {path} 가 403이어야 하는데 {status}"


def test_unauthenticated_requests_get_401(client, fake_db):

    for method, path, body, _ in ENDPOINTS:
        assert call(client, method, path, body, None).status_code == 401, path


def test_viewer_cannot_see_orders_but_can_see_inventory(client, role_users):

    h = headers_for(client, role_users["조회자"], PASSWORD)

    assert client.get("/api/orders", headers=h).status_code == 403          # 요청하신 예시
    assert client.get("/api/inventory", headers=h).status_code != 403


# ------------------------------------------------------------
# 대시보드 위젯
# ------------------------------------------------------------

def test_dashboard_widgets_follow_permissions(client, role_users, admin_headers):

    def kpis(role):

        h = headers_for(client, role_users[role], PASSWORD)
        res = client.get("/api/dashboard", headers=h)
        assert res.status_code == 200, res.text

        return res.json()

    viewer = kpis("조회자")
    assert {k["key"] for k in viewer["kpis"]} == {"demand", "stock", "days"}       # 발주 이행률 제외
    assert viewer["widgets"] == {"forecast": True, "orders": False, "inventory": True, "risks": True}

    buyer = kpis("구매담당")
    assert "fulfillment" in {k["key"] for k in buyer["kpis"]}

    # 대시보드 권한만 있는 사용자는 어떤 데이터도 받지 못한다
    res = client.post("/api/admin/roles", headers=admin_headers, json={"name": "빈역할", "permissions": ["dashboard.view"]})
    role_id = res.json()["role"]["id"]
    client.post("/api/admin/users", headers=admin_headers, json={"username": "empty1", "display_name": "빈", "role_id": role_id, "password": PASSWORD})
    token = login(client, "empty1", PASSWORD).json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    changed = client.post("/api/account/password", headers=h, json={"current_password": PASSWORD, "new_password": "Another-pass77"}).json()["token"]
    data = client.get("/api/dashboard", headers={"Authorization": f"Bearer {changed}"}).json()

    assert data["kpis"] == [] and data["trend"] is None and data["shortage_items"] is None


# ------------------------------------------------------------
# 관리자 기능
# ------------------------------------------------------------

def test_create_user_flow_and_validation(client, admin_headers):

    roles = client.get("/api/admin/users", headers=admin_headers).json()["roles"]
    buyer = next(r for r in roles if r["name"] == "구매담당")

    bad = client.post("/api/admin/users", headers=admin_headers, json={"username": "Bad Name", "display_name": "x", "role_id": buyer["id"]})
    assert bad.status_code == 422

    created = client.post("/api/admin/users", headers=admin_headers, json={"username": "kim.buyer", "display_name": "김구매", "role_id": buyer["id"]})
    assert created.status_code == 200
    temp = created.json()["temp_password"]
    assert passwords.policy_error(temp) is None
    assert created.json()["user"]["must_change_password"] is True

    dup = client.post("/api/admin/users", headers=admin_headers, json={"username": "kim.buyer", "display_name": "김", "role_id": buyer["id"]})
    assert dup.status_code == 409

    weak = client.post("/api/admin/users", headers=admin_headers, json={"username": "kim2", "display_name": "김", "role_id": buyer["id"], "password": "abc"})
    assert weak.status_code == 422

    # 임시 비밀번호로 로그인 → 변경 강제 → 변경 후 사용
    token = login(client, "kim.buyer", temp).json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/orders", headers=h).status_code == 403
    changed = client.post("/api/account/password", headers=h, json={"current_password": temp, "new_password": "Kim-secret-2026"})
    assert changed.status_code == 200
    assert client.get("/api/orders", headers={"Authorization": "Bearer " + changed.json()["token"]}).status_code != 403


def test_reset_password_forces_change_and_revokes_tokens(client, role_users, admin_headers):

    h = headers_for(client, role_users["구매담당"], PASSWORD)
    target = accounts.get_user_by_username(role_users["구매담당"])

    temp = client.post(f"/api/admin/users/{target['id']}/reset-password", headers=admin_headers).json()["temp_password"]

    assert client.get("/api/me", headers=h).status_code == 401
    assert login(client, role_users["구매담당"], PASSWORD).status_code == 401
    token = login(client, role_users["구매담당"], temp).json()["token"]
    assert client.get("/api/me", headers={"Authorization": f"Bearer {token}"}).json()["must_change_password"] is True


def test_admin_safeguards(client, role_users, admin_headers):

    users = client.get("/api/admin/users", headers=admin_headers).json()
    admin = next(u for u in users["users"] if u["username"] == "admin")
    roles = {r["id"]: r["name"] for r in users["roles"]}
    viewer_role = next(i for i, n in roles.items() if n == "조회자")

    # 본인의 역할·활성 상태는 바꿀 수 없다
    assert client.patch(f"/api/admin/users/{admin['id']}", headers=admin_headers, json={"role_id": viewer_role}).status_code == 422
    assert client.patch(f"/api/admin/users/{admin['id']}", headers=admin_headers, json={"is_active": False}).status_code == 422

    # 관리 권한 보유자가 남지 않게 되는 변경은 막는다 (관리자 역할 사용자를 다른 관리자가 강등하는 경우 포함)
    admin_role = next(i for i, n in roles.items() if n == "관리자")
    client.post("/api/admin/users", headers=admin_headers, json={"username": "second", "display_name": "둘째", "role_id": admin_role, "password": PASSWORD})
    second = accounts.get_user_by_username("second")
    # second를 강등해도 admin이 남아 있으므로 허용
    assert client.patch(f"/api/admin/users/{second['id']}", headers=admin_headers, json={"role_id": viewer_role}).status_code == 200

    # 관리자 역할 권한 축소 불가 / 기본 역할 이름 변경·삭제 불가
    role_list = client.get("/api/admin/roles", headers=admin_headers).json()["roles"]
    admin_r = next(r for r in role_list if r["name"] == "관리자")
    assert client.patch(f"/api/admin/roles/{admin_r['id']}", headers=admin_headers, json={"permissions": ["dashboard.view"]}).status_code == 422
    assert client.patch(f"/api/admin/roles/{admin_r['id']}", headers=admin_headers, json={"name": "슈퍼"}).status_code == 422
    assert client.delete(f"/api/admin/roles/{admin_r['id']}", headers=admin_headers).status_code == 422


def test_role_crud_and_in_use_protection(client, admin_headers):

    created = client.post("/api/admin/roles", headers=admin_headers, json={"name": "외부감사", "description": "열람 전용", "permissions": ["dashboard.view", "audit.view", "nonexistent.perm"]})
    assert created.status_code == 200
    role = created.json()["role"]
    assert role["permissions"] == ["dashboard.view", "audit.view"]          # 알 수 없는 권한은 버려짐

    assert client.post("/api/admin/roles", headers=admin_headers, json={"name": "외부감사"}).status_code == 409

    client.post("/api/admin/users", headers=admin_headers, json={"username": "auditor1", "display_name": "감사", "role_id": role["id"], "password": PASSWORD})
    assert client.delete(f"/api/admin/roles/{role['id']}", headers=admin_headers).status_code == 409   # 사용 중

    target = accounts.get_user_by_username("auditor1")
    other = next(r for r in client.get("/api/admin/roles", headers=admin_headers).json()["roles"] if r["name"] == "조회자")
    client.patch(f"/api/admin/users/{target['id']}", headers=admin_headers, json={"role_id": other["id"]})
    assert client.delete(f"/api/admin/roles/{role['id']}", headers=admin_headers).status_code == 200


def test_audit_log_listing_filters_and_export(client, role_users, admin_headers):

    login(client, role_users["조회자"], "bad")
    login(client, role_users["조회자"], "bad")

    res = client.get("/api/admin/audit?action=login_failed", headers=admin_headers).json()
    assert res["rows"] and all(r["action"] == "login_failed" for r in res["rows"])
    assert "login_failed" in res["actions"]

    by_user = client.get(f"/api/admin/audit?username={role_users['조회자']}", headers=admin_headers).json()
    assert all(role_users["조회자"] in r["username"] for r in by_user["rows"])

    assert client.get("/api/admin/audit?date_from=2026-13-xx", headers=admin_headers).status_code == 422

    csv = client.get("/api/export/audit?format=csv", headers=admin_headers)
    assert csv.status_code == 200 and "로그인 실패" in csv.content.decode("utf-8-sig")


def test_my_login_history(client, role_users):

    user = role_users["조회자"]
    login(client, user, "bad")
    h = headers_for(client, user, PASSWORD)

    rows = client.get("/api/account/logins", headers=h).json()["rows"]
    assert {r["action"] for r in rows} == {"login", "login_failed"}


# ------------------------------------------------------------
# 비밀번호 · SQL
# ------------------------------------------------------------

def test_password_hash_and_policy():

    stored = passwords.hash_password("Abcdefghij1")
    assert stored.startswith("scrypt$") and "Abcdefghij1" not in stored
    assert passwords.verify_password("Abcdefghij1", stored)
    assert not passwords.verify_password("Abcdefghij2", stored)
    assert passwords.hash_password("Abcdefghij1") != stored                 # 매번 다른 솔트
    assert not passwords.verify_password("x", "garbage")

    assert passwords.policy_error("short1")
    assert passwords.policy_error("onlyletterspassword")
    assert passwords.policy_error("12345678901234")
    assert passwords.policy_error("Admin12345678", "admin12345678")
    assert passwords.policy_error("GoodPassw0rd") is None
    assert passwords.policy_error(passwords.generate_temp_password()) is None


def test_sql_seed_matches_default_roles():

    sql = open("supabase/auth_schema.sql", encoding="utf-8").read()

    for role in permissions.DEFAULT_ROLES:
        assert f"'{role['name']}'" in sql
        for code in role["permissions"]:
            assert f"'{code}'" in sql

    assert len(re.findall(r"is_system|true\)", sql)) >= 5
