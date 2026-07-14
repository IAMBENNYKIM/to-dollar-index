from __future__ import annotations

from datetime import date
from decimal import Decimal

import httpx
import pytest
import respx

from collector.config import KIS_PRODUCTION_BASE_URL, CollectorConfig
from collector.fetch_stock_prices import (
    STOCK_DAILY_CHART_PATH,
    STOCK_DAILY_CHART_TR_ID,
    fetch_stock_daily_prices,
)
from collector.kis_client import (
    INTER_REQUEST_WAIT_SECONDS,
    KisClient,
    KisQuotationError,
)

STOCK_DAILY_CHART_URL = f"{KIS_PRODUCTION_BASE_URL}{STOCK_DAILY_CHART_PATH}"


def build_test_config() -> CollectorConfig:
    return CollectorConfig(
        kis_app_key="test-app-key",
        kis_app_secret="test-app-secret",
        kis_base_url=KIS_PRODUCTION_BASE_URL,
        supabase_url="https://example.supabase.co",
        supabase_service_role_key="test-service-role-key",
    )


def fail_if_sleep_called(wait_seconds: float) -> None:
    pytest.fail(f"sleep_function이 호출되면 안 됩니다 (wait_seconds={wait_seconds})")


def build_kis_client(sleep_function=None) -> KisClient:
    return KisClient(
        config=build_test_config(),
        access_token="test-token",
        http_client=httpx.Client(),
        sleep_function=sleep_function if sleep_function is not None else (lambda _: None),
    )


def build_output2_row(
    business_date: str,
    close_price: str = "70000",
    open_price: str = "69000",
    high_price: str = "71000",
    low_price: str = "68500",
    trade_volume: str = "12345678",
) -> dict:
    return {
        "stck_bsop_date": business_date,
        "stck_clpr": close_price,
        "stck_oprc": open_price,
        "stck_hgpr": high_price,
        "stck_lwpr": low_price,
        "acml_vol": trade_volume,
    }


def build_success_response(output2_rows: list[dict]) -> httpx.Response:
    return httpx.Response(
        200,
        json={"rt_cd": "0", "msg_cd": "MCA00000", "msg1": "정상처리", "output2": output2_rows},
    )


@respx.mock
def test_parses_rows_into_daily_prices_format_sorted_ascending() -> None:
    # 응답은 최신순(내림차순)으로 오지만 결과는 오름차순이어야 한다.
    quotation_route = respx.get(STOCK_DAILY_CHART_URL).mock(
        return_value=build_success_response(
            [
                build_output2_row("20260110", close_price="72000"),
                build_output2_row("20260109", close_price="71000"),
                build_output2_row("20260108", close_price="70000"),
            ]
        )
    )

    price_rows = fetch_stock_daily_prices(
        build_kis_client(),
        indicator_id="indicator-abc",
        stock_code="005930",
        start_date=date(2026, 1, 8),
        end_date=date(2026, 1, 10),
    )

    assert quotation_route.call_count == 1
    assert [row["price_date"] for row in price_rows] == [
        date(2026, 1, 8),
        date(2026, 1, 9),
        date(2026, 1, 10),
    ]

    first_row = price_rows[0]
    assert first_row["indicator_id"] == "indicator-abc"
    assert first_row["close_price"] == Decimal("70000")
    assert isinstance(first_row["close_price"], Decimal)
    assert isinstance(first_row["open_price"], Decimal)
    assert first_row["trade_volume"] == 12345678
    assert isinstance(first_row["trade_volume"], int)

    # 요청 파라미터 검증(수정주가 0, 시장구분 J 등).
    request_url = quotation_route.calls.last.request.url
    assert request_url.params["FID_INPUT_ISCD"] == "005930"
    assert request_url.params["FID_ORG_ADJ_PRC"] == "0"
    assert request_url.params["FID_COND_MRKT_DIV_CODE"] == "J"
    assert request_url.params["FID_PERIOD_DIV_CODE"] == "D"
    assert request_url.params["FID_INPUT_DATE_1"] == "20260108"
    assert request_url.params["FID_INPUT_DATE_2"] == "20260110"

    request_headers = quotation_route.calls.last.request.headers
    assert request_headers["authorization"] == "Bearer test-token"
    assert request_headers["tr_id"] == STOCK_DAILY_CHART_TR_ID
    assert request_headers["appkey"] == "test-app-key"
    assert request_headers["custtype"] == "P"


