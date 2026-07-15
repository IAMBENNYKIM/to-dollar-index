from __future__ import annotations

import pytest

from collector.config import (
    KIS_MOCK_BASE_URL,
    KIS_PRODUCTION_BASE_URL,
    CollectorConfig,
    KisSettings,
    load_config,
    load_kis_settings,
)

# load_config가 요구하는 필수 환경변수(도메인 결정용 KIS_BASE_URL/KIS_IS_MOCK 제외).
REQUIRED_ENVIRONMENT_VARIABLE_NAMES = [
    "KIS_APP_KEY",
    "KIS_APP_SECRET",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
]


@pytest.fixture(autouse=True)
def isolate_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    # 저장소 루트에 실제 .env가 있으면 테스트가 그 값에 오염되므로, 로드를 no-op으로 막고
    # os.environ만 검사하도록 격리한다.
    monkeypatch.setattr("collector.config.load_dotenv", lambda *args, **kwargs: False)


def clear_kis_domain_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KIS_BASE_URL", raising=False)
    monkeypatch.delenv("KIS_IS_MOCK", raising=False)


def set_valid_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KIS_APP_KEY", "test-app-key")
    monkeypatch.setenv("KIS_APP_SECRET", "test-app-secret")
    monkeypatch.setenv("KIS_BASE_URL", KIS_PRODUCTION_BASE_URL)
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
    monkeypatch.delenv("KIS_IS_MOCK", raising=False)


def test_load_config_success(monkeypatch: pytest.MonkeyPatch) -> None:
    set_valid_environment(monkeypatch)

    config = load_config()

    assert isinstance(config, CollectorConfig)
    assert config.kis_app_key == "test-app-key"
    assert config.kis_app_secret == "test-app-secret"
    assert config.kis_base_url == KIS_PRODUCTION_BASE_URL
    assert config.supabase_url == "https://example.supabase.co"
    assert config.supabase_service_role_key == "test-service-role-key"


def test_load_config_without_kosis_key_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    set_valid_environment(monkeypatch)
    monkeypatch.delenv("KOSIS_KEY", raising=False)

    config = load_config()

    # KOSIS 키가 없어도 로드에 성공하고 kosis_api_key는 None이어야 한다.
    assert config.kosis_api_key is None


def test_load_config_reads_kosis_key_when_present(monkeypatch: pytest.MonkeyPatch) -> None:
    set_valid_environment(monkeypatch)
    monkeypatch.setenv("KOSIS_KEY", "test-kosis-key")

    config = load_config()

    assert config.kosis_api_key == "test-kosis-key"


def test_load_config_reads_ecos_key_when_present(monkeypatch: pytest.MonkeyPatch) -> None:
    set_valid_environment(monkeypatch)
    monkeypatch.setenv("ECOS_API_KEY", "test-ecos-key")

    config = load_config()

    assert config.ecos_api_key == "test-ecos-key"


def test_load_config_without_ecos_key_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    set_valid_environment(monkeypatch)
    monkeypatch.delenv("ECOS_API_KEY", raising=False)

    config = load_config()

    # ECOS 키가 없어도 로드에 성공하고 ecos_api_key는 None이어야 한다.
    assert config.ecos_api_key is None


def test_load_config_blank_ecos_key_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    set_valid_environment(monkeypatch)
    # 공백만 있는 값은 미설정과 동일하게 None으로 처리한다.
    monkeypatch.setenv("ECOS_API_KEY", "   ")

    config = load_config()

    assert config.ecos_api_key is None


def test_load_config_missing_variables_reports_all(monkeypatch: pytest.MonkeyPatch) -> None:
    for environment_variable_name in REQUIRED_ENVIRONMENT_VARIABLE_NAMES:
        monkeypatch.delenv(environment_variable_name, raising=False)
    clear_kis_domain_variables(monkeypatch)

    with pytest.raises(ValueError) as error_info:
        load_config()

    error_message = str(error_info.value)
    for environment_variable_name in REQUIRED_ENVIRONMENT_VARIABLE_NAMES:
        assert environment_variable_name in error_message


def test_load_config_accepts_mock_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    set_valid_environment(monkeypatch)
    # 모의투자 도메인도 명시 허용된다.
    monkeypatch.setenv("KIS_BASE_URL", KIS_MOCK_BASE_URL)

    config = load_config()

    assert config.kis_base_url == KIS_MOCK_BASE_URL


def test_load_config_invalid_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    set_valid_environment(monkeypatch)
    # 알려지지 않은 도메인은 거부되어야 한다.
    monkeypatch.setenv("KIS_BASE_URL", "https://example.com:9443")

    with pytest.raises(ValueError) as error_info:
        load_config()

    error_message = str(error_info.value)
    assert KIS_PRODUCTION_BASE_URL in error_message
    assert KIS_MOCK_BASE_URL in error_message


def test_kis_is_mock_true_selects_mock_domain(monkeypatch: pytest.MonkeyPatch) -> None:
    set_valid_environment(monkeypatch)
    # KIS_BASE_URL을 지우고 KIS_IS_MOCK로만 도메인을 결정하게 한다.
    monkeypatch.delenv("KIS_BASE_URL", raising=False)
    monkeypatch.setenv("KIS_IS_MOCK", "True")

    config = load_config()

    assert config.kis_base_url == KIS_MOCK_BASE_URL


def test_kis_is_mock_false_selects_production_domain(monkeypatch: pytest.MonkeyPatch) -> None:
    set_valid_environment(monkeypatch)
    monkeypatch.delenv("KIS_BASE_URL", raising=False)
    monkeypatch.setenv("KIS_IS_MOCK", "false")

    config = load_config()

    assert config.kis_base_url == KIS_PRODUCTION_BASE_URL


def test_explicit_base_url_takes_precedence_over_mock_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_valid_environment(monkeypatch)
    # KIS_BASE_URL(실전)과 KIS_IS_MOCK(true)가 충돌하면 명시된 KIS_BASE_URL이 우선한다.
    monkeypatch.setenv("KIS_BASE_URL", KIS_PRODUCTION_BASE_URL)
    monkeypatch.setenv("KIS_IS_MOCK", "true")

    config = load_config()

    assert config.kis_base_url == KIS_PRODUCTION_BASE_URL


def test_missing_both_domain_hints_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    set_valid_environment(monkeypatch)
    clear_kis_domain_variables(monkeypatch)

    with pytest.raises(ValueError) as error_info:
        load_config()

    assert "KIS_IS_MOCK" in str(error_info.value)


def test_load_kis_settings_without_supabase(monkeypatch: pytest.MonkeyPatch) -> None:
    # Supabase 변수가 전혀 없어도 KIS 설정만 로드할 수 있어야 한다 (probe 용도).
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.setenv("KIS_APP_KEY", "probe-key")
    monkeypatch.setenv("KIS_APP_SECRET", "probe-secret")
    clear_kis_domain_variables(monkeypatch)
    monkeypatch.setenv("KIS_IS_MOCK", "True")

    settings = load_kis_settings()

    assert isinstance(settings, KisSettings)
    assert settings.app_key == "probe-key"
    assert settings.base_url == KIS_MOCK_BASE_URL


def test_load_kis_settings_missing_keys_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KIS_APP_KEY", raising=False)
    monkeypatch.delenv("KIS_APP_SECRET", raising=False)
    clear_kis_domain_variables(monkeypatch)
    monkeypatch.setenv("KIS_IS_MOCK", "True")

    with pytest.raises(ValueError) as error_info:
        load_kis_settings()

    error_message = str(error_info.value)
    assert "KIS_APP_KEY" in error_message
    assert "KIS_APP_SECRET" in error_message
