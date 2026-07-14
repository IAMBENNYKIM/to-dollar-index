import { describe, expect, it } from "vitest";
import {
  findEndIndex,
  findStartIndex,
  resolvePresetRange,
  resolveRangeIndices,
  subtractDays,
  RANGE_PRESETS,
  type DateRangePreset,
} from "../chartRange";

// 일 단위 연속 날짜 배열 생성 헬퍼. count 개의 "YYYY-MM-DD" 를 오름차순으로 만든다.
function makeDailyDates(startIso: string, count: number): string[] {
  const dates: string[] = [];
  const [year, month, day] = startIso.split("-").map(Number);
  const baseUtc = Date.UTC(year, month - 1, day);
  for (let index = 0; index < count; index += 1) {
    const current = new Date(baseUtc + index * 24 * 60 * 60 * 1000);
    const yyyy = current.getUTCFullYear();
    const mm = String(current.getUTCMonth() + 1).padStart(2, "0");
    const dd = String(current.getUTCDate()).padStart(2, "0");
    dates.push(`${yyyy}-${mm}-${dd}`);
  }
  return dates;
}

describe("subtractDays", () => {
  it("월 경계를 넘어 정확히 역산한다", () => {
    expect(subtractDays("2026-03-01", 1)).toBe("2026-02-28");
  });

  it("연 경계를 넘어 역산한다", () => {
    expect(subtractDays("2026-01-01", 1)).toBe("2025-12-31");
  });

  it("365일 역산", () => {
    // 2025 는 평년이므로 정확히 1년 전.
    expect(subtractDays("2026-07-10", 365)).toBe("2025-07-10");
  });

  it("0일 역산은 동일 날짜", () => {
    expect(subtractDays("2026-07-10", 0)).toBe("2026-07-10");
  });
});

describe("findStartIndex / findEndIndex", () => {
  const dates = ["2026-01-01", "2026-01-05", "2026-01-10", "2026-01-20"];

  it("findStartIndex: 정확히 일치하는 날짜의 인덱스", () => {
    expect(findStartIndex(dates, "2026-01-05")).toBe(1);
  });

  it("findStartIndex: 사이 날짜는 그 이상인 첫 인덱스", () => {
    expect(findStartIndex(dates, "2026-01-06")).toBe(2);
  });

  it("findStartIndex: 데이터보다 이른 날짜 → 0", () => {
    expect(findStartIndex(dates, "2025-12-01")).toBe(0);
  });

  it("findStartIndex: 데이터보다 미래 날짜 → 마지막 인덱스로 clamp", () => {
    expect(findStartIndex(dates, "2026-02-01")).toBe(3);
  });

  it("findEndIndex: 사이 날짜는 그 이하인 마지막 인덱스", () => {
    expect(findEndIndex(dates, "2026-01-06")).toBe(1);
  });

  it("findEndIndex: 데이터보다 미래 날짜 → 마지막 인덱스", () => {
    expect(findEndIndex(dates, "2026-03-01")).toBe(3);
  });

  it("findEndIndex: 데이터보다 이른 날짜 → 0 으로 clamp", () => {
    expect(findEndIndex(dates, "2025-01-01")).toBe(0);
  });
});

describe("resolveRangeIndices", () => {
  const dates = ["2026-01-01", "2026-01-05", "2026-01-10", "2026-01-20"];

  it("범위 안 날짜 구간을 인덱스로 변환", () => {
    expect(resolveRangeIndices(dates, "2026-01-05", "2026-01-10")).toEqual({
      startIndex: 1,
      endIndex: 2,
    });
  });

  it("데이터 범위 밖은 clamp (전체 구간)", () => {
    expect(resolveRangeIndices(dates, "2020-01-01", "2030-01-01")).toEqual({
      startIndex: 0,
      endIndex: 3,
    });
  });

  it("시작 > 종료면 swap 해 방어한다", () => {
    const swapped = resolveRangeIndices(dates, "2026-01-10", "2026-01-05");
    const normal = resolveRangeIndices(dates, "2026-01-05", "2026-01-10");
    expect(swapped).toEqual(normal);
  });

  it("빈 배열 → null", () => {
    expect(resolveRangeIndices([], "2026-01-01", "2026-01-10")).toBeNull();
  });
});

describe("resolvePresetRange", () => {
  // 2025-01-01 부터 400일 연속(마지막 인덱스 399).
  const dates = makeDailyDates("2025-01-01", 400);
  const lastIndex = dates.length - 1;
  const lastDate = dates[lastIndex]; // 2026-02-04

  it("1년 프리셋: 마지막일 - 365일 이상인 첫 인덱스 ~ 마지막", () => {
    const preset: DateRangePreset = { key: "1y", label: "1년", days: 365 };
    const result = resolvePresetRange(dates, preset);

    const expectedStartDate = subtractDays(lastDate, 365);
    const expectedStartIndex = findStartIndex(dates, expectedStartDate);
    expect(result).toEqual({ startIndex: expectedStartIndex, endIndex: lastIndex });
    // 일 단위 연속이므로 시작 인덱스는 정확히 lastIndex - 365.
    expect(result!.startIndex).toBe(lastIndex - 365);
  });

  it("전체 프리셋: [0, 마지막]", () => {
    const preset: DateRangePreset = { key: "all", label: "전체", days: null };
    expect(resolvePresetRange(dates, preset)).toEqual({
      startIndex: 0,
      endIndex: lastIndex,
    });
  });

  it("데이터 범위를 넘는 프리셋(10년)은 전체로 clamp", () => {
    const preset: DateRangePreset = { key: "10y", label: "10년", days: 3650 };
    expect(resolvePresetRange(dates, preset)).toEqual({
      startIndex: 0,
      endIndex: lastIndex,
    });
  });

  it("빈 배열 → null", () => {
    const preset: DateRangePreset = { key: "1y", label: "1년", days: 365 };
    expect(resolvePresetRange([], preset)).toBeNull();
  });

  it("RANGE_PRESETS 는 전체를 마지막에 포함한다", () => {
    const allPreset = RANGE_PRESETS[RANGE_PRESETS.length - 1];
    expect(allPreset.key).toBe("all");
    expect(allPreset.days).toBeNull();
  });
});
