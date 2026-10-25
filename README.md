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

## 기능 메모

**수요예측**: 자재마다 후보 모델(추세×계절지수, 홀트-윈터스, 계절 나이브, LightGBM 이력, LightGBM 이력+외생변수)을
백테스트(학습 30·36개월 → 향후 12개월)해 평균 MAPE가 낮은 모델을 자동 선택하고, 오차 분포로 80% 예측 구간을 만든다.
LightGBM은 통계 모델보다 3% 이상 좋을 때만, 외생변수 모델은 이력 모델보다 3% 이상 좋을 때만 채택한다.
LightGBM이 설치되지 않은 환경에서는 통계 모델만 비교한다.

**내보내기**: 발주·재고·수요예측·시뮬레이션·위험 알림을 CSV(UTF-8 BOM) 또는 엑셀(.xlsx)로 내려받는다.
API는 `/api/export/*` (로그인 토큰 필요).

**외생변수 가상 연관 데이터(선택)**: `python -m scripts.generate_linked_exog --snr 3 --lead 3 --evaluate --write`로
`supabase/linked_exog.sql`(백업 포함)과 `supabase/restore_exog.sql`(복원)을 만든다. Supabase SQL Editor에서 직접 실행한다.
이 데이터는 수요와 연관되도록 만든 시연용(`synthetic_linked`)이라 정확도 향상이 실데이터 성능을 의미하지 않는다.

## .env 항목

- `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`
- `OPENAI_API_KEY`
- `SUPABASE_URL`, `SUPABASE_KEY` — 발주·재고 쓰기를 위해 서버용(service_role/secret) 키 필요. `SUPABASE_SERVICE_KEY`가 있으면 우선 사용
- `APP_ADMIN_ID`, `APP_ADMIN_PASSWORD`, `APP_SECRET` — 웹 로그인용

## 발주·재고 테이블 준비

Supabase SQL Editor에서 `supabase/schema.sql` → `supabase/seed.sql` 순서로 실행합니다.
