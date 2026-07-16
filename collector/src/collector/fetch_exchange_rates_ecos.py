from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import httpx

# 한국은행 ECOS 통계검색 오픈API. 환율 폴백 전용.
# ECOS는 매매기준율이라 KIS 종가와 미세하게 다르지만 비상 폴백 용도로 수용한다.
ECOS_API_BASE_URL = "https://ecos.bok.or.kr/api/StatisticSearch"

# 통계표/주기/항목 식별자(샘플 키 실호출로 검증된 값).
ECOS_STAT_CODE_EXCHANGE_RATE = "731Y001"  # 3.1.1.1. 주요국 통화의 대원화환율
ECOS_ITEM_CODE_USD_KRW = "0000001"  # 원/미국달러(매매기준율)
ECOS_CYCLE_DAILY = "D"  # 조회 주기: 일별

# 무데이터(주말·공휴일 등) 응답의 RESULT 코드. 이 경우 빈 리스트로 처리한다.
ECOS_NO_DATA_RESULT_CODE = "INFO-200"

CURRENCY_PAIR_USD_KRW = "USD_KRW"

DEFAULT_HTTP_TIMEOUT_SECONDS = 30.0


class EcosFetchError(RuntimeError):
    """ECOS 응답이 에러(RESULT 객체)이거나 예상 스키마가 아닐 때 발생한다."""


def fetch_usd_krw_exchange_rates_ecos(
    ecos_api_key: str,
    start_date: date,
    end_date: date,
    http_client: httpx.Client | None = None,
) -> list[dict]:
    """ECOS에서 원/달러 환율(매매기준율) 일별 시계열을 조회해 exchange_rates 행으로 반환한다.

    KIS 환율 조회가 실패했을 때의 비상 폴백이다. ECOS는 매매기준율이라 KIS 종가와
    미세하게 다르지만 폴백 용도로 수용한다.

    시작건수 1, 종료건수는 구간 일수(end_date - start_date + 1)로 한 번에 받아오므로
    분할 호출이 필요 없다. 무데이터(INFO-200)면 빈 리스트를, 그 외 RESULT 에러면
    EcosFetchError를 발생시킨다. 반환 행은 rate_date 오름차순으로 정렬한다.

    http_client 미지정 시 내부에서 생성/종료한다(테스트에서는 주입해 네트워크를 대체).
    """
    start_record = 1
    end_record = (end_date - start_date).days + 1
    request_url = (
        f"{ECOS_API_BASE_URL}/{ecos_api_key}/json/kr/{start_record}/{end_record}/"
        f"{ECOS_STAT_CODE_EXCHANGE_RATE}/{ECOS_CYCLE_DAILY}/"
        f"{start_date.strftime('%Y%m%d')}/{end_date.strftime('%Y%m%d')}/"
        f"{ECOS_ITEM_CODE_USD_KRW}"
    )

    if http_client is not None:
        response_payload = _request_ecos(http_client, request_url)
    else:
        with httpx.Client(timeout=DEFAULT_HTTP_TIMEOUT_SECONDS) as owned_http_client:
            response_payload = _request_ecos(owned_http_client, request_url)

    return _parse_ecos_payload(response_payload)


def _request_ecos(http_client: httpx.Client, request_url: str) -> object:
    try:
        response = http_client.get(request_url)
        response.raise_for_status()
    except httpx.HTTPStatusError as http_error:
        # 요청 URL에 API 키가 포함되므로 httpx 예외 메시지를 그대로 전파하지 않는다.
        raise EcosFetchError(f"ECOS HTTP {http_error.response.status_code} 오류") from None
    except httpx.HTTPError as http_error:
        raise EcosFetchError(f"ECOS 요청 실패: {type(http_error).__name__}") from None
    return response.json()


def _parse_ecos_payload(response_payload: object) -> list[dict]:
    # 정상 응답은 {"StatisticSearch": {"row": [...]}}. 무데이터·에러는 {"RESULT": {...}}로 온다.
    if not isinstance(response_payload, dict):
        raise EcosFetchError(
            f"ECOS 응답 형식이 올바르지 않습니다: {type(response_payload).__name__}"
        )

    if "RESULT" in response_payload:
        result_object = response_payload["RESULT"]
        result_code = ""
        result_message = ""
        if isinstance(result_object, dict):
            result_code = str(result_object.get("CODE") or "")
            result_message = str(result_object.get("MESSAGE") or "")
        if result_code == ECOS_NO_DATA_RESULT_CODE:
            # 주말·공휴일 등 해당 구간 데이터 없음 — 폴백에서는 빈 결과로 취급한다.
            return []
        raise EcosFetchError(
            f"ECOS 조회에 실패했습니다: {result_code} {result_message}"
        )

    statistic_search = response_payload.get("StatisticSearch")
    if not isinstance(statistic_search, dict):
        raise EcosFetchError(
            "ECOS 응답에 StatisticSearch 객체가 없습니다: "
            f"{response_payload!r}"
        )

    source_rows = statistic_search.get("row") or []
    collected_rows: list[dict] = []
    for source_row in source_rows:
        parsed_row = _parse_ecos_row(source_row)
        if parsed_row is not None:
            collected_rows.append(parsed_row)

    collected_rows.sort(key=lambda row: row["rate_date"])
    return collected_rows


def _parse_ecos_row(source_row: object) -> dict | None:
    # TIME은 YYYYMMDD 문자열, DATA_VALUE는 숫자 문자열. 빈 값 행은 건너뛴다.
    if not isinstance(source_row, dict):
        return None

    time_text = (source_row.get("TIME") or "").strip()
    data_value_text = (source_row.get("DATA_VALUE") or "").strip()
    if not time_text or not data_value_text:
        return None

    return {
        "currency_pair": CURRENCY_PAIR_USD_KRW,
        "rate_date": datetime.strptime(time_text, "%Y%m%d").date(),
        "close_rate": Decimal(data_value_text),
    }
