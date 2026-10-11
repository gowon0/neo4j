"""자재별 수요예측 (선형 추세 + 월별 계절지수).

Supabase demand_history(월별 수요량)를 입력으로 향후 12개월을 예측하고,
최근 12개월을 숨기고 예측해 보는 백테스트로 정확도를 계산한다.
"""

from collections import defaultdict
from datetime import date

import numpy as np

from server import store


HORIZON = 12


def _parse_month(text):

    year, month = text[:7].split("-")

    return date(int(year), int(month), 1)


def _add_months(d, n):

    index = d.year * 12 + (d.month - 1) + n

    return date(index // 12, index % 12 + 1, 1)


def _fit_predict(values, months, horizon):
    """values/months: 학습 구간. 이후 horizon개월 예측값 반환."""

    y = np.asarray(values, dtype=float)
    n = len(y)
    t = np.arange(n)

    slope, intercept = np.polyfit(t, y, 1)
    trend = intercept + slope * t

    ratios = defaultdict(list)

    for month, actual, base in zip(months, y, trend):
        if base > 0:
            ratios[month.month].append(actual / base)

    seasonal = {
        m: float(np.mean(ratios[m])) if ratios[m] else 1.0
        for m in range(1, 13)
    }
    mean_seasonal = np.mean(list(seasonal.values())) or 1.0
    seasonal = {m: v / mean_seasonal for m, v in seasonal.items()}

    last = months[-1]
    forecast = []

    for h in range(1, horizon + 1):

        month = _add_months(last, h)
        value = (intercept + slope * (n - 1 + h)) * seasonal[month.month]

        forecast.append((month, max(0, int(round(value)))))

    return forecast


def _accuracy(values, months):

    if len(values) < 24:
        return None

    train_v, train_m = values[:-12], months[:-12]
    actual = np.asarray(values[-12:], dtype=float)

    predicted = np.asarray(
        [v for _, v in _fit_predict(train_v, train_m, 12)],
        dtype=float,
    )

    mask = actual > 0

    if not mask.any():
        return None

    mape = np.mean(
        np.abs(actual[mask] - predicted[mask]) / actual[mask]
    )

    return round(max(0.0, 100 - mape * 100), 1)


def forecast_all():
    """{material_id: {...}} 반환."""

    materials = {
        m["material_id"]: m
        for m in store.get_table("materials")
    }

    series = defaultdict(dict)

    for row in store.get_table("demand_history"):
        series[row["material_id"]][_parse_month(row["month"])] = (
            row["demand_quantity"]
        )

    result = {}

    for material_id, by_month in series.items():

        if material_id not in materials:
            continue

        months = sorted(by_month)
        values = [by_month[m] for m in months]

        forecast = _fit_predict(values, months, HORIZON)

        material = materials[material_id]

        result[material_id] = {
            "material_id": material_id,
            "name": material["material_name"],
            "category": material["category"],
            "unit": material["unit"],
            "history": [
                {"month": m.strftime("%Y-%m"), "value": v}
                for m, v in zip(months, values)
            ],
            "forecast": [
                {"month": m.strftime("%Y-%m"), "value": v}
                for m, v in forecast
            ],
            "accuracy": _accuracy(values, months),
        }

    return result


def materials_list():

    return [
        {
            "material_id": m["material_id"],
            "name": m["material_name"],
            "category": m["category"],
            "unit": m["unit"],
        }
        for m in sorted(
            store.get_table("materials"),
            key=lambda m: m["material_id"],
        )
    ]


def period_sum(points, start, end):

    return sum(
        p["value"]
        for p in points
        if start <= p["month"] <= end
    )


def same_period_last_year(start, end):

    def shift(text):
        year, month = text.split("-")
        return f"{int(year) - 1}-{month}"

    return shift(start), shift(end)
