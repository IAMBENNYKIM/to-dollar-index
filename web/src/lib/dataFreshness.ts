// 데이터 최신성(수집 지연) 판정 순수 함수 모음.
//
// 지표별 최신 데이터 날짜(latestDate)와 오늘 날짜(todayDate)를 비교해, 주말을 제외한
// 영업일 기준으로 며칠 밀렸는지와 지연 여부(isStale)를 계산한다.
// 모든 함수는 부수효과가 없으며 UTC 자정 기준으로 날짜를 계산해 서버 로컬 타임존 영향을 없앤다.

const MILLISECONDS_PER_DAY = 24 * 60 * 60 * 1000;

/** "YYYY-MM-DD" 를 UTC 자정 기준 epoch(ms) 로 변환한다. 파싱 실패 시 NaN. */
function toUtcMillis(dateString: string): number {
  return Date.parse(`${dateString}T00:00:00Z`);
}

/**
 * 서울(KST) 기준 오늘 날짜를 "YYYY-MM-DD" 로 반환한다.
 *
 * Vercel 서버는 UTC 로 동작하므로 `new Date()` 의 로컬 자정 기준으로 날짜를 뽑으면
 * KST 와 최대 9시간 어긋나 날짜가 하루 밀릴 수 있다. 따라서 timeZone 을 "Asia/Seoul" 로
 * 명시해 계산한다. en-CA 로케일은 날짜를 ISO 형식("YYYY-MM-DD")으로 포맷한다.
 *
 * @param now 기준 시각(테스트에서 고정 Date 주입용). 미지정 시 현재 시각.
 */
export function getTodayInSeoul(now: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Seoul" }).format(now);
}

/** 데이터 최신성 판정 결과. */
export interface FreshnessInfo {
  /** 최신 데이터 날짜("YYYY-MM-DD"). 입력을 그대로 전달한다. */
  latestDate: string;
  /** latestDate 다음 날부터 todayDate 까지 토·일을 제외한 영업일 수. */
  businessDaysBehind: number;
  /** businessDaysBehind 가 임계값 이상이면 true. */
  isStale: boolean;
}

/**
 * 데이터 최신성을 평가한다.
 *
 * latestDate 다음 날부터 todayDate(포함)까지 토요일·일요일을 제외한 영업일 수를 센다.
 * businessDaysBehind 가 staleAfterBusinessDays 이상이면 isStale=true.
 * todayDate 가 latestDate 이하(같거나 과거)이면 businessDaysBehind 는 0 이다.
 *
 * 한계: 한국 공휴일은 반영하지 않는다. 공휴일 다음 날에는 최대 하루 정도 지연을
 * 과대 판정할 수 있으나, 개인용 도구라 이 정도 오탐은 수용한다.
 */
export function evaluateDataFreshness(
  latestDate: string,
  todayDate: string,
  staleAfterBusinessDays: number,
): FreshnessInfo {
  const latestMillis = toUtcMillis(latestDate);
  const todayMillis = toUtcMillis(todayDate);

  let businessDaysBehind = 0;
  if (
    Number.isFinite(latestMillis) &&
    Number.isFinite(todayMillis) &&
    todayMillis > latestMillis
  ) {
    for (
      let cursorMillis = latestMillis + MILLISECONDS_PER_DAY;
      cursorMillis <= todayMillis;
      cursorMillis += MILLISECONDS_PER_DAY
    ) {
      const dayOfWeek = new Date(cursorMillis).getUTCDay(); // 0=일, 6=토
      if (dayOfWeek !== 0 && dayOfWeek !== 6) {
        businessDaysBehind += 1;
      }
    }
  }

  return {
    latestDate,
    businessDaysBehind,
    isStale: businessDaysBehind >= staleAfterBusinessDays,
  };
}
