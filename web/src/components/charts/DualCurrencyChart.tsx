"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { EChartsOption } from "echarts";
import type { DualCurrencyPoint } from "@/lib/types";
import {
  calculateRangeReturns,
  resolveZoomIndices,
  type RangeReturns,
} from "@/lib/rangeReturns";
import {
  RANGE_PRESETS,
  resolvePresetRange,
  resolveRangeIndices,
  type DateRangePreset,
} from "@/lib/chartRange";
import { Button } from "@/components/ui/button";
import EChartsBase from "./EChartsBase";
import RangeReturnPanel from "../RangeReturnPanel";

/**
 * 지표의 원화/달러 이중 통화 시계열 차트 + dataZoom 구간 수익률 패널.
 *
 * dataviz 스킬 지침 적용/일탈 근거:
 * - 계열색은 검증된 기본 팔레트의 categorical slot 1(blue=원화) / slot 2(aqua=달러).
 *   ExchangeRateChart 와 동일한 blue 를 원화에 배정해 앱 전체 톤을 일관되게 유지한다.
 * - 색상만으로 구분하지 않는다: 범례 + 각 축 이름(통화/단위) 표기 + 툴팁의 통화 라벨.
 * - 두 계열은 스케일이 크게 다른 원화 가격 vs 달러 가격이므로 이중 y축을 사용한다.
 *   (일반적으로 이중 y축은 피하지만, 본 화면의 핵심 요구사항이다.) 혼동을 줄이기 위해
 *   각 y축의 축선/라벨을 해당 계열 색으로 물들여 어느 축이 어느 통화인지 즉시 식별되게 한다.
 * - 격자/축은 recessive(hairline), 텍스트는 series 색이 아닌 ink 토큰 사용.
 * - 환율 데이터 이전 구간은 달러가 null → connectNulls:false 로 선을 끊는다.
 */

interface DualChartTheme {
  krwSeries: string;
  usdSeries: string;
  surface: string;
  textPrimary: string;
  textSecondary: string;
  muted: string;
  gridline: string;
  axisLine: string;
  border: string;
  zoomFill: string;
  zoomHandle: string;
}

// 검증된 기본 팔레트(references/palette.md)에서 채택.
const LIGHT_THEME: DualChartTheme = {
  krwSeries: "#2a78d6", // slot 1 blue
  usdSeries: "#1baf7a", // slot 2 aqua
  surface: "#fcfcfb",
  textPrimary: "#0b0b0b",
  textSecondary: "#52514e",
  muted: "#898781",
  gridline: "#e1e0d9",
  axisLine: "#c3c2b7",
  border: "rgba(11, 11, 11, 0.10)",
  zoomFill: "rgba(42, 120, 214, 0.08)",
  zoomHandle: "#c3c2b7",
};

const DARK_THEME: DualChartTheme = {
  krwSeries: "#3987e5", // slot 1 blue (dark step)
  usdSeries: "#199e70", // slot 2 aqua (dark step)
  surface: "#1a1a19",
  textPrimary: "#ffffff",
  textSecondary: "#c3c2b7",
  muted: "#898781",
  gridline: "#2c2c2a",
  axisLine: "#383835",
  border: "rgba(255, 255, 255, 0.10)",
  zoomFill: "rgba(57, 135, 229, 0.12)",
  zoomHandle: "#383835",
};

/**
 * 앱 테마 신호(.dark 클래스)와 OS 선호도를 모두 관찰해 다크모드 여부를 반환한다.
 * (ExchangeRateChart 와 동일한 관례. 해당 파일은 훅을 export 하지 않으므로 여기서 재정의한다.)
 */
function useIsDarkMode(): boolean {
  const [isDark, setIsDark] = useState(false);

  useEffect(() => {
    const rootElement = document.documentElement;
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)");

    const compute = () => {
      setIsDark(rootElement.classList.contains("dark") || prefersDark.matches);
    };

    compute();
    prefersDark.addEventListener("change", compute);
    const classObserver = new MutationObserver(compute);
    classObserver.observe(rootElement, {
      attributes: true,
      attributeFilter: ["class"],
    });

    return () => {
      prefersDark.removeEventListener("change", compute);
      classObserver.disconnect();
    };
  }, []);

  return isDark;
}

const KRW_FORMATTER = new Intl.NumberFormat("ko-KR", {
  maximumFractionDigits: 0,
});

const USD_FORMATTER = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const KRW_SERIES_NAME = "원화 (KRW)";
const USD_SERIES_NAME = "달러 (USD)";

