# to-dollar-index 개발 로드맵

원화 자산 지표(주가·최저임금·부동산)를 달러로 환산해, 원화/달러 시계열을 일대일로 비교하는 개인용 웹 서비스.

## 개요

to-dollar-index는 **본인 + 지인 소수**를 위한 개인용 도구로, "원화 상승이 실질 구매력 상승인가"를 한 번의 조회로 확인하게 한다. 핵심 기능은 단 하나 — **각 지표의 원화 값 vs 달러 환산 값 시계열 비교**다.

- **환율 첫 화면**: 접속 즉시 최근 원/달러 환율 변동을 보여준다.
- **원화/달러 이중 차트**: 지표별로 원화 원본 + 조회 시점 환율로 파생한 달러 값을 함께 표시.
- **구간 수익률**: ECharts dataZoom으로 구간을 조정하면 원화%·달러%·환율효과%p를 실시간 계산.
- **무인 수집**: Python 배치가 GitHub Actions cron으로 일 1회 upsert(멱등) 수집, 월 1회 전체 재백필로 자가 치유.

기술 스택: collector(Python CLI) · supabase(PostgreSQL + RLS + 뷰) · web(Next.js 15 + TypeScript + Tailwind + shadcn/ui + ECharts, Vercel 배포).

## 진행률 요약

| Phase | 범위 | Task | 완료 | 상태 |
|-------|------|------|------|------|
| Phase 0 | 기반 스캐폴딩 | 001–005 | 5/5 | ✅ 완료 |
| Phase 1 | MVP (환율 + 국내주식) | 006–018 | 13/13 | ✅ 완료 |
| Phase 2 | 최저임금 | 019 | 1/1 | ✅ 완료 |
| Phase 3 | 부동산 | 020–021 | 2/2 | ✅ 완료 |
| Phase 4 | 운영 신뢰성 & UX 폴리시 | 022–026 | 5/5 | ✅ 완료 |
| Phase 5 | 보안 하드닝 | 027–028 | 2/2 | ✅ 완료 |
| **합계** | | **28** | **28/28 (100%)** | |

> **현재 상태**: **MVP 배포 + 무인 운영 가동**(GitHub Actions 수집 + Vercel + 텔레그램 실패 알림 + ECOS 환율 폴백, 시크릿 3개 등록·실발송 검증 완료 2026-07-16). Phase 5 보안 점검·하드닝, Phase 2 최저임금(Task 019)까지 반영 완료. 계획된 개발 Task 전량(28/28) 완료.

상태 범례: ✅ 완료 · 🔄 진행 중 · ⬜ 대기

---

## Phase 0 — 기반 (완료) ✅

저장소 골격, PRD, DB 스키마, collector/web 스캐폴딩을 완성해 이후 Phase가 병렬로 진행될 수 있는 기반을 마련한다.

### Task 001: 저장소 스캐폴딩 (README, .gitignore) ✅ 완료
- 산출물: `README.md`, `.gitignore`, `.env.example`
- 완료 기준: 모노레포 구조(collector/ · supabase/ · web/)와 실행 개요가 README에 기술됨.

### Task 002: PRD 작성 + 기술 검증 반영 ✅ 완료
- 산출물: `PRD.md`
- 완료 기준: 기능 요구(FR-1~6)·엣지 케이스·환율 TR 리스크 및 대안(ECOS 폴백)까지 문서화됨.

### Task 003: Supabase 초기 스키마·시드 SQL ✅ 완료
- 산출물: `supabase/migrations/0001_initial_schema.sql`, `supabase/migrations/0002_seed_indicators.sql`
- 완료 기준: 5개 테이블 + `daily_prices_with_usd` 뷰(security_invoker) + RLS(anon SELECT-only) 정의, 지표 시드 삽입.

### Task 004: collector 패키지 골격 (config, CLI 스텁) ✅ 완료
- 산출물: `collector/pyproject.toml`, `collector/src/collector/config.py`, `collector/src/collector/main.py`, `collector/tests/test_config.py`
- 완료 기준: 환경변수 로드 config 및 CLI 진입점 스텁 존재, `test_config` 통과.

