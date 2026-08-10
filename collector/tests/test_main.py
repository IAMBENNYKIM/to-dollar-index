from __future__ import annotations

import argparse
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from collector import main as main_module
from collector.fetch_real_estate import RealEstateFetchError
from collector.kis_client import KisQuotationError

FIXED_TODAY = date(2026, 7, 13)


class FakeSupabaseClient:
    """수집 오케스트레이션 테스트용 placeholder. DB 접근 함수는 전부 monkeypatch로 대체된다."""


def build_fake_config(
    kosis_api_key: str | None = None, ecos_api_key: str | None = None
) -> SimpleNamespace:
    # load_config 대체. 부동산 배선은 config.kosis_api_key를, 환율 폴백은 config.ecos_api_key를
    # 참조하므로 그 두 필드만 채운다.
    return SimpleNamespace(kosis_api_key=kosis_api_key, ecos_api_key=ecos_api_key)


def build_backfill_arguments(
    start_date: str = "2026-01-01",
    indicator: str | None = None,
    dry_run: bool = False,
    skip_real_estate: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        start_date=start_date,
        indicator=indicator,
        dry_run=dry_run,
        skip_real_estate=skip_real_estate,
    )


def build_daily_arguments(
    dry_run: bool = False, skip_real_estate: bool = False
) -> argparse.Namespace:
    return argparse.Namespace(dry_run=dry_run, skip_real_estate=skip_real_estate)


def build_stock_indicator(
    indicator_id: str, source_code: str, display_name: str
) -> dict:
    return {
        "id": indicator_id,
        "source_code": source_code,
        "display_name": display_name,
    }


def build_exchange_rate_row(rate_date: date) -> dict:
    return {
        "currency_pair": "USD_KRW",
        "rate_date": rate_date,
        "close_rate": Decimal("1350"),
    }


def build_stock_price_row(indicator_id: str, price_date: date) -> dict:
    return {
        "indicator_id": indicator_id,
        "price_date": price_date,
        "close_price": Decimal("70000"),
    }


@pytest.fixture
def patched_runtime(monkeypatch):
    """토큰/클라이언트 생성과 오늘 날짜를 목킹하고, 호출 기록 컨테이너를 제공한다."""
    recorder: dict[str, list] = {
        "exchange_fetch_ranges": [],
        "stock_fetch_calls": [],
        "exchange_upsert_calls": [],
        "stock_upsert_calls": [],
    }

    monkeypatch.setattr(main_module, "load_config", lambda: build_fake_config())
    monkeypatch.setattr(main_module, "get_access_token", lambda config: "test-token")
    monkeypatch.setattr(
        main_module, "KisClient", lambda config, access_token: object()
    )
    monkeypatch.setattr(
        main_module, "create_supabase_client", lambda config: FakeSupabaseClient()
    )
    monkeypatch.setattr(main_module, "get_today_date", lambda: FIXED_TODAY)

    return recorder


def test_backfill_collects_exchange_rate_before_stocks(patched_runtime, monkeypatch):
    call_order: list[str] = []

    def fake_fetch_exchange(kis_client, start_date, end_date):
        call_order.append("exchange")
        patched_runtime["exchange_fetch_ranges"].append((start_date, end_date))
        return [build_exchange_rate_row(date(2026, 1, 2))]

    def fake_fetch_stock(kis_client, indicator_id, stock_code, start_date, end_date):
        call_order.append(f"stock:{stock_code}")
        patched_runtime["stock_fetch_calls"].append((stock_code, start_date, end_date))
        return [build_stock_price_row(indicator_id, date(2026, 1, 2))]

    monkeypatch.setattr(
        main_module, "fetch_active_stock_indicators",
        lambda client: [build_stock_indicator("id-1", "005930", "삼성전자")],
    )
    monkeypatch.setattr(main_module, "fetch_usd_krw_exchange_rates", fake_fetch_exchange)
    monkeypatch.setattr(main_module, "fetch_stock_daily_prices", fake_fetch_stock)
    monkeypatch.setattr(
        main_module, "upsert_exchange_rates",
        lambda client, rows: patched_runtime["exchange_upsert_calls"].append(rows) or len(rows),
    )
    monkeypatch.setattr(
        main_module, "upsert_daily_prices",
        lambda client, rows: patched_runtime["stock_upsert_calls"].append(rows) or len(rows),
    )

    main_module.run_backfill(build_backfill_arguments())

    assert call_order == ["exchange", "stock:005930"]
    # backfill 구간은 --from ~ 오늘.
    assert patched_runtime["exchange_fetch_ranges"] == [(date(2026, 1, 1), FIXED_TODAY)]
    assert patched_runtime["stock_fetch_calls"] == [("005930", date(2026, 1, 1), FIXED_TODAY)]
    assert len(patched_runtime["exchange_upsert_calls"]) == 1
    assert len(patched_runtime["stock_upsert_calls"]) == 1


def test_backfill_indicator_filter_stock_only(patched_runtime, monkeypatch):
    call_order: list[str] = []

    monkeypatch.setattr(
        main_module, "fetch_active_stock_indicators",
        lambda client: [
            build_stock_indicator("id-1", "005930", "삼성전자"),
            build_stock_indicator("id-2", "000660", "SK하이닉스"),
        ],
    )
    monkeypatch.setattr(
        main_module, "fetch_usd_krw_exchange_rates",
        lambda *args: call_order.append("exchange") or [],
    )

    def fake_fetch_stock(kis_client, indicator_id, stock_code, start_date, end_date):
        call_order.append(f"stock:{stock_code}")
        return [build_stock_price_row(indicator_id, date(2026, 1, 2))]

    monkeypatch.setattr(main_module, "fetch_stock_daily_prices", fake_fetch_stock)
    monkeypatch.setattr(main_module, "upsert_daily_prices", lambda client, rows: len(rows))
    monkeypatch.setattr(main_module, "upsert_exchange_rates", lambda client, rows: len(rows))

    main_module.run_backfill(build_backfill_arguments(indicator="stock:000660"))

    # 환율은 호출되지 않고 지정 종목만 수집된다.
    assert call_order == ["stock:000660"]


