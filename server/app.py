"""기자재 AI 수요예측 시스템 — FastAPI 백엔드.

실행: uvicorn server.app:app --port 8000
"""

import os
import threading
from contextlib import asynccontextmanager
from datetime import date

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from config.settings import (
    APP_ADMIN_ID,
    WARNING_THRESHOLD,
    DANGER_THRESHOLD,
    VERY_DANGER_THRESHOLD,
)
from server import auth, erp, export, forecast as fc, risk, simulation, store


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "frontend", "dist")


def _warm_up():

    try:
        fc.forecast_all()
    except Exception as error:
        print(f"[startup] 수요예측 사전 계산 실패: {error}")

    try:
        risk.get_risks()
    except Exception as error:
        print(f"[startup] 위험 분석 사전 계산 실패: {error}")


@asynccontextmanager
async def lifespan(app):

    threading.Thread(target=_warm_up, daemon=True).start()

    yield


app = FastAPI(title="기자재 AI 수요예측 시스템", lifespan=lifespan)


@app.exception_handler(store.StoreError)
async def store_error_handler(request, error):

    return JSONResponse(status_code=503, content={"detail": str(error)})


def _forecasts():

    return fc.forecast_all()


def _month_range(forecasts):

    first = next(iter(forecasts.values()), None)

    return [p["month"] for p in first["forecast"]] if first else []


# ------------------------------------------------------------
# 인증
# ------------------------------------------------------------

class LoginBody(BaseModel):
    id: str
    password: str


@app.post("/api/auth/login")
def login(body: LoginBody):

    if not auth.verify_credentials(body.id, body.password):
        raise HTTPException(
            status_code=401,
            detail="아이디 또는 비밀번호가 올바르지 않습니다.",
        )

    return {"token": auth.issue_token(body.id), "name": body.id}


@app.get("/api/me")
def me(user: str = Depends(auth.current_user)):

    return {"id": user, "name": user}


# ------------------------------------------------------------
# 기준 정보
# ------------------------------------------------------------

@app.get("/api/materials")
def materials(user: str = Depends(auth.current_user)):

    forecasts = _forecasts()

    return {
        "materials": fc.materials_list(),
        "months": _month_range(forecasts),
        "today": date.today().isoformat(),
    }


# ------------------------------------------------------------
# 대시보드
# ------------------------------------------------------------

@app.get("/api/dashboard")
def dashboard(user: str = Depends(auth.current_user)):

    forecasts = _forecasts()
    inventory = erp.inventory_view(forecasts)

    months = _month_range(forecasts)
    forecast_year = months[0][:4] if months else str(date.today().year)
    prev_year = str(int(forecast_year) - 1)

    forecast_total = 0
    prev_total = 0
    monthly = {}

    for data in forecasts.values():

        for p in data["history"]:
            if p["month"].startswith(prev_year):
                prev_total += p["value"]
            m = monthly.setdefault(p["month"], {"actual": 0, "forecast": None})
            m["actual"] += p["value"]

        for p in data["forecast"]:
            if p["month"].startswith(forecast_year):
                forecast_total += p["value"]
            m = monthly.setdefault(p["month"], {"actual": None, "forecast": 0})
            m["forecast"] = (m["forecast"] or 0) + p["value"]

    demand_delta = (
        round((forecast_total - prev_total) / prev_total * 100, 1)
        if prev_total else None
    )

    ordered_months = sorted(monthly)
    first_forecast = months[0] if months else None

    trend = []

    for month in ordered_months[-(24 + len(months)):]:

        point = {
            "month": month,
            "actual": monthly[month]["actual"],
            "forecast": monthly[month]["forecast"],
        }

        trend.append(point)

    # 실측-예측 선이 이어지도록 마지막 실측 지점에 예측 시작값 부여
    for i, point in enumerate(trend):
        if point["month"] == first_forecast and i > 0:
            trend[i - 1]["forecast"] = trend[i - 1]["actual"]

    recent = erp.fulfillment_rate(60, 0)
    before = erp.fulfillment_rate(120, 60)
    overall = erp.fulfillment_rate(3650, 0)

    fulfill_value = recent if recent is not None else overall
    fulfill_delta = (
        round(recent - before, 1)
        if recent is not None and before is not None else None
    )

    stock_total = sum(i["current_stock"] for i in inventory)
    safety_total = sum(i["safety_stock"] for i in inventory)
    stock_delta = (
        round((stock_total - safety_total) / safety_total * 100, 1)
        if safety_total else None
    )

    critical = [i for i in inventory if i["days_left"] is not None]
    critical.sort(key=lambda i: i["days_left"])

    return {
        "kpis": [
            {
                "key": "demand",
                "label": f"{forecast_year}년 예측 수요",
                "value": forecast_total,
                "unit": "건",
                "delta": demand_delta,
                "note": f"{prev_year}년 실적 대비",
            },
            {
                "key": "fulfillment",
                "label": "발주 이행률",
                "value": fulfill_value,
                "unit": "%",
                "delta": fulfill_delta,
                "note": "최근 60일 납기 기준",
            },
            {
                "key": "stock",
                "label": "재고 현황",
                "value": stock_total,
                "unit": "건",
                "delta": stock_delta,
                "note": "적정 재고 대비",
            },
            {
                "key": "days",
                "label": "예상 재고 소진일",
                "value": critical[0]["days_left"] if critical else None,
                "unit": "일",
                "delta": None,
                "note": (
                    f"{critical[0]['name']} 기준" if critical else ""
                ),
            },
        ],
        "trend": trend,
        "shortage_items": [
            i for i in inventory if i["status"] != "여유"
        ],
    }


