from database.neo4j_client import Neo4jClient


EXTERNAL_RISK_QUERY = """
MATCH (risk:리스크요인)-[r1]->(m:원자재)
      -[r2:원가영향]->(e:기자재)
      -[r3:수급영향]->(s:수급문제)
      -[r4:프로젝트영향]->(p:공사프로젝트)

WHERE risk.isActive = true

RETURN
    risk.name AS risk_name,
    risk.category AS risk_category,
    risk.severity AS risk_severity,
    risk.reason AS risk_reason,

    type(r1) AS risk_relationship,
    r1.impact AS risk_impact,

    m.name AS material,

    e.name AS equipment,

    s.name AS supply_problem,
    s.severity AS supply_severity,

    p.name AS project,
    p.status AS project_status,

    r2.impact AS material_impact,
    r2.direction AS material_direction,
    r2.reason AS material_reason,

    r3.impact AS supply_impact,
    r4.impact AS project_impact
"""


def analyze_external_risks(db: Neo4jClient):

    return db.execute_query(
        EXTERNAL_RISK_QUERY
    )