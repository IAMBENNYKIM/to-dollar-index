"""KIS 모의/실전 시세 조회를 Supabase 없이 검증하는 일회성 probe 스크립트.

확인 목적:
1. 현재 KIS 도메인(모의/실전)에서 국내주식 기간별시세 조회가 동작하는가.
2. 원/달러 환율(FID_COND_MRKT_DIV_CODE='X')의 FID_INPUT_ISCD 종목코드가 무엇인가.

실행: collector 디렉토리에서
    .venv/Scripts/python scripts/probe_kis.py
"""

from __future__ import annotations

from datetime import date, timedelta

from collector.config import CollectorConfig, load_kis_settings
from collector.fetch_exchange_rates import (
    EXCHANGE_RATE_DAILY_CHART_PATH,
    EXCHANGE_RATE_DAILY_CHART_TR_ID,
    MARKET_DIV_CODE_EXCHANGE_RATE,
)
from collector.fetch_stock_prices import fetch_stock_daily_prices
from collector.kis_auth import get_access_token
from collector.kis_client import KisClient

# 원/달러 환율 종목코드 후보. 공식 문서에 명시가 없어 실호출로 어느 것이 유효한지 가려낸다.
USD_KRW_ISCD_CANDIDATES = [
    "FX@KRW",
    "FX@KRW3",
    "FX@USD",
    "KRW",
    "USDKRW",
    "FX@USDKRW",
]


def _build_config_from_kis_settings() -> CollectorConfig:
    # probe는 Supabase를 쓰지 않으므로 Supabase 필드는 빈 값으로 둔다.
    kis_settings = load_kis_settings()
    return CollectorConfig(
        kis_app_key=kis_settings.app_key,
        kis_app_secret=kis_settings.app_secret,
        kis_base_url=kis_settings.base_url,
        supabase_url="",
        supabase_service_role_key="",
    )


def probe_domestic_stock(kis_client: KisClient, start_date: date, end_date: date) -> None:
    print("\n[1] 국내주식 기간별시세 조회 (삼성전자 005930)")
    try:
        rows = fetch_stock_daily_prices(
            kis_client,
            indicator_id="stock:005930",
            stock_code="005930",
            start_date=start_date,
            end_date=end_date,
        )
    except Exception as error:
        print(f"  실패: {error}")
        return

    print(f"  성공: {len(rows)}건 수집")
    for row in rows[:3]:
        print(f"    {row['price_date']} 종가 {row['close_price']}")


def probe_exchange_rate_candidates(
    kis_client: KisClient, start_date: date, end_date: date
) -> None:
    print("\n[2] 원/달러 환율 종목코드 후보 탐색 (FID_COND_MRKT_DIV_CODE='X')")
    for candidate_iscd in USD_KRW_ISCD_CANDIDATES:
        print(f"  - 후보 '{candidate_iscd}':", end=" ")
        try:
            response_body = kis_client.request_quotation(
                path=EXCHANGE_RATE_DAILY_CHART_PATH,
                tr_id=EXCHANGE_RATE_DAILY_CHART_TR_ID,
                query_parameters={
                    "FID_COND_MRKT_DIV_CODE": MARKET_DIV_CODE_EXCHANGE_RATE,
                    "FID_INPUT_ISCD": candidate_iscd,
                    "FID_INPUT_DATE_1": start_date.strftime("%Y%m%d"),
                    "FID_INPUT_DATE_2": end_date.strftime("%Y%m%d"),
                    "FID_PERIOD_DIV_CODE": "D",
                },
            )
        except Exception as error:
            print(f"실패: {error}")
            continue

        output2 = response_body.get("output2") or []
        output1 = response_body.get("output1") or {}
        print(f"성공 rt_cd=0, output2 {len(output2)}행")
        if output1:
            # output1에 종목명/현재가가 있으면 어떤 상품인지 식별에 도움이 된다.
            print(f"      output1 keys: {sorted(output1)[:12]}")
        if output2:
            print(f"      output2[0]: {output2[0]}")


def main() -> None:
    config = _build_config_from_kis_settings()
    print(f"KIS 도메인: {config.kis_base_url}")

    access_token = get_access_token(config)
    print("토큰 발급 성공")

    kis_client = KisClient(config, access_token)

    end_date = date.today()
    start_date = end_date - timedelta(days=14)
    print(f"조회 구간: {start_date} ~ {end_date}")

    probe_domestic_stock(kis_client, start_date, end_date)
    probe_exchange_rate_candidates(kis_client, start_date, end_date)


if __name__ == "__main__":
    main()
