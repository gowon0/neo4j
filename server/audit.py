"""감사 로그 (Supabase audit_logs).

기록 실패가 업무 요청을 막지 않도록 모든 예외를 삼키고 서버 로그에만 남긴다.
"""

from datetime import datetime, timezone

from server import store

TABLE = "audit_logs"

# 화면 필터용 행위 목록
ACTIONS = {
    "login": "로그인",
    "login_failed": "로그인 실패",
    "login_locked": "로그인 잠금",
    "login_emergency": "비상 관리자 로그인",
    "logout": "로그아웃",
    "password_change": "비밀번호 변경",
    "password_reset": "비밀번호 초기화",
    "order_create": "발주 등록",
    "order_update": "발주 상태 변경",
    "export": "내보내기",
    "risks_refresh": "위험 알림 새로 분석",
    "data_refresh": "데이터 새로고침",
    "user_create": "사용자 생성",
    "user_update": "사용자 수정",
    "user_unlock": "잠금 해제",
    "role_create": "역할 생성",
    "role_update": "역할 수정",
    "role_delete": "역할 삭제",
    "access_denied": "접근 거부",
    "bootstrap": "초기 설정",
}


def client_ip(request):
    """nginx가 넘겨준 실제 접속 IP (없으면 직접 연결 주소)."""

    if request is None:
        return ""

    real = request.headers.get("x-real-ip")

    if real:
        return real.strip()

    forwarded = request.headers.get("x-forwarded-for")

    if forwarded:
        return forwarded.split(",")[0].strip()

    return request.client.host if request.client else ""


def record(username, action, target="", detail=None, ip=""):

    try:
        store.insert(TABLE, {
            "at": datetime.now(timezone.utc).isoformat(),
            "username": username or "",
            "action": action,
            "target": target or "",
            "detail": detail or {},
            "ip": ip or "",
        })
    except Exception as error:
        print(f"[audit] 기록 실패({action}): {type(error).__name__}")


def search(username=None, action=None, date_from=None, date_to=None,
           limit=100, offset=0, exact=False):
    """조건에 맞는 로그를 최신순으로 반환. limit+1개를 읽어 다음 페이지 여부를 알려준다.

    limit은 200 이하로 쓴다(store.select의 페이지 크기보다 작아야 한다).
    """

    params = {"order": "at.desc", "limit": limit + 1, "offset": offset}

    if username:
        params["username"] = f"eq.{username}" if exact else f"ilike.*{username}*"

    if isinstance(action, (list, tuple)):
        params["action"] = f"in.({','.join(action)})"
    elif action:
        params["action"] = f"eq.{action}"

    conditions = []

    if date_from:
        conditions.append(f"at.gte.{date_from}T00:00:00+09:00")

    if date_to:
        conditions.append(f"at.lte.{date_to}T23:59:59+09:00")

    if conditions:
        params["and"] = f"({','.join(conditions)})"

    rows = store.select(TABLE, params)

    return rows[:limit], len(rows) > limit