@app.get("/api/risks")
def risks(refresh: bool = False, user: str = Depends(auth.current_user)):

    try:
        return risk.get_risks(force=refresh)
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail=(
                "지식그래프 위험 분석을 불러오지 못했습니다: "
                f"{type(error).__name__}"
            ),
        )


# ------------------------------------------------------------
# 수요예측
# ------------------------------------------------------------

@app.get("/api/forecast")
def forecast(
    material_id: int | None = None,
    start: str | None = None,
    end: str | None = None,
    user: str = Depends(auth.current_user),
):

    forecasts = _forecasts()
    months = _month_range(forecasts)

    start = start or (months[0] if months else "")
    end = end or (months[-1] if months else "")

    prev_start, prev_end = fc.same_period_last_year(start, end)

    rows = []

    for data in forecasts.values():

        if material_id and data["material_id"] != material_id:
            continue

        demand = fc.period_sum(data["forecast"], start, end)
        prev = fc.period_sum(data["history"], prev_start, prev_end)

        rows.append({
            "material_id": data["material_id"],
            "name": data["name"],
            "unit": data["unit"],
            "demand": demand,
            "previous": prev,
            "change": (
                round((demand - prev) / prev * 100, 1) if prev else None
            ),
            "low": fc.period_sum(data["forecast"], start, end, "low"),
            "high": fc.period_sum(data["forecast"], start, end, "high"),
            "accuracy": data["accuracy"],
            "accuracy_2025": data["accuracy_2025"],
            "model": data["model"]["label"],
            "model_key": data["model"]["key"],
        })

    rows.sort(key=lambda r: r["material_id"])

    return {
        "start": start,
        "end": end,
        "months": months,
        "rows": rows,
        "meta": fc.forecast_meta(),
    }


@app.get("/api/forecast/models")
def forecast_models(
    material_id: int | None = None,
    user: str = Depends(auth.current_user),
):
    """자재별 후보 모델 백테스트 비교와 선택 결과."""

    forecasts = _forecasts()

    if material_id is not None and material_id not in forecasts:
        raise HTTPException(404, "자재를 찾을 수 없습니다.")

    items = [
        {
            "material_id": d["material_id"],
            "name": d["name"],
            "model": d["model"],
            "accuracy": d["accuracy"],
            "candidates": d["candidates"],
        }
        for d in forecasts.values()
        if material_id in (None, d["material_id"])
    ]

    return {"meta": fc.forecast_meta(), "materials": items}


@app.get("/api/forecast/series")
def forecast_series(
    material_id: int | None = None,
    user: str = Depends(auth.current_user),
):

    forecasts = _forecasts()

    if material_id is None:
        selected = list(forecasts.values())
        name = "전체"
    else:
        data = forecasts.get(material_id)
        if not data:
            raise HTTPException(404, "자재를 찾을 수 없습니다.")
        selected = [data]
        name = data["name"]

    monthly = {}

    for data in selected:

        for p in data["history"][-24:]:
            m = monthly.setdefault(p["month"], {"actual": 0, "forecast": None})
            m["actual"] += p["value"]

        for p in data["forecast"]:
            m = monthly.setdefault(
                p["month"],
                {"actual": None, "forecast": 0, "low": 0, "high": 0},
            )
            m["forecast"] = (m["forecast"] or 0) + p["value"]
            m["low"] += p["low"]
            m["high"] += p["high"]

    points = [
        {"month": k, **monthly[k]}
        for k in sorted(monthly)
    ]

    first_forecast = next(
        (i for i, p in enumerate(points) if p["actual"] is None), None
    )

    if first_forecast:
        last = points[first_forecast - 1]
        last["forecast"] = last["actual"]
        last["low"] = last["actual"]
        last["high"] = last["actual"]

    for p in points:
        # 예측 구간 밴드용 [하한, 상한] (실적 구간은 없음)
        p["band"] = (
            [p["low"], p["high"]] if p.get("low") is not None and p["forecast"] is not None else None
        )

    model = (
        forecasts[material_id]["model"]["label"]
        if material_id is not None
        else "자재별 최적 모델의 합계"
    )

    return {"name": name, "model": model, "points": points}


