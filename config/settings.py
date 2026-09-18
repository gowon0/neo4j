import os

from dotenv import load_dotenv


load_dotenv()


# ============================================================
# Neo4j
# ============================================================

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")


# ============================================================
# OpenAI
# ============================================================

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


# ============================================================
# 위험도 기준
# ============================================================

WARNING_THRESHOLD = 10
DANGER_THRESHOLD = 15
VERY_DANGER_THRESHOLD = 20