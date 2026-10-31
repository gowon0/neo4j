"""사용자·역할 저장소 (Supabase app_users / app_roles)와 초기 설정.

역할은 30초, 사용자는 30초 동안 서버 메모리에 캐시한다. 이 서버 프로세스에서 일어난
변경은 즉시 캐시를 비우므로 곧바로 반영된다.
"""

import threading
import time
from datetime import datetime, timezone

from config.settings import APP_ADMIN_ID, APP_ADMIN_PASSWORD
from server import audit, passwords, permissions, store

ROLES = "app_roles"
USERS = "app_users"
CACHE_TTL = 30

_lock = threading.Lock()
_roles_cache = {"at": 0.0, "rows": []}
_users_cache = {}


def now():

    return datetime.now(timezone.utc)


def parse(ts):

    if not ts:
        return None

    value = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))

    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


# ------------------------------------------------------------
# 역할
# ------------------------------------------------------------

def _sort_roles(rows):

    order = {r["name"]: i for i, r in enumerate(permissions.DEFAULT_ROLES)}

    return sorted(rows, key=lambda r: (order.get(r["name"], 999), r["name"]))


def list_roles(force=False):

    with _lock:
        if not force and time.time() - _roles_cache["at"] < CACHE_TTL:
            return _roles_cache["rows"]

    rows = _sort_roles(store.select(ROLES))

    with _lock:
        _roles_cache.update(at=time.time(), rows=rows)

    return rows


def invalidate_roles():

    with _lock:
        _roles_cache["at"] = 0.0
        _users_cache.clear()


def get_role(role_id):

    for role in list_roles():
        if str(role["id"]) == str(role_id):
            return role

    return None


def role_permissions(role):
    """관리자 역할은 항상 모든 권한(권한이 추가되어도 자동 포함)."""

    if not role:
        return frozenset()

    if role["name"] == permissions.ADMIN_ROLE and role.get("is_system"):
        return permissions.ALL_SET

    return frozenset(permissions.valid(role.get("permissions") or []))


def create_role(name, description, perms):

    row = store.insert(ROLES, {
        "name": name,
        "description": description or "",
        "permissions": permissions.valid(perms),
        "is_system": False,
    })
    invalidate_roles()

    return row


def update_role(role_id, patch):

    rows = store.update(ROLES, {"id": f"eq.{role_id}"}, patch)
    invalidate_roles()

    return rows[0] if rows else None


def delete_role(role_id):

    rows = store.delete(ROLES, {"id": f"eq.{role_id}"})
    invalidate_roles()

    return bool(rows)


# ------------------------------------------------------------
# 사용자
# ------------------------------------------------------------

def get_user_by_username(username):

    rows = store.select(USERS, {"username": f"eq.{username}", "limit": 1})

    return rows[0] if rows else None


def get_user(user_id, fresh=False):

    key = str(user_id)

    with _lock:
        cached = _users_cache.get(key)

        if cached and not fresh and time.time() - cached[0] < CACHE_TTL:
            return cached[1]

    rows = store.select(USERS, {"id": f"eq.{user_id}", "limit": 1})
    row = rows[0] if rows else None

    with _lock:
        _users_cache[key] = (time.time(), row)

    return row


def list_users():

    return store.select(USERS, {"order": "created_at.asc"})


def invalidate_user(user_id=None):

    with _lock:
        if user_id is None:
            _users_cache.clear()
        else:
            _users_cache.pop(str(user_id), None)


def create_user(username, display_name, role_id, password, must_change=True):

    row = store.insert(USERS, {
        "username": username,
        "display_name": display_name,
        "password_hash": passwords.hash_password(password),
        "role_id": role_id,
        "is_active": True,
        "must_change_password": must_change,
        "failed_logins": 0,
        "token_version": 1,
        "created_at": now().isoformat(),
    })
    invalidate_user(row["id"])

    return row


def update_user(user_id, patch):

    rows = store.update(USERS, {"id": f"eq.{user_id}"}, patch)
    invalidate_user(user_id)

    return rows[0] if rows else None


