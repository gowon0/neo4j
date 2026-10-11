"""지식그래프(Neo4j) 위험 분석 → 프로젝트별 짧은 자연어 알림.

기존 analysis/* 모듈의 조회 결과를 재사용하고, 항목마다
[위험 원인 / 기자재 영향 / 수급 문제 / 프로젝트 영향] 라벨 요약을
LLM으로 생성한다. LLM 호출이 실패하면 그래프 사실로 만든 문장으로 대체한다.
"""

import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from config.settings import WARNING_THRESHOLD
from database.neo4j_client import Neo4jClient
from analysis.material import analyze_materials
from analysis.external_risk import analyze_external_risks
from analysis.disaster import analyze_disasters
from llm.chain import generate_short_explanation
from server import store


CACHE_TTL_SECONDS = 1800

LEVEL_RANK = {"경고": 1, "위험": 2, "매우위험": 3}

SEVERITY_TO_LEVEL = {
    "매우높음": "매우위험",
    "높음": "위험",
}

MATERIAL_LABELS = ["위험 원인", "기자재 영향", "수급 문제", "프로젝트 영향"]
DISASTER_LABELS = ["위험 원인", "공사 영향", "프로젝트 영향"]

_state = {"data": None, "ts": 0.0}
_lock = threading.Lock()


# ------------------------------------------------------------
# 항목 구성
# ------------------------------------------------------------

def _level_from_severity(severity):

    return SEVERITY_TO_LEVEL.get(severity, "경고")


def _material_item(index, d):

    rate = d["increase_rate"]

    return {
        "id": f"material-{index}",
        "kind": "material",
        "kind_label": "원자재 가격",
        "title": f"{d['material']} 가격 +{rate:.1f}%",
        "level": d["risk_level"],
        "project": d["project"],
        "project_status": d["project_status"],
        "equipment": d["equipment"],
        "labels": MATERIAL_LABELS,
        "facts": (
            "[분석 유형] 원자재 가격 상승\n"
            f"[원자재] {d['material']} "
            f"기준 {d['standard_price']:,} → 현재 {d['current_price']:,} "
            f"(+{rate:.1f}%, {d['risk_level']})\n"
            f"[기자재] {d['equipment']} — {d['material_reason']}\n"
            f"[수급 문제] {d['supply_problem']} (심각도 {d['supply_severity']})\n"
            f"[프로젝트] {d['project']} ({d['project_status']})\n"
            f"[출력 라벨] {' / '.join(MATERIAL_LABELS)}"
        ),
        "fallback": {
            "위험 원인": f"{d['material']} 가격이 기준 대비 {rate:.1f}% 상승",
            "기자재 영향": f"{d['equipment']} 제조원가 상승 가능",
            "수급 문제": f"{d['supply_problem']} 우려",
            "프로젝트 영향": f"{d['project']} 진행에 차질 가능",
        },
    }


def _external_item(index, d):

    return {
        "id": f"external-{index}",
        "kind": "external",
        "kind_label": "외부 리스크",
        "title": f"{d['risk_name']} → {d['material']}",
        "level": _level_from_severity(d["risk_severity"]),
        "project": d["project"],
        "project_status": d["project_status"],
        "equipment": d["equipment"],
        "labels": MATERIAL_LABELS,
        "facts": (
            "[분석 유형] 외부 공급망 리스크\n"
            f"[외부 리스크] {d['risk_name']} ({d['risk_category']}, "
            f"심각도 {d['risk_severity']}) — {d['risk_reason']}\n"
            f"[원자재] {d['material']}\n"
            f"[기자재] {d['equipment']} — {d['material_reason']}\n"
            f"[수급 문제] {d['supply_problem']} (심각도 {d['supply_severity']})\n"
            f"[프로젝트] {d['project']} ({d['project_status']})\n"
            f"[출력 라벨] {' / '.join(MATERIAL_LABELS)}"
        ),
        "fallback": {
            "위험 원인": f"{d['risk_name']}로 {d['material']} 부담 증가",
            "기자재 영향": f"{d['equipment']} 제조원가·조달비용 상승 가능",
            "수급 문제": f"{d['supply_problem']} 우려",
            "프로젝트 영향": f"{d['project']} 진행에 차질 가능",
        },
    }


def _disaster_item(index, d):

    return {
        "id": f"disaster-{index}",
        "kind": "disaster",
        "kind_label": "자연재해",
        "title": d["disaster"],
        "level": _level_from_severity(d["disaster_severity"]),
        "project": d["project"],
        "project_status": d["project_status"],
        "equipment": None,
        "labels": DISASTER_LABELS,
        "facts": (
            "[분석 유형] 자연재해\n"
            f"[자연재해] {d['disaster']} ({d['disaster_category']}, "
            f"심각도 {d['disaster_severity']}) — {d['disaster_reason']}\n"
            f"[공사 위험] {d['construction_risk']} "
            f"(심각도 {d['construction_severity']}) — "
            f"{d['construction_reason']}\n"
            f"[프로젝트] {d['project']} ({d['project_status']})\n"
            f"[출력 라벨] {' / '.join(DISASTER_LABELS)}"
        ),
        "fallback": {
            "위험 원인": f"{d['disaster']} 발생 가능성",
            "공사 영향": f"{d['construction_risk']} 우려",
            "프로젝트 영향": f"{d['project']} 일정 차질 가능",
        },
    }


