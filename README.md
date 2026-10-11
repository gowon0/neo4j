# 기자재 AI 수요예측 시스템

FastAPI 백엔드 + React 프론트엔드 기반 자재관리 ERP.

| 화면 | 데이터 출처 |
|---|---|
| 대시보드 / 수요예측 / 시뮬레이션 | Supabase `demand_history` 등 (읽기 전용) |
| AI 위험 알림 | Neo4j 지식그래프 + OpenAI 요약 (실패 시 그래프 사실 기반 문장) |
| 발주관리 / 재고관리 | Supabase `purchase_orders`, `inventory` (생성 SQL: `supabase/schema.sql`, 샘플 데이터: `supabase/seed.sql`) |

## 실행

```bash
# 1) 프론트엔드 빌드 (최초 1회, 화면 수정 시 재빌드)
cd frontend && npm install && npm run build && cd ..

# 2) 서버 실행 → http://localhost:8000
python -m uvicorn server.app:app --port 8000
```

개발 중 핫리로드: 서버를 띄운 뒤 `cd frontend && npm run dev` → http://localhost:5173

## .env 항목

- `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`
- `OPENAI_API_KEY`
- `SUPABASE_URL`, `SUPABASE_KEY` — 발주·재고 쓰기를 위해 서버용(service_role/secret) 키 필요. `SUPABASE_SERVICE_KEY`가 있으면 우선 사용
- `APP_ADMIN_ID`, `APP_ADMIN_PASSWORD`, `APP_SECRET` — 웹 로그인용

## 발주·재고 테이블 준비

Supabase SQL Editor에서 `supabase/schema.sql` → `supabase/seed.sql` 순서로 실행합니다.
