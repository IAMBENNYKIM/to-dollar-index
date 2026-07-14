from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# KIS REST 도메인. 오타로 다른 호스트를 넣는 실수를 막기 위해 알려진 두 도메인만 허용한다.
KIS_PRODUCTION_BASE_URL = "https://openapi.koreainvestment.com:9443"
KIS_MOCK_BASE_URL = "https://openapivts.koreainvestment.com:29443"
KIS_ALLOWED_BASE_URLS = frozenset({KIS_PRODUCTION_BASE_URL, KIS_MOCK_BASE_URL})

# 저장소 루트: config.py -> collector -> src -> collector(subproject) -> repo root
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

_TRUE_TEXTS = frozenset({"true", "1", "yes", "y", "mock"})
_FALSE_TEXTS = frozenset({"false", "0", "no", "n", "real", "production"})


@dataclass(frozen=True)
class KisSettings:
    app_key: str
    app_secret: str
    base_url: str


@dataclass(frozen=True)
class CollectorConfig:
    kis_app_key: str
    kis_app_secret: str
    kis_base_url: str
    supabase_url: str
    supabase_service_role_key: str
    # KOSIS(한국부동산원) 오픈API 키. 부동산 지표 수집에만 쓰이며, 없어도 주식/환율 수집은 동작해야
    # 하므로 선택값(None 허용)이다.
    kosis_api_key: str | None = None


def _load_dotenv_once() -> None:
    # 저장소 루트의 .env를 로드한다. 파일이 없어도 에러 없이 진행한다
    # (GitHub Actions에서는 환경변수로 직접 주입되기 때문).
    load_dotenv(REPOSITORY_ROOT / ".env")


def _parse_mock_flag(raw_value: str) -> bool:
    normalized = raw_value.strip().lower()
    if normalized in _TRUE_TEXTS:
        return True
    if normalized in _FALSE_TEXTS:
        return False
    raise ValueError(
        f"KIS_IS_MOCK 값을 해석할 수 없습니다: '{raw_value}'. "
        f"true/false 형태로 지정하세요."
    )


def resolve_kis_base_url() -> str:
    """KIS 도메인을 결정한다.

    KIS_BASE_URL이 명시되면 그것을(허용 도메인인지 검증), 없으면 KIS_IS_MOCK 플래그로
    모의/실전 도메인을 고른다. 둘 다 없으면 에러.
    """
    explicit_base_url = os.environ.get("KIS_BASE_URL")
    if explicit_base_url and explicit_base_url.strip():
        base_url = explicit_base_url.strip()
        if base_url not in KIS_ALLOWED_BASE_URLS:
            raise ValueError(
                f"KIS_BASE_URL이 허용된 KIS 도메인이 아닙니다: '{base_url}'. "
                f"실전 '{KIS_PRODUCTION_BASE_URL}' 또는 모의 '{KIS_MOCK_BASE_URL}' 중 하나여야 합니다."
            )
        return base_url

    mock_flag = os.environ.get("KIS_IS_MOCK")
    if mock_flag is not None and mock_flag.strip():
        return KIS_MOCK_BASE_URL if _parse_mock_flag(mock_flag) else KIS_PRODUCTION_BASE_URL

    raise ValueError(
        "KIS 도메인을 결정할 수 없습니다. KIS_BASE_URL을 직접 지정하거나 "
        "KIS_IS_MOCK(true/false)을 설정하세요."
    )


def _require_environment_values(
    required_names: dict[str, str],
) -> tuple[dict[str, str], list[str]]:
    # required_names: {필드명: 환경변수명}. (해석된 값, 누락된 환경변수명 목록)을 반환한다.
    resolved_values: dict[str, str] = {}
    missing_variable_names: list[str] = []
    for field_name, environment_variable_name in required_names.items():
        raw_value = os.environ.get(environment_variable_name)
        if raw_value is None or raw_value.strip() == "":
            missing_variable_names.append(environment_variable_name)
        else:
            resolved_values[field_name] = raw_value
    return resolved_values, missing_variable_names


def load_kis_settings() -> KisSettings:
    """KIS 앱키/시크릿/도메인만 로드한다. Supabase 없이 시세 조회를 검증할 때 사용한다."""
    _load_dotenv_once()

    resolved_values, missing_variable_names = _require_environment_values(
        {"app_key": "KIS_APP_KEY", "app_secret": "KIS_APP_SECRET"}
    )
    if missing_variable_names:
        joined_names = ", ".join(missing_variable_names)
        raise ValueError(
            f"필수 KIS 환경변수가 설정되지 않았습니다: {joined_names}. "
            f".env 파일 또는 실행 환경에 값을 설정하세요."
        )

    base_url = resolve_kis_base_url()
    return KisSettings(
        app_key=resolved_values["app_key"],
        app_secret=resolved_values["app_secret"],
        base_url=base_url,
    )


def load_config() -> CollectorConfig:
    """수집 배치가 쓰는 전체 설정(KIS + Supabase)을 로드한다."""
    _load_dotenv_once()

    resolved_values, missing_variable_names = _require_environment_values(
        {
            "kis_app_key": "KIS_APP_KEY",
            "kis_app_secret": "KIS_APP_SECRET",
            "supabase_url": "SUPABASE_URL",
            "supabase_service_role_key": "SUPABASE_SERVICE_ROLE_KEY",
        }
    )
    if missing_variable_names:
        joined_names = ", ".join(missing_variable_names)
        raise ValueError(
            f"필수 환경변수가 설정되지 않았습니다: {joined_names}. "
            f".env 파일 또는 실행 환경에 값을 설정하세요."
        )

    kis_base_url = resolve_kis_base_url()
    # KOSIS 키는 선택적으로만 읽는다. 없으면 None으로 두고 부동산 수집만 건너뛴다.
    raw_kosis_api_key = os.environ.get("KOSIS_KEY")
    kosis_api_key = (
        raw_kosis_api_key.strip()
        if raw_kosis_api_key is not None and raw_kosis_api_key.strip()
        else None
    )
    return CollectorConfig(
        kis_app_key=resolved_values["kis_app_key"],
        kis_app_secret=resolved_values["kis_app_secret"],
        kis_base_url=kis_base_url,
        supabase_url=resolved_values["supabase_url"],
        supabase_service_role_key=resolved_values["supabase_service_role_key"],
        kosis_api_key=kosis_api_key,
    )
