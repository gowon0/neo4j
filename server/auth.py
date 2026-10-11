"""단일 관리자 계정 기반 서명 토큰 인증 (표준 라이브러리만 사용)."""

import base64
import hashlib
import hmac
import secrets
import time

from fastapi import Header, HTTPException

from config.settings import (
    APP_ADMIN_ID,
    APP_ADMIN_PASSWORD,
    APP_SECRET,
    APP_TOKEN_TTL_HOURS,
)


# APP_SECRET이 없으면 프로세스마다 임시 키 사용 (재시작 시 재로그인)
_SECRET = (APP_SECRET or secrets.token_hex(32)).encode()


def _sign(payload):

    return hmac.new(_SECRET, payload.encode(), hashlib.sha256).hexdigest()


def verify_credentials(user_id, password):

    if not APP_ADMIN_PASSWORD:
        raise HTTPException(
            status_code=503,
            detail="서버에 APP_ADMIN_PASSWORD가 설정되지 않았습니다.",
        )

    id_ok = hmac.compare_digest(user_id or "", APP_ADMIN_ID)
    pw_ok = hmac.compare_digest(password or "", APP_ADMIN_PASSWORD)

    return id_ok and pw_ok


def issue_token(user_id):

    expires = int(time.time()) + APP_TOKEN_TTL_HOURS * 3600
    payload = f"{user_id}|{expires}"
    encoded = base64.urlsafe_b64encode(payload.encode()).decode()

    return f"{encoded}.{_sign(payload)}"


def _read_token(token):

    try:
        encoded, signature = token.split(".", 1)
        payload = base64.urlsafe_b64decode(encoded.encode()).decode()
        user_id, expires = payload.rsplit("|", 1)
    except Exception:
        return None

    if not hmac.compare_digest(signature, _sign(payload)):
        return None

    if int(expires) < time.time():
        return None

    return user_id


def current_user(authorization: str = Header(default="")):

    scheme, _, token = authorization.partition(" ")

    user = _read_token(token) if scheme.lower() == "bearer" else None

    if not user:
        raise HTTPException(
            status_code=401,
            detail="로그인이 필요합니다.",
        )

    return user