def set_password(user_id, password, must_change):
    """비밀번호를 바꾸고 기존 토큰을 모두 무효화한다."""

    row = get_user(user_id, fresh=True)

    return update_user(user_id, {
        "password_hash": passwords.hash_password(password),
        "must_change_password": must_change,
        "failed_logins": 0,
        "locked_until": None,
        "token_version": int(row.get("token_version") or 1) + 1,
    })


def bump_token_version(user_id):

    row = get_user(user_id, fresh=True)

    if row:
        update_user(user_id, {"token_version": int(row.get("token_version") or 1) + 1})


# ------------------------------------------------------------
# 안전장치: 사용자·권한 관리자가 한 명도 남지 않는 변경을 막는다
# ------------------------------------------------------------

def lockout_error(user_overrides=None, role_perm_overrides=None):
    """변경을 적용했다고 가정했을 때 관리 권한 보유자가 없어지면 안내 문구를 반환."""

    user_overrides = user_overrides or {}
    role_perm_overrides = role_perm_overrides or {}

    roles = {str(r["id"]): r for r in list_roles(force=True)}
    users = list_users()

    def perms_of(role_id):

        rid = str(role_id)

        if rid in role_perm_overrides:
            return frozenset(role_perm_overrides[rid])

        return role_permissions(roles.get(rid))

    for needed, label in (("users.manage", "사용자 관리"), ("roles.manage", "역할·권한 관리")):
        holders = 0

        for user in users:
            change = user_overrides.get(str(user["id"]), {})
            active = change.get("is_active", user.get("is_active"))
            role_id = change.get("role_id", user.get("role_id"))

            if active and needed in perms_of(role_id):
                holders += 1

        if holders == 0:
            return f"{label} 권한을 가진 활성 사용자가 한 명도 남지 않게 됩니다."

    return None


# ------------------------------------------------------------
# 초기 설정 (서버 시작 시 1회)
# ------------------------------------------------------------

def bootstrap():
    """기본 역할을 채우고, 사용자가 없으면 첫 관리자를 만든다.

    테이블이 아직 없으면(SQL 미실행) 조용히 건너뛰고 비상 관리자로만 로그인할 수 있다.
    첫 관리자의 초기 비밀번호는 APP_ADMIN_PASSWORD이며 첫 로그인에서 변경해야 한다.
    """

    try:
        existing = {r["name"]: r for r in store.select(ROLES)}
    except Exception as error:
        print(f"[auth] 권한 테이블을 사용할 수 없습니다({type(error).__name__}). "
              "supabase/auth_schema.sql 실행 전에는 비상 관리자로만 로그인할 수 있습니다.")
        return False

    for default in permissions.DEFAULT_ROLES:
        role = existing.get(default["name"])

        if role is None:
            store.insert(ROLES, {
                "name": default["name"],
                "description": default["description"],
                "permissions": default["permissions"],
                "is_system": True,
            })
        elif default["name"] == permissions.ADMIN_ROLE and set(role.get("permissions") or []) != permissions.ALL_SET:
            store.update(ROLES, {"id": f"eq.{role['id']}"}, {"permissions": permissions.ALL})

    invalidate_roles()

    if store.select(USERS, {"limit": 1}):
        return True

    if not APP_ADMIN_PASSWORD:
        print("[auth] 사용자가 없고 APP_ADMIN_PASSWORD도 없어 첫 관리자를 만들지 못했습니다.")
        return True

    admin_role = next(r for r in list_roles(force=True) if r["name"] == permissions.ADMIN_ROLE)
    username = (APP_ADMIN_ID or "admin").strip().lower()

    create_user(username, "관리자", admin_role["id"], APP_ADMIN_PASSWORD, must_change=True)
    audit.record("system", "bootstrap", target=username, detail={"note": "첫 관리자 생성"})
    print(f"[auth] 첫 관리자 '{username}' 계정을 만들었습니다. 첫 로그인에서 비밀번호를 변경해야 합니다.")

    return True
