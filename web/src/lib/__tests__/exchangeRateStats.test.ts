import { describe, expect, it } from "vitest";
import {
  getCurrentRate,
  getDailyChange,
  getRangeChangePercent,
} from "../exchangeRateStats";
import type { ExchangeRatePoint } from "../types";

function makePoint(rateDate: string, closeRate: number): ExchangeRatePoint {
  return { rateDate, closeRate };
}

describe("getCurrentRate", () => {
  it("마지막(최근) 포인트의 환율을 반환한다", () => {
    const points = [
      makePoint("2026-07-01", 1300),
      makePoint("2026-07-02", 1325.5),
    ];
    expect(getCurrentRate(points)).toBe(1325.5);
  });

  it("빈 배열 → null", () => {
    expect(getCurrentRate([])).toBeNull();
  });
});

describe("getDailyChange", () => {
  it("직전 포인트 대비 절대값과 % 를 계산한다", () => {
    // 1300 → 1313 : +13, +1%.
    const points = [makePoint("2026-07-01", 1300), makePoint("2026-07-02", 1313)];
    const change = getDailyChange(points);
    expect(change).not.toBeNull();
    expect(change!.absolute).toBeCloseTo(13, 10);
    expect(change!.percent).toBeCloseTo(1, 10);
  });

  it("하락도 부호를 유지한다", () => {
    // 1400 → 1386 : -14, -1%.
    const points = [makePoint("2026-07-01", 1400), makePoint("2026-07-02", 1386)];
    const change = getDailyChange(points);
    expect(change!.absolute).toBeCloseTo(-14, 10);
    expect(change!.percent).toBeCloseTo(-1, 10);
  });

  it("포인트가 1개면 null", () => {
    expect(getDailyChange([makePoint("2026-07-01", 1300)])).toBeNull();
  });

  it("빈 배열 → null", () => {
    expect(getDailyChange([])).toBeNull();
  });

  it("직전 값이 0 이면 percent 는 null, absolute 는 유지", () => {
    const points = [makePoint("2026-07-01", 0), makePoint("2026-07-02", 1300)];
    const change = getDailyChange(points);
    expect(change!.absolute).toBe(1300);
    expect(change!.percent).toBeNull();
  });
});

describe("getRangeChangePercent", () => {
  it("30일 전(근접 과거) 포인트 대비 변동률을 계산한다", () => {
    // 마지막 07-31, 30일 전 목표 = 07-01. 07-01 포인트(1300) 기준 → 1391 = +7%.
    const points = [
      makePoint("2026-07-01", 1300),
      makePoint("2026-07-15", 1350),
      makePoint("2026-07-31", 1391),
    ];
    expect(getRangeChangePercent(points, 30)).toBeCloseTo(7, 10);
  });

  it("정확히 N일 전 데이터가 없으면 목표일 이전의 가장 최근 포인트를 사용한다", () => {
    // 마지막 07-31, 30일 전 목표 = 07-01. 07-01 데이터 없음 → 그 이전 가장 최근인 06-28(1250) 사용.
    // 1250 → 1375 = +10%.
    const points = [
      makePoint("2026-06-28", 1250),
      makePoint("2026-07-03", 1300),
      makePoint("2026-07-31", 1375),
    ];
    expect(getRangeChangePercent(points, 30)).toBeCloseTo(10, 10);
  });

  it("이력이 N일에 못 미치면(목표일 이전 포인트 없음) null", () => {
    // 마지막 07-10, 30일 전 목표 = 06-10. 그 이전 포인트가 없다.
    const points = [
      makePoint("2026-07-01", 1300),
      makePoint("2026-07-10", 1330),
    ];
    expect(getRangeChangePercent(points, 30)).toBeNull();
  });

  it("1년(365일) 변동률도 같은 규칙으로 계산한다", () => {
    // 마지막 2026-07-12, 365일 전 목표 = 2025-07-12. 2025-07-12 포인트(1200) 기준 → 1320 = +10%.
    const points = [
      makePoint("2025-07-12", 1200),
      makePoint("2026-01-01", 1280),
      makePoint("2026-07-12", 1320),
    ];
    expect(getRangeChangePercent(points, 365)).toBeCloseTo(10, 10);
  });

  it("기준값이 0 이면 null", () => {
    const points = [
      makePoint("2026-06-01", 0),
      makePoint("2026-07-31", 1300),
    ];
    expect(getRangeChangePercent(points, 30)).toBeNull();
  });

  it("포인트가 1개 이하면 null", () => {
    expect(getRangeChangePercent([makePoint("2026-07-01", 1300)], 30)).toBeNull();
    expect(getRangeChangePercent([], 30)).toBeNull();
  });
});