### Task 005: Next.js 15 스캐폴딩 (Tailwind, shadcn/ui, ECharts, vitest) ✅ 완료
- 산출물: `web/package.json`, `web/next.config.ts`, `web/vitest.config.ts`, `web/src/app/`, `web/src/components/ui/`, `web/components.json`
- 완료 기준: App Router 초기 페이지 렌더, shadcn/ui·Tailwind 적용, vitest 샘플 테스트(`web/src/lib/__tests__/sample.test.ts`) 통과.

---

## Phase 1 — MVP: 환율 + 국내주식 (완료) ✅

**마일스톤: Phase 1 완료 = MVP 배포.** 환율 첫 화면 + 삼성전자 원화/달러 이중 차트 + dataZoom 구간 수익률을 실데이터로 검증하고 Vercel에 배포한다.

### Task 006: KIS 토큰 발급·캐싱 (kis_auth.py) ✅ 완료
- 산출물: `collector/src/collector/kis_auth.py`
- 완료 기준: 접근토큰 발급 후 파일/메모리 캐시 재사용, 만료 시에만 재발급(발급 빈도 ~1분 1회 제한 대응). 백필 전 구간에서 발급 호출이 최소로 유지됨(단위 테스트로 재사용 검증).

### Task 007: Supabase writer (database_writer.py) ✅ 완료
- 산출물: `collector/src/collector/database_writer.py`
- 완료 기준: service_role 키로 `daily_prices`·`exchange_rates` upsert. 같은 값 재삽입 시 결과 동일(멱등). `--dry-run` 시 쓰기 없이 대상 행 수만 출력.

### Task 008: 백필 구간 분할 유틸 (date_windows.py) ✅ 완료
- 산출물: `collector/src/collector/date_windows.py`, `collector/tests/test_date_windows.py`
- 완료 기준: 임의 시작~종료일을 **120일 이하 구간**으로 분할(기간별시세 1회 100건 제한 대응). 경계·역순·단일일 케이스 단위 테스트 통과.

### Task 009: 국내주식 일봉 수집 (FHKST03010100, 수정주가) ✅ 완료
- 산출물: `collector/src/collector/kis_stock.py`
- 의존: 006, 007, 008
- 완료 기준: 삼성전자 일봉을 **수정주가**로 조회해 `daily_prices`에 upsert. 2018 액면분할 구간에서 시계열 불연속 없음(수집값과 공개 종가 표본 대조).

### Task 010: 환율 일봉 수집 (FHKST03030100) ✅ 완료 (종목코드 FX@KRW 확정)
- 산출물: `collector/src/collector/kis_exchange.py`
- 의존: 006, 007, 008
- 완료 기준: `FID_COND_MRKT_DIV_CODE='X'`로 원/달러 일봉 조회 → `exchange_rates` upsert. **dry-run으로 `FID_INPUT_ISCD`(종목코드) 확정**. 확정 실패 시 **한국은행 ECOS API로 소스 교체**(PRD 리스크 대안). 결정 결과와 근거를 코드 주석/커밋에 명시.

### Task 011: 수집 CLI 통합 (backfill / daily / --dry-run) ✅ 완료
- 산출물: `collector/src/collector/main.py` (기존 스텁 확장)
- 의존: 009, 010
- 완료 기준: `backfill`(전 구간)·`daily`(증분)·`--dry-run` 서브커맨드 동작. `daily`는 `max(price_date)+1`부터 증분 수집해 실패일 자동 복구. 같은 명령 반복 실행 시 결과 동일(멱등).

