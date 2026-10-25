-- linked_exog.sql 로 바꾼 외생변수를 원본으로 되돌립니다 (*_orig 백업 테이블 사용).

update public.raw_material_prices t set price = b.price, data_status = b.data_status
from public.raw_material_prices_orig b where t.price_id = b.price_id;

update public.project_monthly_stats t
set project_count = b.project_count, total_project_scale_m2 = b.total_project_scale_m2,
    avg_project_scale_m2 = b.avg_project_scale_m2, data_status = b.data_status
from public.project_monthly_stats_orig b where t.month = b.month;

update public.electricity_usage t set sales_mwh = b.sales_mwh, data_status = b.data_status
from public.electricity_usage_orig b where t.usage_id = b.usage_id;
