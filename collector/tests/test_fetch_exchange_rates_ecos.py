from __future__ import annotations

from datetime import date
from decimal import Decimal

import httpx
import pytest
import respx

from collector.fetch_exchange_rates_ecos import (
    ECOS_API_BASE_URL,
    EcosFetchError,
    fetch_usd_krw_exchange_rates_ecos,
)


def build_success_payload(rows: list[dict]) -> dict:
    return {"StatisticSearch": {"list_total_count": len(rows), "row": rows}}


def build_source_row(time_text: str, data_value: str) -> dict:
    return {
        "STAT_CODE": "731Y001",
        "STAT_NAME": "3.1.1.1. 주요국 통화의 대원화환율",
        "ITEM_CODE1": "0000001",
        "TIME": time_text,
        "DATA_VALUE": data_value,
    }


@respx.mock
def test_parses_rows_sorted_ascending_with_exact_decimal() -> None:
    route = respx.get(url__startswith=ECOS_API_BASE_URL).mock(
        return_value=httpx.Response(
            200,
            json=build_success_payload(
                [
                    build_source_row("20240104", "1330.7"),
                    build_source_row("20240102", "1289.4"),
                    build_source_row("20240103", "1310.0"),
                ]
            ),
        )
    )

    rate_rows = fetch_usd_krw_exchange_rates_ecos(
        ecos_api_key="test-ecos-key",
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 4),
        http_client=httpx.Client(),
    )

    assert route.call_count == 1
    assert [row["rate_date"] for row in rate_rows] == [
        date(2024, 1, 2),
        date(2024, 1, 3),
        date(2024, 1, 4),
    ]

    first_row = rate_rows[0]
    assert set(first_row.keys()) == {"currency_pair", "rate_date", "close_rate"}
    assert first_row["currency_pair"] == "USD_KRW"
    assert first_row["close_rate"] == Decimal("1289.4")
    assert isinstance(first_row["close_rate"], Decimal)


@respx.mock
def test_request_url_assembly() -> None:
    route = respx.get(url__startswith=ECOS_API_BASE_URL).mock(
        return_value=httpx.Response(200, json=build_success_payload([]))
    )

    fetch_usd_krw_exchange_rates_ecos(
        ecos_api_key="my-key",
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 4),
        http_client=httpx.Client(),
    )

    request_path = route.calls.last.request.url.path
    # 인증키/주기/통계표/항목코드/날짜가 경로에 정확히 실려야 한다.
    # 시작건수 1, 종료건수 = (end - start).days + 1 = 3.
    assert request_path == (
        "/api/StatisticSearch/my-key/json/kr/1/3/731Y001/D/20240102/20240104/0000001"
    )


@respx.mock
def test_no_data_result_returns_empty_list() -> None:
    respx.get(url__startswith=ECOS_API_BASE_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "RESULT": {
                    "CODE": "INFO-200",
                    "MESSAGE": "해당하는 데이터가 없습니다.",
                }
            },
        )
    )

    rate_rows = fetch_usd_krw_exchange_rates_ecos(
        ecos_api_key="test-ecos-key",
        start_date=date(2024, 1, 6),
        end_date=date(2024, 1, 7),
        http_client=httpx.Client(),
    )

    assert rate_rows == []


@respx.mock
def test_other_result_code_raises() -> None:
    respx.get(url__startswith=ECOS_API_BASE_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "RESULT": {
                    "CODE": "INFO-100",
                    "MESSAGE": "인증키가 유효하지 않습니다.",
                }
            },
        )
    )

    with pytest.raises(EcosFetchError) as error_info:
        fetch_usd_krw_exchange_rates_ecos(
            ecos_api_key="bad-key",
            start_date=date(2024, 1, 2),
            end_date=date(2024, 1, 4),
            http_client=httpx.Client(),
        )

    assert "INFO-100" in str(error_info.value)
    assert "인증키가 유효하지 않습니다." in str(error_info.value)


@respx.mock
def test_http_error_does_not_leak_api_key() -> None:
    # 500 응답 시 도메인 에러로 변환되고, URL 경로의 API 키가 예외 메시지에 남지 않아야 한다.
    respx.get(url__startswith=ECOS_API_BASE_URL).mock(
        return_value=httpx.Response(500, text="Internal Server Error")
    )

    with pytest.raises(EcosFetchError) as error_info:
        fetch_usd_krw_exchange_rates_ecos(
            ecos_api_key="test-secret-key",
            start_date=date(2024, 1, 2),
            end_date=date(2024, 1, 4),
            http_client=httpx.Client(),
        )

    assert "500" in str(error_info.value)
    assert "test-secret-key" not in str(error_info.value)


@respx.mock
def test_timeout_does_not_leak_api_key() -> None:
    # 타임아웃 등 전송 계층 오류도 도메인 에러로 변환되고 API 키가 노출되지 않아야 한다.
    respx.get(url__startswith=ECOS_API_BASE_URL).mock(
        side_effect=httpx.TimeoutException("timed out")
    )

    with pytest.raises(EcosFetchError) as error_info:
        fetch_usd_krw_exchange_rates_ecos(
            ecos_api_key="test-secret-key",
            start_date=date(2024, 1, 2),
            end_date=date(2024, 1, 4),
            http_client=httpx.Client(),
        )

    assert "요청 실패" in str(error_info.value)
    assert "test-secret-key" not in str(error_info.value)


@respx.mock
def test_skips_rows_with_empty_data_value() -> None:
    respx.get(url__startswith=ECOS_API_BASE_URL).mock(
        return_value=httpx.Response(
            200,
            json=build_success_payload(
                [
                    build_source_row("20240102", "1289.4"),
                    build_source_row("20240103", ""),  # 빈 값 행은 스킵
                    build_source_row("20240104", "1330.7"),
                ]
            ),
        )
    )

    rate_rows = fetch_usd_krw_exchange_rates_ecos(
        ecos_api_key="test-ecos-key",
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 4),
        http_client=httpx.Client(),
    )

    assert [row["rate_date"] for row in rate_rows] == [
        date(2024, 1, 2),
        date(2024, 1, 4),
    ]
