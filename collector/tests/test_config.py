from __future__ import annotations

import pytest

from collector.config import KIS_PRODUCTION_BASE_URL, CollectorConfig, load_config

ALL_ENVIRONMENT_VARIABLE_NAMES = [
    "KIS_APP_KEY",
    "KIS_APP_SECRET",
    "KIS_BASE_URL",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
]


def set_valid_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KIS_APP_KEY", "test-app-key")
    monkeypatch.setenv("KIS_APP_SECRET", "test-app-secret")
    monkeypatch.setenv("KIS_BASE_URL", KIS_PRODUCTION_BASE_URL)
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")


def test_load_config_success(monkeypatch: pytest.MonkeyPatch) -> None:
    set_valid_environment(monkeypatch)

    config = load_config()

    assert isinstance(config, CollectorConfig)
    assert config.kis_app_key == "test-app-key"
    assert config.kis_app_secret == "test-app-secret"
    assert config.kis_base_url == KIS_PRODUCTION_BASE_URL
    assert config.supabase_url == "https://example.supabase.co"
    assert config.supabase_service_role_key == "test-service-role-key"


def test_load_config_missing_variables_reports_all(monkeypatch: pytest.MonkeyPatch) -> None:
    for environment_variable_name in ALL_ENVIRONMENT_VARIABLE_NAMES:
        monkeypatch.delenv(environment_variable_name, raising=False)

    with pytest.raises(ValueError) as error_info:
        load_config()

    error_message = str(error_info.value)
    for environment_variable_name in ALL_ENVIRONMENT_VARIABLE_NAMES:
        assert environment_variable_name in error_message


def test_load_config_invalid_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    set_valid_environment(monkeypatch)
    # 모의투자 도메인은 거부되어야 한다.
    monkeypatch.setenv("KIS_BASE_URL", "https://openapivts.koreainvestment.com:29443")

    with pytest.raises(ValueError) as error_info:
        load_config()

    error_message = str(error_info.value)
    assert KIS_PRODUCTION_BASE_URL in error_message