function buildOption(
  points: DualCurrencyPoint[],
  theme: DualChartTheme,
): EChartsOption {
  const categories = points.map((point) => point.priceDate);
  const krwData = points.map((point) => point.closePriceKrw);
  // 달러 데이터가 없는(환율 이전) 포인트는 null 로 두어 선이 끊기게 한다.
  const usdData = points.map((point) => point.closePriceUsd);

  return {
    backgroundColor: "transparent",
    color: [theme.krwSeries, theme.usdSeries],
    legend: {
      data: [KRW_SERIES_NAME, USD_SERIES_NAME],
      top: 0,
      right: 0,
      icon: "roundRect",
      itemWidth: 12,
      itemHeight: 12,
      textStyle: { color: theme.textSecondary, fontSize: 12 },
    },
    grid: {
      left: 12,
      right: 12,
      top: 44,
      bottom: 64,
      containLabel: true,
    },
    tooltip: {
      trigger: "axis",
      backgroundColor: theme.surface,
      borderColor: theme.border,
      borderWidth: 1,
      padding: [8, 12],
      textStyle: { color: theme.textPrimary, fontSize: 12 },
      axisPointer: {
        type: "line",
        lineStyle: { color: theme.axisLine, width: 1, type: "dashed" },
      },
      formatter: (rawParams) => {
        const params = rawParams as Array<{
          axisValueLabel?: string;
          axisValue?: string;
          seriesName?: string;
          value?: number | null;
          marker?: string;
        }>;
        if (params.length === 0) {
          return "";
        }
        const dateLabel = params[0].axisValueLabel ?? params[0].axisValue ?? "";
        const rows = params
          .map((entry) => {
            const isKrw = entry.seriesName === KRW_SERIES_NAME;
            let valueText: string;
            if (entry.value === null || entry.value === undefined) {
              valueText = isKrw ? "—" : "달러 데이터 없음";
            } else if (isKrw) {
              valueText = `${KRW_FORMATTER.format(entry.value)} 원`;
            } else {
              valueText = `${USD_FORMATTER.format(entry.value)} USD`;
            }
            return `${entry.marker ?? ""}${entry.seriesName ?? ""}: <strong>${valueText}</strong>`;
          })
          .join("<br/>");
        return `${dateLabel}<br/>${rows}`;
      },
    },
    xAxis: {
      type: "category",
      data: categories,
      boundaryGap: false,
      axisLine: { lineStyle: { color: theme.axisLine } },
      axisTick: { show: false },
      axisLabel: { color: theme.muted, fontSize: 11, hideOverlap: true },
      splitLine: { show: false },
    },
    yAxis: [
      {
        // 좌축: 원화(KRW). 축선/라벨을 원화 계열색으로 물들여 축-통화 대응을 명확히 한다.
        type: "value",
        name: KRW_SERIES_NAME,
        position: "left",
        scale: true,
        nameTextStyle: { color: theme.krwSeries, fontSize: 11, align: "left" },
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: {
          color: theme.krwSeries,
          fontSize: 11,
          formatter: (value: number) => KRW_FORMATTER.format(value),
        },
        splitLine: { lineStyle: { color: theme.gridline, type: "solid" } },
      },
      {
        // 우축: 달러(USD).
        type: "value",
        name: USD_SERIES_NAME,
        position: "right",
        scale: true,
        nameTextStyle: { color: theme.usdSeries, fontSize: 11, align: "right" },
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: {
          color: theme.usdSeries,
          fontSize: 11,
          formatter: (value: number) => USD_FORMATTER.format(value),
        },
        // 두 번째 축의 격자선은 그리지 않아 격자 중복을 피한다.
        splitLine: { show: false },
      },
    ],
    dataZoom: [
      {
        type: "inside",
        xAxisIndex: 0,
        filterMode: "none",
      },
      {
        type: "slider",
        xAxisIndex: 0,
        filterMode: "none",
        bottom: 12,
        height: 24,
        borderColor: theme.border,
        fillerColor: theme.zoomFill,
        dataBackground: {
          lineStyle: { color: theme.axisLine },
          areaStyle: { color: theme.gridline },
        },
        handleStyle: { color: theme.zoomHandle, borderColor: theme.axisLine },
        moveHandleStyle: { color: theme.zoomHandle },
        textStyle: { color: theme.muted, fontSize: 10 },
      },
    ],
    series: [
      {
        name: KRW_SERIES_NAME,
        type: "line",
        yAxisIndex: 0,
        data: krwData,
        showSymbol: false,
        symbolSize: 8,
        sampling: "lttb",
        connectNulls: false,
        lineStyle: { width: 2, color: theme.krwSeries },
        itemStyle: { color: theme.krwSeries },
        emphasis: { focus: "series" },
      },
      {
        name: USD_SERIES_NAME,
        type: "line",
        yAxisIndex: 1,
        data: usdData,
        showSymbol: false,
        symbolSize: 8,
        sampling: "lttb",
        connectNulls: false,
        lineStyle: { width: 2, color: theme.usdSeries },
        itemStyle: { color: theme.usdSeries },
        emphasis: { focus: "series" },
      },
    ],
  };
}

