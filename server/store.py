"""Supabase 읽기 전용 데이터 접근 계층 (서버 메모리 캐시)."""

import threading
import time

import requests

from config.settings import SUPABASE_URL, SUPABASE_KEY


TABLES = [
    "materials",
    "demand_history",
    "raw_material_prices",
    "construction_projects",
    "project_monthly_stats",
    "electricity_usage",
    "inventory",
    "purchase_orders",
]

CACHE_TTL_SECONDS = 600
PAGE_SIZE = 1000

_cache = {}
_lock = threading.Lock()


class StoreError(RuntimeError):
    pass


def _fetch_table(name):

    if not SUPABASE_URL or not SUPABASE_KEY:
        raise StoreError("SUPABASE_URL / SUPABASE_KEY 설정이 없습니다.")

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    }

    rows = []
    offset = 0

    while True:

        response = requests.get(
            f"{SUPABASE_URL.rstrip('/')}/rest/v1/{name}",
            params={
                "select": "*",
                "limit": PAGE_SIZE,
                "offset": offset,
            },
            headers=headers,
            timeout=30,
        )

        if response.status_code != 200:
            raise StoreError(
                f"Supabase '{name}' 조회 실패 "
                f"(HTTP {response.status_code})"
            )

        page = response.json()
        rows.extend(page)

        if len(page) < PAGE_SIZE:
            break

        offset += PAGE_SIZE

    return rows


# ------------------------------------------------------------
# 실시간 읽기/쓰기 (발주·재고 등 캐시하면 안 되는 운영 데이터)
# ------------------------------------------------------------

def _headers(prefer=None):

    if not SUPABASE_URL or not SUPABASE_KEY:
        raise StoreError("SUPABASE_URL / SUPABASE_KEY 설정이 없습니다.")

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }

    if prefer:
        headers["Prefer"] = prefer

    return headers


def _url(table):

    return f"{SUPABASE_URL.rstrip('/')}/rest/v1/{table}"


def _check(response, action):

    if response.status_code in (200, 201):
        return response.json()

    try:
        detail = response.json().get("message", "")
    except ValueError:
        detail = ""

    error = StoreError(
        f"Supabase {action} 실패 "
        f"(HTTP {response.status_code}) {detail}".strip()
    )
    error.status_code = response.status_code

    raise error


def select(table, params=None):
    """캐시 없이 전체 행 조회. params는 PostgREST 필터(예: {'status': 'eq.진행중'})."""

    rows = []
    offset = 0

    while True:

        response = requests.get(
            _url(table),
            params={
                "select": "*",
                "limit": PAGE_SIZE,
                "offset": offset,
                **(params or {}),
            },
            headers=_headers(),
            timeout=30,
        )

        page = _check(response, f"'{table}' 조회")
        rows.extend(page)

        if len(page) < PAGE_SIZE:
            return rows

        offset += PAGE_SIZE


def insert(table, row):

    response = requests.post(
        _url(table),
        json=row,
        headers=_headers("return=representation"),
        timeout=30,
    )

    return _check(response, f"'{table}' 등록")[0]


def update(table, match, patch):
    """match: {'po_no': 'eq.PO...'} 형태. 변경된 행 목록을 반환."""

    response = requests.patch(
        _url(table),
        params=match,
        json=patch,
        headers=_headers("return=representation"),
        timeout=30,
    )

    return _check(response, f"'{table}' 수정")


def delete(table, match):
    """match 조건에 맞는 행을 삭제하고 삭제된 행 목록을 반환."""

    response = requests.delete(
        _url(table),
        params=match,
        headers=_headers("return=representation"),
        timeout=30,
    )

    return _check(response, f"'{table}' 삭제")


def get_table(name, force=False):

    now = time.time()

    with _lock:

        cached = _cache.get(name)

        if (
            cached
            and not force
            and now - cached[0] < CACHE_TTL_SECONDS
        ):
            return cached[1]

    rows = _fetch_table(name)

    with _lock:
        _cache[name] = (now, rows)

    return rows


def refresh_all():

    for name in TABLES:
        get_table(name, force=True)


def table_status():

    result = []

    for name in TABLES:

        try:
            rows = get_table(name)
        except StoreError as error:
            result.append({
                "table": name,
                "rows": None,
                "error": str(error),
            })
            continue

        months = [r["month"] for r in rows if r.get("month")]
        statuses = sorted({
            r["data_status"]
            for r in rows
            if r.get("data_status")
        })

        result.append({
            "table": name,
            "rows": len(rows),
            "first_month": min(months) if months else None,
            "last_month": max(months) if months else None,
            "data_status": statuses,
            "error": None,
        })

    return result
