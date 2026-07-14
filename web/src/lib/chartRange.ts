// 차트 기간 프리셋/날짜 입력을 정렬된 priceDate 배열의 인덱스 구간으로 변환하는 순수 함수 모음.
//
// priceDate 는 "YYYY-MM-DD" 형식이며, 이 형식은 사전식(lexicographic) 문자열 비교가
// 곧 날짜 순서와 일치하므로 Date 파싱 없이 문자열 비교로 인덱스를 탐색한다.
// (배열은 날짜 오름차순으로 정렬되어 있다고 가정한다.)

/** 인덱스 구간. startIndex <= endIndex 를 보장한다. */
export interface RangeIndices {
  startIndex: number;
  endIndex: number;
}

/**
 * 기간 프리셋 정의.
 * days 가 null 이면 "전체"(데이터 시작~끝)를 의미한다.
 */
export interface DateRangePreset {
  key: string;
  label: string;
  days: number | null;
}

/**
 * 상단 프리셋 버튼 목록. 데이터 범위를 넘는 프리셋은 자동으로 전체로 clamp 된다
 * (subtractDays 로 계산한 시작일이 데이터 첫 날짜보다 이르면 첫 인덱스 0 이 선택됨).
 */
export const RANGE_PRESETS: DateRangePreset[] = [
  { key: "1w", label: "1주", days: 7 },
  { key: "1m", label: "1개월", days: 30 },
  { key: "3m", label: "3개월", days: 90 },
  { key: "6m", label: "6개월", days: 180 },
  { key: "1y", label: "1년", days: 365 },
  { key: "2y", label: "2년", days: 730 },
  { key: "3y", label: "3년", days: 1095 },
  { key: "5y", label: "5년", days: 1825 },
  { key: "10y", label: "10년", days: 3650 },
  { key: "all", label: "전체", days: null },
];

/**
 * "YYYY-MM-DD" 날짜에서 지정 일수만큼 뺀 날짜를 같은 형식으로 반환한다.
 *
 * UTC 기준으로 계산해 로컬 타임존/DST 영향을 받지 않게 한다.
 */
export function subtractDays(isoDate: string, days: number): string {
  const [year, month, day] = isoDate.split("-").map(Number);
  const baseUtcMs = Date.UTC(year, month - 1, day);
  const shifted = new Date(baseUtcMs - days * 24 * 60 * 60 * 1000);
  const shiftedYear = shifted.getUTCFullYear();
  const shiftedMonth = String(shifted.getUTCMonth() + 1).padStart(2, "0");
  const shiftedDay = String(shifted.getUTCDate()).padStart(2, "0");
  return `${shiftedYear}-${shiftedMonth}-${shiftedDay}`;
}

/**
 * 정렬된 날짜 배열에서 targetDate 이상인 첫 포인트의 인덱스를 찾는다.
 * 모든 날짜가 targetDate 이전이면(요청 시작일이 데이터보다 미래) 마지막 인덱스로 clamp.
 */
export function findStartIndex(sortedDates: string[], targetDate: string): number {
  for (let index = 0; index < sortedDates.length; index += 1) {
    if (sortedDates[index] >= targetDate) {
      return index;
    }
  }
  return sortedDates.length - 1;
}

/**
 * 정렬된 날짜 배열에서 targetDate 이하인 마지막 포인트의 인덱스를 찾는다.
 * 모든 날짜가 targetDate 이후이면(요청 종료일이 데이터보다 과거) 첫 인덱스 0 으로 clamp.
 */
export function findEndIndex(sortedDates: string[], targetDate: string): number {
  for (let index = sortedDates.length - 1; index >= 0; index -= 1) {
    if (sortedDates[index] <= targetDate) {
      return index;
    }
  }
  return 0;
}

/**
 * 시작일/종료일(YYYY-MM-DD)을 정렬된 날짜 배열의 인덱스 구간으로 변환한다.
 *
 * - 빈 배열이면 null.
 * - startDate > endDate 로 뒤집혀 들어오면 swap 해 방어한다.
 * - 데이터 범위 밖은 findStart/EndIndex 에서 clamp 된다.
 * - clamp 후에도 startIndex > endIndex 이면(요청 구간이 데이터와 겹치지 않음) swap 한다.
 */
export function resolveRangeIndices(
  sortedDates: string[],
  startDate: string,
  endDate: string,
): RangeIndices | null {
  if (sortedDates.length === 0) {
    return null;
  }

  const [fromDate, toDate] =
    startDate <= endDate ? [startDate, endDate] : [endDate, startDate];

  let startIndex = findStartIndex(sortedDates, fromDate);
  let endIndex = findEndIndex(sortedDates, toDate);
  if (startIndex > endIndex) {
    [startIndex, endIndex] = [endIndex, startIndex];
  }

  return { startIndex, endIndex };
}

/**
 * 프리셋을 정렬된 날짜 배열의 인덱스 구간으로 변환한다.
 *
 * 기준일 = 데이터의 마지막 날짜. 프리셋 일수만큼 역산한 시작일부터 마지막까지.
 * "전체"(days=null)는 [0, maxIndex]. 빈 배열이면 null.
 */
export function resolvePresetRange(
  sortedDates: string[],
  preset: DateRangePreset,
): RangeIndices | null {
  if (sortedDates.length === 0) {
    return null;
  }

  const maxIndex = sortedDates.length - 1;
  if (preset.days === null) {
    return { startIndex: 0, endIndex: maxIndex };
  }

  const lastDate = sortedDates[maxIndex];
  const startDate = subtractDays(lastDate, preset.days);
  return resolveRangeIndices(sortedDates, startDate, lastDate);
}