def test_backfill_indicator_filter_exchange_only(patched_runtime, monkeypatch):
    call_order: list[str] = []

    monkeypatch.setattr(
        main_module, "fetch_active_stock_indicators",
        lambda client: pytest.fail("환율 전용 필터에서는 주식 목록을 조회하지 않아야 한다"),
    )
    monkeypatch.setattr(
        main_module, "fetch_usd_krw_exchange_rates",
        lambda *args: call_order.append("exchange") or [build_exchange_rate_row(date(2026, 1, 2))],
    )
    monkeypatch.setattr(
        main_module, "fetch_stock_daily_prices",
        lambda *args, **kwargs: call_order.append("stock") or [],
    )
    monkeypatch.setattr(main_module, "upsert_exchange_rates", lambda client, rows: len(rows))

    main_module.run_backfill(build_backfill_arguments(indicator="exchange_rate:USD_KRW"))

    assert call_order == ["exchange"]


def test_backfill_unknown_stock_indicator_exits_with_code_1(patched_runtime, monkeypatch):
    monkeypatch.setattr(
        main_module, "fetch_active_stock_indicators",
        lambda client: [build_stock_indicator("id-1", "005930", "삼성전자")],
    )
    monkeypatch.setattr(
        main_module, "fetch_stock_daily_prices",
        lambda *args, **kwargs: pytest.fail("매칭 실패 시 수집을 시도하면 안 된다"),
    )

    with pytest.raises(SystemExit) as exit_info:
        main_module.run_backfill(build_backfill_arguments(indicator="stock:999999"))

    assert exit_info.value.code == 1


def test_backfill_dry_run_skips_upsert(patched_runtime, monkeypatch):
    monkeypatch.setattr(
        main_module, "fetch_active_stock_indicators",
        lambda client: [build_stock_indicator("id-1", "005930", "삼성전자")],
    )
    monkeypatch.setattr(
        main_module, "fetch_usd_krw_exchange_rates",
        lambda *args: [build_exchange_rate_row(date(2026, 1, 2))],
    )
    monkeypatch.setattr(
        main_module, "fetch_stock_daily_prices",
        lambda *args, **kwargs: [build_stock_price_row("id-1", date(2026, 1, 2))],
    )
    monkeypatch.setattr(
        main_module, "upsert_exchange_rates",
        lambda client, rows: pytest.fail("dry-run에서는 upsert를 호출하면 안 된다"),
    )
    monkeypatch.setattr(
        main_module, "upsert_daily_prices",
        lambda client, rows: pytest.fail("dry-run에서는 upsert를 호출하면 안 된다"),
    )

    main_module.run_backfill(build_backfill_arguments(dry_run=True))


def test_daily_requests_from_latest_date_plus_one(patched_runtime, monkeypatch):
    exchange_ranges: list[tuple[date, date]] = []
    stock_ranges: list[tuple[date, date]] = []

    monkeypatch.setattr(
        main_module, "fetch_active_stock_indicators",
        lambda client: [build_stock_indicator("id-1", "005930", "삼성전자")],
    )
    monkeypatch.setattr(
        main_module, "fetch_latest_exchange_rate_date", lambda client: date(2026, 7, 10)
    )
    monkeypatch.setattr(
        main_module, "fetch_latest_price_date",
        lambda client, indicator_id: date(2026, 7, 11),
    )

    def fake_fetch_exchange(kis_client, start_date, end_date):
        exchange_ranges.append((start_date, end_date))
        return [build_exchange_rate_row(date(2026, 7, 13))]

    def fake_fetch_stock(kis_client, indicator_id, stock_code, start_date, end_date):
        stock_ranges.append((start_date, end_date))
        return [build_stock_price_row(indicator_id, date(2026, 7, 13))]

    monkeypatch.setattr(main_module, "fetch_usd_krw_exchange_rates", fake_fetch_exchange)
    monkeypatch.setattr(main_module, "fetch_stock_daily_prices", fake_fetch_stock)
    monkeypatch.setattr(main_module, "upsert_exchange_rates", lambda client, rows: len(rows))
    monkeypatch.setattr(main_module, "upsert_daily_prices", lambda client, rows: len(rows))

    main_module.run_daily(build_daily_arguments())

    assert exchange_ranges == [(date(2026, 7, 11), FIXED_TODAY)]
    assert stock_ranges == [(date(2026, 7, 12), FIXED_TODAY)]


def test_daily_skips_empty_db_indicator(patched_runtime, monkeypatch):
    monkeypatch.setattr(
        main_module, "fetch_active_stock_indicators", lambda client: []
    )
    monkeypatch.setattr(
        main_module, "fetch_latest_exchange_rate_date", lambda client: None
    )
    monkeypatch.setattr(
        main_module, "fetch_usd_krw_exchange_rates",
        lambda *args: pytest.fail("빈 DB 지표는 수집을 건너뛰어야 한다"),
    )

    main_module.run_daily(build_daily_arguments())


def test_daily_skips_when_already_up_to_date(patched_runtime, monkeypatch):
    monkeypatch.setattr(
        main_module, "fetch_active_stock_indicators", lambda client: []
    )
    # 최신일이 오늘이면 시작일(오늘+1) > 오늘 이므로 수집하지 않는다.
    monkeypatch.setattr(
        main_module, "fetch_latest_exchange_rate_date", lambda client: FIXED_TODAY
    )
    monkeypatch.setattr(
        main_module, "fetch_usd_krw_exchange_rates",
        lambda *args: pytest.fail("이미 최신이면 수집 함수를 호출하면 안 된다"),
    )

    main_module.run_daily(build_daily_arguments())


