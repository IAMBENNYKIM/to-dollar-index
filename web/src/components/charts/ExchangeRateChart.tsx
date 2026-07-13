"use client";

import { useEffect, useMemo, useState } from "react";
import type { EChartsOption } from "echarts";
import type { ExchangeRatePoint } from "@/lib/types";
import EChartsBase from "./EChartsBase";

/**
 * 원/달러(USD_KRW) 환율 시계열 라인 차트.
 *
 * dataviz 스킬 지침 적용:
 * - 단일 시계열이므로 범례 없이 제목이 계열을 식별(카드 헤더가 담당).
 * - 계열색은 검증된 기본 팔레트의 categorical slot 1(blue): light #2a78d6 / dark #3987e5.
 * - 격자/축은 recessive(hairline), 텍스트는 series 색이 아닌 ink 토큰 사용.
 * - hover 레이어 기본 탑재: axis 트리거 crosshair + 툴팁.
 * - 다크모드는 자동 flip 이 아니라 팔레트의 다크 스텝을 '선택'해 적용한다.
 */

interface DatavizTheme {
  series: string;
  areaTop: string;
  areaBottom: string;
  surface: string;
  textPrimary: string;
  textSecondary: string;
  muted: string;
  gridline: string;
  axisLine: string;
  border: string;
}

// 검증된 기본 팔레트(references/palette.md)에서 채택한 값.
const LIGHT_THEME: DatavizTheme = {
  series: "#2a78d6",
  areaTop: "rgba(42, 120, 214, 0.16)",
  areaBottom: "rgba(42, 120, 214, 0.0)",
  surface: "#fcfcfb",
  textPrimary: "#0b0b0b",
  textSecondary: "#52514e",
  muted: "#898781",
  gridline: "#e1e0d9",
  axisLine: "#c3c2b7",
  border: "rgba(11, 11, 11, 0.10)",
};

const DARK_THEME: DatavizTheme = {
  series: "#3987e5",
  areaTop: "rgba(57, 135, 229, 0.22)",
  areaBottom: "rgba(57, 135, 229, 0.0)",
  surface: "#1a1a19",
  textPrimary: "#ffffff",
  textSecondary: "#c3c2b7",
  muted: "#898781",
  gridline: "#2c2c2a",
  axisLine: "#383835",
  border: "rgba(255, 255, 255, 0.10)",
};

/**
 * 앱의 테마 신호(.dark 클래스, tailwind 방식)와 OS 선호도(prefers-color-scheme)를
 * 모두 관찰해 다크모드 여부를 반환한다. 어느 방식으로 테마가 바뀌어도 차트가 동기화된다.
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

const RATE_FORMATTER = new Intl.NumberFormat("ko-KR", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

function buildOption(
  points: ExchangeRatePoint[],
  theme: DatavizTheme,
): EChartsOption {
  const seriesData = points.map((point) => [point.rateDate, point.closeRate]);

  return {
    backgroundColor: "transparent",
    color: [theme.series],
    grid: {
      left: 12,
      right: 20,
      top: 16,
      bottom: 12,
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
          value?: [string, number];
        }>;
        const first = params[0];
        if (!first || !first.value) {
          return "";
        }
        const [dateLabel, rate] = first.value;
        return `${dateLabel}<br/><strong>${RATE_FORMATTER.format(rate)}</strong> 원`;
      },
    },
    xAxis: {
      type: "time",
      axisLine: { lineStyle: { color: theme.axisLine } },
      axisTick: { show: false },
      axisLabel: { color: theme.muted, fontSize: 11, hideOverlap: true },
      splitLine: { show: false },
    },
    yAxis: {
      type: "value",
      scale: true,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        color: theme.muted,
        fontSize: 11,
        formatter: (value: number) => RATE_FORMATTER.format(value),
      },
      splitLine: { lineStyle: { color: theme.gridline, type: "solid" } },
    },
    series: [
      {
        name: "원/달러 환율",
        type: "line",
        data: seriesData,
        showSymbol: false,
        symbol: "circle",
        symbolSize: 8,
        sampling: "lttb",
        lineStyle: { width: 2, color: theme.series },
        itemStyle: { color: theme.series },
        emphasis: { focus: "series" },
        areaStyle: {
          color: {
            type: "linear",
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: theme.areaTop },
              { offset: 1, color: theme.areaBottom },
            ],
          },
        },
      },
    ],
  };
}

export interface ExchangeRateChartProps {
  points: ExchangeRatePoint[];
  className?: string;
}

export default function ExchangeRateChart({
  points,
  className,
}: ExchangeRateChartProps) {
  const isDark = useIsDarkMode();
  const theme = isDark ? DARK_THEME : LIGHT_THEME;

  const option = useMemo(() => buildOption(points, theme), [points, theme]);

  if (points.length === 0) {
    return (
      <div
        className={className}
        style={{
          height: 360,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <p className="text-sm text-muted-foreground">표시할 환율 데이터가 없습니다.</p>
      </div>
    );
  }

  return (
    <EChartsBase option={option} className={className} style={{ height: 360 }} />
  );
}
