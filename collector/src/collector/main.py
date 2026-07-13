from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date, timedelta

from collector.config import load_config
from collector.database_writer import (
    create_supabase_client,
    fetch_active_stock_indicators,
    fetch_latest_exchange_rate_date,
    fetch_latest_price_date,
    upsert_daily_prices,
    upsert_exchange_rates,
)
from collector.fetch_exchange_rates import fetch_usd_krw_exchange_rates
from collector.fetch_stock_prices import fetch_stock_daily_prices
from collector.kis_auth import get_access_token
from collector.kis_client import KisClient

# --indicator 식별자 규약. 환율은 고정 키, 주식은 'stock:종목코드'.
EXCHANGE_RATE_INDICATOR_KEY = "exchange_rate:USD_KRW"
STOCK_INDICATOR_PREFIX = "stock:"

TASK_KIND_EXCHANGE_RATE = "exchange_rate"
TASK_KIND_STOCK = "stock"


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


def build_collection_tasks(
    supabase_client, indicator_filter: str | None
) -> list[CollectionTask] | None:
    """수집할 지표 작업 목록을 만든다. 환율을 항상 주식보다 앞에 둔다.

    지표 식별자를 해석할 수 없거나 매칭되는 주식이 없으면 안내를 출력하고 None을 반환한다.
    """
    if indicator_filter is None:
        collection_tasks = [_build_exchange_rate_task()]
        for indicator in fetch_active_stock_indicators(supabase_client):
            collection_tasks.append(_build_stock_task(indicator))
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

    print(
        f"알 수 없는 --indicator 형식입니다: '{indicator_filter}'. "
        f"'{STOCK_INDICATOR_PREFIX}종목코드' 또는 '{EXCHANGE_RATE_INDICATOR_KEY}' 형식을 사용하세요.",
        file=sys.stderr,
    )
    return None


def _collect_task_rows(
    task: CollectionTask, kis_client: KisClient, start_date: date, end_date: date
) -> list[dict]:
    if task.kind == TASK_KIND_EXCHANGE_RATE:
        return fetch_usd_krw_exchange_rates(kis_client, start_date, end_date)
    return fetch_stock_daily_prices(
        kis_client, task.indicator_id, task.stock_code, start_date, end_date
    )


def _upsert_task_rows(task: CollectionTask, supabase_client, rows: list[dict]) -> int:
    if task.kind == TASK_KIND_EXCHANGE_RATE:
        return upsert_exchange_rates(supabase_client, rows)
    return upsert_daily_prices(supabase_client, rows)


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


def _create_runtime_clients() -> tuple[KisClient, object]:
    config = load_config()
    access_token = get_access_token(config)
    kis_client = KisClient(config, access_token)
    supabase_client = create_supabase_client(config)
    return kis_client, supabase_client


def run_backfill(arguments: argparse.Namespace) -> None:
    start_date = _parse_start_date(arguments.start_date)
    end_date = get_today_date()
    if start_date > end_date:
        print(
            f"--from({start_date})이 오늘({end_date})보다 늦습니다.",
            file=sys.stderr,
        )
        sys.exit(1)

    kis_client, supabase_client = _create_runtime_clients()

    collection_tasks = build_collection_tasks(supabase_client, arguments.indicator)
    if collection_tasks is None:
        sys.exit(1)

    had_failure = False
    for task in collection_tasks:
        try:
            rows = _collect_task_rows(task, kis_client, start_date, end_date)
            if not arguments.dry_run:
                _upsert_task_rows(task, supabase_client, rows)
            _print_task_summary(task, start_date, end_date, rows, arguments.dry_run)
        except Exception as collection_error:
            had_failure = True
            print(f"[{task.key}] 수집 실패: {collection_error}", file=sys.stderr)

    if had_failure:
        sys.exit(1)


def run_daily(arguments: argparse.Namespace) -> None:
    end_date = get_today_date()

    kis_client, supabase_client = _create_runtime_clients()

    collection_tasks = build_collection_tasks(supabase_client, None)
    if collection_tasks is None:
        sys.exit(1)

    had_failure = False
    for task in collection_tasks:
        try:
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

            rows = _collect_task_rows(task, kis_client, start_date, end_date)
            if not arguments.dry_run:
                _upsert_task_rows(task, supabase_client, rows)
            _print_task_summary(task, start_date, end_date, rows, arguments.dry_run)
        except Exception as collection_error:
            had_failure = True
            print(f"[{task.key}] 수집 실패: {collection_error}", file=sys.stderr)

    if had_failure:
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
