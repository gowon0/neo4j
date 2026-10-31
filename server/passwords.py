"""비밀번호 해시(scrypt, 표준 라이브러리)와 정책."""

import base64
import hashlib
import hmac
import os
import re
import secrets
import string

from config.settings import PASSWORD_MIN_LENGTH

_N, _R, _P = 2 ** 14, 8, 1


def _b64(data):

    return base64.b64encode(data).decode()


def hash_password(password):

    salt = os.urandom(16)
    digest = hashlib.scrypt(
        password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32,
    )

    return f"scrypt${_N}${_R}${_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password, stored):

    try:
        scheme, n, r, p, salt, digest = stored.split("$")

        if scheme != "scrypt":
            return False

        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(
            password.encode(), salt=base64.b64decode(salt),
            n=int(n), r=int(r), p=int(p), dklen=len(expected),
        )
    except Exception:
        return False

    return hmac.compare_digest(actual, expected)


def policy_error(password, username=""):
    """정책을 어기면 안내 문구, 만족하면 None."""

    if len(password or "") < PASSWORD_MIN_LENGTH:
        return f"비밀번호는 {PASSWORD_MIN_LENGTH}자 이상이어야 합니다."

    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        return "비밀번호는 영문과 숫자를 모두 포함해야 합니다."

    if username and password.lower() == username.lower():
        return "비밀번호는 아이디와 달라야 합니다."

    return None


def generate_temp_password(length=12):

    alphabet = string.ascii_letters + string.digits

    while True:
        value = "".join(secrets.choice(alphabet) for _ in range(length))

        if policy_error(value) is None:
            return value
