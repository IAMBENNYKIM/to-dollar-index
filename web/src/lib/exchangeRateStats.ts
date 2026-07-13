// 환율 시계열 통계 계산 순수 함수 모음.
//
// 입력 배열(ExchangeRatePoint[])은 rateDate 오름차순으로 정렬되어 있다고 가정한다.
// (fetchExchangeRateHistory 가 rate_date ascending 으로 반환한다.)
// 모든 함수는 부수효과가 없으며, 데이터가 부족하면 null 을 반환해 UI 에서 방어할 수 있게 한다.

import type { ExchangeRatePoint } from "./types";

/** 하루 사이 변동. percent 는 기준값이 0/비유한이면 null. */
export interface DailyChange {
  /** 절대 변동값 (원). */
  absolute: number;
  /** 변동률 (%). 기준값이 0 이거나 유한하지 않으면 null. */
  percent: number | null;
}

const MILLISECONDS_PER_DAY = 24 * 60 * 60 * 1000;

/** "YYYY-MM-DD" 를 UTC 자정 기준 epoch(ms) 로 변환한다. 파싱 실패 시 NaN. */
function toUtcMillis(dateString: string): number {
  return Date.parse(`${dateString}T00:00:00Z`);
}

/** 시작값 대비 종료값의 변동률(%). 시작값이 0/비유한이면 null. */
function computePercentChange(baseValue: number, currentValue: number): number | null {
  if (baseValue === 0 || !Number.isFinite(baseValue)) {
    return null;
  }
  return (currentValue / baseValue - 1) * 100;
}

/** 가장 최근(마지막) 환율값. 비어 있으면 null. */
export function getCurrentRate(points: ExchangeRatePoint[]): number | null {
  if (points.length === 0) {
    return null;
  }
  return points[points.length - 1].closeRate;
}

/**
 * 전일 대비 변동(절대값 + %).
 * 포인트가 2개 미만이면 null. (직전 관측치와 비교하므로 달력상 '전일'이 아니라
 * 시계열상 직전 데이터 포인트 기준이다.)
 */
export function getDailyChange(points: ExchangeRatePoint[]): DailyChange | null {
  if (points.length < 2) {
    return null;
  }
  const currentValue = points[points.length - 1].closeRate;
  const previousValue = points[points.length - 2].closeRate;
  return {
    absolute: currentValue - previousValue,
    percent: computePercentChange(previousValue, currentValue),
  };
}

/**
 * 마지막 관측일로부터 N일 전 대비 변동률(%).
 *
 * 기준점 선택: 마지막 날짜에서 N 달력일을 뺀 목표일(targetDate)을 구하고,
 * targetDate 이전(포함) 중 가장 최근 포인트를 기준으로 삼는다. (주말·휴일로 정확히
 * N일 전 데이터가 없을 수 있으므로 근접한 과거 포인트를 사용한다.)
 *
 * 이력이 N일에 못 미쳐 targetDate 이전 포인트가 하나도 없으면 null 을 반환한다.
 */
export function getRangeChangePercent(
  points: ExchangeRatePoint[],
  days: number,
): number | null {
  if (points.length < 2) {
    return null;
  }

  const lastPoint = points[points.length - 1];
  const targetMillis = toUtcMillis(lastPoint.rateDate) - days * MILLISECONDS_PER_DAY;
  if (!Number.isFinite(targetMillis)) {
    return null;
  }

  // targetDate 이전(포함) 중 가장 최근 포인트를 뒤에서부터 탐색한다.
  let baseIndex = -1;
  for (let index = points.length - 1; index >= 0; index -= 1) {
    if (toUtcMillis(points[index].rateDate) <= targetMillis) {
      baseIndex = index;
      break;
    }
  }

  if (baseIndex === -1) {
    // 이력이 부족해 N일 전 기준점이 없다.
    return null;
  }

  return computePercentChange(points[baseIndex].closeRate, lastPoint.closeRate);
}
