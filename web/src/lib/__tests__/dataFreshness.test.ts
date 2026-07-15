import { describe, expect, it } from "vitest";
import {
  evaluateDataFreshness,
  getTodayInSeoul,
} from "../dataFreshness";

describe("getTodayInSeoul", () => {
  it("KST 자정을 넘긴 UTC 시각이면 다음 날짜를 반환한다", () => {
    // UTC 2026-07-14T15:30 = KST 2026-07-15T00:30 → 서울 날짜는 이미 15일.
    const utcAfterSeoulMidnight = new Date("2026-07-14T15:30:00Z");
    expect(getTodayInSeoul(utcAfterSeoulMidnight)).toBe("2026-07-15");
  });

  it("KST 자정 이전 UTC 시각이면 같은 날짜를 반환한다", () => {
    // UTC 2026-07-14T14:00 = KST 2026-07-14T23:00 → 서울 날짜는 아직 14일.
    const utcBeforeSeoulMidnight = new Date("2026-07-14T14:00:00Z");
    expect(getTodayInSeoul(utcBeforeSeoulMidnight)).toBe("2026-07-14");
  });
});

describe("evaluateDataFreshness", () => {
  it("금요일 데이터를 월요일에 조회하면 영업일 1일 지연으로 stale 아님(임계 2)", () => {
    // 2026-07-10(금) 데이터, 2026-07-13(월) 조회. 토·일 제외 → 월요일 1일만 카운트.
    const info = evaluateDataFreshness("2026-07-10", "2026-07-13", 2);
    expect(info.businessDaysBehind).toBe(1);
    expect(info.isStale).toBe(false);
    expect(info.latestDate).toBe("2026-07-10");
  });

  it("주말은 영업일 계산에서 제외한다", () => {
    // 2026-07-10(금) 데이터, 2026-07-12(일) 조회. 토·일뿐이라 영업일 0.
    const info = evaluateDataFreshness("2026-07-10", "2026-07-12", 2);
    expect(info.businessDaysBehind).toBe(0);
    expect(info.isStale).toBe(false);
  });

  it("평일 연속 2일 지연이면 stale(임계 2)", () => {
    // 2026-07-13(월) 데이터, 2026-07-15(수) 조회. 화·수 2 영업일.
    const info = evaluateDataFreshness("2026-07-13", "2026-07-15", 2);
    expect(info.businessDaysBehind).toBe(2);
    expect(info.isStale).toBe(true);
  });

  it("당일(같은 날짜) 조회면 지연 0, stale 아님", () => {
    const info = evaluateDataFreshness("2026-07-15", "2026-07-15", 2);
    expect(info.businessDaysBehind).toBe(0);
    expect(info.isStale).toBe(false);
  });

  it("임계값 경계: businessDaysBehind == 임계값이면 stale", () => {
    // 화·수 2 영업일. 임계 2면 stale, 임계 3이면 stale 아님.
    expect(evaluateDataFreshness("2026-07-13", "2026-07-15", 2).isStale).toBe(true);
    expect(evaluateDataFreshness("2026-07-13", "2026-07-15", 3).isStale).toBe(false);
  });

  it("임계 1이면 영업일 1일 지연도 stale", () => {
    const info = evaluateDataFreshness("2026-07-10", "2026-07-13", 1);
    expect(info.businessDaysBehind).toBe(1);
    expect(info.isStale).toBe(true);
  });

  it("today 가 latestDate 보다 과거이면 지연 0", () => {
    const info = evaluateDataFreshness("2026-07-15", "2026-07-10", 2);
    expect(info.businessDaysBehind).toBe(0);
    expect(info.isStale).toBe(false);
  });
});
