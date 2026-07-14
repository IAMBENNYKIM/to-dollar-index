import { createSupabaseServerClient } from "./supabaseClient";
import type {
  DualCurrencyPoint,
  ExchangeRatePoint,
  Indicator,
} from "./types";

/**
 * PostgREST 는 기본적으로 한 번의 조회에서 최대 1000행만 반환한다.
 * 10년치 일봉(~2,500행) 같은 시계열을 전량 가져오려면 range 기반 페이지네이션이 필요하다.
 */
export const PAGE_SIZE = 1000;

/** 페이지네이션 헬퍼가 기대하는, supabase 조회 결과의 최소 형태. */
export interface PageResult<Row> {
  data: Row[] | null;
  error: { message: string } | null;
}

/**
 * [from, to] 포함 범위(inclusive)의 한 페이지를 조회하는 함수.
 * supabase 쿼리 객체와 분리되어 있어 단위 테스트에서 가짜 구현으로 대체할 수 있다.
 *
 * supabase 쿼리 빌더는 Promise 가 아닌 PromiseLike(thenable) 이므로 반환 타입을
 * PromiseLike 로 두어 빌더를 그대로 반환할 수 있게 한다.
 */
export type PageFetcher<Row> = (
  from: number,
  to: number,
) => PromiseLike<PageResult<Row>>;

/** 총 행수를 조회하는 함수. supabase 의 head+count 쿼리 결과 형태와 호환된다. */
export type RowCounter = () => PromiseLike<{
  count: number | null;
  error: { message: string } | null;
}>;

/**
 * 순차 페이지네이션 루프(폴백 경로). fetchPage 를 반복 호출하여 모든 행을 수집한다.
 *
 * 종료 조건:
 * - 반환된 행 수가 PAGE_SIZE 미만이면 마지막 페이지이므로 중단한다.
 * - 반환된 행이 없으면(빈 배열/null) 중단한다.
 */
async function fetchAllRowsSequential<Row>(
  fetchPage: PageFetcher<Row>,
  context: string,
): Promise<Row[]> {
  const allRows: Row[] = [];
  let from = 0;

  for (;;) {
    const to = from + PAGE_SIZE - 1;
    const { data, error } = await fetchPage(from, to);

    if (error) {
      throw new Error(`${context} 조회 중 오류가 발생했습니다: ${error.message}`);
    }

    if (!data || data.length === 0) {
      break;
    }

    allRows.push(...data);

    if (data.length < PAGE_SIZE) {
      break;
    }

    from += PAGE_SIZE;
  }

  return allRows;
}

/**
 * count 기반 병렬 조회. 총 행수를 알고 있으므로 필요한 페이지 범위를 한꺼번에
 * Promise.all 로 조회한다. 순차 왕복(N회)이 1회 왕복 시간으로 단축된다.
 * Promise.all 은 입력 순서를 보존하므로 행 순서(정렬)도 유지된다.
 */
async function fetchAllRowsByCount<Row>(
  fetchPage: PageFetcher<Row>,
  context: string,
  totalCount: number,
): Promise<Row[]> {
  if (totalCount <= 0) {
    return [];
  }

  const pageCount = Math.ceil(totalCount / PAGE_SIZE);
  const pagePromises: Array<PromiseLike<PageResult<Row>>> = [];

  for (let pageIndex = 0; pageIndex < pageCount; pageIndex += 1) {
    const from = pageIndex * PAGE_SIZE;
    const to = from + PAGE_SIZE - 1;
    pagePromises.push(fetchPage(from, to));
  }

  const pages = await Promise.all(pagePromises);

  const allRows: Row[] = [];
  for (const { data, error } of pages) {
    if (error) {
      throw new Error(`${context} 조회 중 오류가 발생했습니다: ${error.message}`);
    }
    if (data) {
      allRows.push(...data);
    }
  }

  return allRows;
}

/**
 * 페이지네이션 헬퍼. 모든 행을 수집한다.
 *
 * countRows 가 주어지고 count 가 non-null 이면 필요한 페이지 수를 계산해 병렬 조회한다.
 * count 가 null(추정 불가)이거나 countRows 가 없으면 순차 루프로 안전하게 폴백한다.
 *
 * @param fetchPage inclusive 범위 [from, to] 의 페이지를 조회하는 함수
 * @param context   에러 메시지에 포함할 조회 대상 설명
 * @param countRows 총 행수를 구하는 함수(선택). head+count 쿼리 사용을 권장.
 */
export async function fetchAllRows<Row>(
  fetchPage: PageFetcher<Row>,
  context: string,
  countRows?: RowCounter,
): Promise<Row[]> {
  if (countRows) {
    const { count, error } = await countRows();

    if (error) {
      throw new Error(`${context} 조회 중 오류가 발생했습니다: ${error.message}`);
    }

    if (count !== null) {
      return fetchAllRowsByCount(fetchPage, context, count);
    }
    // count 가 null 이면 순차 폴백으로 진행한다.
  }

  return fetchAllRowsSequential(fetchPage, context);
}

// ---------------------------------------------------------------------------
// 순수 변환 함수 (numeric string -> number, snake_case -> camelCase)
// 테스트 가능하도록 개별 export 한다. numeric 은 supabase-js 에서 string 으로 온다.
// ---------------------------------------------------------------------------

/** DB 의 indicators 행 형태(필요한 컬럼만). */
export interface IndicatorRow {
  id: string;
  indicator_type: string;
  source_code: string;
  display_name: string;
}