def test_daily_dry_run_reads_latest_but_skips_upsert(patched_runtime, monkeypatch):
    monkeypatch.setattr(
        main_module, "fetch_active_stock_indicators", lambda client: []
    )
    monkeypatch.setattr(
        main_module, "fetch_latest_exchange_rate_date", lambda client: date(2026, 7, 11)
    )
    monkeypatch.setattr(
        main_module, "fetch_usd_krw_exchange_rates",
        lambda *args: [build_exchange_rate_row(date(2026, 7, 13))],
    )
    monkeypatch.setattr(
        main_module, "upsert_exchange_rates",
        lambda client, rows: pytest.fail("dry-run에서는 upsert를 호출하면 안 된다"),
    )

    main_module.run_daily(build_daily_arguments(dry_run=True))


def test_one_indicator_failure_continues_others_and_exits_1(patched_runtime, monkeypatch):
    attempted_stock_codes: list[str] = []

    monkeypatch.setattr(
        main_module, "fetch_active_stock_indicators",
        lambda client: [
            build_stock_indicator("id-1", "005930", "삼성전자"),
            build_stock_indicator("id-2", "000660", "SK하이닉스"),
        ],
    )
    monkeypatch.setattr(
        main_module, "fetch_usd_krw_exchange_rates",
        lambda *args: [build_exchange_rate_row(date(2026, 1, 2))],
    )

    def fake_fetch_stock(kis_client, indicator_id, stock_code, start_date, end_date):
        attempted_stock_codes.append(stock_code)
        if stock_code == "005930":
            raise RuntimeError("일시적 시세 조회 실패")
        return [build_stock_price_row(indicator_id, date(2026, 1, 2))]

    monkeypatch.setattr(main_module, "fetch_stock_daily_prices", fake_fetch_stock)
    monkeypatch.setattr(main_module, "upsert_exchange_rates", lambda client, rows: len(rows))
    monkeypatch.setattr(main_module, "upsert_daily_prices", lambda client, rows: len(rows))

    with pytest.raises(SystemExit) as exit_info:
        main_module.run_backfill(build_backfill_arguments())

    # 첫 종목이 실패해도 두 번째 종목까지 시도되어야 한다.
    assert attempted_stock_codes == ["005930", "000660"]
    assert exit_info.value.code == 1


def build_real_estate_indicator(
    indicator_id: str, source_code: str, display_name: str
) -> dict:
    return {
        "id": indicator_id,
        "source_code": source_code,
        "display_name": display_name,
    }


def build_real_estate_price_row(indicator_id: str, price_date: date) -> dict:
    return {
        "indicator_id": indicator_id,
        "price_date": price_date,
        "close_price": Decimal("273635"),
    }


@pytest.mark.parametrize(
    "today, latest_price_date, expected_months",
    [
        # 공표주기 익익월 기준 정상 순환 범위(2~3개월)는 지연이 아니다.
        # 현재 프로덕션 상태: 오늘 2026-08, 최신 2026-05 → 3개월(정상, 임계 3 이하).
        (date(2026, 8, 10), date(2026, 5, 1), 3),
        # 임계(3)를 초과하는 4개월 → 진짜 지연.
        (date(2026, 8, 10), date(2026, 4, 1), 4),
        # 연 경계: 오늘 2027-01, 최신 2026-10 → 3개월(정상).
        (date(2027, 1, 15), date(2026, 10, 1), 3),
        # 연 경계: 오늘 2027-01, 최신 2026-09 → 4개월(지연).
        (date(2027, 1, 15), date(2026, 9, 1), 4),
    ],
)
def test_real_estate_staleness_months_counts_calendar_months(
    today, latest_price_date, expected_months
):
    # 경과 일수가 아니라 달력 월 차이(연*12 + 월차)로 계산한다.
    assert (
        main_module._real_estate_staleness_months(latest_price_date, today)
        == expected_months
    )


def test_real_estate_staleness_months_returns_none_without_data():
    # 저장된 데이터가 없으면(None) 판정 불가로 None을 반환한다(backfill 안내 대상).
    assert (
        main_module._real_estate_staleness_months(None, date(2026, 8, 10)) is None
    )


def test_daily_real_estate_month_diff_3_is_normal(patched_runtime, monkeypatch):
    # 경계: 오늘과 최신 데이터월의 차이가 임계(3)와 같으면 정상 → 지연 알림 없이 종료.
    monkeypatch.setattr(main_module, "get_today_date", lambda: date(2026, 8, 10))
    monkeypatch.setattr(
        main_module, "load_config", lambda: build_fake_config(kosis_api_key="kosis-key")
    )
    monkeypatch.setattr(
        main_module, "fetch_active_stock_indicators", lambda client: []
    )
    monkeypatch.setattr(
        main_module, "fetch_active_real_estate_indicators",
        lambda client: [
            build_real_estate_indicator(
                "real_estate:seoul-small", "DT_KAB_11672_S19", "서울 소형"
            )
        ],
    )
    monkeypatch.setattr(
        main_module, "fetch_latest_exchange_rate_date", lambda client: date(2026, 8, 10)
    )
    monkeypatch.setattr(
        main_module, "fetch_real_estate_prices",
        lambda kosis_api_key, indicator_id, periods_count: [
            build_real_estate_price_row(indicator_id, date(2026, 5, 1))
        ],
    )
    # 최신 2026-05, 오늘 2026-08 → 3개월(정상).
    monkeypatch.setattr(
        main_module, "fetch_latest_price_date",
        lambda client, indicator_id: date(2026, 5, 1),
    )
    monkeypatch.setattr(main_module, "upsert_daily_prices", lambda client, rows: len(rows))

    # 정상이면 SystemExit 없이 종료해야 한다.
    main_module.run_daily(build_daily_arguments())


