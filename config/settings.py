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
# Supabase (서버에서만 사용 — 브라우저로 노출하지 않음)
# SUPABASE_SERVICE_KEY가 있으면 우선 사용
# ============================================================

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = (
    os.getenv("SUPABASE_SERVICE_KEY")
    or os.getenv("SUPABASE_KEY")
)


# ============================================================
# 웹 시스템 로그인
# ============================================================

APP_ADMIN_ID = os.getenv("APP_ADMIN_ID", "admin")
APP_ADMIN_PASSWORD = os.getenv("APP_ADMIN_PASSWORD")
APP_SECRET = os.getenv("APP_SECRET")
APP_TOKEN_TTL_HOURS = 12


# ============================================================
# 위험도 기준
# ============================================================

WARNING_THRESHOLD = 10
DANGER_THRESHOLD = 15
VERY_DANGER_THRESHOLD = 20
