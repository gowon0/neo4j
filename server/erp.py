"""발주/재고 운영 데이터 (로컬 SQLite).

Supabase에는 발주·재고 테이블이 없어, 최초 실행 시 수요이력(평균 수요)을
기준으로 샘플 데이터를 결정적으로 생성한다. 이후 발주 등록/상태 변경은
이 DB에 저장된다.
"""

import os
import random
import sqlite3
import threading
from datetime import date, timedelta

from server import forecast as fc


DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "erp.db",
)

ORDER_STATUSES = ["발주대기", "진행중", "발주완료", "지연"]

_lock = threading.Lock()


def _connect():

    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    return conn


def _po_number(conn, order_date):

    prefix = f"PO{order_date.strftime('%Y%m%d')}"

    count = conn.execute(
        "SELECT COUNT(*) FROM orders WHERE po_no LIKE ?",
        (prefix + "%",),
    ).fetchone()[0]

    return f"{prefix}{count + 1:03d}"


def init_db(forecasts):
    """테이블 생성 및 최초 1회 샘플 데이터 생성."""

    with _lock, _connect() as conn:

        conn.executescript("""
            CREATE TABLE IF NOT EXISTS inventory (
                material_id   INTEGER PRIMARY KEY,
                current_stock INTEGER NOT NULL,
                safety_stock  INTEGER NOT NULL,
                updated_at    TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS orders (
                po_no       TEXT PRIMARY KEY,
                material_id INTEGER NOT NULL,
                quantity    INTEGER NOT NULL,
                order_date  TEXT NOT NULL,
                due_date    TEXT NOT NULL,
                status      TEXT NOT NULL
            );
        """)

        seeded = conn.execute(
            "SELECT COUNT(*) FROM inventory"
        ).fetchone()[0]

        if seeded or not forecasts:
            return

        today = date.today()

        for material_id, data in forecasts.items():

            rng = random.Random(20260000 + material_id)

            last_year = [p["value"] for p in data["history"][-12:]]
            avg_monthly = sum(last_year) / max(len(last_year), 1)

            safety = max(1, round(avg_monthly * 1.5))
            current = round(safety * rng.uniform(0.55, 1.35))

            conn.execute(
                "INSERT INTO inventory VALUES (?, ?, ?, ?)",
                (material_id, current, safety, today.isoformat()),
            )

            for _ in range(rng.randint(6, 8)):

                order_date = today - timedelta(days=rng.randint(1, 120))
                due_date = order_date + timedelta(days=rng.randint(14, 45))
                quantity = max(
                    1,
                    round(avg_monthly * rng.uniform(0.5, 1.5)),
                )

                if due_date < today:
                    status = "발주완료" if rng.random() < 0.85 else "지연"
                elif (today - order_date).days <= 10:
                    status = rng.choice(["발주대기", "진행중"])
                else:
                    status = "진행중"

                conn.execute(
                    "INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        _po_number(conn, order_date),
                        material_id,
                        quantity,
                        order_date.isoformat(),
                        due_date.isoformat(),
                        status,
                    ),
                )


# ------------------------------------------------------------
# 발주
# ------------------------------------------------------------

def list_orders(material_id=None, status=None):

    query = "SELECT * FROM orders WHERE 1=1"
    params = []

    if material_id:
        query += " AND material_id = ?"
        params.append(material_id)

    if status:
        query += " AND status = ?"
        params.append(status)

    query += " ORDER BY order_date DESC, po_no DESC"

    with _lock, _connect() as conn:
        return [dict(r) for r in conn.execute(query, params)]


def create_order(material_id, quantity, due_date):

    today = date.today()

    with _lock, _connect() as conn:

        po_no = _po_number(conn, today)

        conn.execute(
            "INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?)",
            (
                po_no,
                material_id,
                quantity,
                today.isoformat(),
                due_date,
                "발주대기",
            ),
        )

    return po_no


def update_order_status(po_no, status):

    with _lock, _connect() as conn:

        cursor = conn.execute(
            "UPDATE orders SET status = ? WHERE po_no = ?",
            (status, po_no),
        )

        return cursor.rowcount > 0


def fulfillment_rate(days_from, days_to):
    """납기가 [today-days_from, today-days_to) 구간인 발주의 이행률(%)."""

    today = date.today()

    start = (today - timedelta(days=days_from)).isoformat()
    end = (today - timedelta(days=days_to)).isoformat()

    with _lock, _connect() as conn:
        rows = conn.execute(
            """
            SELECT status, COUNT(*) AS n FROM orders
            WHERE due_date >= ? AND due_date < ?
              AND status IN ('발주완료', '지연')
            GROUP BY status
            """,
            (start, end),
        ).fetchall()

    counts = {r["status"]: r["n"] for r in rows}
    done = counts.get("발주완료", 0)
    total = done + counts.get("지연", 0)

    if total == 0:
        return None

    return round(done / total * 100, 1)


def pending_quantity(material_id):

    with _lock, _connect() as conn:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(quantity), 0) FROM orders
            WHERE material_id = ? AND status IN ('발주대기', '진행중')
            """,
            (material_id,),
        ).fetchone()

    return row[0]


# ------------------------------------------------------------
# 재고
# ------------------------------------------------------------

def _stock_status(current, safety):

    if current >= safety:
        return "여유"

    if current >= safety * 0.5:
        return "부족"

    return "위험"


def next_month_demand(data, today=None):

    today = today or date.today()

    nxt = date(
        today.year + (today.month // 12),
        today.month % 12 + 1,
        1,
    ).strftime("%Y-%m")

    by_month = {p["month"]: p["value"] for p in data["forecast"]}

    if nxt in by_month:
        return by_month[nxt]

    values = list(by_month.values())

    return round(sum(values) / len(values)) if values else 0


def inventory_view(forecasts, material_id=None, status=None):

    with _lock, _connect() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM inventory")]

    result = []

    for row in rows:

        data = forecasts.get(row["material_id"])

        if data is None:
            continue

        if material_id and row["material_id"] != material_id:
            continue

        current = row["current_stock"]
        safety = row["safety_stock"]

        demand_next = next_month_demand(data)
        pending = pending_quantity(row["material_id"])

        recommended = max(
            0,
            safety + demand_next - current - pending,
        )

        daily = demand_next / 30 if demand_next else 0
        days_left = round(current / daily) if daily else None

        item = {
            "material_id": row["material_id"],
            "name": data["name"],
            "unit": data["unit"],
            "current_stock": current,
            "safety_stock": safety,
            "gap": safety - current,
            "status": _stock_status(current, safety),
            "next_month_demand": demand_next,
            "pending_order": pending,
            "recommended_order": recommended,
            "days_left": days_left,
            "updated_at": row["updated_at"],
        }

        if status and item["status"] != status:
            continue

        result.append(item)

    result.sort(key=lambda r: r["material_id"])

    return result