def test_daily_real_estate_month_diff_4_triggers_failure(
    patched_runtime, monkeypatch, tmp_path
):
    # 경계: 차이가 임계(3)를 초과하는 4개월이면 지연 알림.
    summary_file = tmp_path / "collect-failures.txt"
    monkeypatch.setenv("COLLECT_FAILURE_SUMMARY_FILE", str(summary_file))
    monkeypatch.setattr(main_module, "get_today_date", lambda: date(2026, 8, 10))
    monkeypatch.setattr(
        main_module, "load_config", lambda: build_fake_config(kosis_api_key="kosis-key")
    )
    monkeypatch.setattr(
        main_module, "fetch_active_stock_indicators", lambda client: []
    )
    monkeypatch.setattr(
        main_module, "fetch_active_real_estate_indicators",
        lambda client: [
            build_real_estate_indicator(
                "real_estate:seoul-small", "DT_KAB_11672_S19", "서울 소형"
            )
        ],
    )
    monkeypatch.setattr(
        main_module, "fetch_latest_exchange_rate_date", lambda client: date(2026, 8, 10)
    )
    monkeypatch.setattr(
        main_module, "fetch_real_estate_prices",
        lambda kosis_api_key, indicator_id, periods_count: [
            build_real_estate_price_row(indicator_id, date(2026, 4, 1))
        ],
    )
    # 최신 2026-04, 오늘 2026-08 → 4개월(지연).
    monkeypatch.setattr(
        main_module, "fetch_latest_price_date",
        lambda client, indicator_id: date(2026, 4, 1),
    )
    monkeypatch.setattr(main_module, "upsert_daily_prices", lambda client, rows: len(rows))

    with pytest.raises(SystemExit) as exit_info:
        main_module.run_daily(build_daily_arguments())

    assert exit_info.value.code == 1
    summary_content = summary_file.read_text(encoding="utf-8")
    assert "부동산 데이터 지연" in summary_content
    # 최신 데이터월과 경과 개월 수가 알림 본문에 드러나야 한다.
    assert "2026-04월분" in summary_content
    assert "4개월 경과" in summary_content


def test_backfill_without_kosis_key_skips_real_estate(patched_runtime, monkeypatch):
    monkeypatch.setattr(
        main_module, "load_config", lambda: build_fake_config(kosis_api_key=None)
    )
    monkeypatch.setattr(
        main_module, "fetch_active_stock_indicators", lambda client: []
    )
    monkeypatch.setattr(
        main_module, "fetch_active_real_estate_indicators",
        lambda client: pytest.fail("KOSIS 키가 없으면 부동산 지표 목록을 조회하면 안 된다"),
    )
    monkeypatch.setattr(
        main_module, "fetch_usd_krw_exchange_rates",
        lambda *args: [build_exchange_rate_row(date(2026, 1, 2))],
    )
    monkeypatch.setattr(
        main_module, "fetch_real_estate_prices",
        lambda *args, **kwargs: pytest.fail("KOSIS 키가 없으면 부동산을 수집하면 안 된다"),
    )
    monkeypatch.setattr(main_module, "upsert_exchange_rates", lambda client, rows: len(rows))

    main_module.run_backfill(build_backfill_arguments())


def test_backfill_with_kosis_key_appends_real_estate_after_stocks(
    patched_runtime, monkeypatch
):
    call_order: list[str] = []
    real_estate_periods: list[int] = []

    monkeypatch.setattr(
        main_module, "load_config", lambda: build_fake_config(kosis_api_key="kosis-key")
    )
    monkeypatch.setattr(
        main_module, "fetch_active_stock_indicators",
        lambda client: [build_stock_indicator("id-1", "005930", "삼성전자")],
    )
    monkeypatch.setattr(
        main_module, "fetch_active_real_estate_indicators",
        lambda client: [build_real_estate_indicator("re-1", "seoul-small", "서울 소형")],
    )
    monkeypatch.setattr(
        main_module, "fetch_usd_krw_exchange_rates",
        lambda *args: call_order.append("exchange") or [build_exchange_rate_row(date(2026, 1, 2))],
    )

    def fake_fetch_stock(kis_client, indicator_id, stock_code, start_date, end_date):
        call_order.append(f"stock:{stock_code}")
        return [build_stock_price_row(indicator_id, date(2026, 1, 2))]

    def fake_fetch_real_estate(kosis_api_key, indicator_id, periods_count):
        call_order.append(f"real_estate:{indicator_id}")
        real_estate_periods.append(periods_count)
        assert kosis_api_key == "kosis-key"
        return [build_real_estate_price_row(indicator_id, date(2006, 1, 1))]

    monkeypatch.setattr(main_module, "fetch_stock_daily_prices", fake_fetch_stock)
    monkeypatch.setattr(main_module, "fetch_real_estate_prices", fake_fetch_real_estate)
    # 부동산 soft-fail 경로가 신선도 판정을 위해 최신일을 조회한다. 신선한 날짜라 지연 알림은 없다.
    monkeypatch.setattr(
        main_module, "fetch_latest_price_date",
        lambda client, indicator_id: date(2026, 6, 1),
    )
    monkeypatch.setattr(main_module, "upsert_exchange_rates", lambda client, rows: len(rows))
    monkeypatch.setattr(main_module, "upsert_daily_prices", lambda client, rows: len(rows))

    main_module.run_backfill(build_backfill_arguments())

    # 환율 → 주식 → 부동산 순서. 부동산은 backfill 전량 개월 수로 조회한다.
    assert call_order == ["exchange", "stock:005930", "real_estate:re-1"]
    assert real_estate_periods == [main_module.REAL_ESTATE_BACKFILL_PERIODS]


