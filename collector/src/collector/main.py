from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import date, timedelta

from collector.config import load_config
from collector.database_writer import (
    create_supabase_client,
    fetch_active_real_estate_indicators,
    fetch_active_stock_indicators,
    fetch_latest_exchange_rate_date,
    fetch_latest_price_date,
    upsert_daily_prices,
    upsert_exchange_rates,
)
from collector.fetch_exchange_rates import fetch_usd_krw_exchange_rates
from collector.fetch_exchange_rates_ecos import fetch_usd_krw_exchange_rates_ecos
from collector.fetch_real_estate import fetch_real_estate_prices
from collector.fetch_stock_prices import fetch_stock_daily_prices
from collector.kis_auth import get_access_token
from collector.kis_client import KisClient, KisQuotationError

# --indicator 식별자 규약. 환율은 고정 키, 주식은 'stock:종목코드', 부동산은 'real_estate:소스코드'.
EXCHANGE_RATE_INDICATOR_KEY = "exchange_rate:USD_KRW"
STOCK_INDICATOR_PREFIX = "stock:"
REAL_ESTATE_INDICATOR_PREFIX = "real_estate:"

TASK_KIND_EXCHANGE_RATE = "exchange_rate"
TASK_KIND_STOCK = "stock"
TASK_KIND_REAL_ESTATE = "real_estate"

# 부동산(월 데이터) 수집 개월 수. backfill은 전량(244행 커버), daily는 최근 몇 개월을 재수집해
# 통계 개정(revision)을 멱등 upsert로 반영한다.
REAL_ESTATE_BACKFILL_PERIODS = 400
REAL_ESTATE_DAILY_PERIODS = 4


@dataclass(frozen=True)
class CollectionTask:
    """한 지표의 수집 작업 단위. backfill/daily가 공유하는 오케스트레이션 대상."""

    key: str
    kind: str
    display_name: str | None = None
    indicator_id: str | None = None
    stock_code: str | None = None


def get_today_date() -> date:
    # 수집 종료일 기준. 테스트에서 monkeypatch로 고정하기 위해 함수로 분리한다.
    return date.today()


def _parse_start_date(raw_start_date: str) -> date:
    try:
        return date.fromisoformat(raw_start_date)
    except ValueError:
        print(
            f"--from 값이 올바른 날짜(YYYY-MM-DD)가 아닙니다: '{raw_start_date}'",
            file=sys.stderr,
        )
        sys.exit(1)


def _build_exchange_rate_task() -> CollectionTask:
    return CollectionTask(
        key=EXCHANGE_RATE_INDICATOR_KEY,
        kind=TASK_KIND_EXCHANGE_RATE,
        display_name="원/달러 환율",
    )


def _build_stock_task(indicator: dict) -> CollectionTask:
    stock_code = indicator["source_code"]
    return CollectionTask(
        key=f"{STOCK_INDICATOR_PREFIX}{stock_code}",
        kind=TASK_KIND_STOCK,
        display_name=indicator.get("display_name"),
        indicator_id=indicator["id"],
        stock_code=stock_code,
    )


def _build_real_estate_task(indicator: dict) -> CollectionTask:
    # 지표 id가 곧 --indicator 필터 값이자 태스크 키다.
    # 주식과 달리 부동산은 id 접미사(seoul-small)와 source_code(DT_KAB_11672_S19)가 다르다.
    indicator_id = indicator["id"]
    return CollectionTask(
        key=indicator_id,
        kind=TASK_KIND_REAL_ESTATE,
        display_name=indicator.get("display_name"),
        indicator_id=indicator_id,
    )


