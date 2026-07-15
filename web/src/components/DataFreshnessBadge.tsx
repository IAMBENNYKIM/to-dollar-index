import { TriangleAlert } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  evaluateDataFreshness,
  getTodayInSeoul,
} from "@/lib/dataFreshness";

/**
 * 데이터 최신성(수집 지연) 배지. Server Component.
 *
 * 최신 데이터 날짜를 "기준일 YYYY-MM-DD" 로 표시하고, 수집이 밀렸으면 경고 톤 + 아이콘을
 * 함께 보여준다. 색상만으로 의미를 전달하지 않도록 지연 시 TriangleAlert 아이콘을 병행한다.
 *
 * - latestDate 가 null 이면 아무것도 렌더링하지 않는다(데이터 없음).
 * - staleAfterBusinessDays 가 null 이면 지연 판정을 비활성화한다(월별 데이터용). 기준일만 표시.
 */

/** 일별 데이터의 기본 지연 임계값(영업일). 이틀 이상 밀리면 경고. */
const DEFAULT_STALE_AFTER_BUSINESS_DAYS = 2;

export interface DataFreshnessBadgeProps {
  /** 최신 데이터 날짜("YYYY-MM-DD"). null 이면 렌더링하지 않는다. */
  latestDate: string | null;
  /** 지연 판정 임계값(영업일). null 이면 경고 판정을 끄고 기준일만 표시한다. 기본 2. */
  staleAfterBusinessDays?: number | null;
  className?: string;
}

export default function DataFreshnessBadge({
  latestDate,
  staleAfterBusinessDays = DEFAULT_STALE_AFTER_BUSINESS_DAYS,
  className,
}: DataFreshnessBadgeProps) {
  if (latestDate === null) {
    return null;
  }

  const isStale =
    staleAfterBusinessDays === null
      ? false
      : evaluateDataFreshness(
          latestDate,
          getTodayInSeoul(),
          staleAfterBusinessDays,
        ).isStale;

  if (isStale) {
    return (
      <span
        className={cn(
          "inline-flex items-center gap-1 text-xs font-medium text-amber-700 dark:text-amber-500",
          className,
        )}
      >
        <TriangleAlert className="size-3.5 shrink-0" aria-hidden />
        기준일 {latestDate} · 수집 지연
      </span>
    );
  }

  return (
    <span className={cn("inline-flex items-center text-xs text-muted-foreground", className)}>
      기준일 {latestDate}
    </span>
  );
}