def test_backfill_real_estate_filter_matches_indicator(patched_runtime, monkeypatch):
    monkeypatch.setattr(
        main_module, "load_config", lambda: build_fake_config(kosis_api_key="kosis-key")
    )
    monkeypatch.setattr(
        main_module, "fetch_active_stock_indicators",
        lambda client: pytest.fail("부동산 필터에서는 주식 목록을 조회하지 않아야 한다"),
    )
    # 실제 시드처럼 id 접미사(seoul-small)와 source_code(DT_KAB_11672_S19)가 다른 경우.
    # --indicator 는 전체 id 로 매칭되어야 한다.
    monkeypatch.setattr(
        main_module, "fetch_active_real_estate_indicators",
        lambda client: [
            build_real_estate_indicator(
                "real_estate:seoul-small", "DT_KAB_11672_S19", "서울 소형"
            )
        ],
    )

    collected_indicator_ids: list[str] = []

    def fake_fetch_real_estate(kosis_api_key, indicator_id, periods_count):
        collected_indicator_ids.append(indicator_id)
        return [build_real_estate_price_row(indicator_id, date(2006, 1, 1))]

    monkeypatch.setattr(main_module, "fetch_real_estate_prices", fake_fetch_real_estate)
    # 명시적 --indicator 부동산 필터 경로에서도 soft-fail 신선도 판정이 최신일을 조회한다.
    monkeypatch.setattr(
        main_module, "fetch_latest_price_date",
        lambda client, indicator_id: date(2026, 6, 1),
    )
    monkeypatch.setattr(main_module, "upsert_daily_prices", lambda client, rows: len(rows))

    main_module.run_backfill(
        build_backfill_arguments(indicator="real_estate:seoul-small")
    )

    assert collected_indicator_ids == ["real_estate:seoul-small"]


def test_daily_real_estate_recollects_recent_periods(patched_runtime, monkeypatch):
    real_estate_periods: list[int] = []

    monkeypatch.setattr(
        main_module, "load_config", lambda: build_fake_config(kosis_api_key="kosis-key")
    )
    monkeypatch.setattr(
        main_module, "fetch_active_stock_indicators", lambda client: []
    )
    monkeypatch.setattr(
        main_module, "fetch_active_real_estate_indicators",
        lambda client: [build_real_estate_indicator("re-1", "seoul-small", "서울 소형")],
    )
    monkeypatch.setattr(
        main_module, "fetch_latest_exchange_rate_date", lambda client: FIXED_TODAY
    )

    def fake_fetch_latest_price_date(client, indicator_id):
        # 부동산은 증분 시작일 계산엔 쓰지 않지만, soft-fail 신선도 판정엔 최신일을 조회한다.
        # 신선한 날짜를 돌려줘 지연 알림 없이 정상 종료하게 한다. 그 외 지표는 호출되면 안 된다.
        if indicator_id == "re-1":
            return date(2026, 6, 1)
        pytest.fail("부동산 외 지표에는 latest 조회가 일어나면 안 된다")

    monkeypatch.setattr(
        main_module, "fetch_latest_price_date", fake_fetch_latest_price_date
    )

    def fake_fetch_real_estate(kosis_api_key, indicator_id, periods_count):
        real_estate_periods.append(periods_count)
        return [build_real_estate_price_row(indicator_id, date(2026, 4, 1))]

    monkeypatch.setattr(main_module, "fetch_real_estate_prices", fake_fetch_real_estate)
    monkeypatch.setattr(
        main_module, "fetch_usd_krw_exchange_rates",
        lambda *args: pytest.fail("환율은 이미 최신이라 수집하지 않아야 한다"),
    )
    monkeypatch.setattr(main_module, "upsert_daily_prices", lambda client, rows: len(rows))

    # 부동산 수집 성공 + 데이터 신선 → soft-fail 정상 종료(SystemExit 없음).
    main_module.run_daily(build_daily_arguments())

    # 부동산은 최신 여부와 무관하게 항상 최근 개월 수로 재수집한다.
    assert real_estate_periods == [main_module.REAL_ESTATE_DAILY_PERIODS]


def test_daily_real_estate_fetch_failure_is_soft_fail_when_data_fresh(
    patched_runtime, monkeypatch
):
    monkeypatch.setattr(
        main_module, "load_config", lambda: build_fake_config(kosis_api_key="kosis-key")
    )
    monkeypatch.setattr(
        main_module, "fetch_active_stock_indicators", lambda client: []
    )
    monkeypatch.setattr(
        main_module, "fetch_active_real_estate_indicators",
        lambda client: [
            build_real_estate_indicator(
                "real_estate:seoul-small", "DT_KAB_11672_S19", "서울 소형"
            )
        ],
    )
    # 환율은 이미 최신이라 수집을 건너뛴다.
    monkeypatch.setattr(
        main_module, "fetch_latest_exchange_rate_date", lambda client: FIXED_TODAY
    )

    def failing_real_estate(kosis_api_key, indicator_id, periods_count):
        raise RuntimeError("KOSIS 요청 실패: ConnectTimeout")

    monkeypatch.setattr(main_module, "fetch_real_estate_prices", failing_real_estate)
    # 수집은 실패했지만 DB 최신일은 today에 가까워(신선) 지연 알림 대상이 아니다.
    monkeypatch.setattr(
        main_module, "fetch_latest_price_date",
        lambda client, indicator_id: date(2026, 6, 1),
    )
    monkeypatch.setattr(main_module, "upsert_daily_prices", lambda client, rows: len(rows))

    # 부동산 수집 실패는 soft-fail이므로 데이터가 신선하면 SystemExit 없이 정상 종료한다.
    main_module.run_daily(build_daily_arguments())