### Task 012: GitHub Actions 수집 워크플로 (일일 + 월간 재백필·keepalive) ✅ 완료
- 산출물: `.github/workflows/daily-collect.yml`, `.github/workflows/monthly-rebackfill.yml`
- 의존: 011
- 완료 기준: 일일 워크플로가 **평일 KST 19시** cron으로 `daily` 실행. 월 1회 워크플로가 전체 재백필(FR-6, basis drift 대응) 후 **heartbeat 파일 커밋(keepalive)** — GitHub 60일 비활성 및 Supabase 7일 일시정지를 동시 방지. Secrets로 KIS·Supabase 키 주입, 수동 트리거(workflow_dispatch) 지원.

### Task 013: 프론트 Supabase 클라이언트·쿼리 ✅ 완료
- 산출물: `web/src/lib/supabase.ts`, `web/src/lib/queries.ts`
- 의존: Phase 0 (Task 003 스키마)
- 완료 기준: Server Component에서 anon 키로 `exchange_rates`·`daily_prices_with_usd` fetch. **브라우저 직접 조회 없음**, ISR `revalidate 3600` 적용. 반환 타입을 TypeScript 인터페이스로 정의.

### Task 014: 구간 수익률 계산 함수 (rangeReturns.ts + vitest) ✅ 완료
- 산출물: `web/src/lib/rangeReturns.ts`, `web/src/lib/__tests__/rangeReturns.test.ts`
- 의존: 013 (타입)
- 완료 기준: 구간 첫/마지막 거래일 기준 `krwReturnPercent`·`usdReturnPercent`·`exchangeRateEffect(%p = USD − KRW)` 계산. **엣지 케이스 단위 테스트**: 구간 경계 비거래일 → 최근접 거래일 선택, 시작값 0/NULL → 0 나눗셈 방어, 달러 시리즈 NULL 구간 처리.

### Task 015: 첫 화면 환율 차트 + 통계 타일 ✅ 완료
- 산출물: `web/src/app/page.tsx`, `web/src/components/ExchangeRateChart.tsx`, `web/src/components/StatTile.tsx`
- 의존: 013
- 완료 기준: 접속 시 최근 원/달러 환율 시계열 차트 표시(ECharts, `dynamic import ssr:false`). 최근 변동 방향·폭을 통계 타일로 요약. 서버가 내려준 데이터를 props로 받아 클라이언트는 렌더만 담당.

### Task 016: 지표 상세 원화/달러 이중 차트 + dataZoom 구간 수익률 ✅ 완료
- 산출물: `web/src/app/indicators/[id]/page.tsx`, `web/src/components/DualAxisChart.tsx`, `web/src/components/RangeReturnPanel.tsx`
- 의존: 013, 014, 015
- 완료 기준: 동일 시계열에 원화 값 + 달러 환산 값 동시 표시. dataZoom 이벤트에 반응해 구간 수익률 패널(Task 014 계산) **실시간 갱신**. 환율 데이터 이전 구간은 달러 시리즈 미표시(USD=NULL 처리).

### Task 017: 지표 내비게이션·카드 목록 → MVP 완성 ✅ 완료 (첫 화면 지표 카드 목록으로 구현)
- 산출물: `web/src/components/IndicatorNav.tsx`, `web/src/components/IndicatorCard.tsx`, 관련 라우팅 연결
- 의존: 016
- 완료 기준: 지표 목록/카드에서 상세 페이지로 이동하는 내비게이션 완성. 첫 화면 → 지표 목록 → 상세(이중 차트 + 구간 수익률) 전체 플로우가 끊김 없이 동작 = **MVP 기능 완성**.

### Task 018: 실데이터 검증 + Vercel 배포 ✅ 완료
- 산출물: Supabase 프로젝트(운영), Vercel 배포(Root Directory = `web`), 검증 결과 기록
- 의존: 012, 017
- 검증: 모의투자로 10년 백필(주식 2830행·환율 2824행, 2015-01-02~2026-07-14). 액면분할(2018-05) 수정주가 연속성, 달러 환산 뷰·멱등성·RLS·프론트 전량 렌더 통과. GitHub 저장소 push + Actions Secrets + Vercel 연결로 **MVP 배포 완료**.

---

## Phase 2 — 최저임금 (완료) ✅

