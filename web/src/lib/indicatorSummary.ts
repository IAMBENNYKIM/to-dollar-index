// 홈 대시보드 지표 카드 요약 계산 순수 함수.
//
// 입력 배열(DualCurrencyPoint[])은 priceDate 오름차순으로 정렬되어 있다고 가정한다.
// (fetchLatestDualCurrencyPoints 가 오름차순으로 반환한다.)
// 데이터가 부족하면 null 을 반환하거나 개별 필드를 null 로 두어 UI 에서 방어할 수 있게 한다.

import type { DualCurrencyPoint } from "./types";

/** 지표 카드에 표시할 요약 값. */
export interface IndicatorSummary {
  /** 최신 포인트의 날짜("YYYY-MM-DD"). */
  latestDate: string;
  /** 최신 원화 종가. */
  latestKrw: number;
  /** 최신 달러 환산가. 환율 데이터가 없으면 null. */
  latestUsd: number | null;
  /** 직전 포인트 대비 원화 변동률(%). 포인트 2개 미만 또는 직전값 0/비유한이면 null. */
  changePercentKrw: number | null;
}

/**
 * 오름차순 이중 통화 포인트 배열에서 지표 카드용 요약을 만든다.
 * 빈 배열이면 null 을 반환한다.
 */
export function buildIndicatorSummary(
  points: DualCurrencyPoint[],
): IndicatorSummary | null {
  if (points.length === 0) {
    return null;
  }

  const latestPoint = points[points.length - 1];

  let changePercentKrw: number | null = null;
  if (points.length >= 2) {
    const previousKrw = points[points.length - 2].closePriceKrw;
    if (previousKrw !== 0 && Number.isFinite(previousKrw)) {
      changePercentKrw = (latestPoint.closePriceKrw / previousKrw - 1) * 100;
    }
  }

  return {
    latestDate: latestPoint.priceDate,
    latestKrw: latestPoint.closePriceKrw,
    latestUsd: latestPoint.closePriceUsd,
    changePercentKrw,
  };
}
