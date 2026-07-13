// 구간 수익률 표시용 순수 포맷 함수 모음.
//
// RangeReturnPanel 이 사용한다. 표시 규칙:
// - 소수 1자리 고정.
// - 부호를 명시한다. 양수는 "+", 음수는 U+2212(−) 마이너스 기호(하이픈 아님).
// - null / 비유한 값은 "—" 로 표시한다.
// - 반올림 결과가 0 이면 부호 없이 "0.0" 으로 표시해 "−0.0" 같은 표기를 피한다.

/** 진짜 마이너스 기호(U+2212). ASCII 하이픈(-)과 구분된다. */
const MINUS_SIGN = "−";

/** 값이 없을 때 표시할 대체 문자열. */
export const EMPTY_VALUE_TEXT = "—";

const PERCENT_FORMATTER = new Intl.NumberFormat("ko-KR", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

/** 수익률 방향. 부호 색/아이콘 결정에 사용한다. */
export type ReturnSignDirection = "up" | "down" | "flat";

/**
 * 소수 1자리 반올림 기준의 방향을 반환한다.
 * null/비유한/반올림 0 은 "flat".
 */
export function returnDirectionOf(value: number | null): ReturnSignDirection {
  if (value === null || !Number.isFinite(value)) {
    return "flat";
  }
  const roundedToDisplay = Number(value.toFixed(1));
  if (roundedToDisplay > 0) return "up";
  if (roundedToDisplay < 0) return "down";
  return "flat";
}

/**
 * 부호 있는 값을 "부호+숫자+접미사" 로 포맷한다.
 * 부호는 표시 소수 1자리로 반올림한 결과를 기준으로 결정한다.
 */
function formatSignedNumber(value: number | null, suffix: string): string {
  if (value === null || !Number.isFinite(value)) {
    return EMPTY_VALUE_TEXT;
  }

  const roundedToDisplay = Number(value.toFixed(1));
  const sign =
    roundedToDisplay > 0 ? "+" : roundedToDisplay < 0 ? MINUS_SIGN : "";
  const magnitudeText = PERCENT_FORMATTER.format(Math.abs(value));

  return `${sign}${magnitudeText}${suffix}`;
}

/**
 * 수익률(%)을 부호와 함께 포맷한다. 예: 12.34 → "+12.3%", -8.1 → "−8.1%",
 * 0 → "0.0%", null → "—".
 */
export function formatSignedPercent(value: number | null): string {
  return formatSignedNumber(value, "%");
}

/**
 * 퍼센트포인트(%p) 값을 부호와 함께 포맷한다. 예: -20.4 → "−20.4%p", null → "—".
 */
export function formatSignedPercentPoint(value: number | null): string {
  return formatSignedNumber(value, "%p");
}