def build_collection_tasks(
    supabase_client, indicator_filter: str | None, kosis_api_key: str | None
) -> list[CollectionTask] | None:
    """수집할 지표 작업 목록을 만든다. 환율 → 주식 → 부동산 순서를 유지한다.

    부동산 태스크는 KOSIS 키가 있을 때만 추가한다(키가 없으면 안내 후 건너뜀).
    지표 식별자를 해석할 수 없거나 매칭되는 지표가 없으면 안내를 출력하고 None을 반환한다.
    """
    if indicator_filter is None:
        collection_tasks = [_build_exchange_rate_task()]
        for indicator in fetch_active_stock_indicators(supabase_client):
            collection_tasks.append(_build_stock_task(indicator))
        if kosis_api_key:
            for indicator in fetch_active_real_estate_indicators(supabase_client):
                collection_tasks.append(_build_real_estate_task(indicator))
        else:
            print("KOSIS_KEY가 설정되지 않아 부동산 지표 수집을 건너뜁니다.")
        return collection_tasks

    if indicator_filter == EXCHANGE_RATE_INDICATOR_KEY:
        return [_build_exchange_rate_task()]

    if indicator_filter.startswith(STOCK_INDICATOR_PREFIX):
        requested_stock_code = indicator_filter[len(STOCK_INDICATOR_PREFIX):]
        for indicator in fetch_active_stock_indicators(supabase_client):
            if indicator["source_code"] == requested_stock_code:
                return [_build_stock_task(indicator)]
        print(
            f"지표를 찾을 수 없습니다: '{indicator_filter}' "
            f"(활성 주식 지표 목록에 종목코드 {requested_stock_code}가 없습니다).",
            file=sys.stderr,
        )
        return None

    if indicator_filter.startswith(REAL_ESTATE_INDICATOR_PREFIX):
        if not kosis_api_key:
            print(
                f"KOSIS_KEY가 설정되지 않아 부동산 지표를 수집할 수 없습니다: '{indicator_filter}'.",
                file=sys.stderr,
            )
            return None
        # 부동산은 id 접미사가 source_code와 다르므로 전체 id로 매칭한다.
        for indicator in fetch_active_real_estate_indicators(supabase_client):
            if indicator["id"] == indicator_filter:
                return [_build_real_estate_task(indicator)]
        print(
            f"지표를 찾을 수 없습니다: '{indicator_filter}' "
            f"(활성 부동산 지표 목록에 해당 id가 없습니다).",
            file=sys.stderr,
        )
        return None

    print(
        f"알 수 없는 --indicator 형식입니다: '{indicator_filter}'. "
        f"'{STOCK_INDICATOR_PREFIX}종목코드', '{REAL_ESTATE_INDICATOR_PREFIX}소스코드' 또는 "
        f"'{EXCHANGE_RATE_INDICATOR_KEY}' 형식을 사용하세요.",
        file=sys.stderr,
    )
    return None


def _collect_task_rows(
    task: CollectionTask,
    kis_client: KisClient,
    config,
    start_date: date,
    end_date: date,
    real_estate_periods_count: int,
) -> list[dict]:
    if task.kind == TASK_KIND_EXCHANGE_RATE:
        try:
            return fetch_usd_krw_exchange_rates(kis_client, start_date, end_date)
        except KisQuotationError as kis_error:
            # ECOS 키가 없으면 폴백 없이 기존 동작(에러 전파 → per-task 실패 처리) 유지.
            if config.ecos_api_key is None:
                raise
            print(
                f"[{task.key}] KIS 환율 조회 실패, ECOS 폴백을 시도합니다: {kis_error}",
                file=sys.stderr,
            )
            return fetch_usd_krw_exchange_rates_ecos(
                config.ecos_api_key, start_date, end_date
            )
    if task.kind == TASK_KIND_REAL_ESTATE:
        # 부동산은 월 데이터라 start/end 구간이 아니라 최근 개월 수(newEstPrdCnt)로 조회한다.
        return fetch_real_estate_prices(
            config.kosis_api_key, task.indicator_id, real_estate_periods_count
        )
    return fetch_stock_daily_prices(
        kis_client, task.indicator_id, task.stock_code, start_date, end_date
    )


def _upsert_task_rows(task: CollectionTask, supabase_client, rows: list[dict]) -> int:
    if task.kind == TASK_KIND_EXCHANGE_RATE:
        return upsert_exchange_rates(supabase_client, rows)
    # 주식·부동산 모두 daily_prices 테이블을 공유한다.
    return upsert_daily_prices(supabase_client, rows)