/** datazoom 이벤트 payload 에서 start/end 퍼센트를 방어적으로 추출한다. */
function extractZoomPercent(
  rawParams: unknown,
): { start: number; end: number } | null {
  const params = rawParams as {
    batch?: Array<{ start?: number; end?: number }>;
    start?: number;
    end?: number;
  };
  const source =
    params.batch && params.batch.length > 0 ? params.batch[0] : params;
  if (typeof source.start === "number" && typeof source.end === "number") {
    return { start: source.start, end: source.end };
  }
  return null;
}

/** 이벤트에 퍼센트가 없을 때 차트 인스턴스의 현재 dataZoom 상태에서 읽어온다. */
function readZoomPercentFromInstance(
  instance: unknown,
): { start: number; end: number } | null {
  const chart = instance as {
    getOption?: () => {
      dataZoom?: Array<{ start?: number; end?: number }>;
    };
  };
  const currentOption = chart.getOption?.();
  const zoom = currentOption?.dataZoom?.[0];
  if (zoom && typeof zoom.start === "number" && typeof zoom.end === "number") {
    return { start: zoom.start, end: zoom.end };
  }
  return null;
}

const DATAZOOM_DEBOUNCE_MS = 150;

export interface DualCurrencyChartProps {
  points: DualCurrencyPoint[];
  indicatorName: string;
}