# ------------------------------------------------------------
# 자연어 요약
# ------------------------------------------------------------

_LINE = re.compile(r"^\s*\[(.+?)\]\s*(.+?)\s*$")


def _summarize(item):
    """라벨별 한 줄 요약. LLM 실패/누락 라벨은 그래프 사실로 대체."""

    parsed = {}
    used_ai = False

    try:

        text = generate_short_explanation(item["facts"])

        for line in text.splitlines():
            match = _LINE.match(line)
            if match and match.group(1) in item["labels"]:
                parsed[match.group(1)] = match.group(2).rstrip(" .")

        used_ai = bool(parsed)

    except Exception:
        parsed = {}

    lines = [
        {
            "label": label,
            "text": parsed.get(label) or item["fallback"][label],
        }
        for label in item["labels"]
    ]

    return lines, used_ai and len(parsed) == len(item["labels"])


# ------------------------------------------------------------
# 프로젝트 연결 (Neo4j 공사프로젝트 ↔ Supabase construction_projects)
# 연결 기준은 scripts/link_projects.py 참고
# ------------------------------------------------------------

def _project_links(db):
    """{Neo4j 프로젝트명: Supabase 프로젝트 요약}. 연결이 없으면 빈 dict."""

    try:
        nodes = db.execute_query(
            "MATCH (p:공사프로젝트) "
            "RETURN p.name AS name, p.code AS code, "
            "p.completion AS completion, "
            "p.supabase_project_id AS linked"
        )
        by_id = {
            p["project_id"]: p
            for p in store.get_table("construction_projects")
        }
    except Exception:
        return {}

    links = {}

    for node in nodes:

        linked = by_id.get(node["linked"])

        if not linked:
            continue

        links[node["name"]] = {
            "code": node["code"],
            "completion": node["completion"],
            "project_id": linked["project_id"],
            "name": linked["project_name"],
            "region": linked["region"],
            "type": linked["project_type"],
            "start": linked["start_date"][:7],
            "end": linked["end_date"][:7],
            "scale_m2": linked["project_scale_m2"],
        }

    return links


# ------------------------------------------------------------
# 집계
# ------------------------------------------------------------

def _build():

    db = Neo4jClient()

    try:
        materials = analyze_materials(db)
        externals = analyze_external_risks(db)
        disasters = analyze_disasters(db)
        links = _project_links(db)
    finally:
        db.close()

    items = []

    for i, d in enumerate(materials):
        if d["increase_rate"] >= WARNING_THRESHOLD:
            items.append(_material_item(i, d))

    items.extend(_external_item(i, d) for i, d in enumerate(externals))
    items.extend(_disaster_item(i, d) for i, d in enumerate(disasters))

    with ThreadPoolExecutor(max_workers=6) as pool:
        summaries = list(pool.map(_summarize, items))

    for item, (lines, used_ai) in zip(items, summaries):
        item["lines"] = lines
        item["ai"] = used_ai

    projects = {}

    for item in items:

        project = projects.setdefault(item["project"], {
            "project": item["project"],
            "status": item["project_status"],
            "link": links.get(item["project"]),
            "items": [],
        })

        project["items"].append(item)

    result_projects = []

    for project in projects.values():

        project["items"].sort(
            key=lambda x: -LEVEL_RANK[x["level"]]
        )

        level = project["items"][0]["level"]

        equipments = []
        for item in project["items"]:
            e = item["equipment"]
            if e and e not in equipments:
                equipments.append(e)

        if equipments:
            headline = f"{', '.join(equipments)} 수급 차질 우려"
        else:
            headline = "공사 진행 차질 우려"

        project["level"] = level
        project["headline"] = f"{headline} · 위험 요인 {len(project['items'])}건"

        for item in project["items"]:
            for key in ("facts", "fallback", "labels", "project",
                        "project_status", "equipment"):
                item.pop(key, None)

        result_projects.append(project)

    result_projects.sort(
        key=lambda p: (-LEVEL_RANK[p["level"]], -len(p["items"]))
    )

    counts = {"매우위험": 0, "위험": 0, "경고": 0}

    for item in items:
        counts[item["level"]] += 1

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "summary": {
            "total": len(items),
            "projects": len(result_projects),
            "very_danger": counts["매우위험"],
            "danger": counts["위험"],
            "warning": counts["경고"],
            "ai_generated": sum(1 for i in items if i["ai"]),
        },
        "projects": result_projects,
    }


def get_risks(force=False):

    with _lock:

        fresh = (
            _state["data"] is not None
            and time.time() - _state["ts"] < CACHE_TTL_SECONDS
        )

        if fresh and not force:
            return _state["data"]

        _state["data"] = _build()
        _state["ts"] = time.time()

        return _state["data"]
