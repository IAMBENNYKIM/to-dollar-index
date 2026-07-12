from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# 실전투자 도메인. 모의투자 도메인(:29443)과 혼동하면 실데이터가 아닌 값을 받게 되므로 고정 검증한다.
KIS_PRODUCTION_BASE_URL = "https://openapi.koreainvestment.com:9443"

# 저장소 루트: config.py -> collector -> src -> collector(subproject) -> repo root
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class CollectorConfig:
    kis_app_key: str
    kis_app_secret: str
    kis_base_url: str
    supabase_url: str
    supabase_service_role_key: str


def load_config() -> CollectorConfig:
    # 저장소 루트의 .env를 로드한다. 파일이 없어도 에러 없이 진행한다
    # (GitHub Actions에서는 환경변수로 직접 주입되기 때문).
    load_dotenv(REPOSITORY_ROOT / ".env")

    required_environment_variables = {
        "kis_app_key": "KIS_APP_KEY",
        "kis_app_secret": "KIS_APP_SECRET",
        "kis_base_url": "KIS_BASE_URL",
        "supabase_url": "SUPABASE_URL",
        "supabase_service_role_key": "SUPABASE_SERVICE_ROLE_KEY",
    }

    resolved_values: dict[str, str] = {}
    missing_variable_names: list[str] = []
    for field_name, environment_variable_name in required_environment_variables.items():
        raw_value = os.environ.get(environment_variable_name)
        if raw_value is None or raw_value.strip() == "":
            missing_variable_names.append(environment_variable_name)
        else:
            resolved_values[field_name] = raw_value

    if missing_variable_names:
        joined_names = ", ".join(missing_variable_names)
        raise ValueError(
            f"필수 환경변수가 설정되지 않았습니다: {joined_names}. "
            f".env 파일 또는 실행 환경에 값을 설정하세요."
        )

    kis_base_url = resolved_values["kis_base_url"]
    if kis_base_url != KIS_PRODUCTION_BASE_URL:
        raise ValueError(
            f"KIS_BASE_URL이 실전투자 도메인이 아닙니다: '{kis_base_url}'. "
            f"기대값은 '{KIS_PRODUCTION_BASE_URL}' 입니다 (모의투자 도메인 혼동 방지)."
        )

    return CollectorConfig(
        kis_app_key=resolved_values["kis_app_key"],
        kis_app_secret=resolved_values["kis_app_secret"],
        kis_base_url=resolved_values["kis_base_url"],
        supabase_url=resolved_values["supabase_url"],
        supabase_service_role_key=resolved_values["supabase_service_role_key"],
    )
