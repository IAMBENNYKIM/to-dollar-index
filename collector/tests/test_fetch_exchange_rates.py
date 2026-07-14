from __future__ import annotations

from datetime import date
from decimal import Decimal

import httpx
import pytest
import respx

from collector.config import KIS_PRODUCTION_BASE_URL, CollectorConfig
from collector.fetch_exchange_rates import (
    CURRENCY_PAIR_USD_KRW,
    EXCHANGE_RATE_DAILY_CHART_PATH,
    EXCHANGE_RATE_DAILY_CHART_TR_ID,
    MARKET_DIV_CODE_EXCHANGE_RATE,
    USD_KRW_INPUT_ISCD,
    fetch_usd_krw_exchange_rates,
)
from collector.kis_client import (
    INTER_REQUEST_WAIT_SECONDS,
    KisClient,
    KisQuotationError,
)

EXCHANGE_RATE_DAILY_CHART_URL = (
    f"{KIS_PRODUCTION_BASE_URL}{EXCHANGE_RATE_DAILY_CHART_PATH}"
)


def build_test_config() -> CollectorConfig:
    return CollectorConfig(
        kis_app_key="test-app-key",
        kis_app_secret="test-app-secret",
        kis_base_url=KIS_PRODUCTION_BASE_URL,
        supabase_url="https://example.supabase.co",
        supabase_service_role_key="test-service-role-key",
    )


def build_kis_client(sleep_function=None) -> KisClient:
    return KisClient(
        config=build_test_config(),
        access_token="test-token",
        http_client=httpx.Client(),
        sleep_function=sleep_function if sleep_function is not None else (lambda _: None),
    )


def build_output2_row(business_date: str, close_rate: str = "1350.50") -> dict:
    return {
        "stck_bsop_date": business_date,
        "ovrs_nmix_prpr": close_rate,
        "ovrs_nmix_oprc": "1349.00",
        "ovrs_nmix_hgpr": "1352.00",
        "ovrs_nmix_lwpr": "1348.00",
    }


def build_success_response(output2_rows: list[dict]) -> httpx.Response:
    return httpx.Response(
        200,
        json={"rt_cd": "0", "msg_cd": "MCA00000", "msg1": "정상처리", "output2": output2_rows},
    )


@respx.mock
def test_parses_rows_into_exchange_rate_format_sorted_ascending() -> None:
    quotation_route = respx.get(EXCHANGE_RATE_DAILY_CHART_URL).mock(
        return_value=build_success_response(
            [
                build_output2_row("20260110", close_rate="1360.00"),
                build_output2_row("20260109", close_rate="1355.25"),
                build_output2_row("20260108", close_rate="1350.50"),
            ]
        )
    )

    rate_rows = fetch_usd_krw_exchange_rates(
        build_kis_client(),
        start_date=date(2026, 1, 8),
        end_date=date(2026, 1, 10),
    )

    assert quotation_route.call_count == 1
    assert [row["rate_date"] for row in rate_rows] == [
        date(2026, 1, 8),
        date(2026, 1, 9),
        date(2026, 1, 10),
    ]

    first_row = rate_rows[0]
    assert first_row["currency_pair"] == CURRENCY_PAIR_USD_KRW
    assert first_row["close_rate"] == Decimal("1350.50")
    assert isinstance(first_row["close_rate"], Decimal)
    # 스펙상 exchange_rates 행은 종가만 저장한다.
    assert set(first_row.keys()) == {"currency_pair", "rate_date", "close_rate"}

    request_url = quotation_route.calls.last.request.url
    assert request_url.params["FID_COND_MRKT_DIV_CODE"] == MARKET_DIV_CODE_EXCHANGE_RATE
    assert request_url.params["FID_INPUT_ISCD"] == USD_KRW_INPUT_ISCD
    assert request_url.params["FID_PERIOD_DIV_CODE"] == "D"
    assert request_url.params["FID_INPUT_DATE_1"] == "20260108"
    assert request_url.params["FID_INPUT_DATE_2"] == "20260110"

    request_headers = quotation_route.calls.last.request.headers
    assert request_headers["tr_id"] == EXCHANGE_RATE_DAILY_CHART_TR_ID
    assert request_headers["authorization"] == "Bearer test-token"
    assert request_headers["custtype"] == "P"


@respx.mock
def test_filters_out_holiday_placeholder_rows() -> None:
    respx.get(EXCHANGE_RATE_DAILY_CHART_URL).mock(
        return_value=build_success_response(
            [
                build_output2_row("20260109"),
                {"stck_bsop_date": "", "ovrs_nmix_prpr": ""},
                {"stck_bsop_date": "20260107", "ovrs_nmix_prpr": ""},
            ]
        )
    )

    rate_rows = fetch_usd_krw_exchange_rates(
        build_kis_client(),
        start_date=date(2026, 1, 7),
        end_date=date(2026, 1, 9),
    )

    assert [row["rate_date"] for row in rate_rows] == [date(2026, 1, 9)]


@respx.mock
def test_non_zero_rt_cd_raises_error_with_msg1() -> None:
    respx.get(EXCHANGE_RATE_DAILY_CHART_URL).mock(
        return_value=httpx.Response(
            200,
            json={"rt_cd": "1", "msg_cd": "EGW00201", "msg1": "조회할 자료가 없습니다."},
        )
    )

    with pytest.raises(KisQuotationError) as error_info:
        fetch_usd_krw_exchange_rates(
            build_kis_client(),
            start_date=date(2026, 1, 7),
            end_date=date(2026, 1, 9),
        )

    assert "조회할 자료가 없습니다." in str(error_info.value)


@respx.mock
def test_long_range_splits_into_multiple_windows() -> None:
    quotation_route = respx.get(EXCHANGE_RATE_DAILY_CHART_URL).mock(
        return_value=build_success_response([build_output2_row("20260109")])
    )

    fetch_usd_krw_exchange_rates(
        build_kis_client(),
        start_date=date(2026, 1, 1),
        end_date=date(2026, 9, 7),
    )

    assert quotation_route.call_count == 3


@respx.mock
def test_sleep_function_is_invoked_for_rate_limit_spacing() -> None:
    respx.get(EXCHANGE_RATE_DAILY_CHART_URL).mock(
        return_value=build_success_response([build_output2_row("20260109")])
    )
    recorded_wait_seconds: list[float] = []

    fetch_usd_krw_exchange_rates(
        build_kis_client(sleep_function=recorded_wait_seconds.append),
        start_date=date(2026, 1, 8),
        end_date=date(2026, 1, 10),
    )

    assert recorded_wait_seconds == [INTER_REQUEST_WAIT_SECONDS]
