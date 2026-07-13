/**
 * 차트 컴포넌트가 곧바로 사용하기 좋은 도메인 타입 정의.
 *
 * DB(Postgres/PostgREST)는 snake_case 컬럼명과 numeric 타입을 문자열로 반환하지만,
 * 이 타입들은 camelCase 필드명과 number 타입으로 정규화된 형태를 나타낸다.
 */

/** 지표 메타데이터. id 예: 'stock:005930' */
export interface Indicator {
  id: string;
  indicatorType: string;
  sourceCode: string;
  displayName: string;
}

/** 환율 시계열의 한 점 (USD_KRW). */
export interface ExchangeRatePoint {
  /** YYYY-MM-DD 형식의 날짜 문자열. */
  rateDate: string;
  closeRate: number;
}

/**
 * 원화/달러 이중 통화 가격 시계열의 한 점.
 *
 * 환율 데이터가 존재하지 않는(이른) 날짜에는 usdKrwRate 와 closePriceUsd 가 null 이다.
 */
export interface DualCurrencyPoint {
  /** YYYY-MM-DD 형식의 날짜 문자열. */
  priceDate: string;
  closePriceKrw: number;
  usdKrwRate: number | null;
  closePriceUsd: number | null;
}