def _summary_range(
    task: CollectionTask,
    fallback_start_date: date,
    fallback_end_date: date,
    rows: list[dict],
) -> tuple[date, date]:
    # 부동산은 조회 구간이 아니라 실제 수집된 월(price_date) 범위를 요약에 표기한다.
    if task.kind == TASK_KIND_REAL_ESTATE and rows:
        return rows[0]["price_date"], rows[-1]["price_date"]
    return fallback_start_date, fallback_end_date


def _fetch_latest_date_for_task(task: CollectionTask, supabase_client) -> date | None:
    if task.kind == TASK_KIND_EXCHANGE_RATE:
        return fetch_latest_exchange_rate_date(supabase_client)
    return fetch_latest_price_date(supabase_client, task.indicator_id)


def _summary_field_names(task_kind: str) -> tuple[str, str]:
    # (날짜 필드, 종가 필드) 반환.
    if task_kind == TASK_KIND_EXCHANGE_RATE:
        return "rate_date", "close_rate"
    return "price_date", "close_price"


def _print_task_summary(
    task: CollectionTask,
    start_date: date,
    end_date: date,
    rows: list[dict],
    dry_run: bool,
) -> None:
    date_field_name, close_field_name = _summary_field_names(task.kind)
    display_suffix = f" ({task.display_name})" if task.display_name else ""
    indicator_id_text = task.indicator_id if task.indicator_id else "-"
    print(
        f"[{task.key}]{display_suffix} id={indicator_id_text} "
        f"구간 {start_date}~{end_date} 수집 {len(rows)}건"
    )
    if rows:
        first_row = rows[0]
        last_row = rows[-1]
        print(
            f"  첫 행 {first_row[date_field_name]} 종가 {first_row[close_field_name]}"
            f" / 마지막 행 {last_row[date_field_name]} 종가 {last_row[close_field_name]}"
        )
    if dry_run:
        print("  [dry-run] 쓰기 생략")


def _create_runtime_clients() -> tuple[KisClient, object, object]:
    config = load_config()
    access_token = get_access_token(config)
    kis_client = KisClient(config, access_token)
    supabase_client = create_supabase_client(config)
    return kis_client, supabase_client, config


def _write_failure_summary(failure_lines: list[str]) -> None:
    """실패 태스크 요약을 COLLECT_FAILURE_SUMMARY_FILE 경로에 기록한다.

    워크플로 알림 스텝이 이 파일을 읽어 텔레그램 메시지에 실패 지표를 포함한다.
    환경변수가 없거나 빈 문자열이면(로컬 실행 등) 아무것도 하지 않는다.
    파일 쓰기 실패는 배치 종료 코드에 영향을 주지 않도록 경고만 남긴다.
    """
    summary_file_path = os.environ.get("COLLECT_FAILURE_SUMMARY_FILE")
    if not summary_file_path:
        return
    try:
        with open(summary_file_path, "w", encoding="utf-8") as summary_file:
            for failure_line in failure_lines:
                summary_file.write(f"{failure_line}\n")
    except OSError as write_error:
        print(
            f"실패 요약 파일 기록에 실패했습니다: {type(write_error).__name__}",
            file=sys.stderr,
        )


def run_backfill(arguments: argparse.Namespace) -> None:
    start_date = _parse_start_date(arguments.start_date)
    end_date = get_today_date()
    if start_date > end_date:
        print(
            f"--from({start_date})이 오늘({end_date})보다 늦습니다.",
            file=sys.stderr,
        )
        sys.exit(1)

    kis_client, supabase_client, config = _create_runtime_clients()

    collection_tasks = build_collection_tasks(
        supabase_client, arguments.indicator, config.kosis_api_key
    )
    if collection_tasks is None:
        sys.exit(1)

    had_failure = False
    failure_summary_lines: list[str] = []
    for task in collection_tasks:
        try:
            # 부동산은 start/end를 무시하고 전량(REAL_ESTATE_BACKFILL_PERIODS)을 수집한다.
            rows = _collect_task_rows(
                task, kis_client, config, start_date, end_date,
                REAL_ESTATE_BACKFILL_PERIODS,
            )
            if not arguments.dry_run:
                _upsert_task_rows(task, supabase_client, rows)
            summary_start, summary_end = _summary_range(task, start_date, end_date, rows)
            _print_task_summary(task, summary_start, summary_end, rows, arguments.dry_run)
        except Exception as collection_error:
            had_failure = True
            failure_summary_lines.append(f"[{task.key}] {collection_error}")
            print(f"[{task.key}] 수집 실패: {collection_error}", file=sys.stderr)

    if had_failure:
        _write_failure_summary(failure_summary_lines)
        sys.exit(1)


