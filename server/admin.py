"""관리자 API: 사용자·역할·감사 로그와 내 계정."""

import re

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from config.settings import APP_ADMIN_ID, APP_EMERGENCY_ID
from server import accounts, audit, auth, export, passwords, permissions

router = APIRouter()

USERNAME = re.compile(r"^[a-z0-9._-]{3,30}$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
EXPORT_PAGE = 200
EXPORT_MAX_ROWS = 2000


# ------------------------------------------------------------
# 사용자 관리
# ------------------------------------------------------------

def _role_map():

    return {str(r["id"]): r for r in accounts.list_roles(force=True)}


def _user_view(row, roles):

    role = roles.get(str(row.get("role_id")))
    locked = accounts.parse(row.get("locked_until"))

    return {
        "id": row["id"],
        "username": row["username"],
        "display_name": row.get("display_name") or row["username"],
        "role_id": row.get("role_id"),
        "role_name": role["name"] if role else "(역할 없음)",
        "is_active": bool(row.get("is_active")),
        "must_change_password": bool(row.get("must_change_password")),
        "locked": bool(locked and locked > accounts.now()),
        "failed_logins": int(row.get("failed_logins") or 0),
        "last_login_at": row.get("last_login_at"),
        "created_at": row.get("created_at"),
    }


def _role_view(role, user_counts):

    return {
        "id": role["id"],
        "name": role["name"],
        "description": role.get("description") or "",
        "permissions": sorted(accounts.role_permissions(role), key=permissions.ALL.index),
        "is_system": bool(role.get("is_system")),
        "user_count": user_counts.get(str(role["id"]), 0),
    }


def _counts(users):

    counts = {}

    for u in users:
        key = str(u.get("role_id"))
        counts[key] = counts.get(key, 0) + 1

    return counts


@router.get("/api/admin/users")
def list_users(user: auth.Principal = Depends(auth.require("users.manage"))):

    roles = _role_map()
    users = accounts.list_users()

    return {
        "users": [_user_view(u, roles) for u in users],
        "roles": [{"id": r["id"], "name": r["name"]} for r in roles.values()],
    }


class UserCreate(BaseModel):
    username: str
    display_name: str = Field(min_length=1, max_length=50)
    role_id: int
    password: str | None = None


@router.post("/api/admin/users")
def create_user(
    body: UserCreate,
    request: Request,
    user: auth.Principal = Depends(auth.require("users.manage")),
):

    username = body.username.strip().lower()

    if not USERNAME.match(username):
        raise HTTPException(422, "아이디는 영문 소문자·숫자·._- 로 3~30자여야 합니다.")

    reserved = {(APP_EMERGENCY_ID or "").lower(), (APP_ADMIN_ID or "").lower()} - {""}

    if username in reserved and accounts.get_user_by_username(username) is None and username == (APP_EMERGENCY_ID or "").lower():
        raise HTTPException(422, "비상 관리자용으로 예약된 아이디입니다.")

    if accounts.get_role(body.role_id) is None:
        raise HTTPException(422, "존재하지 않는 역할입니다.")

    if accounts.get_user_by_username(username):
        raise HTTPException(409, "이미 사용 중인 아이디입니다.")

    password = body.password or passwords.generate_temp_password()

    if body.password:
        error = passwords.policy_error(password, username)

        if error:
            raise HTTPException(422, error)

    row = accounts.create_user(
        username, body.display_name.strip(), body.role_id, password, must_change=True,
    )
    audit.record(
        user.username, "user_create", target=username, ip=audit.client_ip(request),
        detail={"role_id": body.role_id},
    )

    return {"user": _user_view(row, _role_map()), "temp_password": password}


class UserUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=50)
    role_id: int | None = None
    is_active: bool | None = None


@router.patch("/api/admin/users/{user_id}")
def update_user(
    user_id: int,
    body: UserUpdate,
    request: Request,
    user: auth.Principal = Depends(auth.require("users.manage")),
):

    target = accounts.get_user(user_id, fresh=True)

    if not target:
        raise HTTPException(404, "사용자를 찾을 수 없습니다.")

    patch = {}
    changes = {}

    if body.display_name is not None and body.display_name.strip() != target.get("display_name"):
        patch["display_name"] = body.display_name.strip()
        changes["display_name"] = patch["display_name"]

    if body.role_id is not None and str(body.role_id) != str(target.get("role_id")):
        if accounts.get_role(body.role_id) is None:
            raise HTTPException(422, "존재하지 않는 역할입니다.")
        patch["role_id"] = body.role_id
        changes["role_id"] = body.role_id

    if body.is_active is not None and body.is_active != bool(target.get("is_active")):
        patch["is_active"] = body.is_active
        changes["is_active"] = body.is_active

    if not patch:
        return {"user": _user_view(target, _role_map())}

    if str(target["id"]) == user.id and ("role_id" in patch or "is_active" in patch):
        raise HTTPException(422, "본인의 역할과 활성 상태는 바꿀 수 없습니다.")

    overrides = {k: patch[k] for k in ("role_id", "is_active") if k in patch}

    if overrides:
        error = accounts.lockout_error(user_overrides={str(target["id"]): overrides})

        if error:
            raise HTTPException(422, error)

    if patch.get("is_active") is False:
        patch["token_version"] = int(target.get("token_version") or 1) + 1

    row = accounts.update_user(user_id, patch)
    audit.record(
        user.username, "user_update", target=target["username"],
        ip=audit.client_ip(request), detail=changes,
    )

    return {"user": _user_view(row, _role_map())}


