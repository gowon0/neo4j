"""외생변수(원자재 가격·프로젝트 통계·전력 판매량)를 수요와 연관되도록 새로 만든다.

!! 이 데이터는 시연용 '가상 연관 데이터'다 !!
이미 확정된 수요 이력(demand_history)에서 계산한 '앞으로 6개월의 수요 변동'을 선행지표로
섞어 만들기 때문에, 이 데이터로 얻은 백테스트 정확도 향상은 실제 데이터에서의 성능을
의미하지 않는다. 만든 행에는 data_status = 'synthetic_linked'를 붙인다.

원래 값의 수준과 변동폭은 유지한다 (이동평균 추세 + 원래 노이즈의 절반 + 연관 신호).
연관 강도는 --snr 로 조절한다 (신호 / 남은 노이즈 비율, 1.0이면 상관계수 약 0.7).

사용:
  python -m scripts.generate_linked_exog --evaluate          # 효과만 로컬 평가 (DB 변경 없음)
  python -m scripts.generate_linked_exog --snr 1.0 --write   # supabase/*.sql 파일 생성

Supabase는 직접 수정하지 않는다. 생성된 SQL(백업 포함)을 SQL Editor에서 실행한다.
"""

import argparse
import json
import os
import time

import numpy as np

from server import forecast as fc
from server import store

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAPSHOT = os.path.join(ROOT, "data", "exog_original_snapshot.json")
OUT_DIR = os.path.join(ROOT, "supabase")

TABLES = ("raw_material_prices", "project_monthly_stats", "electricity_usage")
LEAD = 6          # 선행 개월 수: 지표가 앞으로 LEAD개월의 수요 변동을 반영 (--lead 로 변경)
STATUS = "synthetic_linked"
SEED = 20261025


# ------------------------------------------------------------
# 입력
# ------------------------------------------------------------

def load_originals():
    """처음 실행할 때 원본을 스냅샷으로 저장하고, 이후에는 항상 원본을 기준으로 만든다."""

    if os.path.exists(SNAPSHOT):
        return json.load(open(SNAPSHOT, encoding="utf-8"))

    data = {t: store.get_table(t, force=True) for t in TABLES}

    if any(r.get("data_status") == STATUS for rows in data.values() for r in rows):
        raise SystemExit("이미 연관 데이터로 바뀐 상태입니다. 원본 스냅샷이 없어 기준 데이터를 만들 수 없습니다.")

    os.makedirs(os.path.dirname(SNAPSHOT), exist_ok=True)
    json.dump(data, open(SNAPSHOT, "w", encoding="utf-8"), ensure_ascii=False)

    return data


def smooth(a, w=5):
    """중심 이동평균 (가장자리는 있는 값만 평균)."""

    half = w // 2
    out = np.empty(len(a))

    for i in range(len(a)):
        out[i] = np.mean(a[max(0, i - half):i + half + 1])

    return out


def standardize(a):

    s = np.std(a)

    return (a - np.mean(a)) / s if s > 1e-12 else np.zeros(len(a))


def demand_signal():
    """자재별 '앞으로 LEAD개월 수요 변동' 신호 f_m(t)와 공통 신호."""

    ctx = fc._build_context()
    n = len(ctx["months"])
    f = {}

    for mid in ctx["mids"]:
        y = ctx["y"][mid]
        t = np.arange(n)
        slope, intercept = np.polyfit(t, y, 1)
        ratio = y / (intercept + slope * t)
        seasonal = np.array([ratio[ctx["moy"] == m].mean() for m in range(1, 13)])
        z = np.log(ratio / seasonal[ctx["moy"] - 1])

        zz = np.concatenate([z, np.zeros(LEAD)])   # 미래는 알 수 없으므로 0
        f[mid] = np.array([zz[i + 1:i + 1 + LEAD].sum() / LEAD for i in range(n)])

    names = {mid: ctx["materials"][mid]["material_name"] for mid in ctx["mids"]}

    return ctx, f, names


# ------------------------------------------------------------
# 생성
# ------------------------------------------------------------

