from database.neo4j_client import Neo4jClient

from utils.calculator import (
    calculate_increase_rate,
    calculate_risk_level
)


MATERIAL_QUERY = """
MATCH (m:원자재)-[r1:원가영향]->(e:기자재)
      -[r2:수급영향]->(s:수급문제)
      -[r3:프로젝트영향]->(p:공사프로젝트)

RETURN
    m.name AS material,
    m.code AS material_code,
    m.standard AS standard_price,
    m.current AS current_price,

    e.name AS equipment,

    s.name AS supply_problem,
    s.severity AS supply_severity,

    p.name AS project,
    p.status AS project_status,

    r1.impact AS material_impact,
    r1.direction AS material_direction,
    r1.reason AS material_reason,

    r2.impact AS supply_impact,
    r2.reason AS supply_reason,

    r3.impact AS project_impact
"""


def analyze_materials(db: Neo4jClient):

    records = db.execute_query(
        MATERIAL_QUERY
    )

    results = []

    for record in records:

        standard = record["standard_price"]
        current = record["current_price"]

        increase_rate = calculate_increase_rate(
            standard,
            current
        )

        risk_level = calculate_risk_level(
            increase_rate
        )

        result = {
            **record,

            "increase_rate": round(
                increase_rate,
                2
            ),

            "risk_level": risk_level
        }

        results.append(result)

    return results