import { describe, expect, it } from "vitest";
import {
  EMPTY_VALUE_TEXT,
  formatSignedPercent,
  formatSignedPercentPoint,
  returnDirectionOf,
} from "../../lib/formatReturns";

const MINUS_SIGN = "−";

describe("formatSignedPercent", () => {
  it("양수는 '+' 부호와 소수 1자리로 표시한다", () => {
    expect(formatSignedPercent(12.34)).toBe("+12.3%");
  });

  it("음수는 U+2212 마이너스 기호와 소수 1자리로 표시한다", () => {
    expect(formatSignedPercent(-8.14)).toBe(`${MINUS_SIGN}8.1%`);
    // ASCII 하이픈이 아니라 진짜 마이너스 기호여야 한다.
    expect(formatSignedPercent(-8.14).startsWith("-")).toBe(false);
  });

  it("0 은 부호 없이 '0.0%' 로 표시한다", () => {
    expect(formatSignedPercent(0)).toBe("0.0%");
  });

  it("반올림 결과가 0 이면 부호를 붙이지 않는다 (−0.0 방지)", () => {
    expect(formatSignedPercent(-0.04)).toBe("0.0%");
    expect(formatSignedPercent(0.04)).toBe("0.0%");
  });

  it("반올림(소수 1자리)이 적용된다", () => {
    expect(formatSignedPercent(1.25)).toBe("+1.3%");
    expect(formatSignedPercent(-1.25)).toBe(`${MINUS_SIGN}1.3%`);
  });

  it("null 은 대체 문자열로 표시한다", () => {
    expect(formatSignedPercent(null)).toBe(EMPTY_VALUE_TEXT);
  });

  it("NaN/Infinity 도 대체 문자열로 표시한다", () => {
    expect(formatSignedPercent(Number.NaN)).toBe(EMPTY_VALUE_TEXT);
    expect(formatSignedPercent(Number.POSITIVE_INFINITY)).toBe(EMPTY_VALUE_TEXT);
  });
});

describe("formatSignedPercentPoint", () => {
  it("%p 접미사를 붙인다", () => {
    expect(formatSignedPercentPoint(-20.44)).toBe(`${MINUS_SIGN}20.4%p`);
    expect(formatSignedPercentPoint(3.1)).toBe("+3.1%p");
  });

  it("null 은 대체 문자열", () => {
    expect(formatSignedPercentPoint(null)).toBe(EMPTY_VALUE_TEXT);
  });
});

describe("returnDirectionOf", () => {
  it("양수 → up, 음수 → down, 0 → flat", () => {
    expect(returnDirectionOf(1.2)).toBe("up");
    expect(returnDirectionOf(-1.2)).toBe("down");
    expect(returnDirectionOf(0)).toBe("flat");
  });

  it("반올림 결과가 0 이면 flat", () => {
    expect(returnDirectionOf(-0.04)).toBe("flat");
  });

  it("null/비유한은 flat", () => {
    expect(returnDirectionOf(null)).toBe("flat");
    expect(returnDirectionOf(Number.NaN)).toBe("flat");
  });
});
