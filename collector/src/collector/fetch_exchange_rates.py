from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from collector.date_windows import split_date_range
from collector.kis_client import KisClient

# TR: 해외지수/환율 기간별시세
EXCHANGE_RATE_DAILY_CHART_PATH = (
    "/uapi/overseas-price/v1/quotations/inquire-daily-chartprice"
)
EXCHANGE_RATE_DAILY_CHART_TR_ID = "FHKST03030100"

CURRENCY_PAIR_USD_KRW = "USD_KRW"

# FID_COND_MRKT_DIV_CODE=X 는 "환율" 계열.
# 출처: koreainvestment/open-trading-api
# examples_llm/overseas_stock/inquire_daily_chartprice/inquire_daily_chartprice.py
# docstring "N: 해외지수, X 환율, I: 국채, S:금선물".
MARKET_DIV_CODE_EXCHANGE_RATE = "X"

# 원/달러 환율 종목코드. 모의 도메인 실호출(scripts/probe_kis.py)로 확정: 후보 6종 중
# 'FX@KRW'만 유효한 시계열(output2)을 반환했고 값도 원/달러 환율과 일치했다(예: 2026-07-13 종가 1493.8).
USD_KRW_INPUT_ISCD = "FX@KRW"

# 응답 output2 필드명(해외지수/환율 계열). 종가 ovrs_nmix_prpr, 영업일 stck_bsop_date.
# probe 실응답에서 확인: {'stck_bsop_date': '20260713', 'ovrs_nmix_prpr': '1493.8000', ...}.
# exchange_rates 테이블은 종가만 저장하므로 종가 필드만 파싱한다.
FIELD_BUSINESS_DATE = "stck_bsop_date"
FIELD_CLOSE_RATE = "ovrs_nmix_prpr"


def fetch_usd_krw_exchange_rates(
    kis_client: KisClient,
    start_date: date,
    end_date: date,
) -> list[dict]:
    """원/달러 환율 일봉을 조회해 exchange_rates 행 리스트로 반환한다.

    120일 구간으로 분할 호출하고, 휴장일 placeholder 행은 제외해
    날짜 오름차순으로 정렬한다.
    """
    collected_rows: list[dict] = []

    for window_start_date, window_end_date in split_date_range(start_date, end_date):
        response_body = kis_client.request_quotation(
            path=EXCHANGE_RATE_DAILY_CHART_PATH,
            tr_id=EXCHANGE_RATE_DAILY_CHART_TR_ID,
            query_parameters={
                "FID_COND_MRKT_DIV_CODE": MARKET_DIV_CODE_EXCHANGE_RATE,
                "FID_INPUT_ISCD": USD_KRW_INPUT_ISCD,
                "FID_INPUT_DATE_1": window_start_date.strftime("%Y%m%d"),
                "FID_INPUT_DATE_2": window_end_date.strftime("%Y%m%d"),
                "FID_PERIOD_DIV_CODE": "D",
            },
        )

        for output_row in response_body.get("output2") or []:
            parsed_row = _parse_exchange_rate_row(output_row)
            if parsed_row is not None:
                collected_rows.append(parsed_row)

    collected_rows.sort(key=lambda row: row["rate_date"])
    return collected_rows


def _parse_exchange_rate_row(output_row: dict) -> dict | None:
    """output2 한 행을 exchange_rates 행으로 변환한다. 휴장일 placeholder면 None을 반환한다."""
    business_date_text = (output_row.get(FIELD_BUSINESS_DATE) or "").strip()
    close_rate_text = (output_row.get(FIELD_CLOSE_RATE) or "").strip()
    if not business_date_text or not close_rate_text:
        return None

    return {
        "currency_pair": CURRENCY_PAIR_USD_KRW,
        "rate_date": datetime.strptime(business_date_text, "%Y%m%d").date(),
        "close_rate": Decimal(close_rate_text),
    }
