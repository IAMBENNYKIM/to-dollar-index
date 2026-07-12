from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

import httpx

from collector.config import CollectorConfig

# KIS 접근토큰 발급 엔드포인트(실전투자). 응답 필드: access_token(str), expires_in(초, 보통 86400).
TOKEN_ISSUE_PATH = "/oauth2/tokenP"

# collector 서브프로젝트 루트: kis_auth.py -> collector(pkg) -> src -> collector(subproject)
COLLECTOR_SUBPROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CACHE_FILE_PATH = COLLECTOR_SUBPROJECT_ROOT / ".kis_token_cache.json"

# 캐시 토큰은 만료까지 최소 이만큼 남아 있어야 재사용한다.
CACHE_VALIDITY_MARGIN = timedelta(hours=1)

# KIS는 토큰 발급을 약 1분에 1회로 제한한다. 초과 시 이만큼 대기 후 1회 재시도한다.
RETRY_WAIT_SECONDS = 60

DEFAULT_HTTP_TIMEOUT_SECONDS = 30.0


class KisTokenIssuanceError(RuntimeError):
    """KIS 접근토큰 발급에 실패했을 때 발생한다."""


def get_access_token(
    config: CollectorConfig,
    cache_file_path: Path = DEFAULT_CACHE_FILE_PATH,
    http_client: httpx.Client | None = None,
    sleep_function: Callable[[float], None] = time.sleep,
) -> str:
    """유효한 KIS 접근토큰을 반환한다.

    캐시가 유효하면(만료까지 1시간 이상) 캐시된 토큰을 반환하고,
    아니면 신규 발급 후 캐시에 저장한다. 발급 실패 시 60초 대기 후 1회 재시도한다.
    """
    cached_token = _read_cached_token(cache_file_path)
    if cached_token is not None:
        return cached_token

    if http_client is None:
        with httpx.Client(timeout=DEFAULT_HTTP_TIMEOUT_SECONDS) as owned_http_client:
            access_token, expires_in_seconds = _issue_token_with_retry(
                config, owned_http_client, sleep_function
            )
    else:
        access_token, expires_in_seconds = _issue_token_with_retry(
            config, http_client, sleep_function
        )

    _write_cached_token(cache_file_path, access_token, expires_in_seconds)
    return access_token


def _read_cached_token(cache_file_path: Path) -> str | None:
    """캐시가 유효하면 토큰을, 없거나 손상되었거나 만료 임박이면 None을 반환한다."""
    try:
        raw_text = cache_file_path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return None

    try:
        cached_content = json.loads(raw_text)
    except json.JSONDecodeError:
        return None

    if not isinstance(cached_content, dict):
        return None

    access_token = cached_content.get("access_token")
    expires_at_text = cached_content.get("expires_at")
    if not isinstance(access_token, str) or not access_token:
        return None
    if not isinstance(expires_at_text, str):
        return None

    try:
        expires_at = datetime.fromisoformat(expires_at_text)
    except ValueError:
        return None
    # 시간대 정보가 없는 값은 손상으로 간주하고 신규 발급한다.
    if expires_at.tzinfo is None:
        return None

    remaining_time = expires_at - datetime.now(timezone.utc)
    if remaining_time >= CACHE_VALIDITY_MARGIN:
        return access_token
    return None


def _write_cached_token(
    cache_file_path: Path, access_token: str, expires_in_seconds: int
) -> None:
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds)
    cache_content = {
        "access_token": access_token,
        "expires_at": expires_at.isoformat(),
    }
    cache_file_path.parent.mkdir(parents=True, exist_ok=True)
    cache_file_path.write_text(json.dumps(cache_content), encoding="utf-8")


def _issue_token_with_retry(
    config: CollectorConfig,
    http_client: httpx.Client,
    sleep_function: Callable[[float], None],
) -> tuple[str, int]:
    try:
        return _issue_token(config, http_client)
    except KisTokenIssuanceError as first_error:
        # 발급 빈도 제한(약 1분 1회)에 걸렸을 수 있으므로 대기 후 1회 재시도한다.
        sleep_function(RETRY_WAIT_SECONDS)
        try:
            return _issue_token(config, http_client)
        except KisTokenIssuanceError as second_error:
            raise KisTokenIssuanceError(
                "KIS 접근토큰 발급이 재시도 후에도 실패했습니다. "
                f"첫 시도: {first_error} / 재시도: {second_error}"
            ) from second_error


def _issue_token(config: CollectorConfig, http_client: httpx.Client) -> tuple[str, int]:
    """KIS 토큰 발급 API를 호출해 (access_token, expires_in) 을 반환한다. 실패 시 예외를 raise 한다."""
    request_url = f"{config.kis_base_url}{TOKEN_ISSUE_PATH}"
    request_body = {
        "grant_type": "client_credentials",
        "appkey": config.kis_app_key,
        "appsecret": config.kis_app_secret,
    }

    try:
        response = http_client.post(request_url, json=request_body)
    except httpx.HTTPError as network_error:
        raise KisTokenIssuanceError(
            f"KIS 토큰 발급 요청 중 네트워크 오류: {network_error}"
        ) from network_error

    if response.status_code != httpx.codes.OK:
        raise KisTokenIssuanceError(
            f"KIS 토큰 발급 응답 오류: HTTP {response.status_code}, 본문: {response.text}"
        )

    try:
        response_body = response.json()
    except json.JSONDecodeError as parse_error:
        raise KisTokenIssuanceError(
            f"KIS 토큰 발급 응답 JSON 파싱 실패: {parse_error}"
        ) from parse_error

    if not isinstance(response_body, dict):
        raise KisTokenIssuanceError(
            f"KIS 토큰 발급 응답 형식이 올바르지 않습니다: {response_body!r}"
        )

    access_token = response_body.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise KisTokenIssuanceError(
            f"KIS 토큰 발급 응답에 access_token이 없습니다: {response_body!r}"
        )

    raw_expires_in = response_body.get("expires_in")
    try:
        expires_in_seconds = int(raw_expires_in)
    except (TypeError, ValueError):
        raise KisTokenIssuanceError(
            f"KIS 토큰 발급 응답의 expires_in이 올바르지 않습니다: {raw_expires_in!r}"
        )

    return access_token, expires_in_seconds
