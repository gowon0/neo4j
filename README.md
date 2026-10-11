# 기자재 AI 수요예측 시스템

FastAPI 백엔드 + React 프론트엔드 기반 자재관리 ERP.

| 화면 | 데이터 출처 |
|---|---|
| 대시보드 / 수요예측 / 시뮬레이션 | Supabase `demand_history` 등 (읽기 전용) |
| AI 위험 알림 | Neo4j 지식그래프 + OpenAI 요약 (실패 시 그래프 사실 기반 문장) |
| 발주관리 / 재고관리 | 로컬 SQLite `data/erp.db` (최초 실행 시 샘플 자동 생성) |

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
- `SUPABASE_URL`, `SUPABASE_KEY` (서비스 키가 있으면 `SUPABASE_SERVICE_KEY` 우선)
- `APP_ADMIN_ID`, `APP_ADMIN_PASSWORD`, `APP_SECRET` — 웹 로그인용

## 발주·재고 데이터 초기화

`data/erp.db`를 삭제하고 서버를 재시작하면 샘플 데이터가 다시 생성됩니다.