def test_daily_real_estate_stale_data_triggers_failure(
    patched_runtime, monkeypatch, tmp_path
):
    summary_file = tmp_path / "collect-failures.txt"
    monkeypatch.setenv("COLLECT_FAILURE_SUMMARY_FILE", str(summary_file))
    monkeypatch.setattr(
        main_module, "load_config", lambda: build_fake_config(kosis_api_key="kosis-key")
    )
    monkeypatch.setattr(
        main_module, "fetch_active_stock_indicators", lambda client: []
    )
    monkeypatch.setattr(
        main_module, "fetch_active_real_estate_indicators",
        lambda client: [
            build_real_estate_indicator(
                "real_estate:seoul-small", "DT_KAB_11672_S19", "서울 소형"
            )
        ],
    )
    monkeypatch.setattr(
        main_module, "fetch_latest_exchange_rate_date", lambda client: FIXED_TODAY
    )
    # 부동산 수집 자체는 성공하지만 DB 최신일(2026-01)이 오늘(2026-07) 기준 6개월 경과로
    # 임계 3개월을 초과해 오래됐다(공표주기 익익월 기준 정상 순환 범위인 2~3개월을 벗어남).
    monkeypatch.setattr(
        main_module, "fetch_real_estate_prices",
        lambda kosis_api_key, indicator_id, periods_count: [
            build_real_estate_price_row(indicator_id, date(2026, 1, 1))
        ],
    )
    monkeypatch.setattr(
        main_module, "fetch_latest_price_date",
        lambda client, indicator_id: date(2026, 1, 1),
    )
    monkeypatch.setattr(main_module, "upsert_daily_prices", lambda client, rows: len(rows))

    with pytest.raises(SystemExit) as exit_info:
        main_module.run_daily(build_daily_arguments())

    assert exit_info.value.code == 1
    assert summary_file.exists()
    summary_content = summary_file.read_text(encoding="utf-8")
    assert "real_estate:seoul-small" in summary_content
    assert "부동산 데이터 지연" in summary_content


def test_daily_stale_alert_appends_collection_success(
    patched_runtime, monkeypatch, tmp_path
):
    # 지연 + 당일 수집 성공 경로: 알림에 수집 성공과 소스 최신 발표분 월이 부기돼야 한다.
    summary_file = tmp_path / "collect-failures.txt"
    monkeypatch.setenv("COLLECT_FAILURE_SUMMARY_FILE", str(summary_file))
    monkeypatch.setattr(
        main_module, "load_config", lambda: build_fake_config(kosis_api_key="kosis-key")
    )
    monkeypatch.setattr(
        main_module, "fetch_active_stock_indicators", lambda client: []
    )
    monkeypatch.setattr(
        main_module, "fetch_active_real_estate_indicators",
        lambda client: [
            build_real_estate_indicator(
                "real_estate:seoul-small", "DT_KAB_11672_S19", "서울 소형"
            )
        ],
    )
    monkeypatch.setattr(
        main_module, "fetch_latest_exchange_rate_date", lambda client: FIXED_TODAY
    )
    # 수집은 성공하고 소스가 2026-04월분까지 내려주지만, DB 최신일(2026-01)은 오늘(2026-07)
    # 기준 6개월 경과라 지연이다. 즉 소스 발표 자체가 밀린 상황(대기 대상).
    monkeypatch.setattr(
        main_module, "fetch_real_estate_prices",
        lambda kosis_api_key, indicator_id, periods_count: [
            build_real_estate_price_row(indicator_id, date(2026, 4, 1))
        ],
    )
    monkeypatch.setattr(
        main_module, "fetch_latest_price_date",
        lambda client, indicator_id: date(2026, 1, 1),
    )
    monkeypatch.setattr(main_module, "upsert_daily_prices", lambda client, rows: len(rows))

    with pytest.raises(SystemExit) as exit_info:
        main_module.run_daily(build_daily_arguments())

    assert exit_info.value.code == 1
    summary_content = summary_file.read_text(encoding="utf-8")
    assert "부동산 데이터 지연" in summary_content
    assert "수집 성공" in summary_content
    # 소스 최신 발표분(마지막 수집 행의 월)이 부기돼야 한다.
    assert "2026-04월" in summary_content


def test_daily_stale_alert_appends_collection_failure_cause(
    patched_runtime, monkeypatch, tmp_path
):
    # 지연 + 당일 수집 실패 경로: 알림에 수집 실패와 원인이 부기돼야 한다.
    # RealEstateFetchError는 메시지에 시크릿이 없으므로 원문 그대로 부기한다.
    summary_file = tmp_path / "collect-failures.txt"
    monkeypatch.setenv("COLLECT_FAILURE_SUMMARY_FILE", str(summary_file))
    monkeypatch.setattr(
        main_module, "load_config", lambda: build_fake_config(kosis_api_key="kosis-key")
    )
    monkeypatch.setattr(
        main_module, "fetch_active_stock_indicators", lambda client: []
    )
    monkeypatch.setattr(
        main_module, "fetch_active_real_estate_indicators",
        lambda client: [
            build_real_estate_indicator(
                "real_estate:seoul-small", "DT_KAB_11672_S19", "서울 소형"
            )
        ],
    )
    monkeypatch.setattr(
        main_module, "fetch_latest_exchange_rate_date", lambda client: FIXED_TODAY
    )

    def failing_real_estate(kosis_api_key, indicator_id, periods_count):
        raise RealEstateFetchError("KOSIS HTTP 500 오류")

    monkeypatch.setattr(main_module, "fetch_real_estate_prices", failing_real_estate)
    # DB 최신일(2026-01)이 오늘(2026-07) 기준 6개월 경과라 지연. 수집까지 실패했으므로
    # 소스 발표 지연이 아니라 수집 문제(조치 필요)일 수 있다.
    monkeypatch.setattr(
        main_module, "fetch_latest_price_date",
        lambda client, indicator_id: date(2026, 1, 1),
    )
    monkeypatch.setattr(main_module, "upsert_daily_prices", lambda client, rows: len(rows))

    with pytest.raises(SystemExit) as exit_info:
        main_module.run_daily(build_daily_arguments())

    assert exit_info.value.code == 1
    summary_content = summary_file.read_text(encoding="utf-8")
    assert "부동산 데이터 지연" in summary_content
    assert "수집 실패" in summary_content
    assert "KOSIS HTTP 500 오류" in summary_content