**마일스톤: 연도별 최저임금의 원화/달러 실질 구매력 비교 제공.**

**설계 개정**: 원래 계획한 전용 `minimum_wages` 테이블·별도 `/minimum-wage` 페이지·`MinimumWageChart` 컴포넌트를 폐기하고, **부동산(Task 021) 선례를 그대로 미러링**한다. 즉 기존 `daily_prices`(지표 `minimum_wage:hourly`, `price_date`=해당 연도 1월 1일, `close_price`=시간급 원)와 `indicators`를 재사용하고, 상세 페이지(`indicators/[id]`)를 지표 타입으로 분기 재사용한다. USD 환산은 시점 환율이 아니라 **해당 연도 평균 환율**을 쓰는 전용 뷰(`minimum_wage_prices_with_usd`, `date_trunc('year')`)로 파생한다(연 데이터는 연평균이 의미상 정확하며, 진행 중인 연도는 YTD 평균이라 새 환율이 쌓이면 값이 갱신됨). 기준값은 시간급.

### Task 019: 최저임금 시간급 시드 + 연평균 환율 USD 환산 뷰 + 상세 페이지 분기 ✅ 완료
- 산출물: `supabase/migrations/0004_minimum_wage.sql`, `web/src/lib/indicatorQueries.ts`(`fetchMinimumWageYearlyWithUsd`, `fetchLatestDualCurrencyPoints` 분기), `web/src/app/indicators/[id]/page.tsx`(타입 분기)
- 의존: Phase 1, Task 021(재사용 패턴)
- 완료 기준: 정적 시드로 `minimum_wage:hourly` 지표 + 시간급 12행(2015~2026, minimumwage.go.kr 고시값·교차검증) 적재. 연평균 USD 환산 뷰(`minimum_wage_prices_with_usd`, security_invoker) 마이그레이션. 상세 페이지가 `indicatorType === 'minimum_wage'`이면 연평균 뷰를 조회하도록 분기. 반환 컬럼이 동일해 `mapDualCurrencyRow`·`DualCurrencyChart`·구간 수익률·홈 카드 전부 재사용. 정적 데이터라 별도 수집기 없음. web 빌드·테스트(94) 통과.

---

## Phase 3 — 부동산 (완료) ✅

**마일스톤: 서울 소형 아파트 월별 매매가의 원화/달러 비교 제공.**

**설계 개정**: 데이터 소스를 국토부 실거래가 API → **KOSIS 한국부동산원 통계표**(`DT_KAB_11672_S19`, 서울 소형 40㎡초과 60㎡이하)로 교체하고 **59㎡ 기준 원(KRW)으로 환산**한다. 저장은 신규 테이블 대신 **기존 `daily_prices` 지표(`real_estate:seoul-small`)를 재사용**(월별, `price_date`=해당 월 1일). USD 환산은 시점 환율 폴백이 아니라 **해당 월 평균 환율**을 쓰는 전용 뷰(`real_estate_prices_with_usd`)로 파생한다(월 데이터는 그 달이 끝난 뒤 확정 공개되므로 월평균이 의미상 정확). 프론트는 별도 페이지 없이 **기존 상세 페이지(`indicators/[id]`)를 지표 타입으로 분기 재사용**한다.

### Task 020: KOSIS 한국부동산원 부동산 수집기 ✅ 완료
- 산출물: collector의 KOSIS 수집 로직(`real_estate:seoul-small` 지표 적재), `.github/workflows` 수집 스텝 `KOSIS_KEY` env 확장
- 의존: Phase 1 (collector 인프라)
- 완료 기준: KOSIS OpenAPI(`DT_KAB_11672_S19`, 서울 소형 40㎡초과 60㎡이하) 조회 → 59㎡ 원(KRW) 환산 → `daily_prices`에 월별 upsert(`price_date`=해당 월 1일, `close_price`=59㎡ 환산 원가). 멱등 보장. `daily`·`monthly-rebackfill` 워크플로 env에 `KOSIS_KEY` 추가.
- Actions Secret `KOSIS_KEY` 등록 및 백필 실행 완료.

