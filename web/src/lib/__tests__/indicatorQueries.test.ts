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
  type RowCounter,
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
   * countRows 는 기본적으로 실제 rowCount 를 반환하지만, options.count 로 재정의할 수 있다.
   */
  function makeFakeFetcher(
    rowCount: number,
    options: { count?: number | null } = {},
  ): {
    fetchPage: PageFetcher<{ index: number }>;
    countRows: RowCounter;
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

    const resolvedCount =
      "count" in options ? (options.count as number | null) : rowCount;
    const countRows: RowCounter = () =>
      Promise.resolve({ count: resolvedCount, error: null });

    return { fetchPage, countRows, calls };
  }

  describe("count 기반 병렬 조회", () => {
    it("페이지들을 순차가 아니라 병렬로(동시에) 요청한다", async () => {
      // 수동으로 resolve 하는 지연 fetchPage 로, 첫 페이지가 끝나기 전에
      // 모든 페이지가 이미 요청되었는지(=병렬)를 검증한다.
      const calls: Array<{ from: number; to: number }> = [];
      const resolvers: Array<() => void> = [];

      const fetchPage: PageFetcher<{ index: number }> = (from, to) => {
        calls.push({ from, to });
        return new Promise<PageResult<{ index: number }>>((resolve) => {
          resolvers.push(() => {
            const slice: Array<{ index: number }> = [];
            for (let index = from; index <= to && index < 2500; index += 1) {
              slice.push({ index });
            }
            resolve({ data: slice, error: null });
          });
        });
      };
      const countRows: RowCounter = () =>
        Promise.resolve({ count: 2500, error: null });

      const promise = fetchAllRows(fetchPage, "테스트", countRows);

      // count 쿼리 resolve + 병렬 dispatch 를 위해 마이크로태스크를 흘려보낸다.
      await Promise.resolve();
      await Promise.resolve();

      // 어떤 페이지도 아직 resolve 되지 않았지만 3개 페이지가 모두 요청되어 있어야 한다.
      // (순차라면 첫 페이지가 resolve 되기 전에는 다음 페이지를 요청하지 않는다.)
      expect(calls).toEqual([
        { from: 0, to: 999 },
        { from: 1000, to: 1999 },
        { from: 2000, to: 2999 },
      ]);

      resolvers.forEach((resolve) => resolve());
      const rows = await promise;

      expect(rows).toHaveLength(2500);
      expect(rows.map((row) => row.index)).toEqual(
        Array.from({ length: 2500 }, (_unused, index) => index),
      );
    });

    it("정확히 필요한 페이지 수만 요청한다(1000의 배수여도 추가 조회 없음)", async () => {
      const { fetchPage, countRows, calls } = makeFakeFetcher(2000);

      const rows = await fetchAllRows(fetchPage, "테스트", countRows);

      expect(rows).toHaveLength(2000);
      // count 기반은 count 로 페이지 수(2)를 정확히 알므로 빈 3번째 페이지를 요청하지 않는다.
      expect(calls).toEqual([
        { from: 0, to: 999 },
        { from: 1000, to: 1999 },
      ]);
    });

    it("부분 페이지(2500행)도 정확히 3페이지만 요청하고 순서대로 수집한다", async () => {
      const { fetchPage, countRows, calls } = makeFakeFetcher(2500);

      const rows = await fetchAllRows(fetchPage, "테스트", countRows);

      expect(rows).toHaveLength(2500);
      expect(calls).toEqual([
        { from: 0, to: 999 },
        { from: 1000, to: 1999 },
        { from: 2000, to: 2999 },
      ]);
      expect(rows.map((row) => row.index)).toEqual(
        Array.from({ length: 2500 }, (_unused, index) => index),
      );
    });

    it("count 가 0이면 페이지를 아예 요청하지 않는다", async () => {
      const { fetchPage, countRows, calls } = makeFakeFetcher(0);

      const rows = await fetchAllRows(fetchPage, "테스트", countRows);

      expect(rows).toEqual([]);
      expect(calls).toEqual([]);
    });

    it("count 쿼리가 에러면 context 와 함께 throw 한다", async () => {
      const { fetchPage } = makeFakeFetcher(10);
      const countRows: RowCounter = () =>
        Promise.resolve({ count: null, error: { message: "count denied" } });

      await expect(
        fetchAllRows(fetchPage, "환율 시계열", countRows),
      ).rejects.toThrow("환율 시계열 조회 중 오류가 발생했습니다: count denied");
    });

    it("병렬 조회 중 한 페이지가 에러면 context 와 함께 throw 한다", async () => {
      const calls: Array<{ from: number; to: number }> = [];
      const fetchPage: PageFetcher<{ index: number }> = (from, to) => {
        calls.push({ from, to });
        if (from === 1000) {
          return Promise.resolve({
            data: null,
            error: { message: "page fail" },
          });
        }
        return Promise.resolve({ data: [{ index: from }], error: null });
      };
      const countRows: RowCounter = () =>
        Promise.resolve({ count: 2500, error: null });

      await expect(
        fetchAllRows(fetchPage, "일봉 시계열", countRows),
      ).rejects.toThrow("일봉 시계열 조회 중 오류가 발생했습니다: page fail");
    });
  });

  describe("순차 폴백 (countRows 없음 또는 count=null)", () => {
    it("countRows 가 없으면 순차 루프로 전량 수집한다(2500행)", async () => {
      const { fetchPage, calls } = makeFakeFetcher(2500);

      const rows = await fetchAllRows(fetchPage, "테스트");

      expect(rows).toHaveLength(2500);
      expect(calls).toEqual([
        { from: 0, to: 999 },
        { from: 1000, to: 1999 },
        { from: 2000, to: 2999 },
      ]);
      expect(rows.map((row) => row.index)).toEqual(
        Array.from({ length: 2500 }, (_unused, index) => index),
      );
    });

    it("count 가 null 이면 순차 폴백으로 전량 수집한다", async () => {
      const { fetchPage, countRows, calls } = makeFakeFetcher(2500, {
        count: null,
      });

      const rows = await fetchAllRows(fetchPage, "테스트", countRows);

      expect(rows).toHaveLength(2500);
      expect(calls).toEqual([
        { from: 0, to: 999 },
        { from: 1000, to: 1999 },
        { from: 2000, to: 2999 },
      ]);
    });

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
    });

    it("빈 결과(0행)면 한 번 조회 후 종료한다", async () => {
      const { fetchPage, calls } = makeFakeFetcher(0);

      const rows = await fetchAllRows(fetchPage, "테스트");

      expect(rows).toEqual([]);
      expect(calls).toEqual([{ from: 0, to: PAGE_SIZE - 1 }]);
    });

    it("data 가 null 이어도 안전하게 빈 배열을 반환한다", async () => {
      const fetchPage = vi
        .fn<PageFetcher<{ index: number }>>()
        .mockResolvedValue({ data: null, error: null });

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
});
