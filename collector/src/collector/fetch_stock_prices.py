from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from collector.date_windows import split_date_range
from collector.kis_client import KisClient

# TR: 국내주식기간별시세(일/주/월/년)
STOCK_DAILY_CHART_PATH = (
    "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
)
STOCK_DAILY_CHART_TR_ID = "FHKST03010100"

# FID_ORG_ADJ_PRC=0 은 수정주가. 액면분할 전후 종가 연속성 확보에 필수 — 절대 1로 바꾸지 말 것.
ORG_ADJ_PRICE_USE_ADJUSTED = "0"

# 응답 output2 필드명(국내주식 기간별시세). 출처: koreainvestment/open-trading-api
# examples_llm/domestic_stock/inquire_daily_itemchartprice, KIS API 포털 기간별시세 명세.
FIELD_BUSINESS_DATE = "stck_bsop_date"
FIELD_CLOSE_PRICE = "stck_clpr"
FIELD_OPEN_PRICE = "stck_oprc"
FIELD_HIGH_PRICE = "stck_hgpr"
FIELD_LOW_PRICE = "stck_lwpr"
FIELD_TRADE_VOLUME = "acml_vol"


def fetch_stock_daily_prices(
    kis_client: KisClient,
    indicator_id: str,
    stock_code: str,
    start_date: date,
    end_date: date,
) -> list[dict]:
    """국내주식 일봉을 start_date~end_date 구간에서 조회해 daily_prices 행 리스트로 반환한다.

    KIS 기간별시세는 1회 반환 건수가 제한되므로 120일 구간으로 분할 호출한다.
    휴장일 placeholder(빈 문자열/누락) 행은 제외하고 날짜 오름차순으로 정렬한다.
    """
    collected_rows: list[dict] = []

    for window_start_date, window_end_date in split_date_range(start_date, end_date):
        response_body = kis_client.request_quotation(
            path=STOCK_DAILY_CHART_PATH,
            tr_id=STOCK_DAILY_CHART_TR_ID,
            query_parameters={
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": stock_code,
                "FID_INPUT_DATE_1": window_start_date.strftime("%Y%m%d"),
                "FID_INPUT_DATE_2": window_end_date.strftime("%Y%m%d"),
                "FID_PERIOD_DIV_CODE": "D",
                "FID_ORG_ADJ_PRC": ORG_ADJ_PRICE_USE_ADJUSTED,
            },
        )

        for output_row in response_body.get("output2") or []:
            parsed_row = _parse_stock_price_row(output_row, indicator_id)
            if parsed_row is not None:
                collected_rows.append(parsed_row)

    collected_rows.sort(key=lambda row: row["price_date"])
    return collected_rows


def _parse_stock_price_row(output_row: dict, indicator_id: str) -> dict | None:
    """output2 한 행을 daily_prices 행으로 변환한다. 휴장일 placeholder면 None을 반환한다."""
    business_date_text = (output_row.get(FIELD_BUSINESS_DATE) or "").strip()
    close_price_text = (output_row.get(FIELD_CLOSE_PRICE) or "").strip()
    if not business_date_text or not close_price_text:
        return None

    trade_volume_text = (output_row.get(FIELD_TRADE_VOLUME) or "").strip()
    return {
        "indicator_id": indicator_id,
        "price_date": datetime.strptime(business_date_text, "%Y%m%d").date(),
        "close_price": Decimal(close_price_text),
        # 시/고/저/거래량은 비어 있어도 종가 수집을 막지 않도록 None으로 둔다 (DB 컬럼 nullable).
        "open_price": _parse_optional_decimal(output_row.get(FIELD_OPEN_PRICE)),
        "high_price": _parse_optional_decimal(output_row.get(FIELD_HIGH_PRICE)),
        "low_price": _parse_optional_decimal(output_row.get(FIELD_LOW_PRICE)),
        "trade_volume": int(trade_volume_text) if trade_volume_text else None,
    }


def _parse_optional_decimal(raw_text: str | None) -> Decimal | None:
    stripped_text = (raw_text or "").strip()
    return Decimal(stripped_text) if stripped_text else None
