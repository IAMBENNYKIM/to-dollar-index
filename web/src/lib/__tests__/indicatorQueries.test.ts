import { describe, expect, it, vi } from "vitest";
import {
  PAGE_SIZE,
  fetchAllRows,
  mapDualCurrencyRow,
  mapExchangeRateRow,
  mapIndicatorRow,
  type DualCurrencyRow,
  type ExchangeRateRow,
  type IndicatorRow,
  type PageFetcher,
  type PageResult,
} from "../indicatorQueries";

describe("변환 함수", () => {
  describe("mapIndicatorRow", () => {
    it("snake_case 컬럼을 camelCase 필드로 매핑한다", () => {
      const row: IndicatorRow = {
        id: "stock:005930",
        indicator_type: "stock",
        source_code: "005930",
        display_name: "삼성전자",
      };

      expect(mapIndicatorRow(row)).toEqual({
        id: "stock:005930",
        indicatorType: "stock",
        sourceCode: "005930",
        displayName: "삼성전자",
      });
    });
  });

  describe("mapExchangeRateRow", () => {
    it("numeric 문자열 close_rate 를 number 로 변환하고 날짜 문자열은 유지한다", () => {
      const row: ExchangeRateRow = {
        rate_date: "2024-01-02",
        close_rate: "1309.50",
      };

      const point = mapExchangeRateRow(row);

      expect(point).toEqual({ rateDate: "2024-01-02", closeRate: 1309.5 });
      expect(typeof point.closeRate).toBe("number");
      expect(typeof point.rateDate).toBe("string");
    });

    it("이미 number 인 close_rate 도 그대로 number 로 처리한다", () => {
      const row: ExchangeRateRow = { rate_date: "2024-01-03", close_rate: 1310 };
      expect(mapExchangeRateRow(row).closeRate).toBe(1310);
    });
  });

  describe("mapDualCurrencyRow", () => {
    it("모든 numeric 값이 존재하면 number 로 변환한다", () => {
      const row: DualCurrencyRow = {
        price_date: "2024-05-10",
        close_price_krw: "78900.00",
        usd_krw_rate: "1360.20",
        close_price_usd: "58.006175",
      };

      const point = mapDualCurrencyRow(row);

      expect(point).toEqual({
        priceDate: "2024-05-10",
        closePriceKrw: 78900,
        usdKrwRate: 1360.2,
        closePriceUsd: 58.006175,
      });
    });

    it("환율 데이터 이전 날짜의 null usd 컬럼은 null 로 유지한다", () => {
      const row: DualCurrencyRow = {
        price_date: "2010-01-04",
        close_price_krw: "16180.00",
        usd_krw_rate: null,
        close_price_usd: null,
      };

      const point = mapDualCurrencyRow(row);

      expect(point.priceDate).toBe("2010-01-04");
      expect(point.closePriceKrw).toBe(16180);
      expect(point.usdKrwRate).toBeNull();
      expect(point.closePriceUsd).toBeNull();
    });

    it("krw 는 값이 있고 usd 만 null 인 경우도 각각 올바르게 처리한다", () => {
      const row: DualCurrencyRow = {
        price_date: "2010-06-15",
        close_price_krw: "20000",
        usd_krw_rate: null,
        close_price_usd: null,
      };

      const point = mapDualCurrencyRow(row);
      expect(point.closePriceKrw).toBe(20000);
      expect(point.usdKrwRate).toBeNull();
    });
  });
});

describe("fetchAllRows 페이지네이션 헬퍼", () => {
  /**
   * 전체 rowCount 개의 행을 PAGE_SIZE 단위로 반환하는 가짜 PageFetcher 를 만든다.
   * 각 행은 인덱스를 담은 객체이며, 호출된 [from, to] 범위를 기록한다.
   */
  function makeFakeFetcher(rowCount: number): {
    fetchPage: PageFetcher<{ index: number }>;
    calls: Array<{ from: number; to: number }>;
  } {
    const calls: Array<{ from: number; to: number }> = [];

    const fetchPage: PageFetcher<{ index: number }> = (from, to) => {
      calls.push({ from, to });
      // to 는 inclusive 이므로 슬라이스는 to + 1 까지.
      const slice: Array<{ index: number }> = [];
      for (let index = from; index <= to && index < rowCount; index += 1) {
        slice.push({ index });
      }
      const result: PageResult<{ index: number }> = { data: slice, error: null };
      return Promise.resolve(result);
    };

    return { fetchPage, calls };
  }

  it("999행(1페이지 미만)이면 한 번만 조회하고 전량 수집한다", async () => {
    const { fetchPage, calls } = makeFakeFetcher(999);

    const rows = await fetchAllRows(fetchPage, "테스트");

    expect(rows).toHaveLength(999);
    expect(calls).toEqual([{ from: 0, to: PAGE_SIZE - 1 }]);
  });

  it("정확히 1000행이면 두 번째 페이지가 빈 것을 확인 후 종료한다", async () => {
    const { fetchPage, calls } = makeFakeFetcher(1000);

    const rows = await fetchAllRows(fetchPage, "테스트");

    // 1페이지가 정확히 가득 찼으므로 다음 페이지를 한 번 더 요청한 뒤 빈 결과로 종료한다.
    expect(rows).toHaveLength(1000);
    expect(calls).toEqual([
      { from: 0, to: 999 },
      { from: 1000, to: 1999 },
    ]);
    expect(rows[0]).toEqual({ index: 0 });
    expect(rows[999]).toEqual({ index: 999 });
  });

  it("1001행이면 두 페이지에 걸쳐 전량 수집한다", async () => {
    const { fetchPage, calls } = makeFakeFetcher(1001);

    const rows = await fetchAllRows(fetchPage, "테스트");

    expect(rows).toHaveLength(1001);
    expect(calls).toEqual([
      { from: 0, to: 999 },
      { from: 1000, to: 1999 },
    ]);
    expect(rows[1000]).toEqual({ index: 1000 });
  });

  it("여러 페이지(2500행)에 걸친 데이터를 순서대로 수집한다", async () => {
    const { fetchPage, calls } = makeFakeFetcher(2500);

    const rows = await fetchAllRows(fetchPage, "테스트");

    expect(rows).toHaveLength(2500);
    expect(calls).toHaveLength(3);
    expect(rows.map((row) => row.index)).toEqual(
      Array.from({ length: 2500 }, (_unused, index) => index),
    );
  });

  it("빈 결과(0행)면 한 번 조회 후 종료한다", async () => {
    const { fetchPage, calls } = makeFakeFetcher(0);

    const rows = await fetchAllRows(fetchPage, "테스트");

    expect(rows).toEqual([]);
    expect(calls).toEqual([{ from: 0, to: PAGE_SIZE - 1 }]);
  });

  it("data 가 null 이어도 안전하게 빈 배열을 반환한다", async () => {
    const fetchPage = vi.fn<PageFetcher<{ index: number }>>().mockResolvedValue({
      data: null,
      error: null,
    });

    const rows = await fetchAllRows(fetchPage, "테스트");

    expect(rows).toEqual([]);
    expect(fetchPage).toHaveBeenCalledTimes(1);
  });

  it("에러가 반환되면 context 와 error.message 를 포함해 throw 한다", async () => {
    const fetchPage: PageFetcher<{ index: number }> = () =>
      Promise.resolve({ data: null, error: { message: "permission denied" } });

    await expect(fetchAllRows(fetchPage, "환율 시계열")).rejects.toThrow(
      "환율 시계열 조회 중 오류가 발생했습니다: permission denied",
    );
  });
});