export default function DualCurrencyChart({
  points,
  indicatorName,
}: DualCurrencyChartProps) {
  const isDark = useIsDarkMode();
  const theme = isDark ? DARK_THEME : LIGHT_THEME;

  // 옵션은 points/theme 에만 의존하도록 memo 한다. 구간 수익률 state 가 바뀌어도
  // 옵션 객체가 유지되어 dataZoom 이 초기화(리셋)되지 않는다.
  const option = useMemo(() => buildOption(points, theme), [points, theme]);

  // 초기 표시: 전체 구간(0~마지막 인덱스)의 수익률.
  const [rangeReturns, setRangeReturns] = useState<RangeReturns | null>(() =>
    points.length === 0
      ? null
      : calculateRangeReturns(points, 0, points.length - 1),
  );

  // points 가 바뀌면 전체 구간 기준으로 재계산.
  useEffect(() => {
    setRangeReturns(
      points.length === 0
        ? null
        : calculateRangeReturns(points, 0, points.length - 1),
    );
  }, [points]);

  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
    };
  }, []);

  // 정렬된 priceDate 배열. 프리셋/날짜 입력을 인덱스로 변환할 때 사용한다.
  const dates = useMemo(() => points.map((point) => point.priceDate), [points]);
  const firstDate = points.length > 0 ? points[0].priceDate : "";
  const lastDate =
    points.length > 0 ? points[points.length - 1].priceDate : "";

  // 날짜 직접 입력값. points 가 바뀌면 전체 범위로 초기화한다.
  const [startDateInput, setStartDateInput] = useState(firstDate);
  const [endDateInput, setEndDateInput] = useState(lastDate);
  useEffect(() => {
    setStartDateInput(firstDate);
    setEndDateInput(lastDate);
  }, [firstDate, lastDate]);

  // echarts 인스턴스 보관. onChartReady 콜백으로 주입되며 dispatchAction 에 사용한다.
  const chartInstanceRef = useRef<{
    dispatchAction?: (payload: unknown) => void;
  } | null>(null);
  const handleChartReady = useCallback((instance: unknown) => {
    chartInstanceRef.current = instance as {
      dispatchAction?: (payload: unknown) => void;
    };
  }, []);

  /**
   * 지정 인덱스 구간으로 차트를 줌하고 구간 수익률 패널을 갱신한다.
   *
   * - dispatchAction(dataZoom) 은 category 축이므로 startValue/endValue 에 배열 인덱스를
   *   그대로 넘긴다. inside(0)/slider(1) 두 dataZoom 을 batch 로 함께 갱신해 슬라이더 위치도 반영.
   * - dispatchAction 은 datazoom 이벤트를 트리거해 handleDataZoom → 패널 갱신으로 이어지지만,
   *   트리거 여부와 무관하게 즉시 패널이 갱신되도록 여기서 직접 계산도 수행한다(이중 안전).
   */
  const applyRange = useCallback(
    (startIndex: number, endIndex: number) => {
      if (points.length === 0) {
        return;
      }
      const maxIndex = points.length - 1;
      const clampedStart = Math.max(0, Math.min(startIndex, maxIndex));
      const clampedEnd = Math.max(0, Math.min(endIndex, maxIndex));

      chartInstanceRef.current?.dispatchAction?.({
        type: "dataZoom",
        batch: [
          { dataZoomIndex: 0, startValue: clampedStart, endValue: clampedEnd },
          { dataZoomIndex: 1, startValue: clampedStart, endValue: clampedEnd },
        ],
      });

      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
      setRangeReturns(
        calculateRangeReturns(points, clampedStart, clampedEnd),
      );
    },
    [points],
  );

  const handlePresetClick = useCallback(
    (preset: DateRangePreset) => {
      const range = resolvePresetRange(dates, preset);
      if (range) {
        applyRange(range.startIndex, range.endIndex);
      }
    },
    [dates, applyRange],
  );

  const handleApplyDates = useCallback(() => {
    if (!startDateInput || !endDateInput) {
      return;
    }
    const range = resolveRangeIndices(dates, startDateInput, endDateInput);
    if (range) {
      applyRange(range.startIndex, range.endIndex);
    }
  }, [dates, startDateInput, endDateInput, applyRange]);

  const handleDataZoom = useCallback(
    (rawParams: unknown, instance: unknown) => {
      const percent =
        extractZoomPercent(rawParams) ?? readZoomPercentFromInstance(instance);
      if (!percent || points.length === 0) {
        return;
      }

      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
      debounceTimerRef.current = setTimeout(() => {
        const { startIndex, endIndex } = resolveZoomIndices(
          points.length,
          percent.start,
          percent.end,
        );
        setRangeReturns(calculateRangeReturns(points, startIndex, endIndex));
      }, DATAZOOM_DEBOUNCE_MS);
    },
    [points],
  );

  const chartEvents = useMemo(
    () => ({ datazoom: handleDataZoom }),
    [handleDataZoom],
  );

  if (points.length === 0) {
    return (
      <div className="flex flex-col gap-4">
        <div
          style={{
            height: 420,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <p className="text-sm text-muted-foreground">
            {indicatorName}의 시계열 데이터가 없습니다.
          </p>
        </div>
        <RangeReturnPanel rangeReturns={null} />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-3">
        {/* 기간 프리셋 버튼: 모바일에서 wrap */}
        <div className="flex flex-wrap gap-1.5">
          {RANGE_PRESETS.map((preset) => (
            <Button
              key={preset.key}
              type="button"
              variant="outline"
              size="sm"
              onClick={() => handlePresetClick(preset)}
            >
              {preset.label}
            </Button>
          ))}
        </div>

        {/* 날짜 직접 입력: 시작일/종료일 + 적용 */}
        <div className="flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
            시작일
            <input
              type="date"
              value={startDateInput}
              min={firstDate}
              max={lastDate}
              onChange={(event) => setStartDateInput(event.target.value)}
              className="h-7 rounded-md border border-border bg-background px-2 text-[0.8rem] text-foreground outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:border-input dark:bg-input/30 [color-scheme:light] dark:[color-scheme:dark]"
            />
          </label>
          <span className="text-xs text-muted-foreground">~</span>
          <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
            종료일
            <input
              type="date"
              value={endDateInput}
              min={firstDate}
              max={lastDate}
              onChange={(event) => setEndDateInput(event.target.value)}
              className="h-7 rounded-md border border-border bg-background px-2 text-[0.8rem] text-foreground outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:border-input dark:bg-input/30 [color-scheme:light] dark:[color-scheme:dark]"
            />
          </label>
          <Button type="button" variant="outline" size="sm" onClick={handleApplyDates}>
            적용
          </Button>
        </div>
      </div>

      <EChartsBase
        option={option}
        onEvents={chartEvents}
        onChartReady={handleChartReady}
        style={{ height: 420 }}
      />
      <RangeReturnPanel rangeReturns={rangeReturns} />
    </div>
  );
}
