"""로그인, 서명 토큰, 권한 검사.

- 사용자는 Supabase app_users에 있고 비밀번호는 scrypt 해시로 저장한다.
- 토큰은 `사용자|토큰버전|만료시각`에 HMAC 서명을 붙인 형태다. 사용자별 토큰 버전을 올리면
  (로그아웃·비밀번호 변경) 이전에 발급된 토큰이 모두 무효가 된다.
- 요청마다 사용자·역할을 확인하므로 권한 변경과 비활성화가 곧바로 적용된다.
- 비상 관리자(.env)는 DB를 쓸 수 없을 때도 로그인할 수 있다.
"""

import base64
import hashlib
import hmac
import secrets
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import timedelta

from fastapi import Depends, Header, HTTPException, Request

from config.settings import (
    APP_ADMIN_ID,
    APP_ADMIN_PASSWORD,
    APP_EMERGENCY_ENABLED,
    APP_EMERGENCY_ID,
    APP_SECRET,
    APP_TOKEN_TTL_HOURS,
    LOGIN_IP_LIMIT,
    LOGIN_LOCK_MINUTES,
    LOGIN_MAX_FAILURES,
)
from server import accounts, audit, passwords, permissions

# APP_SECRET이 없으면 프로세스마다 임시 키 사용 (재시작 시 재로그인)
_SECRET = (APP_SECRET or secrets.token_hex(32)).encode()

_DUMMY_HASH = passwords.hash_password("dummy-password-for-timing")
_attempts = defaultdict(deque)
_env_fail = {"count": 0, "until": 0.0}
_denied_seen = {}
_guard = threading.Lock()

GENERIC_LOGIN_ERROR = "아이디 또는 비밀번호가 올바르지 않습니다."
FORBIDDEN = "이 화면 또는 기능을 사용할 권한이 없습니다."


@dataclass(frozen=True)
class Principal:
    id: str
    username: str
    display_name: str
    role: str
    permissions: frozenset
    must_change_password: bool = False
    emergency: bool = False

    def can(self, *codes):

        return all(code in self.permissions for code in codes)

    def info(self):

        return {
            "id": self.id,
            "username": self.username,
            "name": self.display_name,
            "role": self.role,
            "permissions": sorted(self.permissions, key=permissions.ALL.index),
            "must_change_password": self.must_change_password,
            "emergency": self.emergency,
        }


# ------------------------------------------------------------
# 토큰
# ------------------------------------------------------------

def _sign(payload):

    return hmac.new(_SECRET, payload.encode(), hashlib.sha256).hexdigest()


def issue_token(user_id, version=1):

    expires = int(time.time()) + APP_TOKEN_TTL_HOURS * 3600
    payload = f"{user_id}|{version}|{expires}"
    encoded = base64.urlsafe_b64encode(payload.encode()).decode()

    return f"{encoded}.{_sign(payload)}"


def _read_token(token):
    """(사용자 id, 토큰 버전) 또는 None."""

    try:
        encoded, signature = token.split(".", 1)
        payload = base64.urlsafe_b64decode(encoded.encode()).decode()
        user_id, version, expires = payload.rsplit("|", 2)
    except Exception:
        return None

    if not hmac.compare_digest(signature, _sign(payload)):
        return None

    if int(expires) < time.time():
        return None

    return user_id, int(version)


# ------------------------------------------------------------
# 로그인
# ------------------------------------------------------------

def _throttle_ip(ip):
    """IP당 10분 내 시도 횟수 제한."""

    if not ip:
        return

    limit_at = time.time() - 600

    with _guard:
        queue = _attempts[ip]

        while queue and queue[0] < limit_at:
            queue.popleft()

        if len(queue) >= LOGIN_IP_LIMIT:
            raise HTTPException(429, "로그인 시도가 너무 많습니다. 잠시 후 다시 시도해 주세요.")

        queue.append(time.time())


def _principal_from_row(row):

    role = accounts.get_role(row.get("role_id"))

    return Principal(
        id=str(row["id"]),
        username=row["username"],
        display_name=row.get("display_name") or row["username"],
        role=role["name"] if role else "(역할 없음)",
        permissions=accounts.role_permissions(role),
        must_change_password=bool(row.get("must_change_password")),
    )


def _locked_message():

    return (
        f"로그인 시도가 너무 많아 잠겼습니다. {LOGIN_LOCK_MINUTES}분 뒤 다시 시도하거나 "
        "관리자에게 잠금 해제를 요청하세요."
    )


