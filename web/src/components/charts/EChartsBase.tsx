"use client";

import dynamic from "next/dynamic";
import type { CSSProperties } from "react";
import type { EChartsOption } from "echarts";

/**
 * ECharts 는 SSR 을 지원하지 않으므로(window/canvas 의존) echarts-for-react 를
 * 반드시 클라이언트 전용 dynamic import(ssr:false)로 로드한다.
 * 모든 차트 컴포넌트는 이 래퍼를 재사용해 SSR 우회 로직을 중복하지 않는다.
 */
const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });

/** ECharts 이벤트 핸들러 맵. 예: { datazoom: (params) => {...} } */
export type EChartsEventHandlers = Record<
  string,
  (params: unknown, instance: unknown) => void
>;

export interface EChartsBaseProps {
  option: EChartsOption;
  onEvents?: EChartsEventHandlers;
  style?: CSSProperties;
  className?: string;
  /** 옵션을 병합하지 않고 통째로 교체할지 여부. 기본 true (테마 전환 시 잔상 방지). */
  notMerge?: boolean;
}

export default function EChartsBase({
  option,
  onEvents,
  style,
  className,
  notMerge = true,
}: EChartsBaseProps) {
  return (
    <ReactECharts
      option={option}
      onEvents={onEvents}
      notMerge={notMerge}
      lazyUpdate
      style={{ width: "100%", height: "100%", ...style }}
      className={className}
    />
  );
}
