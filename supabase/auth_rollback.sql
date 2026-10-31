-- 권한 고도화 테이블을 모두 삭제합니다. (사용자·역할·감사 로그 데이터가 사라집니다)
-- 실행 전에 필요하면 Table Editor에서 audit_logs를 CSV로 내려받아 보관하세요.
-- 삭제 후 앱은 .env 비상 관리자 계정으로만 로그인할 수 있습니다.

drop table if exists public.audit_logs;
drop table if exists public.app_users;
drop table if exists public.app_roles;