def _login_db(row, password, ip):

    username = row["username"]
    locked = accounts.parse(row.get("locked_until"))

    if locked and locked > accounts.now():
        audit.record(username, "login_locked", ip=ip)
        raise HTTPException(429, _locked_message())

    ok = passwords.verify_password(password, row["password_hash"]) and bool(row.get("is_active"))

    if not ok:
        failures = int(row.get("failed_logins") or 0) + 1
        patch = {"failed_logins": failures}
        lock_now = failures >= LOGIN_MAX_FAILURES

        if lock_now:
            patch = {
                "failed_logins": 0,
                "locked_until": (accounts.now() + timedelta(minutes=LOGIN_LOCK_MINUTES)).isoformat(),
            }

        accounts.update_user(row["id"], patch)
        audit.record(
            username, "login_failed", ip=ip,
            detail={"failures": failures, "inactive": not row.get("is_active")},
        )

        if lock_now:
            raise HTTPException(429, _locked_message())

        raise HTTPException(401, GENERIC_LOGIN_ERROR)

    row = accounts.update_user(row["id"], {
        "failed_logins": 0,
        "locked_until": None,
        "last_login_at": accounts.now().isoformat(),
    }) or row
    audit.record(username, "login", ip=ip)

    return _principal_from_row(row), int(row.get("token_version") or 1)


def _emergency_principal(username):

    return Principal(
        id=f"env:{username}",
        username=username,
        display_name="비상 관리자",
        role="비상 관리자",
        permissions=permissions.ALL_SET,
        emergency=True,
    )


def _login_emergency(username, password, ip):

    names = {(APP_EMERGENCY_ID or "").lower(), (APP_ADMIN_ID or "").lower()} - {""}

    if not (APP_EMERGENCY_ENABLED and APP_ADMIN_PASSWORD and username in names):
        passwords.verify_password(password, _DUMMY_HASH)   # 사용자 존재 여부가 시간으로 드러나지 않게
        raise HTTPException(401, GENERIC_LOGIN_ERROR)

    with _guard:
        if _env_fail["until"] > time.time():
            raise HTTPException(429, _locked_message())

    if not hmac.compare_digest(password or "", APP_ADMIN_PASSWORD):
        with _guard:
            _env_fail["count"] += 1

            if _env_fail["count"] >= LOGIN_MAX_FAILURES:
                _env_fail.update(count=0, until=time.time() + LOGIN_LOCK_MINUTES * 60)
                audit.record(username, "login_locked", ip=ip, detail={"emergency": True})
                raise HTTPException(429, _locked_message())

        audit.record(username, "login_failed", ip=ip, detail={"emergency": True})
        raise HTTPException(401, GENERIC_LOGIN_ERROR)

    with _guard:
        _env_fail["count"] = 0

    audit.record(username, "login_emergency", ip=ip)

    return _emergency_principal(username), 1


def authenticate(username, password, ip=""):
    """(Principal, 토큰 버전)을 반환하고, 실패하면 401/429를 낸다."""

    name = (username or "").strip().lower()
    _throttle_ip(ip)

    try:
        row = accounts.get_user_by_username(name)
    except Exception:
        row = None   # 사용자 저장소를 쓸 수 없으면 비상 관리자만 허용

    if row:
        return _login_db(row, password or "", ip)

    return _login_emergency(name, password or "", ip)


def make_token(principal, version):

    return issue_token(principal.id, version)


# ------------------------------------------------------------
# 요청 인증 · 권한
# ------------------------------------------------------------

def current_principal(authorization: str = Header(default="")):
    """토큰만 확인한다. (비밀번호 변경 대기 중인 사용자도 통과)"""

    scheme, _, token = authorization.partition(" ")
    parsed = _read_token(token) if scheme.lower() == "bearer" else None

    if not parsed:
        raise HTTPException(401, "로그인이 필요합니다.")

    user_id, version = parsed

    if user_id.startswith("env:"):
        name = user_id[4:]

        if not APP_EMERGENCY_ENABLED or name not in {(APP_EMERGENCY_ID or "").lower(), (APP_ADMIN_ID or "").lower()}:
            raise HTTPException(401, "로그인이 필요합니다.")

        return _emergency_principal(name)

    try:
        row = accounts.get_user(user_id)
    except Exception:
        raise HTTPException(503, "사용자 저장소를 사용할 수 없습니다. 잠시 후 다시 시도해 주세요.")

    if not row or not row.get("is_active") or int(row.get("token_version") or 1) != version:
        raise HTTPException(401, "로그인이 필요합니다.")

    return _principal_from_row(row)


def current_user(principal: Principal = Depends(current_principal)):
    """로그인 + 비밀번호 변경 완료 상태."""

    if principal.must_change_password:
        raise HTTPException(403, "비밀번호를 먼저 변경해야 합니다.")

    return principal


def _log_denied(principal, request):

    key = (principal.username, request.url.path)
    now = time.time()

    with _guard:
        if now - _denied_seen.get(key, 0) < 60:
            return

        _denied_seen[key] = now

    audit.record(
        principal.username, "access_denied",
        target=f"{request.method} {request.url.path}", ip=audit.client_ip(request),
    )


def require(*codes):
    """필요한 권한을 모두 가진 사용자만 통과시키는 의존성."""

    unknown = [c for c in codes if c not in permissions.ALL_SET]

    if unknown:
        raise ValueError(f"알 수 없는 권한 코드: {unknown}")

    def dependency(request: Request, principal: Principal = Depends(current_user)):

        if not principal.can(*codes):
            _log_denied(principal, request)
            raise HTTPException(403, FORBIDDEN)

        return principal

    return dependency
