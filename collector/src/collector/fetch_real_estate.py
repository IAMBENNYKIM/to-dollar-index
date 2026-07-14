from __future__ import annotations

from datetime import date
from decimal import Decimal

import httpx

# KOSIS(한국부동산원) 통계 파라미터 조회 오픈API.
KOSIS_PARAM_URL = "https://kosis.kr/openapi/Param/statisticsParameterData.do"

# 통계표 식별자와 서버사이드 필터 코드. 이름이 아니라 코드로 필터한다(실호출로 검증된 값).
ORG_ID = "408"
TBL_ID = "DT_KAB_11672_S19"
ITM_ID = "T001"  # 항목: ㎡당 평균 매매가격
REGION_CODE = "010"  # 지역(C1): 서울
SIZE_CODE = "s6"  # 규모(C2): 소형(40㎡초과 60㎡이하)

# 표시 기준 면적과 단위 환산. DT는 '만원/㎡' 단위이므로 59㎡ 기준 원(KRW)으로 환산해 저장한다.
FLOOR_AREA_SQM = Decimal("59")
MANWON_TO_KRW = Decimal("10000")

DEFAULT_HTTP_TIMEOUT_SECONDS = 30.0


class RealEstateFetchError(RuntimeError):
    """KOSIS 응답이 에러(객체 형태)이거나 예상 스키마가 아닐 때 발생한다."""


def fetch_real_estate_prices(
    kosis_api_key: str,
    indicator_id: str,
    periods_count: int,
    http_client: httpx.Client | None = None,
) -> list[dict]:
    """KOSIS에서 서울 소형 아파트 ㎡당 매매가격을 조회해 daily_prices 행 리스트로 반환한다.

    최근 periods_count개월(newEstPrdCnt) 분량을 서버사이드 필터(objL 코드)로 받아온다.
    응답의 각 행 중 서울(C1=010)·소형(C2=s6)·항목(ITM_ID=T001)만 채택하고,
    DT(만원/㎡)를 59㎡ 기준 원 단위로 환산해 저장값을 만든다. 월 데이터이므로
    price_date는 해당 월 1일로 둔다. 날짜 오름차순 정렬.

    http_client 미지정 시 내부에서 생성/종료한다(테스트에서는 주입해 네트워크를 대체).
    """
    request_parameters = {
        "method": "getList",
        "apiKey": kosis_api_key,
        "itmId": f"{ITM_ID}+",
        "objL1": REGION_CODE,
        "objL2": SIZE_CODE,
        "objL3": "",
        "objL4": "",
        "objL5": "",
        "objL6": "",
        "objL7": "",
        "objL8": "",
        "format": "json",
        "jsonVD": "Y",
        "prdSe": "M",
        "newEstPrdCnt": str(periods_count),
        "orgId": ORG_ID,
        "tblId": TBL_ID,
    }

    if http_client is not None:
        response_payload = _request_kosis(http_client, request_parameters)
    else:
        with httpx.Client(timeout=DEFAULT_HTTP_TIMEOUT_SECONDS) as owned_http_client:
            response_payload = _request_kosis(owned_http_client, request_parameters)

    return _parse_real_estate_payload(response_payload, indicator_id)


def _request_kosis(http_client: httpx.Client, request_parameters: dict) -> object:
    response = http_client.get(KOSIS_PARAM_URL, params=request_parameters)
    response.raise_for_status()
    return response.json()


def _parse_real_estate_payload(response_payload: object, indicator_id: str) -> list[dict]:
    # 정상 응답은 JSON 배열이다. 키 오류·자료 없음 등 에러는 dict(err/errMsg 포함)로 온다.
    if not isinstance(response_payload, list):
        error_message = _extract_kosis_error_message(response_payload)
        raise RealEstateFetchError(f"KOSIS 조회에 실패했습니다: {error_message}")

    collected_rows: list[dict] = []
    for source_row in response_payload:
        parsed_row = _parse_real_estate_row(source_row, indicator_id)
        if parsed_row is not None:
            collected_rows.append(parsed_row)

    collected_rows.sort(key=lambda row: row["price_date"])
    return collected_rows


def _extract_kosis_error_message(response_payload: object) -> str:
    if isinstance(response_payload, dict):
        error_text = response_payload.get("errMsg") or response_payload.get("err")
        if error_text:
            return str(error_text)
        return str(response_payload)
    return f"예상하지 못한 응답 형식입니다: {type(response_payload).__name__}"


def _parse_real_estate_row(source_row: object, indicator_id: str) -> dict | None:
    # 방어적으로 코드가 정확히 일치하는 행만 채택한다.
    if not isinstance(source_row, dict):
        return None
    if source_row.get("C1") != REGION_CODE:
        return None
    if source_row.get("C2") != SIZE_CODE:
        return None
    if source_row.get("ITM_ID") != ITM_ID:
        return None

    data_value_text = (source_row.get("DT") or "").strip()
    if not data_value_text or data_value_text == "-":
        return None

    period_text = (source_row.get("PRD_DE") or "").strip()
    if len(period_text) != 6:
        return None
    price_date = date(int(period_text[:4]), int(period_text[4:6]), 1)

    close_price = Decimal(data_value_text) * FLOOR_AREA_SQM * MANWON_TO_KRW
    return {
        "indicator_id": indicator_id,
        "price_date": price_date,
        "close_price": close_price,
    }
