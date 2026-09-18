from database.neo4j_client import Neo4jClient


DISASTER_QUERY = """
MATCH (d:자연재해)-[r1:발생원인]->(c:공사위험)
      -[r2:공사영향]->(p:공사프로젝트)

WHERE d.isActive = true

RETURN
    d.name AS disaster,
    d.category AS disaster_category,
    d.severity AS disaster_severity,
    d.reason AS disaster_reason,

    c.name AS construction_risk,
    c.severity AS construction_severity,
    c.reason AS construction_reason,

    p.name AS project,
    p.status AS project_status,

    r1.impact AS disaster_impact,
    r2.impact AS project_impact
"""


def analyze_disasters(db: Neo4jClient):

    return db.execute_query(
        DISASTER_QUERY
    )