from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
import respx

from collector.config import KIS_PRODUCTION_BASE_URL, CollectorConfig
from collector.kis_auth import (
    TOKEN_ISSUE_PATH,
    KisTokenIssuanceError,
    get_access_token,
)

TOKEN_ISSUE_URL = f"{KIS_PRODUCTION_BASE_URL}{TOKEN_ISSUE_PATH}"


def build_test_config() -> CollectorConfig:
    return CollectorConfig(
        kis_app_key="test-app-key",
        kis_app_secret="test-app-secret",
        kis_base_url=KIS_PRODUCTION_BASE_URL,
        supabase_url="https://example.supabase.co",
        supabase_service_role_key="test-service-role-key",
    )


def build_success_response(access_token: str = "fresh-token") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "access_token": access_token,
            "access_token_token_expired": "2026-07-13 00:00:00",
            "token_type": "Bearer",
            "expires_in": 86400,
        },
    )


def write_cache_file(cache_file_path: Path, access_token: str, expires_at: datetime) -> None:
    cache_file_path.write_text(
        json.dumps({"access_token": access_token, "expires_at": expires_at.isoformat()}),
        encoding="utf-8",
    )


def fail_if_sleep_called(wait_seconds: float) -> None:
    pytest.fail(f"sleep_function이 호출되면 안 됩니다 (wait_seconds={wait_seconds})")


@respx.mock
def test_issues_new_token_and_creates_cache_file(tmp_path: Path) -> None:
    token_route = respx.post(TOKEN_ISSUE_URL).mock(
        return_value=build_success_response("fresh-token")
    )
    cache_file_path = tmp_path / ".kis_token_cache.json"

    access_token = get_access_token(
        build_test_config(),
        cache_file_path=cache_file_path,
        sleep_function=fail_if_sleep_called,
    )

    assert access_token == "fresh-token"
    assert token_route.call_count == 1

    request_body = json.loads(token_route.calls.last.request.content)
    assert request_body == {
        "grant_type": "client_credentials",
        "appkey": "test-app-key",
        "appsecret": "test-app-secret",
    }

    cached_content = json.loads(cache_file_path.read_text(encoding="utf-8"))
    assert cached_content["access_token"] == "fresh-token"
    cached_expires_at = datetime.fromisoformat(cached_content["expires_at"])
    remaining_time = cached_expires_at - datetime.now(timezone.utc)
    # expires_in=86400초 기준으로 저장되었는지 넉넉한 오차로 확인한다.
    assert timedelta(hours=23) < remaining_time <= timedelta(hours=24)


@respx.mock
def test_valid_cache_returns_token_without_http_call(tmp_path: Path) -> None:
    token_route = respx.post(TOKEN_ISSUE_URL).mock(
        return_value=build_success_response("should-not-be-used")
    )
    cache_file_path = tmp_path / ".kis_token_cache.json"
    write_cache_file(
        cache_file_path,
        "cached-token",
        datetime.now(timezone.utc) + timedelta(hours=12),
    )

    access_token = get_access_token(
        build_test_config(),
        cache_file_path=cache_file_path,
        sleep_function=fail_if_sleep_called,
    )

    assert access_token == "cached-token"
    assert token_route.call_count == 0


@respx.mock
def test_cache_expiring_within_one_hour_triggers_reissue(tmp_path: Path) -> None:
    token_route = respx.post(TOKEN_ISSUE_URL).mock(
        return_value=build_success_response("reissued-token")
    )
    cache_file_path = tmp_path / ".kis_token_cache.json"
    write_cache_file(
        cache_file_path,
        "expiring-token",
        datetime.now(timezone.utc) + timedelta(minutes=30),
    )

    access_token = get_access_token(
        build_test_config(),
        cache_file_path=cache_file_path,
        sleep_function=fail_if_sleep_called,
    )

    assert access_token == "reissued-token"
    assert token_route.call_count == 1


@respx.mock
@pytest.mark.parametrize(
    "corrupted_cache_text",
    [
        "not-json{{{",
        json.dumps({"access_token": "token-without-expiry"}),
        json.dumps({"expires_at": "2099-01-01T00:00:00+00:00"}),
        json.dumps({"access_token": "token", "expires_at": "not-a-datetime"}),
    ],
    ids=["invalid_json", "missing_expires_at", "missing_access_token", "invalid_expires_at"],
)
def test_corrupted_cache_triggers_reissue(tmp_path: Path, corrupted_cache_text: str) -> None:
    token_route = respx.post(TOKEN_ISSUE_URL).mock(
        return_value=build_success_response("reissued-token")
    )
    cache_file_path = tmp_path / ".kis_token_cache.json"
    cache_file_path.write_text(corrupted_cache_text, encoding="utf-8")

    access_token = get_access_token(
        build_test_config(),
        cache_file_path=cache_file_path,
        sleep_function=fail_if_sleep_called,
    )

    assert access_token == "reissued-token"
    assert token_route.call_count == 1

    # 재발급 후 캐시가 정상 내용으로 복구되었는지 확인한다.
    cached_content = json.loads(cache_file_path.read_text(encoding="utf-8"))
    assert cached_content["access_token"] == "reissued-token"


@respx.mock
def test_first_failure_sleeps_sixty_seconds_then_retry_succeeds(tmp_path: Path) -> None:
    token_route = respx.post(TOKEN_ISSUE_URL).mock(
        side_effect=[
            httpx.Response(403, json={"error_code": "EGW00133", "error_description": "발급 빈도 초과"}),
            build_success_response("retried-token"),
        ]
    )
    cache_file_path = tmp_path / ".kis_token_cache.json"
    recorded_wait_seconds: list[float] = []

    access_token = get_access_token(
        build_test_config(),
        cache_file_path=cache_file_path,
        sleep_function=recorded_wait_seconds.append,
    )

    assert access_token == "retried-token"
    assert token_route.call_count == 2
    assert recorded_wait_seconds == [60]

    cached_content = json.loads(cache_file_path.read_text(encoding="utf-8"))
    assert cached_content["access_token"] == "retried-token"


@respx.mock
def test_two_consecutive_failures_raise_error(tmp_path: Path) -> None:
    token_route = respx.post(TOKEN_ISSUE_URL).mock(
        return_value=httpx.Response(500, text="internal server error")
    )
    cache_file_path = tmp_path / ".kis_token_cache.json"
    recorded_wait_seconds: list[float] = []

    with pytest.raises(KisTokenIssuanceError) as error_info:
        get_access_token(
            build_test_config(),
            cache_file_path=cache_file_path,
            sleep_function=recorded_wait_seconds.append,
        )

    assert token_route.call_count == 2
    assert recorded_wait_seconds == [60]
    assert "재시도" in str(error_info.value)
    # 실패 시 캐시 파일이 생성되면 안 된다.
    assert not cache_file_path.exists()