@router.post("/api/admin/users/{user_id}/reset-password")
def reset_password(
    user_id: int,
    request: Request,
    user: auth.Principal = Depends(auth.require("users.manage")),
):

    target = accounts.get_user(user_id, fresh=True)

    if not target:
        raise HTTPException(404, "사용자를 찾을 수 없습니다.")

    password = passwords.generate_temp_password()
    accounts.set_password(user_id, password, must_change=True)
    audit.record(user.username, "password_reset", target=target["username"], ip=audit.client_ip(request))

    return {"temp_password": password}


@router.post("/api/admin/users/{user_id}/unlock")
def unlock_user(
    user_id: int,
    request: Request,
    user: auth.Principal = Depends(auth.require("users.manage")),
):

    target = accounts.get_user(user_id, fresh=True)

    if not target:
        raise HTTPException(404, "사용자를 찾을 수 없습니다.")

    row = accounts.update_user(user_id, {"failed_logins": 0, "locked_until": None})
    audit.record(user.username, "user_unlock", target=target["username"], ip=audit.client_ip(request))

    return {"user": _user_view(row, _role_map())}


# ------------------------------------------------------------
# 역할·권한 관리
# ------------------------------------------------------------

@router.get("/api/admin/roles")
def list_roles(principal: auth.Principal = Depends(auth.current_user)):

    if not (principal.can("users.manage") or principal.can("roles.manage")):
        raise HTTPException(403, auth.FORBIDDEN)

    counts = _counts(accounts.list_users())

    return {
        "roles": [_role_view(r, counts) for r in accounts.list_roles(force=True)],
        "permissions": permissions.catalog(),
    }


class RoleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=30)
    description: str = Field(default="", max_length=200)
    permissions: list[str] = []


@router.post("/api/admin/roles")
def create_role(
    body: RoleCreate,
    request: Request,
    user: auth.Principal = Depends(auth.require("roles.manage")),
):

    name = body.name.strip()

    if any(r["name"] == name for r in accounts.list_roles(force=True)):
        raise HTTPException(409, "이미 있는 역할 이름입니다.")

    row = accounts.create_role(name, body.description.strip(), body.permissions)
    audit.record(
        user.username, "role_create", target=name, ip=audit.client_ip(request),
        detail={"permissions": row.get("permissions")},
    )

    return {"role": _role_view(row, {})}


class RoleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=30)
    description: str | None = Field(default=None, max_length=200)
    permissions: list[str] | None = None


@router.patch("/api/admin/roles/{role_id}")
def update_role(
    role_id: int,
    body: RoleUpdate,
    request: Request,
    user: auth.Principal = Depends(auth.require("roles.manage")),
):

    role = accounts.get_role(role_id)

    if not role:
        raise HTTPException(404, "역할을 찾을 수 없습니다.")

    is_admin_role = role["name"] == permissions.ADMIN_ROLE and role.get("is_system")
    patch = {}
    changes = {}

    if body.name is not None and body.name.strip() != role["name"]:
        if role.get("is_system"):
            raise HTTPException(422, "기본 역할의 이름은 바꿀 수 없습니다.")
        if any(r["name"] == body.name.strip() for r in accounts.list_roles(force=True)):
            raise HTTPException(409, "이미 있는 역할 이름입니다.")
        patch["name"] = body.name.strip()
        changes["name"] = patch["name"]

    if body.description is not None and body.description.strip() != (role.get("description") or ""):
        patch["description"] = body.description.strip()

    if body.permissions is not None:
        new_perms = permissions.valid(body.permissions)

        if is_admin_role and set(new_perms) != permissions.ALL_SET:
            raise HTTPException(422, "관리자 역할의 권한은 줄일 수 없습니다.")

        if set(new_perms) != set(accounts.role_permissions(role)):
            error = accounts.lockout_error(role_perm_overrides={str(role_id): new_perms})

            if error:
                raise HTTPException(422, error)

            patch["permissions"] = new_perms
            changes["permissions"] = {
                "added": sorted(set(new_perms) - set(accounts.role_permissions(role))),
                "removed": sorted(set(accounts.role_permissions(role)) - set(new_perms)),
            }

    if not patch:
        return {"role": _role_view(role, _counts(accounts.list_users()))}

    row = accounts.update_role(role_id, patch)
    audit.record(user.username, "role_update", target=role["name"], ip=audit.client_ip(request), detail=changes)

    return {"role": _role_view(row, _counts(accounts.list_users()))}


