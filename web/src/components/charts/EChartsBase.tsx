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
  /**
   * echarts 인스턴스가 준비되면 호출된다. 상위 컴포넌트가 dispatchAction 등
   * 프로그래매틱 제어를 하려면 이 콜백으로 인스턴스를 보관한다.
   * (dynamic import 라 ref forwarding 대신 콜백 방식을 사용한다.)
   */
  onChartReady?: (instance: unknown) => void;
}

export default function EChartsBase({
  option,
  onEvents,
  style,
  className,
  notMerge = true,
  onChartReady,
}: EChartsBaseProps) {
  return (
    <ReactECharts
      option={option}
      onEvents={onEvents}
      onChartReady={onChartReady}
      notMerge={notMerge}
      lazyUpdate
      style={{ width: "100%", height: "100%", ...style }}
      className={className}
    />
  );
}