### Task 021: 부동산 월별 원화/달러 노출 (뷰 + 상세 페이지 분기) ✅ 완료
- 산출물: `supabase/migrations/0003_real_estate.sql`, `web/src/lib/indicatorQueries.ts`(`fetchRealEstateMonthlyWithUsd`), `web/src/app/indicators/[id]/page.tsx`(타입 분기)
- 의존: 020
- 완료 기준: 지표 시드(`real_estate:seoul-small`) + 월평균 환율 USD 환산 뷰(`real_estate_prices_with_usd`, security_invoker) 마이그레이션. 상세 페이지가 `indicatorType === 'real_estate'`이면 월별 뷰를, 아니면 기존 `daily_prices_with_usd`를 조회하도록 분기. 반환 컬럼이 동일해 `mapDualCurrencyRow`·`DualCurrencyChart`·dataZoom 구간 수익률(Task 014) 전부 재사용. web 빌드·테스트 통과.
- `0003_real_estate.sql` 운영 DB 적용 완료.

---

## Phase 4 — 운영 신뢰성 & UX 폴리시 (완료) ✅

**마일스톤: 무인 운영 안정화 — 수집 실패·데이터 지연을 즉시 인지하고, 환율 수집을 이중화하며, 첫 화면에서 지표 현황을 한눈에 파악한다.**

### Task 022: 데이터 최신성 배지 ✅ 완료
- 산출물: `web/src/lib/dataFreshness.ts`, `web/src/components/DataFreshnessBadge.tsx`, 홈·상세 페이지 배선
- 의존: Phase 1
- 완료 기준: 홈 환율 차트·지표 상세 헤더에 마지막 수집일("기준일") 표시. KST 기준·주말 제외 영업일 2일 이상 지연 시 amber 경고(아이콘 병행). 부동산(월별)은 지연 판정 없이 날짜만 표시. 공휴일 미반영 한계는 주석 명시. 순수 함수 단위 테스트 통과.

### Task 023: 수집 실패 텔레그램 알림 ✅ 완료
- 산출물: `daily-collect.yml`·`monthly-rebackfill.yml`의 `if: failure()` 텔레그램 알림 스텝
- 의존: 012
- 완료 기준: 워크플로 실패 시 텔레그램으로 워크플로명 + 실행 로그 링크 발송. `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` 시크릿 미설정 시 스킵(기존 동작 무영향). collector 코드 무수정.
- 런타임 검증 완료(2026-07-16): 시크릿 등록·봇 /start·실발송 성공 확인.

### Task 024: 환율 ECOS 폴백 이중화 ✅ 완료
- 산출물: `collector/src/collector/fetch_exchange_rates_ecos.py`, config `ECOS_API_KEY` 선택값, main 폴백 배선, 워크플로 env
- 의존: 010, 011
- 완료 기준: KIS 환율 조회 실패(`KisQuotationError`) 시 한국은행 ECOS StatisticSearch(731Y001/D/0000001, 매매기준율)로 폴백해 동일 스키마로 upsert. 키 없으면 기존 동작(에러 전파) 유지. 폴백·무데이터·에러 케이스 단위 테스트 통과.
- 런타임 검증 완료(2026-07-16): 실키 호출 성공(스키마 일치) 확인.

### Task 025: 첫 화면 요약 대시보드 ✅ 완료
- 산출물: `web/src/lib/indicatorQueries.ts`(`fetchLatestDualCurrencyPoints`), `web/src/lib/indicatorSummary.ts`, `web/src/components/IndicatorCard.tsx`
- 의존: 017
- 완료 기준: 홈 지표 카드에 최신 원화값·달러 환산값·직전 대비 변동률·기준일 표시. 지표별 최신 2행만 경량 조회(내림차순 limit, 병렬), 개별 실패는 요약 없는 카드로 폴백.