def generate(orig, snr):

    rng = np.random.default_rng(SEED)
    ctx, f, names = demand_signal()
    months = [d.strftime("%Y-%m") for d in ctx["months"]]
    index = {m: i for i, m in enumerate(months)}
    n = len(months)

    common = standardize(np.mean([f[m] for m in ctx["mids"]], axis=0))
    new = {}
    report = {}

    # --- 원자재 가격 --------------------------------------------------
    used_by = {}

    for mid, name in names.items():
        for raw in fc.MATERIAL_INPUTS.get(name, []):
            used_by.setdefault(raw, []).append(mid)

    rows = [dict(r) for r in orig["raw_material_prices"]]
    by_raw = {}

    for r in rows:
        by_raw.setdefault(r["material_name"], {})[r["month"][:7]] = r

    for raw, rmap in by_raw.items():
        lp = np.log(np.array([rmap[m]["price"] for m in months], dtype=float))
        base = smooth(lp)
        noise = 0.5 * (lp - base)
        sigma = max(np.std(noise), 0.01)
        signal = standardize(np.mean([f[mid] for mid in used_by.get(raw, [])], axis=0)) if raw in used_by else np.zeros(n)
        new_lp = base + noise + snr * sigma * signal

        for i, m in enumerate(months):
            rmap[m]["price"] = round(float(np.exp(new_lp[i])), 2)
            rmap[m]["data_status"] = STATUS

        report[f"가격_{raw}"] = round(float(np.corrcoef(new_lp - base, signal)[0, 1]), 2) if raw in used_by else None

    new["raw_material_prices"] = rows

    # --- 프로젝트 월별 통계 ------------------------------------------
    rows = [dict(r) for r in orig["project_monthly_stats"]]
    rmap = {r["month"][:7]: r for r in rows}
    cnt = np.array([rmap[m]["project_count"] for m in months], dtype=float)
    base = smooth(cnt)
    noise = 0.5 * (cnt - base)
    sigma = max(np.std(noise), 0.5)
    new_cnt = np.maximum(3, np.round(base + noise + snr * sigma * common))

    for i, m in enumerate(months):
        r = rmap[m]
        avg = float(r["avg_project_scale_m2"])
        r["project_count"] = int(new_cnt[i])
        r["total_project_scale_m2"] = int(round(new_cnt[i] * avg))
        r["avg_project_scale_m2"] = round(r["total_project_scale_m2"] / new_cnt[i], 1)
        r["data_status"] = STATUS

    new["project_monthly_stats"] = rows
    report["프로젝트수"] = round(float(np.corrcoef(new_cnt - base, common)[0, 1]), 2)

    # --- 전력 판매량 (영향이 간접적이므로 신호를 70%로 약하게) ----------
    rows = [dict(r) for r in orig["electricity_usage"]]
    tot = {}

    for r in rows:
        tot[r["month"][:7]] = tot.get(r["month"][:7], 0) + r["sales_mwh"]

    em = sorted(tot)
    le = np.log([tot[m] for m in em])
    moy = np.array([int(m[5:]) for m in em])
    trend = np.polyval(np.polyfit(np.arange(len(le)), le, 1), np.arange(len(le)))
    seas = np.array([np.mean((le - trend)[moy == k]) for k in range(1, 13)])
    sigma_e = max(np.std(le - trend - seas[moy - 1]), 0.005)
    sig_e = np.array([common[index[m]] for m in em])
    amp = {m: float(np.exp(0.7 * snr * sigma_e * sig_e[i])) for i, m in enumerate(em)}

    for r in rows:
        r["sales_mwh"] = int(round(r["sales_mwh"] * amp[r["month"][:7]]))
        r["data_status"] = STATUS

    new["electricity_usage"] = rows
    report["전력판매량"] = round(float(0.7 * snr / np.sqrt(1 + (0.7 * snr) ** 2)), 2)

    return new, report


# ------------------------------------------------------------
# 평가 (DB를 바꾸지 않고, 이 프로세스의 캐시에만 새 데이터를 넣어 비교)
# ------------------------------------------------------------

def inject(tables):

    for name, rows in tables.items():
        store._cache[name] = (time.time(), rows)


def summarize(result):

    keys = fc.STAT_KEYS + fc.ML_KEYS
    tot = {k: [] for k in keys}
    chosen = []

    for d in result["materials"].values():
        for c in d["candidates"]:
            tot[c["key"]].append(c["mape_avg"])
        chosen.append(next(c["mape_avg"] for c in d["candidates"] if c["selected"]))

    return {
        "candidates": {k: round(float(np.mean(v)) * 100, 2) for k, v in tot.items() if v},
        "selected_avg_mape": round(float(np.mean(chosen)) * 100, 2),
        "models": {d["name"]: d["model"]["label"] for d in result["materials"].values()},
        "forecast_2026": sum(p["value"] for d in result["materials"].values() for p in d["forecast"]),
    }


def evaluate(orig, snr):

    inject({t: orig[t] for t in TABLES})
    before = summarize(fc._compute())

    new, report = generate(orig, snr)
    inject(new)
    after = summarize(fc._compute())

    return before, after, report, new


