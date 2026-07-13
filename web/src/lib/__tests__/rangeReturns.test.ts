import { describe, expect, it } from "vitest";
import {
  calculateRangeReturns,
  resolveZoomIndices,
  type DualCurrencyPoint,
} from "../rangeReturns";

// 테스트용 포인트 생성 헬퍼. usd 가격이 있으면 usdKrwRate 는 임의 값으로 채운다.
function makePoint(
  priceDate: string,
  closePriceKrw: number,
  closePriceUsd: number | null,
): DualCurrencyPoint {
  return {
    priceDate,
    closePriceKrw,
    usdKrwRate: closePriceUsd === null ? null : 1300,
    closePriceUsd,
  };
}

describe("calculateRangeReturns", () => {
  it("상승 구간: krw +10%, usd -5% → 환율효과 -15%p", () => {
    // 시작 krw 100 → 종료 krw 110 = +10%.
    // 시작 usd 100 → 종료 usd 95 = -5%.
    // 환율효과 = usd% - krw% = -5 - 10 = -15%p.
    const points: DualCurrencyPoint[] = [
      makePoint("2026-01-01", 100, 100),
      makePoint("2026-01-02", 110, 95),
    ];

    const result = calculateRangeReturns(points, 0, 1);

    expect(result).not.toBeNull();
    expect(result!.startDate).toBe("2026-01-01");
    expect(result!.endDate).toBe("2026-01-02");
    expect(result!.krwReturnPercent).toBeCloseTo(10, 10);
    expect(result!.usdReturnPercent).toBeCloseTo(-5, 10);
    expect(result!.exchangeRateEffectPercentPoint).toBeCloseTo(-15, 10);
  });

  it("하락 구간: krw -10%, usd -20% → 환율효과 -10%p", () => {
    // krw 200 → 180 = -10%. usd 100 → 80 = -20%. 효과 = -20 - (-10) = -10%p.
    const points: DualCurrencyPoint[] = [
      makePoint("2026-02-01", 200, 100),
      makePoint("2026-02-02", 180, 80),
    ];

    const result = calculateRangeReturns(points, 0, 1);

    expect(result!.krwReturnPercent).toBeCloseTo(-10, 10);
    expect(result!.usdReturnPercent).toBeCloseTo(-20, 10);
    expect(result!.exchangeRateEffectPercentPoint).toBeCloseTo(-10, 10);
  });

  it("시작=끝(동일 인덱스): 모든 수익률 0%", () => {
    const points: DualCurrencyPoint[] = [
      makePoint("2026-03-01", 100, 100),
      makePoint("2026-03-02", 110, 95),
    ];

    const result = calculateRangeReturns(points, 1, 1);

    expect(result!.startDate).toBe("2026-03-02");
    expect(result!.endDate).toBe("2026-03-02");
    expect(result!.krwReturnPercent).toBe(0);
    expect(result!.usdReturnPercent).toBe(0);
    expect(result!.exchangeRateEffectPercentPoint).toBe(0);
  });

  it("단일 포인트 배열 구간: 0%", () => {
    const points: DualCurrencyPoint[] = [makePoint("2026-04-01", 500, 400)];

    const result = calculateRangeReturns(points, 0, 0);

    expect(result!.startDate).toBe("2026-04-01");
    expect(result!.endDate).toBe("2026-04-01");
    expect(result!.krwReturnPercent).toBe(0);
    expect(result!.usdReturnPercent).toBe(0);
    expect(result!.exchangeRateEffectPercentPoint).toBe(0);
  });

  it("경계 usd null: 구간 첫/끝이 null 이고 내부에 non-null 존재 → 내부 non-null 첫/마지막으로 계산", () => {
    // 구간 양끝은 usd null, 내부 d1(usd 100)~d2(usd 95) 로 계산되어야 한다.
    // krw 는 반드시 d1/d2 의 krw(100→110)로 계산 → +10%, usd -5%.
    const points: DualCurrencyPoint[] = [
      makePoint("2026-05-01", 999, null), // 경계 null (사용 안 됨)
      makePoint("2026-05-02", 100, 100), // 첫 non-null usd
      makePoint("2026-05-03", 110, 95), // 마지막 non-null usd
      makePoint("2026-05-04", 888, null), // 경계 null (사용 안 됨)
    ];

    const result = calculateRangeReturns(points, 0, 3);

    // startDate/endDate 가 경계가 아니라 내부 non-null 포인트 날짜인지 검증.
    expect(result!.startDate).toBe("2026-05-02");
    expect(result!.endDate).toBe("2026-05-03");
    expect(result!.krwReturnPercent).toBeCloseTo(10, 10);
    expect(result!.usdReturnPercent).toBeCloseTo(-5, 10);
    expect(result!.exchangeRateEffectPercentPoint).toBeCloseTo(-15, 10);
  });

  it("구간 전체 usd null → krw 만 계산, usd 관련 필드는 null", () => {
    const points: DualCurrencyPoint[] = [
      makePoint("2026-06-01", 100, null),
      makePoint("2026-06-02", 120, null),
    ];

    const result = calculateRangeReturns(points, 0, 1);

    expect(result!.startDate).toBe("2026-06-01");
    expect(result!.endDate).toBe("2026-06-02");
    expect(result!.krwReturnPercent).toBeCloseTo(20, 10);
    expect(result!.usdReturnPercent).toBeNull();
    expect(result!.exchangeRateEffectPercentPoint).toBeNull();
  });

  it("krw 시작값 0 → krwReturnPercent null (환율효과도 null)", () => {
    const points: DualCurrencyPoint[] = [
      makePoint("2026-07-01", 0, 100),
      makePoint("2026-07-02", 110, 95),
    ];

    const result = calculateRangeReturns(points, 0, 1);

    expect(result).not.toBeNull();
    expect(result!.krwReturnPercent).toBeNull();
    // usd 시작값(100)은 유효하므로 usd% 는 계산됨.
    expect(result!.usdReturnPercent).toBeCloseTo(-5, 10);
    // krw% 가 null 이므로 환율효과는 null.
    expect(result!.exchangeRateEffectPercentPoint).toBeNull();
  });

  it("인덱스 정규화: 범위 밖 인덱스는 clamp 된다", () => {
    const points: DualCurrencyPoint[] = [
      makePoint("2026-08-01", 100, 100),
      makePoint("2026-08-02", 110, 95),
    ];

    // -5 → 0, 99 → 1 로 clamp 되어 전체 구간과 동일.
    const result = calculateRangeReturns(points, -5, 99);

    expect(result!.startDate).toBe("2026-08-01");
    expect(result!.endDate).toBe("2026-08-02");
    expect(result!.krwReturnPercent).toBeCloseTo(10, 10);
  });

  it("인덱스 정규화: start > end 면 swap 된다", () => {
    const points: DualCurrencyPoint[] = [
      makePoint("2026-09-01", 100, 100),
      makePoint("2026-09-02", 110, 95),
    ];

    const swapped = calculateRangeReturns(points, 1, 0);
    const normal = calculateRangeReturns(points, 0, 1);

    expect(swapped).toEqual(normal);
  });

  it("빈 배열 → null", () => {
    expect(calculateRangeReturns([], 0, 0)).toBeNull();
  });
});

describe("resolveZoomIndices", () => {
  it("0/100 퍼센트 → 전체 구간(첫/마지막 인덱스)", () => {
    const result = resolveZoomIndices(10, 0, 100);
    expect(result).toEqual({ startIndex: 0, endIndex: 9 });
  });

  it("중간 퍼센트 환산 (반올림)", () => {
    // 총 11 포인트 → maxIndex 10. 25% → 2.5 → 반올림 3, 75% → 7.5 → 반올림 8.
    const result = resolveZoomIndices(11, 25, 75);
    expect(result).toEqual({ startIndex: 3, endIndex: 8 });
  });

  it("범위를 벗어난 퍼센트는 clamp 된다", () => {
    const result = resolveZoomIndices(5, -10, 250);
    expect(result).toEqual({ startIndex: 0, endIndex: 4 });
  });

  it("포인트 1개 → 항상 0", () => {
    const result = resolveZoomIndices(1, 0, 100);
    expect(result).toEqual({ startIndex: 0, endIndex: 0 });
  });
});
