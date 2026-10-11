"""Neo4j 공사프로젝트 노드를 Supabase construction_projects와 연결한다.

매칭 규칙 (프로젝트명 문자열이 서로 달라 속성으로 매칭):
  1. 공사 유형: 노드 이름의 키워드로 유형을 추정해 project_type이 같은 것만 후보
     (예: '변전소 증설공사' -> '변전소 증설', '배전망 확충공사' -> '배전선로 확충')
  2. 미완료: end_date가 오늘 이후인 프로젝트만 후보
  3. 완료예정일: 노드의 completion과 end_date의 차이(일)가 가장 작은 것
  4. 동률이면 이름에서 추정한 지역(강남->서울 등)이 같은 것 우선

결과는 노드 속성 supabase_project_id / link_basis 로 기록한다 (추가만 하며
기존 속성은 바꾸지 않는다).

사용:
  python -m scripts.link_projects            # 드라이런 (기록 안 함)
  python -m scripts.link_projects --apply    # Neo4j에 기록
"""

import sys
from datetime import date

from database.neo4j_client import Neo4jClient
from server import store


TYPE_KEYWORDS = [
    ("변전소 증설", "변전소 증설"),
    ("변전소 신설", "변전소 신설"),
    ("배전망 확충", "배전선로 확충"),
    ("배전선로", "배전선로 확충"),
    ("데이터센터", "데이터센터 전력공급"),
    ("산업단지", "산업단지 전력공급"),
]

REGION_KEYWORDS = [
    ("강남", "서울"),
    ("서울", "서울"),
    ("인천", "인천"),
    ("경기", "경기"),
]


def _first_match(name, table):

    return next((v for k, v in table if k in name), None)


def find_match(node, projects, today):

    project_type = _first_match(node["name"], TYPE_KEYWORDS)
    region = _first_match(node["name"], REGION_KEYWORDS)

    if not project_type or not node.get("completion"):
        return None, "유형 또는 완료예정일을 판단할 수 없음"

    completion = date.fromisoformat(node["completion"])

    candidates = [
        p for p in projects
        if p["project_type"] == project_type
        and date.fromisoformat(p["end_date"]) >= today
    ]

    if not candidates:
        return None, f"유형 '{project_type}'의 미완료 프로젝트 없음"

    def key(p):
        diff = abs((date.fromisoformat(p["end_date"]) - completion).days)
        return (diff, p["region"] != region)

    best = min(candidates, key=key)
    diff = key(best)[0]

    basis = (
        f"유형={project_type}, 완료예정 차이={diff}일"
        f", 지역 {'일치' if best['region'] == region else '불일치'}"
        f"({region or '미상'}→{best['region']})"
    )

    return best, basis


def main(apply):

    projects = store.get_table("construction_projects")
    today = date.today()

    db = Neo4jClient()

    try:
        nodes = db.execute_query(
            "MATCH (p:공사프로젝트) "
            "RETURN p.name AS name, p.code AS code, "
            "p.completion AS completion, "
            "p.supabase_project_id AS linked"
        )

        for node in nodes:

            match, basis = find_match(node, projects, today)

            if not match:
                print(f"[건너뜀] {node['name']}: {basis}")
                continue

            print(
                f"{node['name']} ({node['completion']}) -> "
                f"#{match['project_id']} {match['project_name']} "
                f"[{match['region']}/{match['project_type']}, "
                f"{match['start_date']}~{match['end_date']}]\n"
                f"    근거: {basis}"
            )

            if apply:
                db.execute_query(
                    "MATCH (p:공사프로젝트 {name: $name}) "
                    "SET p.supabase_project_id = $pid, "
                    "    p.link_basis = $basis",
                    {
                        "name": node["name"],
                        "pid": match["project_id"],
                        "basis": basis,
                    },
                )

        print("\n기록 완료" if apply else "\n드라이런 (--apply로 기록)")

    finally:
        db.close()


if __name__ == "__main__":

    main("--apply" in sys.argv)
