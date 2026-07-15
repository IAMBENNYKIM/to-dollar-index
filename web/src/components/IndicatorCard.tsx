import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { Indicator } from "@/lib/types";
import type { IndicatorSummary } from "@/lib/indicatorSummary";
import {
  DIRECTION_META,
  type StatTileDeltaDirection,
} from "@/components/StatTile";

/**
 * 홈 대시보드의 지표 카드. Server Component.
 *
 * 기존 홈 인라인 카드(hover, ChevronRight, focus ring)를 그대로 옮기고, summary 가
 * 있으면 최신 원화값·달러 환산값·변동률·기준일을 추가로 표시한다. summary 가 null 이면
 * 기존과 동일한 미니멀 카드를 렌더링한다.
 */

const KRW_FORMATTER = new Intl.NumberFormat("ko-KR", {
  maximumFractionDigits: 0,
});

const USD_FORMATTER = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const PERCENT_FORMATTER = new Intl.NumberFormat("ko-KR", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
  signDisplay: "exceptZero",
});

function directionOf(value: number): StatTileDeltaDirection {
  if (value > 0) return "up";
  if (value < 0) return "down";
  return "flat";
}

export interface IndicatorCardProps {
  indicator: Indicator;
  summary: IndicatorSummary | null;
}

export default function IndicatorCard({
  indicator,
  summary,
}: IndicatorCardProps) {
  const changePercent = summary?.changePercentKrw ?? null;
  const directionMeta =
    changePercent === null ? null : DIRECTION_META[directionOf(changePercent)];
  const ChangeIcon = directionMeta?.Icon;

  return (
    <Link
      href={`/indicators/${indicator.id}`}
      className="group block rounded-xl outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <Card className="gap-2 px-5 transition-colors group-hover:bg-muted/50">
        <div className="flex items-center justify-between gap-2">
          <div className="flex flex-col gap-1">
            <span className="font-medium text-foreground">
              {indicator.displayName}
            </span>
            <span className="text-xs text-muted-foreground">
              {indicator.indicatorType} · {indicator.sourceCode}
            </span>
          </div>
          <ChevronRight
            className="size-5 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5"
            aria-hidden
          />
        </div>

        {summary ? (
          <div className="flex flex-col gap-1">
            <div className="flex items-baseline gap-2">
              <span className="text-xl font-semibold leading-tight text-foreground">
                {KRW_FORMATTER.format(summary.latestKrw)}
                <span className="ml-1 text-sm font-normal text-muted-foreground">
                  원
                </span>
              </span>
              {summary.latestUsd !== null ? (
                <span className="text-sm text-muted-foreground">
                  ${USD_FORMATTER.format(summary.latestUsd)}
                </span>
              ) : null}
            </div>

            {directionMeta && ChangeIcon && changePercent !== null ? (
              <span
                className={cn(
                  "flex items-center gap-1 text-sm font-medium",
                  directionMeta.color,
                )}
              >
                <ChangeIcon className="size-4" aria-hidden />
                {PERCENT_FORMATTER.format(changePercent)}%
              </span>
            ) : null}

            <span className="text-xs text-muted-foreground">
              기준일 {summary.latestDate}
            </span>
          </div>
        ) : null}
      </Card>
    </Link>
  );
}