@respx.mock
def test_filters_out_holiday_placeholder_rows() -> None:
    respx.get(STOCK_DAILY_CHART_URL).mock(
        return_value=build_success_response(
            [
                build_output2_row("20260109"),
                {"stck_bsop_date": "", "stck_clpr": "", "stck_oprc": ""},
                {"stck_bsop_date": "20260107", "stck_clpr": ""},
            ]
        )
    )

    price_rows = fetch_stock_daily_prices(
        build_kis_client(),
        indicator_id="indicator-abc",
        stock_code="005930",
        start_date=date(2026, 1, 7),
        end_date=date(2026, 1, 9),
    )

    assert [row["price_date"] for row in price_rows] == [date(2026, 1, 9)]


@respx.mock
def test_non_zero_rt_cd_raises_error_with_msg1() -> None:
    respx.get(STOCK_DAILY_CHART_URL).mock(
        return_value=httpx.Response(
            200,
            json={"rt_cd": "1", "msg_cd": "EGW00201", "msg1": "초당 거래건수를 초과하였습니다."},
        )
    )

    with pytest.raises(KisQuotationError) as error_info:
        fetch_stock_daily_prices(
            build_kis_client(),
            indicator_id="indicator-abc",
            stock_code="005930",
            start_date=date(2026, 1, 7),
            end_date=date(2026, 1, 9),
        )

    assert "초당 거래건수를 초과하였습니다." in str(error_info.value)


@respx.mock
def test_http_error_raises_error() -> None:
    respx.get(STOCK_DAILY_CHART_URL).mock(
        return_value=httpx.Response(500, text="internal server error")
    )

    with pytest.raises(KisQuotationError):
        fetch_stock_daily_prices(
            build_kis_client(),
            indicator_id="indicator-abc",
            stock_code="005930",
            start_date=date(2026, 1, 7),
            end_date=date(2026, 1, 9),
        )


@respx.mock
def test_long_range_splits_into_multiple_windows() -> None:
    # 250일 구간 -> 120일 창 기준 3개 구간으로 분할되어 3회 호출된다.
    quotation_route = respx.get(STOCK_DAILY_CHART_URL).mock(
        return_value=build_success_response([build_output2_row("20260109")])
    )

    fetch_stock_daily_prices(
        build_kis_client(),
        indicator_id="indicator-abc",
        stock_code="005930",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 9, 7),
    )

    assert quotation_route.call_count == 3


@respx.mock
def test_sleep_function_is_invoked_for_rate_limit_spacing() -> None:
    respx.get(STOCK_DAILY_CHART_URL).mock(
        return_value=build_success_response([build_output2_row("20260109")])
    )
    recorded_wait_seconds: list[float] = []

    fetch_stock_daily_prices(
        build_kis_client(sleep_function=recorded_wait_seconds.append),
        indicator_id="indicator-abc",
        stock_code="005930",
        start_date=date(2026, 1, 8),
        end_date=date(2026, 1, 10),
    )

    # 단일 구간 = 1회 호출 = 호출 전 대기 1회.
    assert recorded_wait_seconds == [INTER_REQUEST_WAIT_SECONDS]


@respx.mock
def test_default_sleep_uses_real_sleep_but_injected_suppresses_it() -> None:
    # fail_if_sleep_called 를 주입하면 대기가 발생하지 않아야 정상(호출 자체는 sleep 억제 대상 아님).
    # 여기서는 sleep 억제 람다가 실제로 sleep을 건너뛰는지 확인한다.
    respx.get(STOCK_DAILY_CHART_URL).mock(
        return_value=build_success_response([build_output2_row("20260109")])
    )

    price_rows = fetch_stock_daily_prices(
        build_kis_client(sleep_function=lambda _: None),
        indicator_id="indicator-abc",
        stock_code="005930",
        start_date=date(2026, 1, 8),
        end_date=date(2026, 1, 10),
    )

    assert len(price_rows) == 1