### Task 026: 모바일 반응형 개선 ✅ 완료
- 산출물: `ExchangeRateChart.tsx`·`DualCurrencyChart.tsx`·`loading.tsx` 반응형 처리
- 의존: 016
- 완료 기준: 차트 고정 높이를 반응형(모바일 280/320px → sm 360/420px)으로 교체, 날짜 입력 컨트롤 모바일 세로 스택, 좁은 뷰포트에서 이중 y축 이름 숨김·라벨/슬라이더 축소로 플롯 영역 확보.

---

## Phase 5 — 보안 하드닝 (완료) ✅

**마일스톤: 보안 점검(web/collector/CI/git 이력)에서 발견된 취약점을 치유하고 결과를 기록한다.** (저장소 public 전제)

### Task 027: 보안 점검 및 하드닝 ✅ 완료
- 산출물: `fetch_exchange_rates_ecos.py`·`fetch_real_estate.py` HTTP 예외 메시지 정화(+테스트 4개), `monthly-rebackfill.yml` 입력값 env 경유, `daily-collect.yml` `contents: read`, `web/next.config.ts` 보안 응답 헤더 4종
- 완료 기준: ECOS·KOSIS API 키가 httpx 예외 메시지(URL)로 stderr에 유출되지 않음(테스트로 고정), workflow_dispatch 입력 셸 보간 제거, daily 잡 토큰 최소 권한, 전 경로에 nosniff·X-Frame-Options·Referrer-Policy·Permissions-Policy 적용.
- 점검 결과(수정 불필요 확인): git 전 이력 시크릿 유출 없음, RLS SELECT-only + 쓰기 revoke, web은 anon 키만 사용, XSS 싱크 없음, TLS 무력화 없음. npm audit moderate 1건(next 번들 postcss, GHSA-qx2v-qp2m-jg93)은 신뢰하지 않는 CSS 입력이 없어 수용. 액션 SHA 핀 고정은 공식 액션 2개뿐이라 비채택.

### Task 028: 화이트햇 진단 후속 하드닝 ✅ 완료
- 산출물: `web/src/app/indicators/[id]/page.tsx`(generateStaticParams + `dynamicParams=false`), `web/next.config.ts`(CSP 헤더)
- 배경: 구현 컨텍스트 없는 독립 서브에이전트가 블랙박스+화이트박스 화이트햇 진단 수행. Critical/High 없음(서버 API 라우트 없음, PostgREST 바인딩, RLS SELECT-only). 도출된 Medium 조치.
- 완료 기준: 동적 라우트를 활성 지표만 정적 프리렌더로 제한(미등록 id는 서버 렌더·DB 조회 없이 404 → 비용/DoS 표면 제거), 저위험 CSP(`frame-ancestors 'none'`·`base-uri 'self'`·`object-src 'none'`·`form-action 'self'`) 적용. 프로덕션 실측 완료: CSP 헤더 반영, 유효 id 200 / 무효 id 404, HSTS 포함 기존 헤더 5종 유지.
- 비채택/수용: HSTS 명시(프로덕션 실측상 Vercel 자동 적용 확인 → 불필요), 엄격 script/style-src CSP(Next 인라인·ECharts 충돌 위험 → 브라우저 육안 검증 후 별도), Supabase env 서버 전용 이전(Vercel 콘솔 동반 변경 필요 → 보류).

---

## 개발 원칙 (요약)

- **멱등성 우선**: 모든 수집은 upsert 기반. 재실행/재수집이 안전하고 자가 치유된다.
- **달러는 저장하지 않는다**: 원화 원본만 저장하고 조회 시점 뷰(`daily_prices_with_usd`)에서 파생, 직전 환율 폴백.
- **정확성 최우선**: 수정주가(분할 연속성) + 직전 환율 폴백으로 결측일·분할일에도 값이 끊기거나 튀지 않게 한다.
- **무인 운영**: GitHub Actions cron 일 1회 수집 + 월 1회 재백필/keepalive로 사람 개입 없이 유지.
- **1인 유지보수 가능한 단순 구조**: 별도 API 서버 없이 Server Component + ISR로 통일.
