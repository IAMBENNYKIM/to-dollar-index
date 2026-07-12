from __future__ import annotations

import json
import time
from typing import Callable

import httpx

from collector.config import CollectorConfig

DEFAULT_HTTP_TIMEOUT_SECONDS = 30.0

# KIS 시세 API는 초당 유량 제한이 있어, 연속 호출 사이에 이만큼 대기한다.
INTER_REQUEST_WAIT_SECONDS = 0.5


class KisQuotationError(RuntimeError):
    """KIS 시세 조회 호출이 실패했을 때 발생한다."""


class KisClient:
    """KIS 시세 조회 API 공통 GET 호출기.

    인증 헤더 구성, 호출 간 대기, rt_cd 검사를 담당한다.
    http_client와 sleep_function은 테스트 주입을 위해 생성자로 받는다.
    """

    def __init__(
        self,
        config: CollectorConfig,
        access_token: str,
        http_client: httpx.Client | None = None,
        sleep_function: Callable[[float], None] = time.sleep,
    ) -> None:
        self._config = config
        self._access_token = access_token
        self._http_client = http_client
        self._sleep_function = sleep_function

    def request_quotation(
        self, path: str, tr_id: str, query_parameters: dict
    ) -> dict:
        """KIS 시세 API를 GET 호출하고 성공 응답 본문(dict)을 반환한다.

        HTTP 오류 또는 응답 rt_cd != "0"이면 KisQuotationError를 raise 한다.
        호출 전 유량 제한 여유를 위해 0.5초 대기한다.
        """
        self._sleep_function(INTER_REQUEST_WAIT_SECONDS)

        request_url = f"{self._config.kis_base_url}{path}"
        request_headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self._access_token}",
            "appkey": self._config.kis_app_key,
            "appsecret": self._config.kis_app_secret,
            "tr_id": tr_id,
            "custtype": "P",
        }

        if self._http_client is None:
            with httpx.Client(
                timeout=DEFAULT_HTTP_TIMEOUT_SECONDS
            ) as owned_http_client:
                response = self._send_request(
                    owned_http_client, request_url, request_headers, query_parameters
                )
        else:
            response = self._send_request(
                self._http_client, request_url, request_headers, query_parameters
            )

        return self._parse_response(response, path, tr_id)

    @staticmethod
    def _send_request(
        http_client: httpx.Client,
        request_url: str,
        request_headers: dict,
        query_parameters: dict,
    ) -> httpx.Response:
        try:
            return http_client.get(
                request_url, headers=request_headers, params=query_parameters
            )
        except httpx.HTTPError as network_error:
            raise KisQuotationError(
                f"KIS 시세 조회 요청 중 네트워크 오류: {network_error}"
            ) from network_error

    @staticmethod
    def _parse_response(response: httpx.Response, path: str, tr_id: str) -> dict:
        if response.status_code != httpx.codes.OK:
            raise KisQuotationError(
                f"KIS 시세 조회 응답 오류(tr_id={tr_id}, path={path}): "
                f"HTTP {response.status_code}, 본문: {response.text}"
            )

        try:
            response_body = response.json()
        except json.JSONDecodeError as parse_error:
            raise KisQuotationError(
                f"KIS 시세 조회 응답 JSON 파싱 실패(tr_id={tr_id}): {parse_error}"
            ) from parse_error

        if not isinstance(response_body, dict):
            raise KisQuotationError(
                f"KIS 시세 조회 응답 형식이 올바르지 않습니다(tr_id={tr_id}): "
                f"{response_body!r}"
            )

        return_code = response_body.get("rt_cd")
        if return_code != "0":
            message = response_body.get("msg1", "")
            message_code = response_body.get("msg_cd", "")
            raise KisQuotationError(
                f"KIS 시세 조회 실패(tr_id={tr_id}): rt_cd={return_code!r}, "
                f"msg_cd={message_code!r}, msg1={message!r}"
            )

        return response_body