# ------------------------------------------------------------
# SQL
# ------------------------------------------------------------

def _v(x):
    return str(x)


def write_sql(new):

    os.makedirs(OUT_DIR, exist_ok=True)

    head = (
        "-- 외생변수를 수요와 연관되도록 새로 만든 '가상 연관 데이터' (data_status = 'synthetic_linked')\n"
        "-- Supabase SQL Editor에서 실행하세요. 원본은 *_orig 테이블에 백업됩니다.\n"
        "-- 되돌리려면 supabase/restore_exog.sql 을 실행하세요.\n\n"
    )

    backups = "".join(
        f"create table if not exists public.{t}_orig as select * from public.{t};\n"
        f"alter table public.{t}_orig enable row level security;\n"
        for t in TABLES
    ) + "\n"

    p = ",\n  ".join(f"({r['price_id']}, {r['price']})" for r in new["raw_material_prices"])
    s = ",\n  ".join(
        f"('{r['month']}'::date, {r['project_count']}, {r['total_project_scale_m2']}, {r['avg_project_scale_m2']})"
        for r in new["project_monthly_stats"]
    )
    e = ",\n  ".join(f"({r['usage_id']}, {r['sales_mwh']})" for r in new["electricity_usage"])

    body = (
        "update public.raw_material_prices t\n"
        f"set price = v.price, data_status = '{STATUS}'\n"
        f"from (values\n  {p}\n) as v(price_id, price)\n"
        "where t.price_id = v.price_id;\n\n"
        "update public.project_monthly_stats t\n"
        f"set project_count = v.project_count, total_project_scale_m2 = v.total_project_scale_m2,\n"
        f"    avg_project_scale_m2 = v.avg_project_scale_m2, data_status = '{STATUS}'\n"
        f"from (values\n  {s}\n) as v(month, project_count, total_project_scale_m2, avg_project_scale_m2)\n"
        "where t.month = v.month;\n\n"
        "update public.electricity_usage t\n"
        f"set sales_mwh = v.sales_mwh, data_status = '{STATUS}'\n"
        f"from (values\n  {e}\n) as v(usage_id, sales_mwh)\n"
        "where t.usage_id = v.usage_id;\n"
    )

    open(os.path.join(OUT_DIR, "linked_exog.sql"), "w", encoding="utf-8").write(head + backups + body)

    restore = (
        "-- linked_exog.sql 로 바꾼 외생변수를 원본으로 되돌립니다 (*_orig 백업 테이블 사용).\n\n"
        "update public.raw_material_prices t set price = b.price, data_status = b.data_status\n"
        "from public.raw_material_prices_orig b where t.price_id = b.price_id;\n\n"
        "update public.project_monthly_stats t\n"
        "set project_count = b.project_count, total_project_scale_m2 = b.total_project_scale_m2,\n"
        "    avg_project_scale_m2 = b.avg_project_scale_m2, data_status = b.data_status\n"
        "from public.project_monthly_stats_orig b where t.month = b.month;\n\n"
        "update public.electricity_usage t set sales_mwh = b.sales_mwh, data_status = b.data_status\n"
        "from public.electricity_usage_orig b where t.usage_id = b.usage_id;\n"
    )

    open(os.path.join(OUT_DIR, "restore_exog.sql"), "w", encoding="utf-8").write(restore)


def main():

    ap = argparse.ArgumentParser()
    ap.add_argument("--snr", type=float, default=1.0)
    ap.add_argument("--lead", type=int, default=6)
    ap.add_argument("--evaluate", action="store_true")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    global LEAD
    LEAD = args.lead
    orig = load_originals()
    before, after, report, new = evaluate(orig, args.snr)

    print(f"연관 강도 snr={args.snr}  (생성 지표와 수요 신호의 상관: {report})")
    print("\n[후보별 자재 평균 MAPE %]  (원본 → 연관 데이터)")

    for k in fc.STAT_KEYS + fc.ML_KEYS:
        if k in before["candidates"]:
            print(f"  {fc.LABELS[k]:24s} {before['candidates'][k]:6.2f} → {after['candidates'].get(k, float('nan')):6.2f}")

    print(f"\n선택 모델 평균 MAPE: {before['selected_avg_mape']} → {after['selected_avg_mape']}")
    print("선택 모델(연관 후):", after["models"])
    print(f"2026 예측 합계: {before['forecast_2026']:,} → {after['forecast_2026']:,}")

    if args.write:
        write_sql(new)
        print(f"\n생성: {OUT_DIR}/linked_exog.sql, restore_exog.sql")


if __name__ == "__main__":
    main()