def test_daily_stale_alert_masks_non_fetch_error_cause(
    patched_runtime, monkeypatch, tmp_path
):
    # 지연 + RealEstateFetchError가 아닌 예외: 시크릿 유출 방지를 위해 타입명만 부기한다.
    summary_file = tmp_path / "collect-failures.txt"
    monkeypatch.setenv("COLLECT_FAILURE_SUMMARY_FILE", str(summary_file))
    monkeypatch.setattr(
        main_module, "load_config", lambda: build_fake_config(kosis_api_key="kosis-key")
    )
    monkeypatch.setattr(
        main_module, "fetch_active_stock_indicators", lambda client: []
    )
    monkeypatch.setattr(
        main_module, "fetch_active_real_estate_indicators",
        lambda client: [
            build_real_estate_indicator(
                "real_estate:seoul-small", "DT_KAB_11672_S19", "서울 소형"
            )
        ],
    )
    monkeypatch.setattr(
        main_module, "fetch_latest_exchange_rate_date", lambda client: FIXED_TODAY
    )

    secret_bearing_message = "apiKey=super-secret-value 로 요청 실패"

    def failing_real_estate(kosis_api_key, indicator_id, periods_count):
        raise ValueError(secret_bearing_message)

    monkeypatch.setattr(main_module, "fetch_real_estate_prices", failing_real_estate)
    monkeypatch.setattr(
        main_module, "fetch_latest_price_date",
        lambda client, indicator_id: date(2026, 1, 1),
    )
    monkeypatch.setattr(main_module, "upsert_daily_prices", lambda client, rows: len(rows))

    with pytest.raises(SystemExit) as exit_info:
        main_module.run_daily(build_daily_arguments())

    assert exit_info.value.code == 1
    summary_content = summary_file.read_text(encoding="utf-8")
    assert "수집 실패" in summary_content
    # 타입명만 남고 메시지 본문(시크릿 포함)은 새지 않아야 한다.
    assert "ValueError" in summary_content
    assert secret_bearing_message not in summary_content


def test_daily_skip_real_estate_excludes_real_estate(patched_runtime, monkeypatch):
    monkeypatch.setattr(
        main_module, "load_config", lambda: build_fake_config(kosis_api_key="kosis-key")
    )
    monkeypatch.setattr(
        main_module, "fetch_active_stock_indicators", lambda client: []
    )
    # --skip-real-estate 지정 시 KOSIS 키가 있어도 부동산 목록/수집이 일어나면 안 된다.
    monkeypatch.setattr(
        main_module, "fetch_active_real_estate_indicators",
        lambda client: pytest.fail(
            "--skip-real-estate 지정 시 부동산 지표 목록을 조회하면 안 된다"
        ),
    )
    monkeypatch.setattr(
        main_module, "fetch_real_estate_prices",
        lambda *args, **kwargs: pytest.fail(
            "--skip-real-estate 지정 시 부동산을 수집하면 안 된다"
        ),
    )
    monkeypatch.setattr(
        main_module, "fetch_latest_exchange_rate_date", lambda client: FIXED_TODAY
    )

    main_module.run_daily(build_daily_arguments(skip_real_estate=True))


def test_daily_failure_writes_summary_file(patched_runtime, monkeypatch, tmp_path):
    summary_file = tmp_path / "collect-failures.txt"
    monkeypatch.setenv("COLLECT_FAILURE_SUMMARY_FILE", str(summary_file))
    monkeypatch.setattr(
        main_module, "load_config", lambda: build_fake_config(kosis_api_key="kosis-key")
    )
    monkeypatch.setattr(
        main_module, "fetch_active_stock_indicators", lambda client: []
    )
    monkeypatch.setattr(
        main_module, "fetch_active_real_estate_indicators",
        lambda client: [
            build_real_estate_indicator(
                "real_estate:seoul-small", "DT_KAB_11672_S19", "서울 소형"
            )
        ],
    )
    # 환율은 이미 최신이라 수집을 건너뛰고, 부동산은 수집 실패 + 데이터도 임계 초과로 밀려 exit 1.
    monkeypatch.setattr(
        main_module, "fetch_latest_exchange_rate_date", lambda client: FIXED_TODAY
    )

    def failing_real_estate(kosis_api_key, indicator_id, periods_count):
        raise RuntimeError("KOSIS 요청 실패: ConnectTimeout")

    monkeypatch.setattr(main_module, "fetch_real_estate_prices", failing_real_estate)
    # 부동산 수집이 실패했고 DB 최신일(2026-01)도 오늘(2026-07) 기준 6개월 경과로 임계 3개월
    # 초과라 오래됐다 → 지연 알림.
    monkeypatch.setattr(
        main_module, "fetch_latest_price_date",
        lambda client, indicator_id: date(2026, 1, 1),
    )
    monkeypatch.setattr(main_module, "upsert_daily_prices", lambda client, rows: len(rows))

    with pytest.raises(SystemExit) as exit_info:
        main_module.run_daily(build_daily_arguments())

    assert exit_info.value.code == 1
    assert summary_file.exists()
    summary_content = summary_file.read_text(encoding="utf-8")
    assert "real_estate:seoul-small" in summary_content
    assert "부동산 데이터 지연" in summary_content


