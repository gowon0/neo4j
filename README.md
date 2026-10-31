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

## 권한 (역할 기반)

로그인한 사용자의 **역할**에 따라 화면·기능·대시보드 위젯을 제한한다. 서버가 모든 API에서 권한을 검사하고
화면은 메뉴·버튼을 숨긴다. 설계는 `docs/권한고도화_설계안.md` 참고.

- **기본 역할**: 관리자 · 구매담당 · 재고담당 · 수요계획 · 조회자 (역할·권한 화면에서 수정, 새 역할 생성 가능)
- **화면**: 사용자 관리, 역할·권한, 감사 로그, 내 계정(비밀번호 변경·내 권한·로그인 이력)
- **보안**: 비밀번호 scrypt 해시, 10자 이상 영문+숫자, 5회 실패 시 15분 잠금, 첫 로그인 시 비밀번호 변경 강제,
  로그아웃·비밀번호 변경·비활성화 시 토큰 즉시 무효화, 주요 행위 감사 로그

**처음 적용하는 순서**

1. Supabase SQL Editor에서 `supabase/auth_schema.sql` 실행 (테이블 3개 + 기본 역할 5개)
2. 서버를 (재)시작하면 `.env`의 `APP_ADMIN_ID` / `APP_ADMIN_PASSWORD`로 **첫 관리자**가 자동 생성된다.
   이 비밀번호로 로그인하면 바로 새 비밀번호를 정해야 한다.
3. 관리자가 사용자 관리 화면에서 계정을 발급한다 (임시 비밀번호는 한 번만 표시).

**비상 관리자**: DB(사용자 테이블)를 쓸 수 없을 때도 `.env` 계정으로 로그인할 수 있다. 아이디는
`APP_EMERGENCY_ID`(기본 `emergency`) 또는 `APP_ADMIN_ID`, 비밀번호는 `APP_ADMIN_PASSWORD`.
사용하지 않으려면 `APP_EMERGENCY_ENABLED=off`. 로그인하면 감사 로그에 남는다.

**롤백**: `supabase/auth_rollback.sql`로 테이블을 삭제하면 비상 관리자로만 로그인할 수 있다.

**테스트**: `python -m pytest tests -q` — 인증 테이블은 메모리 가짜 저장소, 쓰기는 스텁이라 운영 데이터가 바뀌지 않는다
(그 외 테이블은 Supabase를 읽기 전용으로 사용).

## .env 항목

- `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`
- `OPENAI_API_KEY`
- `SUPABASE_URL`, `SUPABASE_KEY` — 발주·재고 쓰기를 위해 서버용(service_role/secret) 키 필요. `SUPABASE_SERVICE_KEY`가 있으면 우선 사용
- `APP_ADMIN_ID`, `APP_ADMIN_PASSWORD`, `APP_SECRET` — 웹 로그인용

## 발주·재고 테이블 준비

Supabase SQL Editor에서 `supabase/schema.sql` → `supabase/seed.sql` 순서로 실행합니다.