# ------------------------------------------------------------
# 발주관리
# ------------------------------------------------------------

@app.get("/api/orders")
def orders(
    material_id: int | None = None,
    status: str | None = None,
    user: str = Depends(auth.current_user),
):

    forecasts = _forecasts()

    rows = erp.list_orders(material_id, status)

    for row in rows:
        data = forecasts.get(row["material_id"])
        row["name"] = data["name"] if data else str(row["material_id"])
        row["unit"] = data["unit"] if data else ""

    return {"statuses": erp.ORDER_STATUSES, "rows": rows}


class OrderBody(BaseModel):
    material_id: int
    quantity: int = Field(gt=0, le=10_000_000)
    due_date: str


@app.post("/api/orders")
def create_order(body: OrderBody, user: str = Depends(auth.current_user)):

    forecasts = _forecasts()

    if body.material_id not in forecasts:
        raise HTTPException(404, "자재를 찾을 수 없습니다.")

    try:
        due = date.fromisoformat(body.due_date)
    except ValueError:
        raise HTTPException(422, "납기일 형식이 올바르지 않습니다.")

    if due < date.today():
        raise HTTPException(422, "납기일은 오늘 이후여야 합니다.")

    po_no = erp.create_order(body.material_id, body.quantity, due.isoformat())

    return {"po_no": po_no}


class StatusBody(BaseModel):
    status: str


@app.patch("/api/orders/{po_no}")
def update_order(
    po_no: str,
    body: StatusBody,
    user: str = Depends(auth.current_user),
):

    if body.status not in erp.ORDER_STATUSES:
        raise HTTPException(422, "허용되지 않는 상태입니다.")

    if not erp.update_order_status(po_no, body.status):
        raise HTTPException(404, "발주번호를 찾을 수 없습니다.")

    return {"po_no": po_no, "status": body.status}


# ------------------------------------------------------------
# 재고현황
# ------------------------------------------------------------

@app.get("/api/inventory")
def inventory(
    material_id: int | None = None,
    status: str | None = None,
    user: str = Depends(auth.current_user),
):

    forecasts = _forecasts()

    return {
        "rows": erp.inventory_view(forecasts, material_id, status),
    }


# ------------------------------------------------------------
# 시뮬레이션
# ------------------------------------------------------------

class SimulationBody(BaseModel):
    material_id: int | None = None
    start: str
    end: str
    demand_change: float = Field(default=0, ge=-50, le=100)
    delay_days: int = Field(default=0, ge=0, le=120)


@app.get("/api/simulation/scenarios")
def scenarios(user: str = Depends(auth.current_user)):

    return {
        "scenarios": [
            {"key": k, **v} for k, v in simulation.SCENARIOS.items()
        ]
    }


@app.post("/api/simulation")
def run_simulation(
    body: SimulationBody,
    user: str = Depends(auth.current_user),
):

    forecasts = _forecasts()
    inventory_rows = erp.inventory_view(forecasts)

    return simulation.simulate(
        inventory_rows,
        forecasts,
        body.material_id,
        body.start,
        body.end,
        body.demand_change,
        body.delay_days,
    )


# ------------------------------------------------------------
# 내보내기 (CSV / 엑셀)
# ------------------------------------------------------------

def _material_name(forecasts, material_id):

    if material_id is None:
        return "전체"

    data = forecasts.get(material_id)

    return data["name"] if data else str(material_id)


@app.get("/api/export/orders")
def export_orders(
    fmt: str = Query("csv", alias="format"),
    material_id: int | None = None,
    status: str | None = None,
    user: str = Depends(auth.current_user),
):

    export.check_format(fmt)
    forecasts = _forecasts()
    rows = erp.list_orders(material_id, status)

    for row in rows:
        data = forecasts.get(row["material_id"])
        row["name"] = data["name"] if data else str(row["material_id"])
        row["unit"] = data["unit"] if data else ""

    return export.respond("발주목록", fmt, export.orders_sheets(rows))


