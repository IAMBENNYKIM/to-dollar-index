-- 초기 지표 시드. 멱등하게 삽입 (on conflict do nothing).

insert into indicators (id, indicator_type, source_code, display_name)
values ('stock:005930', 'stock', '005930', '삼성전자')
on conflict (id) do nothing;
