from __future__ import annotations

import json
import time
from typing import Callable

import httpx

from collector.config import CollectorConfig

DEFAULT_HTTP_TIMEOUT_SECONDS = 30.0

# KIS 시세 API는 초당 유량 제한이 있어, 연속 호출 사이에 이만큼 대기한다.
# 모의투자 계정은 제한이 더 낮으므로 실전보다 넉넉히 둔다.
INTER_REQUEST_WAIT_SECONDS = 1.0

# 유량 초과(EGW00201) 응답 시 백오프 재시도 설정.
RATE_LIMIT_MSG_CODE = "EGW00201"
MAX_RATE_LIMIT_RETRIES = 5
RATE_LIMIT_INITIAL_BACKOFF_SECONDS = 1.0


class KisQuotationError(RuntimeError):
    """KIS 시세 조회 호출이 실패했을 때 발생한다."""


class KisRateLimitError(KisQuotationError):
    """유량 제한(초당 거래건수 초과)에 걸렸을 때 발생한다. 재시도 대상이다."""


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
        유량 초과(EGW00201)는 백오프하며 최대 MAX_RATE_LIMIT_RETRIES회 재시도한다.
        각 호출 전 유량 제한 여유를 위해 대기한다.
        """
        request_url = f"{self._config.kis_base_url}{path}"
        request_headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self._access_token}",
            "appkey": self._config.kis_app_key,
            "appsecret": self._config.kis_app_secret,
            "tr_id": tr_id,
            "custtype": "P",
        }

        backoff_seconds = RATE_LIMIT_INITIAL_BACKOFF_SECONDS
        for remaining_retries in range(MAX_RATE_LIMIT_RETRIES, -1, -1):
            self._sleep_function(INTER_REQUEST_WAIT_SECONDS)
            response = self._dispatch_request(
                request_url, request_headers, query_parameters
            )
            try:
                return self._parse_response(response, path, tr_id)
            except KisRateLimitError:
                if remaining_retries == 0:
                    raise
                # 초당 거래건수 초과 — 대기 후 재시도한다.
                self._sleep_function(backoff_seconds)
                backoff_seconds *= 2

        # 루프는 반드시 return 하거나 raise 하므로 여기 도달하지 않는다.
        raise AssertionError("unreachable")

    def _dispatch_request(
        self, request_url: str, request_headers: dict, query_parameters: dict
    ) -> httpx.Response:
        if self._http_client is None:
            with httpx.Client(
                timeout=DEFAULT_HTTP_TIMEOUT_SECONDS
            ) as owned_http_client:
                return self._send_request(
                    owned_http_client, request_url, request_headers, query_parameters
                )
        return self._send_request(
            self._http_client, request_url, request_headers, query_parameters
        )

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
        # 유량 초과(EGW00201)는 HTTP 500 + rt_cd=1로 오므로, 상태코드보다 본문을 먼저 본다.
        try:
            response_body = response.json()
        except json.JSONDecodeError:
            response_body = None

        if isinstance(response_body, dict):
            return_code = response_body.get("rt_cd")
            message = response_body.get("msg1", "")
            message_code = response_body.get("msg_cd", "")
            if message_code == RATE_LIMIT_MSG_CODE:
                raise KisRateLimitError(
                    f"KIS 유량 초과(tr_id={tr_id}): msg_cd={message_code!r}, msg1={message!r}"
                )
            if response.status_code != httpx.codes.OK:
                raise KisQuotationError(
                    f"KIS 시세 조회 응답 오류(tr_id={tr_id}, path={path}): "
                    f"HTTP {response.status_code}, 본문: {response.text}"
                )
            if return_code != "0":
                raise KisQuotationError(
                    f"KIS 시세 조회 실패(tr_id={tr_id}): rt_cd={return_code!r}, "
                    f"msg_cd={message_code!r}, msg1={message!r}"
                )
            return response_body

        # 본문이 JSON dict가 아니다.
        if response.status_code != httpx.codes.OK:
            raise KisQuotationError(
                f"KIS 시세 조회 응답 오류(tr_id={tr_id}, path={path}): "
                f"HTTP {response.status_code}, 본문: {response.text}"
            )
        raise KisQuotationError(
            f"KIS 시세 조회 응답 형식이 올바르지 않습니다(tr_id={tr_id}): {response_body!r}"
        )
