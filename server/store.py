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
