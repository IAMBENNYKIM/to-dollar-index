from __future__ import annotations

import httpx
import pytest
import respx

from collector.config import KIS_PRODUCTION_BASE_URL, CollectorConfig
from collector.kis_client import (
    KisClient,
    KisQuotationError,
    KisRateLimitError,
)

TEST_PATH = "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
TEST_TR_ID = "FHKST03010100"
TEST_URL = f"{KIS_PRODUCTION_BASE_URL}{TEST_PATH}"


def build_config() -> CollectorConfig:
    return CollectorConfig(
        kis_app_key="test-key",
        kis_app_secret="test-secret",
        kis_base_url=KIS_PRODUCTION_BASE_URL,
        supabase_url="",
        supabase_service_role_key="",
    )


def build_client(sleep_calls: list[float]) -> KisClient:
    return KisClient(
        build_config(),
        access_token="test-token",
        http_client=httpx.Client(),
        sleep_function=sleep_calls.append,
    )


RATE_LIMIT_BODY = {
    "rt_cd": "1",
    "msg_cd": "EGW00201",
    "msg1": "초당 거래건수를 초과하였습니다.",
}
SUCCESS_BODY = {"rt_cd": "0", "msg_cd": "MCA00000", "output2": [{"a": 1}]}


@respx.mock
def test_success_returns_body() -> None:
    respx.get(TEST_URL).mock(return_value=httpx.Response(200, json=SUCCESS_BODY))
    sleep_calls: list[float] = []

    result = build_client(sleep_calls).request_quotation(TEST_PATH, TEST_TR_ID, {})

    assert result["output2"] == [{"a": 1}]


@respx.mock
def test_rate_limit_500_is_retried_then_succeeds() -> None:
    # 유량 초과는 HTTP 500 + rt_cd=1로 온다. 재시도 후 성공해야 한다.
    route = respx.get(TEST_URL).mock(
        side_effect=[
            httpx.Response(500, json=RATE_LIMIT_BODY),
            httpx.Response(500, json=RATE_LIMIT_BODY),
            httpx.Response(200, json=SUCCESS_BODY),
        ]
    )
    sleep_calls: list[float] = []

    result = build_client(sleep_calls).request_quotation(TEST_PATH, TEST_TR_ID, {})

    assert result["output2"] == [{"a": 1}]
    assert route.call_count == 3
    # 호출 간 대기(3회) + 유량 초과 백오프(2회) = 5회 sleep.
    assert len(sleep_calls) == 5


@respx.mock
def test_rate_limit_exhausts_retries_raises() -> None:
    respx.get(TEST_URL).mock(return_value=httpx.Response(500, json=RATE_LIMIT_BODY))
    sleep_calls: list[float] = []

    with pytest.raises(KisRateLimitError):
        build_client(sleep_calls).request_quotation(TEST_PATH, TEST_TR_ID, {})


@respx.mock
def test_non_rate_limit_error_is_not_retried() -> None:
    error_body = {"rt_cd": "1", "msg_cd": "EGW00123", "msg1": "잘못된 요청"}
    route = respx.get(TEST_URL).mock(return_value=httpx.Response(200, json=error_body))
    sleep_calls: list[float] = []

    with pytest.raises(KisQuotationError) as error_info:
        build_client(sleep_calls).request_quotation(TEST_PATH, TEST_TR_ID, {})

    assert not isinstance(error_info.value, KisRateLimitError)
    assert route.call_count == 1


@respx.mock
def test_http_500_without_json_raises_quotation_error() -> None:
    respx.get(TEST_URL).mock(return_value=httpx.Response(500, text="gateway error"))
    sleep_calls: list[float] = []

    with pytest.raises(KisQuotationError) as error_info:
        build_client(sleep_calls).request_quotation(TEST_PATH, TEST_TR_ID, {})

    assert not isinstance(error_info.value, KisRateLimitError)
