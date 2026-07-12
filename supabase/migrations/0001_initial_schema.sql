-- to-dollar-index 초기 스키마: 지표 메타, 일별 시세, 환율, 최저임금, 부동산 월별 데이터.
-- Python 배치가 service_role로 쓰고, Next.js 프론트가 anon 키로 읽는다 (읽기 전용).

-- 지표 메타데이터. id는 'stock:005930' 형식.
create table indicators (
  id text primary key,
  indicator_type text not null
    check (indicator_type in ('stock', 'exchange_rate', 'minimum_wage', 'real_estate')),
  source_code text not null,            -- KIS 종목코드 '005930' 등
  display_name text not null,
  is_active boolean not null default true,
  created_at timestamptz not null default now()
);

-- 일별 시세. KRW 원본만 저장. 수정주가는 소수 가능하므로 numeric 사용.
create table daily_prices (
  indicator_id text not null references indicators (id),
  price_date date not null,
  close_price numeric(18, 4) not null,
  open_price numeric(18, 4),
  high_price numeric(18, 4),
  low_price numeric(18, 4),
  trade_volume bigint,
  primary key (indicator_id, price_date)
);

-- 일별 환율. close_rate는 1 USD당 KRW.
create table exchange_rates (
  currency_pair text not null default 'USD_KRW',
  rate_date date not null,
  close_rate numeric(12, 4) not null,
  primary key (currency_pair, rate_date)
);

-- 연도별 최저임금 (시급, KRW).
create table minimum_wages (
  effective_year smallint primary key,
  hourly_wage_krw integer not null
);

-- 지역별 월별 부동산 통계. trade_month는 해당 월 1일.
create table real_estate_monthly (
  region_code text not null,
  region_name text not null,
  trade_month date not null,
  average_price_krw numeric(18, 2) not null,
  trade_count integer not null,
  primary key (region_code, trade_month)
);

-- 일별 시세에 달러 환산을 붙인 뷰.
-- 당일 환율이 없으면 직전 환율로 폴백 (left join lateral). 최초 환율 이전 날짜 행도
-- 살아남고 usd 컬럼은 NULL이 된다. security_invoker로 base 테이블 RLS를 우회하지 않는다.
create view daily_prices_with_usd with (security_invoker = on) as
select
  p.indicator_id,
  p.price_date,
  p.close_price as close_price_krw,
  r.close_rate as usd_krw_rate,
  round(p.close_price / r.close_rate, 6) as close_price_usd
from daily_prices p
left join lateral (
  select close_rate
  from exchange_rates
  where currency_pair = 'USD_KRW'
    and rate_date <= p.price_date
  order by rate_date desc
  limit 1
) r on true;

-- RLS: 모든 테이블 읽기 전용 공개. 쓰기는 service_role만 (RLS 우회하므로 정책 불필요).
alter table indicators enable row level security;
alter table daily_prices enable row level security;
alter table exchange_rates enable row level security;
alter table minimum_wages enable row level security;
alter table real_estate_monthly enable row level security;

create policy indicators_select on indicators
  for select to anon, authenticated using (true);
create policy daily_prices_select on daily_prices
  for select to anon, authenticated using (true);
create policy exchange_rates_select on exchange_rates
  for select to anon, authenticated using (true);
create policy minimum_wages_select on minimum_wages
  for select to anon, authenticated using (true);
create policy real_estate_monthly_select on real_estate_monthly
  for select to anon, authenticated using (true);

-- 방어적으로 anon/authenticated의 쓰기 권한을 회수한다.
revoke insert, update, delete on all tables in schema public from anon, authenticated;
