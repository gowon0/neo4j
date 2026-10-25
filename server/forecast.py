"""자재별 수요예측.

후보 모델을 같은 조건으로 백테스트해 자재별 최적 모델을 고르고,
선택 모델의 백테스트 오차로 예측 구간(80%)을 만든다.

후보 모델
- trend_seasonal : 선형 추세 × 월별 계절지수
- holt_winters   : 홀트-윈터스(곱셈 계절, 감쇠 추세)
- seasonal_naive : 작년 같은 달 × 최근 성장률
- lgbm_base      : LightGBM, 수요 이력 기반 피처만 사용
- lgbm_exog      : LightGBM, 위 피처 + 외생변수(원자재 가격·프로젝트·전력 판매량)

검증: 학습 30개월·36개월 두 시점에서 향후 12개월을 각각 예측해 평균 MAPE로 비교한다.
(두 구간은 6개월이 겹치는 롤링 백테스트이며, 자료가 48개월뿐이라 불확실성이 크다.)
"""

import threading
from collections import defaultdict
from datetime import date

import numpy as np

from server import store

try:
    import lightgbm as lgb

    HAS_LGBM = True
except Exception:  # 설치되지 않았거나 로드할 수 없는 환경
    lgb = None
    HAS_LGBM = False


HORIZON = 12
FOLD_TRAIN_ENDS = (30, 36)   # 학습에 쓰는 개월 수. 각각 이후 12개월을 예측해 비교
MIN_ORIGIN = 17              # ML 학습 행의 최소 기준월(18개월 이상 이력 필요)
ML_MIN_GAIN = 0.03           # ML이 통계 모델보다 평균 MAPE가 3%(상대) 이상 낮아야 채택
INTERVAL_PCT = (10, 90)      # 80% 예측 구간

LABELS = {
    "trend_seasonal": "추세×계절지수",
    "holt_winters": "홀트-윈터스",
    "seasonal_naive": "계절 나이브",
    "lgbm_base": "LightGBM (이력)",
    "lgbm_exog": "LightGBM (이력+외생변수)",
}
STAT_KEYS = ("trend_seasonal", "holt_winters", "seasonal_naive")
ML_KEYS = ("lgbm_base", "lgbm_exog")

# 자재별 가격 영향을 받는 원자재.
# 개폐기·변압기는 지식그래프의 원가영향 관계를 따르고, 나머지는 업무 상식에 따른 가정이다.
MATERIAL_INPUTS = {
    "개폐기": ["구리", "알루미늄"],
    "변압기": ["철광석", "아연", "니켈"],
    "차단기": ["구리", "니켈"],
    "전력케이블": ["구리", "알루미늄"],
    "피뢰기": ["아연"],
    "단로기": ["구리", "알루미늄"],
    "전력퓨즈": ["구리", "아연"],
    "배전반": ["철광석", "구리"],
}

_lock = threading.Lock()
_cache = {"key": None, "value": None}


# ------------------------------------------------------------
# 날짜 유틸
# ------------------------------------------------------------

def _parse_month(text):

    year, month = text[:7].split("-")

    return date(int(year), int(month), 1)


