# to-dollar-index

한국 자산 지표(주가·최저임금·부동산)를 **달러 가치로 환산**해 실질 상승 여부를 확인하는 개인용 웹 대시보드.

원화 가치 하락 국면에서 "원화로는 올랐지만 달러로는 얼마나 올랐는가?"를 지표별 원화/달러 시계열 일대일 비교와 인터랙티브 구간 수익률로 확인한다.

## 아키텍처

```
[일 1회, GitHub Actions cron]
Python 수집 배치 (collector/)
  ├─ KIS 오픈API → 주가/환율 일일 종가
  └─ upsert → Supabase (PostgreSQL)

[사용자 접속 시]
Next.js 15 (web/, Vercel 배포)
  └─ Supabase 직접 조회 → ECharts 차트 렌더링
```

- 상시 실행 서버 없음. 달러 환산은 저장하지 않고 조회 시점에 DB 뷰(`daily_prices_with_usd`)에서 계산.
- 데이터 소스: 주가·환율 = 한국투자증권 KIS 오픈API, 최저임금 = 최저임금위원회 고시 시간급 정적 시드, 부동산 = KOSIS 한국부동산원 통계(월별, 서울 소형 아파트).
- 최저임금·부동산은 별도 테이블 없이 `daily_prices`를 재사용하고, USD 환산은 각각 연평균 뷰(`minimum_wage_prices_with_usd`)·월평균 뷰(`real_estate_prices_with_usd`)에서 파생한다.

## 디렉토리 구조

| 경로 | 설명 |
|---|---|
| `collector/` | Python 수집 배치 (KIS API → Supabase) |
| `supabase/migrations/` | DB 스키마 마이그레이션 SQL |
| `web/` | Next.js 15 프론트엔드 (Vercel Root Directory = `web`) |
| `.github/workflows/` | 일일 수집 cron 워크플로 |

## 환경 변수

| 변수 | 사용처 | 설명 |
|---|---|---|
| `KIS_APP_KEY` / `KIS_APP_SECRET` | collector, GitHub Actions | KIS 개발자센터 앱키/시크릿 |
| `KIS_BASE_URL` | collector, GitHub Actions | 실전: `https://openapi.koreainvestment.com:9443` |
| `SUPABASE_URL` | collector, GitHub Actions | Supabase 프로젝트 URL |
| `SUPABASE_SERVICE_ROLE_KEY` | collector, GitHub Actions | 쓰기용 service_role 키 (프론트 노출 금지) |
| `NEXT_PUBLIC_SUPABASE_URL` | web, Vercel | Supabase 프로젝트 URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | web, Vercel | 읽기 전용 anon 키 (RLS로 select만 허용) |

로컬 개발: `collector/`는 저장소 루트의 `.env`, `web/`은 `web/.env.local` 사용.

## 수집 CLI (collector)

```bash
# 초기 백필 (과거 데이터 대량 적재)
python -m collector.main backfill --from 2015-01-01 [--indicator stock:005930] [--dry-run]

# 일일 증분 수집 (GitHub Actions에서 자동 실행)
python -m collector.main daily [--dry-run]
```

## 지표 추가 방법

지표는 두 종류다.

**1) 수집기 기반 (주가 등)** — 일별 API로 증분 수집.
1. Supabase에 지표 등록: `insert into indicators values ('stock:000660', 'stock', '000660', 'SK하이닉스');`
2. 백필 1회 실행: `python -m collector.main backfill --from 2015-01-01 --indicator stock:000660`

**2) 정적/집계 기반 (최저임금·부동산)** — 마이그레이션 SQL로 지표·데이터·전용 USD 뷰를 함께 등록한다(`supabase/migrations/0004_minimum_wage.sql` 등 참고). 최저임금은 정적 시드, 부동산은 KOSIS 수집기가 `daily_prices`에 월별 적재.

> **배포 순서 주의**: 상세 페이지(`indicators/[id]`)는 `dynamicParams=false` + `generateStaticParams`(빌드 타임 DB 조회)로 SSG된다. 새 지표는 **DB에 먼저 등록/시드한 뒤 재배포(push)**해야 상세 페이지가 프리렌더된다. 순서가 반대면 재배포 전까지 해당 상세 경로가 404된다.
