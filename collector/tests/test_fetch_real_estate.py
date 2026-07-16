from __future__ import annotations

from datetime import date
from decimal import Decimal

import httpx
import pytest
import respx

from collector.fetch_real_estate import (
    KOSIS_PARAM_URL,
    RealEstateFetchError,
    fetch_real_estate_prices,
)


def build_source_row(
    period: str,
    data_value: str,
    region_code: str = "010",
    size_code: str = "s6",
    item_id: str = "T001",
) -> dict:
    return {
        "C1": region_code,
        "C1_NM": "서울",
        "C2": size_code,
        "C2_NM": "소형(40㎡초과 60㎡이하)",
        "ITM_ID": item_id,
        "UNIT_NM": "만원/㎡",
        "PRD_DE": period,
        "DT": data_value,
    }


@respx.mock
def test_parses_rows_sorted_ascending_with_exact_decimal() -> None:
    route = respx.get(KOSIS_PARAM_URL).mock(
        return_value=httpx.Response(
            200,
            json=[
                build_source_row("200603", "470.0"),
                build_source_row("200601", "463.8095317"),
                build_source_row("200602", "465.5"),
            ],
        )
    )

    price_rows = fetch_real_estate_prices(
        kosis_api_key="test-kosis-key",
        indicator_id="re-1",
        periods_count=400,
        http_client=httpx.Client(),
    )

    assert route.call_count == 1
    assert [row["price_date"] for row in price_rows] == [
        date(2006, 1, 1),
        date(2006, 2, 1),
        date(2006, 3, 1),
    ]

    first_row = price_rows[0]
    assert first_row["indicator_id"] == "re-1"
    # 만원/㎡ → 59㎡ 기준 원. float 경유 없이 Decimal 정확 계산.
    assert first_row["close_price"] == Decimal("463.8095317") * Decimal("59") * Decimal("10000")
    assert isinstance(first_row["close_price"], Decimal)
    assert set(first_row.keys()) == {"indicator_id", "price_date", "close_price"}

    # 서버사이드 필터 파라미터가 정확히 실려야 한다.
    request_params = route.calls.last.request.url.params
    assert request_params["objL1"] == "010"
    assert request_params["objL2"] == "s6"
    assert request_params["newEstPrdCnt"] == "400"
    assert request_params["orgId"] == "408"
    assert request_params["tblId"] == "DT_KAB_11672_S19"


@respx.mock
def test_skips_mismatched_codes_and_empty_values() -> None:
    respx.get(KOSIS_PARAM_URL).mock(
        return_value=httpx.Response(
            200,
            json=[
                build_source_row("200601", "463.8095317"),
                build_source_row("200602", "999.0", region_code="020"),  # 다른 지역
                build_source_row("200603", "999.0", size_code="s5"),  # 다른 규모
                build_source_row("200604", "999.0", item_id="T002"),  # 다른 항목
                build_source_row("200605", "-"),  # 결측
                build_source_row("200606", ""),  # 빈값
            ],
        )
    )

    price_rows = fetch_real_estate_prices(
        kosis_api_key="test-kosis-key",
        indicator_id="re-1",
        periods_count=400,
        http_client=httpx.Client(),
    )

    assert [row["price_date"] for row in price_rows] == [date(2006, 1, 1)]


@respx.mock
def test_error_object_response_raises() -> None:
    respx.get(KOSIS_PARAM_URL).mock(
        return_value=httpx.Response(
            200,
            json={"err": "20", "errMsg": "인증키가 유효하지 않습니다."},
        )
    )

    with pytest.raises(RealEstateFetchError) as error_info:
        fetch_real_estate_prices(
            kosis_api_key="bad-key",
            indicator_id="re-1",
            periods_count=400,
            http_client=httpx.Client(),
        )

    assert "인증키가 유효하지 않습니다." in str(error_info.value)


@respx.mock
def test_http_error_does_not_leak_api_key() -> None:
    # 500 응답 시 도메인 에러로 변환되고, 쿼리스트링(apiKey)의 키가 예외 메시지에 남지 않아야 한다.
    respx.get(KOSIS_PARAM_URL).mock(
        return_value=httpx.Response(500, text="Internal Server Error")
    )

    with pytest.raises(RealEstateFetchError) as error_info:
        fetch_real_estate_prices(
            kosis_api_key="test-secret-key",
            indicator_id="re-1",
            periods_count=400,
            http_client=httpx.Client(),
        )

    assert "500" in str(error_info.value)
    assert "test-secret-key" not in str(error_info.value)


@respx.mock
def test_timeout_does_not_leak_api_key() -> None:
    # 타임아웃 등 전송 계층 오류도 도메인 에러로 변환되고 API 키가 노출되지 않아야 한다.
    respx.get(KOSIS_PARAM_URL).mock(side_effect=httpx.TimeoutException("timed out"))

    with pytest.raises(RealEstateFetchError) as error_info:
        fetch_real_estate_prices(
            kosis_api_key="test-secret-key",
            indicator_id="re-1",
            periods_count=400,
            http_client=httpx.Client(),
        )

    assert "요청 실패" in str(error_info.value)
    assert "test-secret-key" not in str(error_info.value)
