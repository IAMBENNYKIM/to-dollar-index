// 차트 구간(원화 vs 달러 환산) 수익률 계산 순수 함수 모음.
//
// 통합 시 아래 DualCurrencyPoint 로컬 타입은 src/lib/types.ts 의 동일 구조 타입
// import 로 교체될 예정이다. (다른 작업이 types.ts 를 작성 중이므로 여기서는
// 직접 참조하지 않고 동일 구조의 로컬 타입을 정의해 사용한다.)

/**
 * 하루치 원화/달러 가격 포인트.
 * priceDate 는 "YYYY-MM-DD" 형식이며 배열은 날짜 오름차순으로 정렬되어 있다고 가정한다.
 */
export interface DualCurrencyPoint {
  priceDate: string;
  closePriceKrw: number;
  usdKrwRate: number | null;
  closePriceUsd: number | null;
}

/**
 * 구간 수익률 계산 결과.
 *
 * krwReturnPercent 는 시작값이 0/비유한이면 null 이 될 수 있으므로 number | null 이다.
 * usdReturnPercent, exchangeRateEffectPercentPoint 는 구간 내 달러 데이터가 없거나
 * 시작값이 유효하지 않으면 null 이다.
 */
export interface RangeReturns {
  startDate: string;
  endDate: string;
  krwReturnPercent: number | null;
  usdReturnPercent: number | null;
  exchangeRateEffectPercentPoint: number | null;
}

/**
 * 값을 [min, max] 범위로 clamp 한다.
 */
function clamp(value: number, min: number, max: number): number {
  if (value < min) return min;
  if (value > max) return max;
  return value;
}

/**
 * 시작값 대비 종료값의 수익률(%)을 계산한다.
 *
 * 0 나눗셈 방어: 시작값이 0 이거나 유한하지 않으면(NaN/Infinity) null 을 반환한다.
 * 시작=종료 같은 값이면 0 을 반환한다.
 */
function computeReturnPercent(startValue: number, endValue: number): number | null {
  if (startValue === 0 || !Number.isFinite(startValue)) {
    return null;
  }
  return (endValue / startValue - 1) * 100;
}

/**
 * 구간 [rangeStartIndex, rangeEndIndex] 의 원화/달러 환산 수익률을 계산한다.
 *
 * 인덱스 정규화: 배열 범위 밖이면 clamp, start > end 면 swap 한다.
 * 정규화 후에도 유효 포인트가 없으면(빈 배열) null 을 반환한다.
 *
 * 비교 기준점 선택(정확성 핵심): krw 와 usd 수익률은 반드시 동일한 두 시점으로
 * 계산해야 환율 효과(%p)가 의미를 가진다. 따라서 구간 내 closePriceUsd 가 non-null 인
 * 첫/마지막 포인트를 찾아 그 두 시점으로 계산한다. 구간 전체가 usd null 이면 구간의
 * 첫/마지막 포인트로 krw 수익률만 계산하고 usd 관련 필드는 null 로 둔다.
 */
export function calculateRangeReturns(
  points: DualCurrencyPoint[],
  rangeStartIndex: number,
  rangeEndIndex: number,
): RangeReturns | null {
  if (points.length === 0) {
    return null;
  }

  const maxIndex = points.length - 1;
  let startIndex = clamp(Math.trunc(rangeStartIndex), 0, maxIndex);
  let endIndex = clamp(Math.trunc(rangeEndIndex), 0, maxIndex);
  if (startIndex > endIndex) {
    [startIndex, endIndex] = [endIndex, startIndex];
  }

  // 구간 내 closePriceUsd 가 non-null 인 첫/마지막 포인트를 찾는다.
  let firstUsdIndex = -1;
  let lastUsdIndex = -1;
  for (let index = startIndex; index <= endIndex; index += 1) {
    if (points[index].closePriceUsd !== null) {
      if (firstUsdIndex === -1) {
        firstUsdIndex = index;
      }
      lastUsdIndex = index;
    }
  }

  if (firstUsdIndex !== -1) {
    // 달러 데이터가 있는 경우: 동일한 두 시점(첫/마지막 non-null usd)으로 모두 계산.
    const startPoint = points[firstUsdIndex];
    const endPoint = points[lastUsdIndex];

    const krwReturnPercent = computeReturnPercent(
      startPoint.closePriceKrw,
      endPoint.closePriceKrw,
    );
    const usdReturnPercent = computeReturnPercent(
      startPoint.closePriceUsd as number,
      endPoint.closePriceUsd as number,
    );

    const exchangeRateEffectPercentPoint =
      krwReturnPercent !== null && usdReturnPercent !== null
        ? usdReturnPercent - krwReturnPercent
        : null;

    return {
      startDate: startPoint.priceDate,
      endDate: endPoint.priceDate,
      krwReturnPercent,
      usdReturnPercent,
      exchangeRateEffectPercentPoint,
    };
  }

  // 구간 전체가 usd null 인 경우: 구간 첫/마지막 포인트로 krw 수익률만 계산.
  const startPoint = points[startIndex];
  const endPoint = points[endIndex];
  const krwReturnPercent = computeReturnPercent(
    startPoint.closePriceKrw,
    endPoint.closePriceKrw,
  );

  return {
    startDate: startPoint.priceDate,
    endDate: endPoint.priceDate,
    krwReturnPercent,
    usdReturnPercent: null,
    exchangeRateEffectPercentPoint: null,
  };
}

/**
 * ECharts dataZoom 이벤트의 start/end 퍼센트(0~100)를 배열 인덱스로 환산한다.
 *
 * 퍼센트를 (totalPointCount - 1) 스케일에 반올림 매핑하고 유효 인덱스 범위로 clamp 한다.
 * 포인트가 1개 이하이면 항상 0 을 반환한다.
 */
export function resolveZoomIndices(
  totalPointCount: number,
  dataZoomStartPercent: number,
  dataZoomEndPercent: number,
): { startIndex: number; endIndex: number } {
  const maxIndex = Math.max(0, totalPointCount - 1);

  const toIndex = (percent: number): number => {
    const clampedPercent = clamp(percent, 0, 100);
    const rawIndex = Math.round((clampedPercent / 100) * maxIndex);
    return clamp(rawIndex, 0, maxIndex);
  };

  return {
    startIndex: toIndex(dataZoomStartPercent),
    endIndex: toIndex(dataZoomEndPercent),
  };
}
