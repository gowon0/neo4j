"""발주/재고 운영 데이터 (Supabase purchase_orders / inventory).

테이블 생성 SQL은 supabase/schema.sql 참고. 운영 데이터이므로 캐시 없이
항상 실시간으로 읽고 쓴다.
"""

from datetime import date, timedelta

from server import store


ORDER_STATUSES = ["발주대기", "진행중", "발주완료", "지연"]

ORDERS = "purchase_orders"
INVENTORY = "inventory"


# ------------------------------------------------------------
# 발주
# ------------------------------------------------------------

def list_orders(material_id=None, status=None):

    params = {"order": "order_date.desc,po_no.desc"}

    if material_id:
        params["material_id"] = f"eq.{material_id}"

    if status:
        params["status"] = f"eq.{status}"

    return store.select(ORDERS, params)


def _next_po_number(order_date):

    prefix = f"PO{order_date.strftime('%Y%m%d')}"

    existing = store.select(
        ORDERS,
        {"select": "po_no", "po_no": f"like.{prefix}*"},
    )

    last = max(
        (int(r["po_no"][len(prefix):]) for r in existing),
        default=0,
    )

    return f"{prefix}{last + 1:03d}"


def create_order(material_id, quantity, due_date):

    today = date.today()

    # 동시 등록으로 번호가 겹치면(409) 다음 번호로 재시도
    for _ in range(3):

        po_no = _next_po_number(today)

        try:
            store.insert(ORDERS, {
                "po_no": po_no,
                "material_id": material_id,
                "quantity": quantity,
                "order_date": today.isoformat(),
                "due_date": due_date,
                "status": "발주대기",
                "data_status": "user_input",
            })
            return po_no
        except store.StoreError as error:
            if getattr(error, "status_code", None) != 409:
                raise

    raise store.StoreError("발주번호 생성에 실패했습니다. 다시 시도해 주세요.")


def update_order_status(po_no, status):

    rows = store.update(
        ORDERS,
        {"po_no": f"eq.{po_no}"},
        {"status": status},
    )

    return len(rows) > 0


def fulfillment_rate(days_from, days_to):
    """납기가 [today-days_from, today-days_to) 구간인 발주의 이행률(%)."""

    today = date.today()

    start = (today - timedelta(days=days_from)).isoformat()
    end = (today - timedelta(days=days_to)).isoformat()

    rows = store.select(ORDERS, {
        "select": "status",
        "and": f"(due_date.gte.{start},due_date.lt.{end})",
        "status": "in.(발주완료,지연)",
    })

    done = sum(1 for r in rows if r["status"] == "발주완료")

    if not rows:
        return None

    return round(done / len(rows) * 100, 1)


def _pending_by_material():

    rows = store.select(ORDERS, {
        "select": "material_id,quantity",
        "status": "in.(발주대기,진행중)",
    })

    pending = {}

    for r in rows:
        pending[r["material_id"]] = (
            pending.get(r["material_id"], 0) + r["quantity"]
        )

    return pending


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

    rows = store.select(INVENTORY)
    pending_map = _pending_by_material()

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
        pending = pending_map.get(row["material_id"], 0)

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