def run_daily(arguments: argparse.Namespace) -> None:
    end_date = get_today_date()

    kis_client, supabase_client, config = _create_runtime_clients()

    collection_tasks = build_collection_tasks(supabase_client, None, config.kosis_api_key)
    if collection_tasks is None:
        sys.exit(1)

    had_failure = False
    failure_summary_lines: list[str] = []
    for task in collection_tasks:
        try:
            if task.kind == TASK_KIND_REAL_ESTATE:
                # 부동산은 증분 로직을 타지 않고 최근 몇 개월을 재수집해 개정분을 멱등 upsert한다.
                rows = _collect_task_rows(
                    task, kis_client, config, end_date, end_date,
                    REAL_ESTATE_DAILY_PERIODS,
                )
                if not arguments.dry_run:
                    _upsert_task_rows(task, supabase_client, rows)
                summary_start, summary_end = _summary_range(task, end_date, end_date, rows)
                _print_task_summary(task, summary_start, summary_end, rows, arguments.dry_run)
                continue

            latest_date = _fetch_latest_date_for_task(task, supabase_client)
            if latest_date is None:
                print(
                    f"[{task.key}] 저장된 데이터가 없습니다. 먼저 backfill을 실행하세요. 건너뜁니다."
                )
                continue

            start_date = latest_date + timedelta(days=1)
            if start_date > end_date:
                print(f"[{task.key}] 이미 최신입니다(최신일 {latest_date}). 건너뜁니다.")
                continue

            rows = _collect_task_rows(
                task, kis_client, config, start_date, end_date,
                REAL_ESTATE_DAILY_PERIODS,
            )
            if not arguments.dry_run:
                _upsert_task_rows(task, supabase_client, rows)
            _print_task_summary(task, start_date, end_date, rows, arguments.dry_run)
        except Exception as collection_error:
            had_failure = True
            failure_summary_lines.append(f"[{task.key}] {collection_error}")
            print(f"[{task.key}] 수집 실패: {collection_error}", file=sys.stderr)

    if had_failure:
        _write_failure_summary(failure_summary_lines)
        sys.exit(1)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="collector",
        description="KIS 오픈API 주가/환율 일일 종가를 Supabase에 적재하는 수집 배치",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    backfill_parser = subparsers.add_parser(
        "backfill",
        help="지정 시작일부터 과거 데이터를 소급 수집한다",
    )
    backfill_parser.add_argument(
        "--from",
        dest="start_date",
        required=True,
        metavar="YYYY-MM-DD",
        help="수집 시작일 (YYYY-MM-DD)",
    )
    backfill_parser.add_argument(
        "--indicator",
        dest="indicator",
        default=None,
        help="특정 지표만 수집 (미지정 시 전체)",
    )
    backfill_parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="적재 없이 수집 결과만 확인한다",
    )
    backfill_parser.set_defaults(handler=run_backfill)

    daily_parser = subparsers.add_parser(
        "daily",
        help="당일 종가를 수집한다",
    )
    daily_parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="적재 없이 수집 결과만 확인한다",
    )
    daily_parser.set_defaults(handler=run_daily)

    return parser


def main(argument_list: list[str] | None = None) -> None:
    parser = build_argument_parser()
    arguments = parser.parse_args(argument_list)
    arguments.handler(arguments)


if __name__ == "__main__":
    main()
