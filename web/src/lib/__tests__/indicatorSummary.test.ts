import { describe, expect, it } from "vitest";
import { buildIndicatorSummary } from "../indicatorSummary";
import type { DualCurrencyPoint } from "../types";

function makePoint(
  priceDate: string,
  closePriceKrw: number,
  closePriceUsd: number | null,
): DualCurrencyPoint {
  return {
    priceDate,
    closePriceKrw,
    usdKrwRate: closePriceUsd === null ? null : closePriceKrw / closePriceUsd,
    closePriceUsd,
  };
}

describe("buildIndicatorSummary", () => {
  it("빈 배열이면 null", () => {
    expect(buildIndicatorSummary([])).toBeNull();
  });

  it("포인트가 1개면 변동률 null, 최신값은 채운다", () => {
    const summary = buildIndicatorSummary([
      makePoint("2026-07-14", 78900, 57.5),
    ]);
    expect(summary).not.toBeNull();
    expect(summary!.latestDate).toBe("2026-07-14");
    expect(summary!.latestKrw).toBe(78900);
    expect(summary!.latestUsd).toBe(57.5);
    expect(summary!.changePercentKrw).toBeNull();
  });

  it("포인트가 2개면 직전 대비 원화 변동률을 계산한다", () => {
    // 1000 → 1100 = +10%.
    const summary = buildIndicatorSummary([
      makePoint("2026-07-13", 1000, 0.72),
      makePoint("2026-07-14", 1100, 0.79),
    ]);
    expect(summary!.latestKrw).toBe(1100);
    expect(summary!.changePercentKrw).toBeCloseTo(10, 10);
  });

  it("하락도 부호를 유지한다", () => {
    // 1400 → 1386 = -1%.
    const summary = buildIndicatorSummary([
      makePoint("2026-07-13", 1400, 1),
      makePoint("2026-07-14", 1386, 1),
    ]);
    expect(summary!.changePercentKrw).toBeCloseTo(-1, 10);
  });

  it("직전 원화값이 0 이면 변동률 null(0 나눗셈 방어)", () => {
    const summary = buildIndicatorSummary([
      makePoint("2026-07-13", 0, null),
      makePoint("2026-07-14", 1100, 0.79),
    ]);
    expect(summary!.latestKrw).toBe(1100);
    expect(summary!.changePercentKrw).toBeNull();
  });

  it("최신 포인트의 usd 가 null 이면 latestUsd 는 null 로 유지된다", () => {
    const summary = buildIndicatorSummary([
      makePoint("2010-01-03", 16000, null),
      makePoint("2010-01-04", 16180, null),
    ]);
    expect(summary!.latestUsd).toBeNull();
    expect(summary!.changePercentKrw).toBeCloseTo((16180 / 16000 - 1) * 100, 10);
  });
});
