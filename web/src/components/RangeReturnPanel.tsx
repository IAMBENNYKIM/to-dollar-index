import { ArrowDownRight, ArrowRight, ArrowUpRight } from "lucide-react";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { RangeReturns } from "@/lib/rangeReturns";
import {
  EMPTY_VALUE_TEXT,
  formatSignedPercent,
  formatSignedPercentPoint,
  returnDirectionOf,
  type ReturnSignDirection,
} from "@/lib/formatReturns";

/**
 * dataZoom 으로 선택한 구간의 원화/달러 수익률과 환율 효과를 표시하는 패널.
 *
 * 접근성(dataviz): 방향을 색상 하나로만 전달하지 않는다.
 * - 부호(+/−)가 이미 방향을 나타내고,
 * - 방향 아이콘(↗/↘/→)을 함께 제공하며,
 * - 금융 관례색(상승 녹색 / 하락 적색)은 보조 채널로만 쓴다.
 * 달러 데이터가 없는 구간(환율 데이터 이전)은 "달러 데이터 없음" 으로 명시한다.
 */

const DIRECTION_META: Record<
  ReturnSignDirection,
  { color: string; Icon: typeof ArrowUpRight }
> = {
  up: { color: "text-[#006300] dark:text-[#0ca30c]", Icon: ArrowUpRight },
  down: { color: "text-[#d03b3b] dark:text-[#e66767]", Icon: ArrowDownRight },
  flat: { color: "text-muted-foreground", Icon: ArrowRight },
};

interface ReturnMetricProps {
  label: string;
  /** 미리 포맷된 값. null 이면 nullText 를 표시한다. */
  value: number | null;
  formatValue: (value: number | null) => string;
  /** value 가 null 일 때 표시할 문구. */
  nullText?: string;
}

function ReturnMetric({
  label,
  value,
  formatValue,
  nullText,
}: ReturnMetricProps) {
  if (value === null) {
    return (
      <div className="flex flex-col gap-0.5">
        <span className="text-xs text-muted-foreground">{label}</span>
        <span className="text-sm text-muted-foreground">
          {nullText ?? EMPTY_VALUE_TEXT}
        </span>
      </div>
    );
  }

  const direction = returnDirectionOf(value);
  const meta = DIRECTION_META[direction];
  const DirectionIcon = meta.Icon;

  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span
        className={cn(
          "flex items-center gap-1 text-base font-semibold tabular-nums",
          meta.color,
        )}
      >
        <DirectionIcon className="size-4 shrink-0" aria-hidden />
        {formatValue(value)}
      </span>
    </div>
  );
}

export interface RangeReturnPanelProps {
  rangeReturns: RangeReturns | null;
  className?: string;
}

export default function RangeReturnPanel({
  rangeReturns,
  className,
}: RangeReturnPanelProps) {
  return (
    <Card className={cn("gap-3 px-5", className)}>
      <div className="flex flex-col gap-0.5">
        <span className="text-sm font-medium text-foreground">구간 수익률</span>
        <span className="text-xs text-muted-foreground tabular-nums">
          {rangeReturns
            ? `${rangeReturns.startDate} ~ ${rangeReturns.endDate}`
            : "차트에서 구간을 선택하면 수익률이 표시됩니다."}
        </span>
      </div>

      {rangeReturns ? (
        <div className="flex flex-wrap gap-x-8 gap-y-3">
          <ReturnMetric
            label="원화 (KRW)"
            value={rangeReturns.krwReturnPercent}
            formatValue={formatSignedPercent}
          />
          <ReturnMetric
            label="달러 (USD)"
            value={rangeReturns.usdReturnPercent}
            formatValue={formatSignedPercent}
            nullText="달러 데이터 없음"
          />
          <ReturnMetric
            label="환율 효과"
            value={rangeReturns.exchangeRateEffectPercentPoint}
            formatValue={formatSignedPercentPoint}
            nullText="달러 데이터 없음"
          />
        </div>
      ) : null}
    </Card>
  );
}