@router.delete("/api/admin/roles/{role_id}")
def delete_role(
    role_id: int,
    request: Request,
    user: auth.Principal = Depends(auth.require("roles.manage")),
):

    role = accounts.get_role(role_id)

    if not role:
        raise HTTPException(404, "역할을 찾을 수 없습니다.")

    if role.get("is_system"):
        raise HTTPException(422, "기본 역할은 삭제할 수 없습니다.")

    if _counts(accounts.list_users()).get(str(role_id)):
        raise HTTPException(409, "이 역할을 쓰는 사용자가 있어 삭제할 수 없습니다.")

    accounts.delete_role(role_id)
    audit.record(user.username, "role_delete", target=role["name"], ip=audit.client_ip(request))

    return {"ok": True}


# ------------------------------------------------------------
# 감사 로그
# ------------------------------------------------------------

def _check_dates(date_from, date_to):

    for value in (date_from, date_to):
        if value and not DATE.match(value):
            raise HTTPException(422, "날짜는 YYYY-MM-DD 형식이어야 합니다.")


@router.get("/api/admin/audit")
def audit_logs(
    username: str | None = None,
    action: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: auth.Principal = Depends(auth.require("audit.view")),
):

    _check_dates(date_from, date_to)
    rows, more = audit.search(username, action, date_from, date_to, limit, offset)

    return {"rows": rows, "has_more": more, "actions": audit.ACTIONS}


@router.get("/api/export/audit")
def export_audit(
    request: Request,
    fmt: str = Query("csv", alias="format"),
    username: str | None = None,
    action: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    user: auth.Principal = Depends(auth.require("audit.view")),
):

    export.check_format(fmt)
    _check_dates(date_from, date_to)
    audit.record(
        user.username, "export", target="감사로그", ip=audit.client_ip(request),
        detail={"format": fmt, "username": username, "action": action},
    )

    rows, offset = [], 0

    while len(rows) < EXPORT_MAX_ROWS:
        page, more = audit.search(username, action, date_from, date_to, EXPORT_PAGE, offset)
        rows.extend(page)
        offset += EXPORT_PAGE

        if not more:
            break

    sheet = [export._sheet(
        "감사 로그",
        ["일시", "사용자", "행위", "대상", "IP", "상세"],
        [
            [r["at"], r["username"], audit.ACTIONS.get(r["action"], r["action"]), r["target"], r["ip"],
             str(r.get("detail") or "")]
            for r in rows[:EXPORT_MAX_ROWS]
        ],
        primary=True,
    )]

    return export.respond("감사로그", fmt, sheet)


# ------------------------------------------------------------
# 내 계정
# ------------------------------------------------------------

class PasswordChange(BaseModel):
    current_password: str
    new_password: str


@router.post("/api/account/password")
def change_password(
    body: PasswordChange,
    request: Request,
    principal: auth.Principal = Depends(auth.current_principal),
):

    if principal.emergency:
        raise HTTPException(422, "비상 관리자 비밀번호는 서버 설정(.env)에서 바꿉니다.")

    row = accounts.get_user(principal.id, fresh=True)

    if not row or not passwords.verify_password(body.current_password, row["password_hash"]):
        audit.record(principal.username, "login_failed", ip=audit.client_ip(request),
                     detail={"reason": "password_change_wrong_current"})
        raise HTTPException(422, "현재 비밀번호가 올바르지 않습니다.")

    if body.new_password == body.current_password:
        raise HTTPException(422, "새 비밀번호가 현재 비밀번호와 같습니다.")

    error = passwords.policy_error(body.new_password, principal.username)

    if error:
        raise HTTPException(422, error)

    updated = accounts.set_password(principal.id, body.new_password, must_change=False)
    audit.record(principal.username, "password_change", ip=audit.client_ip(request))

    refreshed = auth._principal_from_row(updated)

    return {
        "token": auth.issue_token(refreshed.id, int(updated.get("token_version") or 1)),
        "user": refreshed.info(),
    }


@router.get("/api/account/logins")
def my_logins(principal: auth.Principal = Depends(auth.current_principal)):
    """내 최근 로그인 이력(성공·실패 각 최근 기록)."""

    rows, _ = audit.search(
        principal.username, ["login", "login_failed", "login_emergency"],
        limit=15, exact=True,
    )

    return {"rows": [
        {"at": r["at"], "action": r["action"], "ip": r["ip"]} for r in rows
    ]}
