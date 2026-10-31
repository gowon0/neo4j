-- 권한 고도화: 사용자 · 역할 · 감사 로그 테이블과 기본 역할
-- Supabase 대시보드 > SQL Editor 에서 한 번 실행하세요. (여러 번 실행해도 안전)
--
-- * 앱은 서버용(service_role/secret) 키로 접근하므로 RLS를 켜고 공개 정책은 만들지 않습니다.
-- * 첫 관리자 계정은 SQL이 아니라 서버가 시작할 때 .env의 APP_ADMIN_ID / APP_ADMIN_PASSWORD로
--   자동 생성합니다(비밀번호는 해시로만 저장, 첫 로그인에서 변경 강제).
-- * 되돌리려면 supabase/auth_rollback.sql 을 실행하세요.

create table if not exists public.app_roles (
    id          bigint generated always as identity primary key,
    name        text    not null unique,
    description text    not null default '',
    permissions text[]  not null default '{}',
    is_system   boolean not null default false,
    created_at  timestamptz not null default now()
);

create table if not exists public.app_users (
    id                   bigint generated always as identity primary key,
    username             text    not null unique check (username = lower(username)),
    display_name         text    not null,
    password_hash        text    not null,
    role_id              bigint  references public.app_roles (id),
    is_active            boolean not null default true,
    must_change_password boolean not null default true,
    failed_logins        integer not null default 0,
    locked_until         timestamptz,
    token_version        integer not null default 1,
    last_login_at        timestamptz,
    created_at           timestamptz not null default now()
);

create index if not exists app_users_role_idx on public.app_users (role_id);

create table if not exists public.audit_logs (
    id       bigint generated always as identity primary key,
    at       timestamptz not null default now(),
    username text  not null default '',
    action   text  not null,
    target   text  not null default '',
    detail   jsonb not null default '{}'::jsonb,
    ip       text  not null default ''
);

create index if not exists audit_logs_at_idx     on public.audit_logs (at desc);
create index if not exists audit_logs_user_idx   on public.audit_logs (username, at desc);
create index if not exists audit_logs_action_idx on public.audit_logs (action, at desc);

alter table public.app_roles  enable row level security;
alter table public.app_users  enable row level security;
alter table public.audit_logs enable row level security;

-- 기본 역할 5개 (이름이 이미 있으면 건너뜀)
insert into public.app_roles (name, description, permissions, is_system) values
    ('관리자', '모든 기능과 사용자·권한·감사 로그 관리',
     array['dashboard.view', 'forecast.view', 'forecast.export', 'orders.view', 'orders.create', 'orders.update', 'orders.export', 'inventory.view', 'inventory.export', 'simulation.run', 'simulation.export', 'risks.view', 'risks.refresh', 'risks.export', 'data.view', 'data.refresh', 'settings.view', 'users.manage', 'roles.manage', 'audit.view']::text[], true),
    ('구매담당', '발주 등록·변경, 수요예측·재고 조회, 시뮬레이션',
     array['dashboard.view', 'forecast.view', 'forecast.export', 'orders.view', 'orders.create', 'orders.update', 'orders.export', 'inventory.view', 'inventory.export', 'simulation.run', 'simulation.export', 'risks.view', 'risks.export']::text[], true),
    ('재고담당', '재고 조회·내보내기, 발주는 조회만',
     array['dashboard.view', 'forecast.view', 'orders.view', 'inventory.view', 'inventory.export', 'risks.view']::text[], true),
    ('수요계획', '수요예측·시뮬레이션·위험 분석·데이터 조회',
     array['dashboard.view', 'forecast.view', 'forecast.export', 'inventory.view', 'simulation.run', 'simulation.export', 'risks.view', 'risks.refresh', 'risks.export', 'data.view']::text[], true),
    ('조회자', '대시보드·수요예측·재고·위험 알림 조회만',
     array['dashboard.view', 'forecast.view', 'inventory.view', 'risks.view']::text[], true)
on conflict (name) do nothing;