def _add_months(d, n):

    index = d.year * 12 + (d.month - 1) + n

    return date(index // 12, index % 12 + 1, 1)


# ------------------------------------------------------------
# 통계 모델
# ------------------------------------------------------------

def _ts_forecast(y, moy, horizon=HORIZON):
    """선형 추세 × 월별 계절지수. moy: 학습 구간 각 월의 달력 월(1~12)."""

    y = np.asarray(y, dtype=float)
    n = len(y)
    t = np.arange(n)

    slope, intercept = np.polyfit(t, y, 1)
    trend = intercept + slope * t

    ratios = defaultdict(list)

    for month, actual, base in zip(moy, y, trend):
        if base > 0:
            ratios[month].append(actual / base)

    seasonal = {
        m: float(np.mean(ratios[m])) if ratios[m] else 1.0
        for m in range(1, 13)
    }
    norm = np.mean(list(seasonal.values())) or 1.0
    seasonal = {m: v / norm for m, v in seasonal.items()}

    out = []

    for h in range(1, horizon + 1):
        month = (moy[-1] - 1 + h) % 12 + 1
        out.append(max(0.0, (intercept + slope * (n - 1 + h)) * seasonal[month]))

    return np.array(out)


_HW_GRID = [
    (a, b, g)
    for a in (0.1, 0.3, 0.5)
    for b in (0.0, 0.05, 0.15)
    for g in (0.1, 0.3, 0.5)
]


def _hw_run(y, alpha, beta, gamma, m=12):

    n = len(y)
    level = y[:m].mean()
    trend = (y[m:2 * m].mean() - y[:m].mean()) / m if n >= 2 * m else 0.0
    season = list(y[:m] / level)
    sse = 0.0

    for t in range(n):
        i = t % m
        pred = (level + trend) * season[i]

        if t >= m:
            sse += (y[t] - pred) ** 2

        new_level = alpha * (y[t] / season[i]) + (1 - alpha) * (level + trend)
        trend = beta * (new_level - level) + (1 - beta) * trend
        season[i] = gamma * (y[t] / new_level) + (1 - gamma) * season[i]
        level = new_level

    return sse, level, trend, season


def _hw_forecast(y, moy, horizon=HORIZON, phi=0.95):
    """곱셈 계절 + 감쇠 추세. 모수는 학습 구간의 1단계 예측오차(SSE)로 격자 탐색."""

    y = np.asarray(y, dtype=float)
    n = len(y)
    m = 12

    if n < 2 * m or y.min() <= 0:
        return _ts_forecast(y, moy, horizon)

    best = min(
        (_hw_run(y, *params) for params in _HW_GRID),
        key=lambda r: r[0],
    )
    _, level, trend, season = best

    out = []
    damp = 0.0

    for h in range(1, horizon + 1):
        damp += phi ** h
        out.append(max(0.0, (level + trend * damp) * season[(n + h - 1) % m]))

    return np.array(out)


def _snaive_forecast(y, moy, horizon=HORIZON):
    """작년 같은 달 값 × 최근 12개월 성장률(0.85~1.15로 제한)."""

    y = np.asarray(y, dtype=float)
    n = len(y)
    m = 12

    growth = 1.0

    if n >= 2 * m and y[-2 * m:-m].mean() > 0:
        growth = float(np.clip(y[-m:].mean() / y[-2 * m:-m].mean(), 0.85, 1.15))

    return np.array([y[-m + (h - 1) % m] * growth for h in range(1, horizon + 1)])


STAT_MODELS = {
    "trend_seasonal": _ts_forecast,
    "holt_winters": _hw_forecast,
    "seasonal_naive": _snaive_forecast,
}


# ------------------------------------------------------------
# 입력 데이터
# ------------------------------------------------------------

def _safe_table(name):

    try:
        return store.get_table(name)
    except Exception:
        return []


def _dev(arr, k=12):
    """각 시점의 값 - 직전 k개월(자기 포함) 평균. 자료가 모자라면 NaN."""

    out = np.full(len(arr), np.nan)

    for o in range(k - 1, len(arr)):
        seg = arr[o - k + 1:o + 1]

        if not np.isnan(seg).any():
            out[o] = arr[o] - seg.mean()

    return out


def _chg(arr, k=3):

    out = np.full(len(arr), np.nan)
    out[k:] = arr[k:] - arr[:-k]

    return out


def _build_context():
    """월 목록, 자재별 수요, 외생변수 파생값을 한 번에 만든다."""

    materials = {m["material_id"]: m for m in store.get_table("materials")}
    rows = store.get_table("demand_history")

    by_mid = defaultdict(dict)

    for r in rows:
        by_mid[r["material_id"]][_parse_month(r["month"])] = r["demand_quantity"]

    months = sorted({d for series in by_mid.values() for d in series})
    mids = [mid for mid in sorted(by_mid) if mid in materials]

    y = {
        mid: np.array([by_mid[mid].get(d, np.nan) for d in months], dtype=float)
        for mid in mids
    }

    index = {d: i for i, d in enumerate(months)}
    n = len(months)

    def monthly(table, field, agg=sum):
        acc = defaultdict(list)

        for r in _safe_table(table):
            d = _parse_month(r["month"])

            if d in index and r.get(field) is not None:
                acc[d].append(float(r[field]))

        arr = np.full(n, np.nan)

        for d, vals in acc.items():
            arr[index[d]] = agg(vals)

        return arr

    # 원자재 가격 (로그)
    prices = {}
    status = set()

    for r in _safe_table("raw_material_prices"):
        d = _parse_month(r["month"])
        status.add(r.get("data_status"))

        if d in index:
            prices.setdefault(r["material_name"], np.full(n, np.nan))[index[d]] = np.log(r["price"])

    projects = np.log(np.where(monthly("project_monthly_stats", "project_count", sum) > 0,
                               monthly("project_monthly_stats", "project_count", sum), np.nan))
    scale = monthly("project_monthly_stats", "total_project_scale_m2", sum)
    scale = np.log(np.where(scale > 0, scale, np.nan))
    elec = monthly("electricity_usage", "sales_mwh", sum)
    elec = np.log(np.where(elec > 0, elec, np.nan))

    for table in ("project_monthly_stats", "electricity_usage"):
        status |= {r.get("data_status") for r in _safe_table(table)}

    exog = {
        "price_dev": {},
        "price_chg3": {},
        "proj_dev": _dev(projects),
        "proj_chg3": _chg(projects),
        "scale_dev": _dev(scale),
        "elec_dev": _dev(elec),
    }

    for mid in mids:
        names = [p for p in MATERIAL_INPUTS.get(materials[mid]["material_name"], []) if p in prices]

        if names:
            exog["price_dev"][mid] = np.nanmean([_dev(prices[p]) for p in names], axis=0)
            exog["price_chg3"][mid] = np.nanmean([_chg(prices[p]) for p in names], axis=0)
        else:
            exog["price_dev"][mid] = np.full(n, np.nan)
            exog["price_chg3"][mid] = np.full(n, np.nan)

    return {
        "materials": materials,
        "mids": mids,
        "months": months,
        "moy": np.array([d.month for d in months]),
        "y": y,
        "exog": exog,
        "has_exog": bool(prices) and not np.isnan(projects).all(),
        "linked": "synthetic_linked" in status,
    }


# ------------------------------------------------------------
# LightGBM
# ------------------------------------------------------------

def _features(ctx, mid, y, o, h, level, ts_h, use_exog):

    moy_t = (ctx["moy"][o] - 1 + h) % 12 + 1
    last_year = y[o + h - 12] if o + h - 12 >= 0 else np.nan
    growth = (
        y[o - 11:o + 1].mean() / y[o - 23:o - 11].mean()
        if o >= 23 and y[o - 23:o - 11].mean() > 0 else np.nan
    )

    f = [
        h,
        ts_h / level,
        np.sin(2 * np.pi * moy_t / 12),
        np.cos(2 * np.pi * moy_t / 12),
        y[o] / level,
        y[o - 2:o + 1].mean() / level,
        last_year / level,
        growth,
    ]

    if use_exog:
        ex = ctx["exog"]
        f += [
            ex["price_dev"][mid][o],
            ex["price_chg3"][mid][o],
            ex["proj_dev"][o],
            ex["proj_chg3"][o],
            ex["scale_dev"][o],
            ex["elec_dev"][o],
        ]

    return f


def _ml_forecast(ctx, train_end, use_exog):
    """train_end개월까지의 자료로 학습해 모든 자재의 이후 12개월을 예측한다.

    모든 자재를 한 모델로 학습하고(목표는 최근 12개월 평균 대비 비율),
    기준월마다 1~12개월 뒤를 직접 예측한다. 통계 모델 예측을 피처로 함께 쓴다.
    """

    if not HAS_LGBM:
        return None

    X, target = [], []

    for mid in ctx["mids"]:
        y = ctx["y"][mid][:train_end]

        for o in range(MIN_ORIGIN, train_end - 1):
            level = y[o - 11:o + 1].mean()

            if level <= 0:
                continue

            ts = _ts_forecast(y[:o + 1], ctx["moy"][:o + 1])

            for h in range(1, HORIZON + 1):
                if o + h >= train_end:
                    break

                X.append(_features(ctx, mid, y, o, h, level, ts[h - 1], use_exog))
                target.append(y[o + h] / level)

    if len(X) < 100:
        return None

    # scikit-learn 없이 쓸 수 있는 기본 API 사용 (서버 설치 용량 절약)
    model = lgb.train(
        {
            "objective": "regression",
            "learning_rate": 0.04,
            "num_leaves": 7,
            "min_data_in_leaf": 20,
            "bagging_fraction": 0.8,
            "bagging_freq": 1,
            "feature_fraction": 0.8,
            "lambda_l2": 2.0,
            "seed": 7,
            "num_threads": 1,
            "verbosity": -1,
        },
        lgb.Dataset(np.array(X, dtype=float), label=np.array(target, dtype=float)),
        num_boost_round=200,
    )

    out = {}

    for mid in ctx["mids"]:
        y = ctx["y"][mid][:train_end]
        o = train_end - 1
        level = y[o - 11:o + 1].mean()
        ts = _ts_forecast(y, ctx["moy"][:train_end])
        rows = [
            _features(ctx, mid, y, o, h, level, ts[h - 1], use_exog)
            for h in range(1, HORIZON + 1)
        ]
        out[mid] = np.maximum(0.0, model.predict(np.array(rows, dtype=float)) * level)

    return out


# ------------------------------------------------------------
# 백테스트 · 모델 선택
# ------------------------------------------------------------

def _mape(actual, pred):

    mask = actual > 0

    if not mask.any():
        return None

    return float(np.mean(np.abs(actual[mask] - pred[mask]) / actual[mask]))


def _compute():

    ctx = _build_context()
    n = len(ctx["months"])
    mids = ctx["mids"]

    # key -> mid -> [fold별 예측]
    folds = {}

    for te in FOLD_TRAIN_ENDS:
        if te + HORIZON > n:
            continue

        preds = {key: {} for key in STAT_KEYS}

        for mid in mids:
            y = ctx["y"][mid][:te]
            for key, fn in STAT_MODELS.items():
                preds[key][mid] = fn(y, ctx["moy"][:te])

        if HAS_LGBM:
            for key, use_exog in (("lgbm_base", False), ("lgbm_exog", True)):
                if key == "lgbm_exog" and not ctx["has_exog"]:
                    continue
                result = _ml_forecast(ctx, te, use_exog)
                if result:
                    preds[key] = result

        folds[te] = preds

    # 최종 예측 (전체 자료 학습)
    final = {}

    for mid in mids:
        y = ctx["y"][mid]
        for key, fn in STAT_MODELS.items():
            final.setdefault(key, {})[mid] = fn(y, ctx["moy"])

    if HAS_LGBM:
        for key, use_exog in (("lgbm_base", False), ("lgbm_exog", True)):
            if key == "lgbm_exog" and not ctx["has_exog"]:
                continue
            result = _ml_forecast(ctx, n, use_exog)
            if result:
                final[key] = result

    last_month = ctx["months"][-1]
    future = [_add_months(last_month, h) for h in range(1, HORIZON + 1)]

    output = {}

    for mid in mids:
        meta = ctx["materials"][mid]
        y_all = ctx["y"][mid]

        candidates = []
        rel_errors = {}

        for key in STAT_KEYS + ML_KEYS:
            mapes, errs = [], []

            for te, preds in folds.items():
                if key not in preds:
                    continue

                actual = y_all[te:te + HORIZON]
                pred = preds[key][mid]
                mapes.append(_mape(actual, pred))
                ok = actual > 0
                errs.extend((actual[ok] / np.maximum(pred[ok], 1e-9) - 1).tolist())

            if not mapes or key not in final or None in mapes:
                continue

            by_fold = dict(zip([te for te in folds if key in folds[te]], mapes))

            candidates.append({
                "key": key,
                "label": LABELS[key],
                "mape_a": by_fold.get(FOLD_TRAIN_ENDS[0]),
                "mape_b": by_fold.get(FOLD_TRAIN_ENDS[1]),
                "mape_avg": float(np.mean(mapes)),
            })
            rel_errors[key] = errs

        stat_best = min(
            (c for c in candidates if c["key"] in STAT_KEYS),
            key=lambda c: c["mape_avg"],
        )
        ml_by_key = {c["key"]: c for c in candidates if c["key"] in ML_KEYS}
        ml_best = ml_by_key.get("lgbm_base")
        exog = ml_by_key.get("lgbm_exog")

        # 외생변수 모델은 이력만 쓰는 모델보다 확실히(3%) 좋을 때만 채택 (우연한 차이 배제)
        if exog and (ml_best is None or exog["mape_avg"] <= ml_best["mape_avg"] * (1 - ML_MIN_GAIN)):
            ml_best = exog

        chosen = stat_best

        if ml_best and ml_best["mape_avg"] <= stat_best["mape_avg"] * (1 - ML_MIN_GAIN):
            chosen = ml_best

        for c in candidates:
            c["selected"] = c["key"] == chosen["key"]

        point = np.asarray(final[chosen["key"]][mid], dtype=float)
        recent = y_all[-12:].mean()
        point = np.clip(point, 0.3 * recent, 3.0 * recent)

        errs = np.array(rel_errors[chosen["key"]])
        q_low, q_high = np.percentile(errs, INTERVAL_PCT)
        q_low, q_high = min(q_low, -0.01), max(q_high, 0.01)

        history = [
            {"month": d.strftime("%Y-%m"), "value": int(v)}
            for d, v in zip(ctx["months"], y_all)
        ]
        forecast = [
            {
                "month": d.strftime("%Y-%m"),
                "value": int(round(v)),
                "low": int(round(v * (1 + q_low))),
                "high": int(round(v * (1 + q_high))),
            }
            for d, v in zip(future, point)
        ]

        output[mid] = {
            "material_id": mid,
            "name": meta["material_name"],
            "category": meta["category"],
            "unit": meta["unit"],
            "history": history,
            "forecast": forecast,
            "accuracy": round(max(0.0, 100 - chosen["mape_avg"] * 100), 1),
            "accuracy_2025": (
                round(max(0.0, 100 - chosen["mape_b"] * 100), 1)
                if chosen["mape_b"] is not None else None
            ),
            "model": {"key": chosen["key"], "label": chosen["label"]},
            "candidates": candidates,
        }

    meta = {
        "ml_available": HAS_LGBM,
        "exog_used": ctx["has_exog"],
        "exog_linked": ctx["linked"],
        "folds": [
            {"train_months": te, "test_from": ctx["months"][te].strftime("%Y-%m"),
             "test_to": ctx["months"][min(te + HORIZON, n) - 1].strftime("%Y-%m")}
            for te in folds
        ],
        "interval": f"{INTERVAL_PCT[1] - INTERVAL_PCT[0]}%",
        "ml_min_gain_pct": int(ML_MIN_GAIN * 100),
    }

    return {"materials": output, "meta": meta}


def _fingerprint():

    key = []

    for table, field in (
        ("demand_history", "demand_quantity"),
        ("raw_material_prices", "price"),
        ("project_monthly_stats", "project_count"),
        ("electricity_usage", "sales_mwh"),
    ):
        rows = _safe_table(table)
        key.append((
            table, len(rows),
            max((r["month"] for r in rows), default=""),
            round(sum(float(r.get(field) or 0) for r in rows), 2),
        ))

    return tuple(key)


def _result():

    key = _fingerprint()

    with _lock:
        if _cache["key"] != key:
            _cache["value"] = _compute()
            _cache["key"] = key

        return _cache["value"]


def forecast_all():
    """{material_id: {...}} 반환. 입력 데이터가 같으면 계산 결과를 재사용한다."""

    return _result()["materials"]


def forecast_meta():

    return _result()["meta"]


# ------------------------------------------------------------
# 조회 보조
# ------------------------------------------------------------

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


def period_sum(points, start, end, field="value"):

    return sum(
        p[field]
        for p in points
        if start <= p["month"] <= end
    )


def same_period_last_year(start, end):

    def shift(text):
        year, month = text.split("-")
        return f"{int(year) - 1}-{month}"

    return shift(start), shift(end)
