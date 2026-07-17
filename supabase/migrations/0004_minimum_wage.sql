-- 최저임금(시간급) 지표 시드 + 연도별 USD 환산 뷰.
-- collector가 아닌 정적 시드로 적재한다: 최저임금위원회 고시값(minimumwage.go.kr)을
-- 연도별 시간급(원)으로 daily_prices 에 price_date='YYYY-01-01' 기준 적재한다.

-- 지표 시드
insert into indicators (id, indicator_type, source_code, display_name, is_active)
values ('minimum_wage:hourly', 'minimum_wage', 'minimumwage.go.kr', '최저임금 (시간급)', true)
on conflict (id) do nothing;

-- 연도별 시간급(원) 시드. price_date 는 각 연도 1월 1일. close_price=시간급.
-- open/high/low/volume 은 연간 지표에 무의미하므로 생략(nullable).
insert into daily_prices (indicator_id, price_date, close_price)
values
  ('minimum_wage:hourly', '2015-01-01', 5580),
  ('minimum_wage:hourly', '2016-01-01', 6030),
  ('minimum_wage:hourly', '2017-01-01', 6470),
  ('minimum_wage:hourly', '2018-01-01', 7530),
  ('minimum_wage:hourly', '2019-01-01', 8350),
  ('minimum_wage:hourly', '2020-01-01', 8590),
  ('minimum_wage:hourly', '2021-01-01', 8720),
  ('minimum_wage:hourly', '2022-01-01', 9160),
  ('minimum_wage:hourly', '2023-01-01', 9620),
  ('minimum_wage:hourly', '2024-01-01', 9860),
  ('minimum_wage:hourly', '2025-01-01', 10030),
  ('minimum_wage:hourly', '2026-01-01', 10320)
on conflict (indicator_id, price_date) do nothing;

-- 최저임금(연도별) 전용 USD 환산 뷰: 해당 연도의 평균 USD_KRW 환율을 사용한다.
-- 연간 데이터는 해당 연도 평균 환율로 환산하며, 2026처럼 진행 중인 연도는 YTD(연초~현재)
-- 평균이라 새 환율이 쌓이면 값이 갱신된다(연말에 확정).
-- 반환 컬럼은 daily_prices_with_usd 와 동일해 프론트 매핑(mapDualCurrencyRow)을 재사용한다.
-- security_invoker=on 으로 base 테이블 RLS(anon SELECT 정책)를 우회하지 않는다.
create view minimum_wage_prices_with_usd with (security_invoker = on) as
select
  p.indicator_id,
  p.price_date,
  p.close_price as close_price_krw,
  y.avg_rate    as usd_krw_rate,
  round(p.close_price / y.avg_rate, 6) as close_price_usd
from daily_prices p
join indicators i
  on i.id = p.indicator_id and i.indicator_type = 'minimum_wage'
left join lateral (
  select avg(close_rate) as avg_rate
  from exchange_rates
  where currency_pair = 'USD_KRW'
    and date_trunc('year', rate_date) = date_trunc('year', p.price_date)
) y on true;
