"""수요/납기 변동 시나리오 시뮬레이션.

월별로 '수요 + 목표 안전재고 - (현재고 + 입고예정)'만큼 발주하고,
납기 지연일수만큼 입고가 늦어진다고 가정해 결품을 계산한다.
"""

SCENARIOS = {
    "base": {"label": "기준", "demand_change": 0, "delay_days": 0},
    "demand_surge": {"label": "수요 급증", "demand_change": 20, "delay_days": 0},
    "supply_delay": {"label": "공급 지연", "demand_change": 0, "delay_days": 30},
    "combined": {"label": "복합 위험", "demand_change": 15, "delay_days": 30},
}


def simulate(inventory, forecasts, material_id, start, end,
             demand_change, delay_days):

    items = [
        i for i in inventory
        if material_id in (None, i["material_id"])
    ]

    shift = int(round(delay_days / 30))
    factor = 1 + demand_change / 100

    month_keys = None
    totals = {}

    min_days = None
    min_days_name = None

    for item in items:

        data = forecasts[item["material_id"]]

        points = [
            p for p in data["forecast"]
            if start <= p["month"] <= end
        ]

        if not points:
            continue

        if month_keys is None:
            month_keys = [p["month"] for p in points]
            totals = {
                m: {"demand": 0, "order": 0, "shortage": 0}
                for m in month_keys
            }

        stock = item["current_stock"]
        target = item["safety_stock"] * (1 + delay_days / 30)

        arrivals = [0] * (len(points) + shift + 1)

        for i, point in enumerate(points):

            demand = point["value"] * factor

            in_transit = sum(arrivals[i:])
            order = max(0, demand + target - (stock + in_transit))

            if i + shift < len(arrivals):
                arrivals[i + shift] += order

            available = stock + arrivals[i] - demand
            shortage = max(0, -available)
            stock = max(0, available)

            bucket = totals[point["month"]]
            bucket["demand"] += demand
            bucket["order"] += order
            bucket["shortage"] += shortage

        first_demand = points[0]["value"] * factor
        daily = first_demand / 30

        if daily > 0:

            days = round(item["current_stock"] / daily)

            if min_days is None or days < min_days:
                min_days = days
                min_days_name = item["name"]

    months = [
        {
            "month": m,
            "demand": round(v["demand"]),
            "order": round(v["order"]),
            "shortage": round(v["shortage"]),
        }
        for m, v in totals.items()
    ]

    return {
        "demand": sum(m["demand"] for m in months),
        "order": sum(m["order"] for m in months),
        "shortage": sum(m["shortage"] for m in months),
        "days_left": min_days,
        "days_left_material": min_days_name,
        "months": months,
    }
