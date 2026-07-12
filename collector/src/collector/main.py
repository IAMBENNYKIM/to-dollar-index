from __future__ import annotations

import argparse


def run_backfill(arguments: argparse.Namespace) -> None:
    raise NotImplementedError("이후 커밋에서 구현")


def run_daily(arguments: argparse.Namespace) -> None:
    raise NotImplementedError("이후 커밋에서 구현")


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
