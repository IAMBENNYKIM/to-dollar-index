import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import {
  fetchDailyPricesWithUsd,
  fetchIndicatorById,
} from "@/lib/indicatorQueries";
import type { DualCurrencyPoint, Indicator } from "@/lib/types";
import DualCurrencyChart from "@/components/charts/DualCurrencyChart";
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

// Next 15 App Router 에서 동적 라우트의 params 는 Promise 이므로 await 해야 한다.
interface IndicatorDetailPageProps {
  params: Promise<{ id: string }>;
}

export default async function IndicatorDetailPage({
  params,
}: IndicatorDetailPageProps) {
  const { id } = await params;
  // 라우트 세그먼트는 Next 가 디코드하지만, id 예 'stock:005930' 처럼 인코딩된 경우를 방어한다.
  const indicatorId = decodeURIComponent(id);

  // 빌드/조회 시 환경변수가 없으면 조회가 throw 되므로 폴백한다.
  let indicator: Indicator | null = null;
  let loadFailed = false;
  try {
    indicator = await fetchIndicatorById(indicatorId);
  } catch {
    loadFailed = true;
  }

  // 조회 자체가 성공했는데 지표가 없으면 404.
  if (!loadFailed && indicator === null) {
    notFound();
  }

  let points: DualCurrencyPoint[] = [];
  if (indicator) {
    try {
      points = await fetchDailyPricesWithUsd(indicator.id);
    } catch {
      points = [];
    }
  }

  const displayName = indicator?.displayName ?? indicatorId;

  return (
    <div className="mx-auto flex min-h-screen max-w-6xl flex-col gap-8 px-4 py-10 sm:px-8">
      <header className="flex flex-col gap-4">
        <Link
          href="/"
          className="inline-flex w-fit items-center gap-1 rounded-md text-sm text-muted-foreground outline-none transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
        >
          <ArrowLeft className="size-4" aria-hidden />
          전체 지표로 돌아가기
        </Link>
        <div className="flex flex-col gap-2">
          <h1 className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
            {displayName}
          </h1>
          {indicator ? (
            <p className="text-sm text-muted-foreground">
              {indicator.indicatorType} · {indicator.sourceCode}
            </p>
          ) : null}
        </div>
      </header>

      <section aria-label="원화·달러 이중 통화 차트">
        <Card className="gap-4 px-5 py-5">
          <CardHeader className="px-0">
            <CardTitle>원화·달러 환산 추이</CardTitle>
            <CardDescription>
              {loadFailed
                ? "데이터를 불러오지 못했습니다. 잠시 후 다시 시도해주세요."
                : points.length > 0
                  ? "좌축은 원화(KRW) 종가, 우축은 달러(USD) 환산가입니다. 상단 프리셋 버튼·날짜 입력 또는 하단 슬라이더로 기간을 조절하면 구간 수익률이 갱신됩니다."
                  : "표시할 시계열 데이터가 없습니다."}
            </CardDescription>
          </CardHeader>
          <DualCurrencyChart points={points} indicatorName={displayName} />
        </Card>
      </section>
    </div>
  );
}