@app.get("/api/export/inventory")
def export_inventory(
    fmt: str = Query("csv", alias="format"),
    material_id: int | None = None,
    status: str | None = None,
    user: str = Depends(auth.current_user),
):

    export.check_format(fmt)
    rows = erp.inventory_view(_forecasts(), material_id, status)

    return export.respond("재고현황", fmt, export.inventory_sheets(rows))


@app.get("/api/export/forecast")
def export_forecast(
    fmt: str = Query("csv", alias="format"),
    material_id: int | None = None,
    start: str | None = None,
    end: str | None = None,
    user: str = Depends(auth.current_user),
):

    export.check_format(fmt)
    forecasts = _forecasts()
    months = _month_range(forecasts)

    start = start or (months[0] if months else "")
    end = end or (months[-1] if months else "")

    items = sorted(
        (d for d in forecasts.values() if material_id in (None, d["material_id"])),
        key=lambda d: d["material_id"],
    )

    return export.respond(
        "수요예측",
        fmt,
        export.forecast_sheets(items, start, end, fc.period_sum, fc.same_period_last_year),
    )


class SimulationExportBody(SimulationBody):
    format: str = "csv"
    compare: bool = False


@app.post("/api/export/simulation")
def export_simulation(
    body: SimulationExportBody,
    user: str = Depends(auth.current_user),
):

    export.check_format(body.format)
    forecasts = _forecasts()
    inventory_rows = erp.inventory_view(forecasts)
    name = _material_name(forecasts, body.material_id)

    if body.compare:
        rows = []

        for key, scenario in simulation.SCENARIOS.items():
            result = simulation.simulate(
                inventory_rows, forecasts, body.material_id, body.start, body.end,
                scenario["demand_change"], scenario["delay_days"],
            )
            rows.append({"key": key, **scenario, **result})

        return export.respond(
            "시나리오비교", body.format,
            export.scenarios_sheets(rows, name, body.start, body.end),
        )

    result = simulation.simulate(
        inventory_rows, forecasts, body.material_id, body.start, body.end,
        body.demand_change, body.delay_days,
    )

    return export.respond(
        "시뮬레이션", body.format,
        export.simulation_sheets(result, body.model_dump(), name),
    )


@app.get("/api/export/risks")
def export_risks(
    fmt: str = Query("csv", alias="format"),
    user: str = Depends(auth.current_user),
):

    export.check_format(fmt)

    try:
        data = risk.get_risks()
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail=f"지식그래프 위험 분석을 불러오지 못했습니다: {type(error).__name__}",
        )

    return export.respond("위험알림", fmt, export.risks_sheets(data))


# ------------------------------------------------------------
# 데이터 관리 / 설정
# ------------------------------------------------------------

@app.get("/api/data/status")
def data_status(user: str = Depends(auth.current_user)):

    return {"tables": store.table_status()}


@app.post("/api/data/refresh")
def data_refresh(user: str = Depends(auth.current_user)):

    store.refresh_all()
    risk.get_risks(force=False)

    return {"tables": store.table_status()}


@app.get("/api/settings")
def settings(user: str = Depends(auth.current_user)):

    return {
        "user": user,
        "admin_id": APP_ADMIN_ID,
        "thresholds": {
            "warning": WARNING_THRESHOLD,
            "danger": DANGER_THRESHOLD,
            "very_danger": VERY_DANGER_THRESHOLD,
        },
        "risk_cache_minutes": risk.CACHE_TTL_SECONDS // 60,
        "data_cache_minutes": store.CACHE_TTL_SECONDS // 60,
    }


# ------------------------------------------------------------
# 프론트엔드 정적 파일 (npm run build 이후)
# ------------------------------------------------------------

if os.path.isdir(DIST):

    app.mount(
        "/assets",
        StaticFiles(directory=os.path.join(DIST, "assets")),
        name="assets",
    )

    @app.get("/{path:path}")
    def spa(path: str):

        if path.startswith("api/"):
            raise HTTPException(404)

        candidate = os.path.realpath(os.path.join(DIST, path))
        inside = candidate.startswith(os.path.realpath(DIST) + os.sep)

        if path and inside and os.path.isfile(candidate):
            return FileResponse(candidate)

        return FileResponse(os.path.join(DIST, "index.html"))