/** DB 의 exchange_rates 행 형태(필요한 컬럼만). close_rate 는 numeric -> string. */
export interface ExchangeRateRow {
  rate_date: string;
  close_rate: string | number;
}

/** 뷰 daily_prices_with_usd 의 행 형태. numeric 컬럼은 string, null 가능. */
export interface DualCurrencyRow {
  price_date: string;
  close_price_krw: string | number;
  usd_krw_rate: string | number | null;
  close_price_usd: string | number | null;
}

/** numeric(문자열 또는 숫자)을 number 로 변환한다. */
function toNumber(value: string | number): number {
  return typeof value === "number" ? value : Number(value);
}

/** null 을 유지하면서 numeric 을 number 로 변환한다. */
function toNullableNumber(value: string | number | null): number | null {
  return value === null ? null : toNumber(value);
}

export function mapIndicatorRow(row: IndicatorRow): Indicator {
  return {
    id: row.id,
    indicatorType: row.indicator_type,
    sourceCode: row.source_code,
    displayName: row.display_name,
  };
}

export function mapExchangeRateRow(row: ExchangeRateRow): ExchangeRatePoint {
  return {
    rateDate: row.rate_date,
    closeRate: toNumber(row.close_rate),
  };
}

export function mapDualCurrencyRow(row: DualCurrencyRow): DualCurrencyPoint {
  return {
    priceDate: row.price_date,
    closePriceKrw: toNumber(row.close_price_krw),
    usdKrwRate: toNullableNumber(row.usd_krw_rate),
    closePriceUsd: toNullableNumber(row.close_price_usd),
  };
}

// ---------------------------------------------------------------------------
// 조회 함수 (Server Component 등 서버에서 호출)
// ---------------------------------------------------------------------------

/** is_active=true 인 지표를 created_at 오름차순으로 조회한다. */
export async function fetchActiveIndicators(): Promise<Indicator[]> {
  const supabase = createSupabaseServerClient();

  const { data, error } = await supabase
    .from("indicators")
    .select("id, indicator_type, source_code, display_name")
    .eq("is_active", true)
    .order("created_at", { ascending: true });

  if (error) {
    throw new Error(`활성 지표 목록 조회 중 오류가 발생했습니다: ${error.message}`);
  }

  return (data ?? []).map(mapIndicatorRow);
}

/** id 로 단일 지표를 조회한다. 없으면 null. */
export async function fetchIndicatorById(
  indicatorId: string,
): Promise<Indicator | null> {
  const supabase = createSupabaseServerClient();

  const { data, error } = await supabase
    .from("indicators")
    .select("id, indicator_type, source_code, display_name")
    .eq("id", indicatorId)
    .maybeSingle();

  if (error) {
    throw new Error(
      `지표(${indicatorId}) 조회 중 오류가 발생했습니다: ${error.message}`,
    );
  }

  return data ? mapIndicatorRow(data) : null;
}

/**
 * USD_KRW 환율 시계열을 rate_date 오름차순으로 전량 조회한다.
 * sinceDate 를 지정하면 해당 날짜 이후(포함)만 조회한다.
 */
export async function fetchExchangeRateHistory(
  sinceDate?: string,
): Promise<ExchangeRatePoint[]> {
  const supabase = createSupabaseServerClient();

  const fetchPage: PageFetcher<ExchangeRateRow> = (from, to) => {
    let query = supabase
      .from("exchange_rates")
      .select("rate_date, close_rate")
      .eq("currency_pair", "USD_KRW")
      .order("rate_date", { ascending: true });

    if (sinceDate) {
      query = query.gte("rate_date", sinceDate);
    }

    return query.range(from, to);
  };

  // 총 행수를 먼저 구해 페이지들을 병렬 조회한다(head+count → 본문 전송 없음).
  const countRows: RowCounter = () => {
    let query = supabase
      .from("exchange_rates")
      .select("rate_date", { count: "exact", head: true })
      .eq("currency_pair", "USD_KRW");

    if (sinceDate) {
      query = query.gte("rate_date", sinceDate);
    }

    return query;
  };

  const rows = await fetchAllRows(fetchPage, "환율 시계열", countRows);
  return rows.map(mapExchangeRateRow);
}

/**
 * 뷰 daily_prices_with_usd 에서 특정 지표의 이중 통화 일봉 시계열을
 * price_date 오름차순으로 전량 조회한다.
 */
export async function fetchDailyPricesWithUsd(
  indicatorId: string,
): Promise<DualCurrencyPoint[]> {
  const supabase = createSupabaseServerClient();

  const fetchPage: PageFetcher<DualCurrencyRow> = (from, to) =>
    supabase
      .from("daily_prices_with_usd")
      .select("price_date, close_price_krw, usd_krw_rate, close_price_usd")
      .eq("indicator_id", indicatorId)
      .order("price_date", { ascending: true })
      .range(from, to);

  // 총 행수를 먼저 구해 페이지들을 병렬 조회한다(head+count → 본문 전송 없음).
  const countRows: RowCounter = () =>
    supabase
      .from("daily_prices_with_usd")
      .select("price_date", { count: "exact", head: true })
      .eq("indicator_id", indicatorId);

  const rows = await fetchAllRows(
    fetchPage,
    `일봉 시계열(${indicatorId})`,
    countRows,
  );
  return rows.map(mapDualCurrencyRow);
}
