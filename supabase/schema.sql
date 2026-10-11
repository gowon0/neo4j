-- 기자재 AI 수요예측 시스템: 발주·재고 테이블
-- Supabase 대시보드 > SQL Editor 에서 실행하세요. (여러 번 실행해도 안전)

create table if not exists public.inventory (
    material_id   bigint primary key,           -- materials.material_id
    current_stock bigint not null check (current_stock >= 0),
    safety_stock  bigint not null check (safety_stock >= 0),
    updated_at    date   not null default current_date,
    data_status   text   not null default 'synthetic'
);

create table if not exists public.purchase_orders (
    po_no       text   primary key,             -- 예: PO20261002001
    material_id bigint not null,                -- materials.material_id
    quantity    bigint not null check (quantity > 0),
    order_date  date   not null,
    due_date    date   not null,
    status      text   not null
                check (status in ('발주대기', '진행중', '발주완료', '지연')),
    data_status text   not null default 'synthetic'
);

create index if not exists purchase_orders_material_idx
    on public.purchase_orders (material_id);

-- 공개용(anon) 키로는 접근하지 못하도록 RLS를 켜고 정책은 만들지 않습니다.
-- 서버는 service_role 키로 접근하므로 RLS의 영향을 받지 않습니다.
alter table public.inventory       enable row level security;
alter table public.purchase_orders enable row level security;