def test_daily_failure_without_summary_env_skips_file(
    patched_runtime, monkeypatch, tmp_path
):
    monkeypatch.delenv("COLLECT_FAILURE_SUMMARY_FILE", raising=False)
    monkeypatch.setattr(
        main_module, "load_config", lambda: build_fake_config(kosis_api_key="kosis-key")
    )
    monkeypatch.setattr(
        main_module, "fetch_active_stock_indicators", lambda client: []
    )
    monkeypatch.setattr(
        main_module, "fetch_active_real_estate_indicators",
        lambda client: [
            build_real_estate_indicator(
                "real_estate:seoul-small", "DT_KAB_11672_S19", "서울 소형"
            )
        ],
    )
    monkeypatch.setattr(
        main_module, "fetch_latest_exchange_rate_date", lambda client: FIXED_TODAY
    )

    def failing_real_estate(kosis_api_key, indicator_id, periods_count):
        raise RuntimeError("KOSIS 요청 실패: ConnectTimeout")

    monkeypatch.setattr(main_module, "fetch_real_estate_prices", failing_real_estate)
    # 부동산 수집 실패 + 데이터도 임계 초과로 밀려 exit 1 상황(요약 파일 경로만 미설정).
    monkeypatch.setattr(
        main_module, "fetch_latest_price_date",
        lambda client, indicator_id: date(2026, 1, 1),
    )
    monkeypatch.setattr(main_module, "upsert_daily_prices", lambda client, rows: len(rows))

    with pytest.raises(SystemExit) as exit_info:
        main_module.run_daily(build_daily_arguments())

    # 환경변수 미설정 시 요약 파일을 만들지 않고 여전히 exit 1로 끝난다.
    assert exit_info.value.code == 1
    assert list(tmp_path.iterdir()) == []


def test_exchange_kis_failure_falls_back_to_ecos(patched_runtime, monkeypatch):
    ecos_calls: list[tuple] = []
    upserted_rows: list[list] = []

    monkeypatch.setattr(
        main_module, "load_config",
        lambda: build_fake_config(ecos_api_key="ecos-key"),
    )

    def fake_fetch_kis(kis_client, start_date, end_date):
        raise KisQuotationError("KIS 환율 일시 실패")

    def fake_fetch_ecos(ecos_api_key, start_date, end_date):
        ecos_calls.append((ecos_api_key, start_date, end_date))
        return [build_exchange_rate_row(date(2026, 1, 2))]

    monkeypatch.setattr(main_module, "fetch_usd_krw_exchange_rates", fake_fetch_kis)
    monkeypatch.setattr(
        main_module, "fetch_usd_krw_exchange_rates_ecos", fake_fetch_ecos
    )
    monkeypatch.setattr(
        main_module, "upsert_exchange_rates",
        lambda client, rows: upserted_rows.append(rows) or len(rows),
    )

    # KIS 실패 + ECOS 키 있음 → 폴백 성공이므로 SystemExit 없이 정상 종료해야 한다.
    main_module.run_backfill(
        build_backfill_arguments(indicator="exchange_rate:USD_KRW")
    )

    assert ecos_calls == [("ecos-key", date(2026, 1, 1), FIXED_TODAY)]
    # 폴백이 반환한 행이 그대로 upsert 되어야 한다.
    assert len(upserted_rows) == 1
    assert upserted_rows[0] == [build_exchange_rate_row(date(2026, 1, 2))]


def test_exchange_kis_failure_without_ecos_key_exits_1(patched_runtime, monkeypatch):
    monkeypatch.setattr(
        main_module, "load_config",
        lambda: build_fake_config(ecos_api_key=None),
    )

    def fake_fetch_kis(kis_client, start_date, end_date):
        raise KisQuotationError("KIS 환율 일시 실패")

    monkeypatch.setattr(main_module, "fetch_usd_krw_exchange_rates", fake_fetch_kis)
    monkeypatch.setattr(
        main_module, "fetch_usd_krw_exchange_rates_ecos",
        lambda *args, **kwargs: pytest.fail("ECOS 키가 없으면 폴백을 호출하면 안 된다"),
    )
    monkeypatch.setattr(main_module, "upsert_exchange_rates", lambda client, rows: len(rows))

    # 키가 없으면 에러가 전파되어 per-task 실패로 처리 → exit 1.
    with pytest.raises(SystemExit) as exit_info:
        main_module.run_backfill(
            build_backfill_arguments(indicator="exchange_rate:USD_KRW")
        )

    assert exit_info.value.code == 1


def test_exchange_kis_success_skips_ecos(patched_runtime, monkeypatch):
    monkeypatch.setattr(
        main_module, "load_config",
        lambda: build_fake_config(ecos_api_key="ecos-key"),
    )
    monkeypatch.setattr(
        main_module, "fetch_usd_krw_exchange_rates",
        lambda *args: [build_exchange_rate_row(date(2026, 1, 2))],
    )
    monkeypatch.setattr(
        main_module, "fetch_usd_krw_exchange_rates_ecos",
        lambda *args, **kwargs: pytest.fail("KIS 성공 시 ECOS를 호출하면 안 된다"),
    )
    monkeypatch.setattr(main_module, "upsert_exchange_rates", lambda client, rows: len(rows))

    main_module.run_backfill(
        build_backfill_arguments(indicator="exchange_rate:USD_KRW")
    )


def test_invalid_from_date_exits_with_code_1(patched_runtime, monkeypatch):
    monkeypatch.setattr(
        main_module, "fetch_active_stock_indicators",
        lambda client: pytest.fail("날짜 파싱 실패 시 그 뒤 단계로 진행하면 안 된다"),
    )

    with pytest.raises(SystemExit) as exit_info:
        main_module.run_backfill(build_backfill_arguments(start_date="2026-13-40"))

    assert exit_info.value.code == 1
