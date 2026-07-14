import Link from "next/link";
import { ChevronRight } from "lucide-react";
import {
  fetchActiveIndicators,
  fetchExchangeRateHistory,
} from "@/lib/indicatorQueries";
import type { ExchangeRatePoint, Indicator } from "@/lib/types";
import {
  getCurrentRate,
  getDailyChange,
  getRangeChangePercent,
} from "@/lib/exchangeRateStats";
import ExchangeRateChart from "@/components/charts/ExchangeRateChart";
import StatTile, {
  type StatTileDelta,
  type StatTileDeltaDirection,
} from "@/components/StatTile";
import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

// ISR: 1시간마다 재생성.
export const revalidate = 3600;

// Vercel 배포 시 인천(서울) 리전을 선호한다. Supabase 서울 리전과 가까워 서버-DB 왕복이 짧아진다.
// (Hobby 플랜에서는 무시될 수 있으나 무해하다.)
export const preferredRegion = "icn1";

const RATE_FORMATTER = new Intl.NumberFormat("ko-KR", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const PERCENT_FORMATTER = new Intl.NumberFormat("ko-KR", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
  signDisplay: "exceptZero",
});

/** 절대 변동값을 부호와 함께 "±1,234.56" 형태로 포맷한다. */
function formatSignedRate(value: number): string {
  const sign = value > 0 ? "+" : value < 0 ? "-" : "";
  return `${sign}${RATE_FORMATTER.format(Math.abs(value))}`;
}

function directionOf(value: number): StatTileDeltaDirection {
  if (value > 0) return "up";
  if (value < 0) return "down";
  return "flat";
}

/** 변동률(%) 하나로 이루어진 delta 를 만든다. null 이면 undefined 반환(타일이 "—" 표시). */
function percentDelta(percent: number | null): StatTileDelta | undefined {
  if (percent === null) {
    return undefined;
  }
  return {
    text: `${PERCENT_FORMATTER.format(percent)}%`,
    direction: directionOf(percent),
  };
}

export default async function Home() {
  // 빌드 타임에 Supabase 환경변수가 없으면 조회가 throw 되므로 반드시 폴백한다.
  let rateHistory: ExchangeRatePoint[] = [];
  let indicators: Indicator[] = [];

  try {
    rateHistory = await fetchExchangeRateHistory();
  } catch {
    rateHistory = [];
  }

  try {
    indicators = await fetchActiveIndicators();
  } catch {
    indicators = [];
  }

  const currentRate = getCurrentRate(rateHistory);
  const dailyChange = getDailyChange(rateHistory);
  const change30d = getRangeChangePercent(rateHistory, 30);
  const change1y = getRangeChangePercent(rateHistory, 365);
  const hasData = rateHistory.length > 0;

  const dailyDelta: StatTileDelta | undefined = dailyChange
    ? {
        text:
          dailyChange.percent === null
            ? `${formatSignedRate(dailyChange.absolute)}원`
            : `${formatSignedRate(dailyChange.absolute)}원 (${PERCENT_FORMATTER.format(dailyChange.percent)}%)`,
        direction: directionOf(dailyChange.absolute),
      }
    : undefined;

  return (
    <div className="mx-auto flex min-h-screen max-w-6xl flex-col gap-8 px-4 py-10 sm:px-8">
      <header className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
          원/달러 환율 지수
        </h1>
        <p className="text-sm text-muted-foreground">
          원/달러(USD·KRW) 환율의 최근 흐름과 등록된 지표의 원화·달러 환산 성과를 한눈에 확인하세요.
        </p>
      </header>

      {/* 통계 타일 행 */}
      <section
        aria-label="환율 요약 통계"
        className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4"
      >
        <StatTile
          label="현재 환율"
          value={currentRate === null ? "—" : RATE_FORMATTER.format(currentRate)}
          unit={currentRate === null ? undefined : "원"}
        />
        <StatTile
          label="전일 대비"
          value={
            dailyChange === null ? "—" : formatSignedRate(dailyChange.absolute)
          }
          unit={dailyChange === null ? undefined : "원"}
          delta={dailyDelta}
        />
        <StatTile
          label="30일 변동률"
          value={change30d === null ? "—" : `${PERCENT_FORMATTER.format(change30d)}%`}
          delta={percentDelta(change30d)}
        />
        <StatTile
          label="1년 변동률"
          value={change1y === null ? "—" : `${PERCENT_FORMATTER.format(change1y)}%`}
          delta={percentDelta(change1y)}
        />
      </section>

      {/* 환율 차트 */}
      <section aria-label="환율 시계열 차트">
        <Card className="gap-4 px-5 py-5">
          <CardHeader className="px-0">
            <CardTitle>원/달러 환율 추이</CardTitle>
            <CardDescription>
              {hasData
                ? "USD·KRW 종가 기준 시계열"
                : "환율 데이터를 불러오지 못했습니다."}
            </CardDescription>
          </CardHeader>
          <ExchangeRateChart points={rateHistory} />
        </Card>
      </section>

      {/* 등록 지표 목록 */}
      <section aria-label="등록 지표" className="flex flex-col gap-4">
        <h2 className="text-lg font-semibold text-foreground">등록 지표</h2>
        {indicators.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            등록된 지표가 없습니다.
          </p>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {indicators.map((indicator) => (
              <Link
                key={indicator.id}
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
                </Card>
              </Link>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
