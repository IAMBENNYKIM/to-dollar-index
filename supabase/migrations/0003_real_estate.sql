-- 부동산 지표(서울 소형 아파트) 시드 + 월별 USD 환산 뷰.
-- collector가 KOSIS 한국부동산원 통계표(DT_KAB_11672_S19, 서울 소형 40㎡초과 60㎡이하)를
-- 59㎡ 기준 원(KRW)으로 환산해 daily_prices 에 월별로 적재한다.

-- 지표 시드
insert into indicators (id, indicator_type, source_code, display_name, is_active)
values ('real_estate:seoul-small', 'real_estate', 'DT_KAB_11672_S19', '서울 아파트 소형 (59㎡ 환산)', true)
on conflict (id) do nothing;

-- 부동산(월별) 전용 USD 환산 뷰: 해당 월의 평균 USD_KRW 환율을 사용한다.
-- 월 데이터는 그 달이 끝난 뒤 공개되므로 월평균이 확정적이고 의미상 정확하다.
-- 반환 컬럼은 daily_prices_with_usd 와 동일해 프론트 매핑(mapDualCurrencyRow)을 재사용한다.
-- security_invoker=on 으로 base 테이블 RLS(anon SELECT 정책)를 우회하지 않는다.
create view real_estate_prices_with_usd with (security_invoker = on) as
select
  p.indicator_id,
  p.price_date,
  p.close_price as close_price_krw,
  m.avg_rate    as usd_krw_rate,
  round(p.close_price / m.avg_rate, 6) as close_price_usd
from daily_prices p
join indicators i
  on i.id = p.indicator_id and i.indicator_type = 'real_estate'
left join lateral (
  select avg(close_rate) as avg_rate
  from exchange_rates
  where currency_pair = 'USD_KRW'
    and date_trunc('month', rate_date) = date_trunc('month', p.price_date)
) m on true;
