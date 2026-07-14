import { ArrowLeft } from "lucide-react";
import { Card, CardHeader } from "@/components/ui/card";

/**
 * 지표 상세 페이지의 로딩 UI(Suspense fallback).
 *
 * page.tsx 는 Server Component 에서 10년치 일봉을 조회하므로 첫 페인트까지 시간이 걸린다.
 * 실제 페이지와 동일한 레이아웃(헤더 + 뒤로가기 링크 자리, Card 안 420px 차트 영역)의
 * 스켈레톤을 즉시 표시해 빈 화면 대기와 레이아웃 점프를 최소화한다.
 */
export default function IndicatorDetailLoading() {
  return (
    <div className="mx-auto flex min-h-screen max-w-6xl flex-col gap-8 px-4 py-10 sm:px-8">
      <header className="flex flex-col gap-4">
        {/* 뒤로가기 링크 자리 */}
        <span className="inline-flex w-fit items-center gap-1 text-sm text-muted-foreground">
          <ArrowLeft className="size-4" aria-hidden />
          전체 지표로 돌아가기
        </span>
        <div className="flex animate-pulse flex-col gap-2">
          {/* 제목 자리 */}
          <div className="h-8 w-64 max-w-full rounded-md bg-muted sm:h-9" />
          {/* 지표 타입 · 소스코드 자리 */}
          <div className="h-4 w-40 rounded bg-muted" />
        </div>
      </header>

      <section aria-label="원화·달러 이중 통화 차트 로딩 중" aria-busy="true">
        <Card className="gap-4 px-5 py-5">
          <CardHeader className="px-0">
            <div className="flex animate-pulse flex-col gap-2">
              {/* 카드 제목 자리 */}
              <div className="h-5 w-48 rounded bg-muted" />
              {/* 카드 설명 자리 */}
              <div className="h-4 w-72 max-w-full rounded bg-muted" />
            </div>
          </CardHeader>
          {/* 차트 영역(실제 차트 높이 420px 와 동일) */}
          <div className="flex flex-col gap-4">
            <div
              className="animate-pulse rounded-md bg-muted"
              style={{ height: 420 }}
            />
            {/* 구간 수익률 패널 자리 */}
            <div className="grid animate-pulse grid-cols-2 gap-4 sm:grid-cols-4">
              <div className="h-16 rounded-md bg-muted" />
              <div className="h-16 rounded-md bg-muted" />
              <div className="h-16 rounded-md bg-muted" />
              <div className="h-16 rounded-md bg-muted" />
            </div>
          </div>
        </Card>
      </section>
    </div>
  );
}
