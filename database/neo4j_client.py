from neo4j import GraphDatabase

from config.settings import (
    NEO4J_URI,
    NEO4J_USERNAME,
    NEO4J_PASSWORD
)


class Neo4jClient:

    def __init__(self):

        self.driver = GraphDatabase.driver(
            NEO4J_URI,
            auth=(
                NEO4J_USERNAME,
                NEO4J_PASSWORD
            )
        )

    def execute_query(self, query, parameters=None):

        with self.driver.session() as session:

            result = session.run(
                query,
                parameters or {}
            )

            return [
                record.data()
                for record in result
            ]

    def close(self):

        self.driver.close()