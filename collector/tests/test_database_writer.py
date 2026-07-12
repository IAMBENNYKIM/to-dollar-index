from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from collector.database_writer import (
    UPSERT_BATCH_SIZE,
    fetch_latest_exchange_rate_date,
    fetch_latest_price_date,
    upsert_daily_prices,
    upsert_exchange_rates,
)


class FakeResponse:
    def __init__(self, data: list[dict]) -> None:
        self.data = data


class FakeUpsertCall:
    def __init__(self, table_name: str, rows: list[dict], on_conflict: str) -> None:
        self.table_name = table_name
        self.rows = rows
        self.on_conflict = on_conflict


class FakeQuery:
    def __init__(self, client: FakeClient, table_name: str) -> None:
        self._client = client
        self._table_name = table_name
        self._response_data: list[dict] = []

    def select(self, *columns: str) -> FakeQuery:
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        return self

    def order(self, column: str, desc: bool = False) -> FakeQuery:
        return self

    def limit(self, size: int) -> FakeQuery:
        return self

    def upsert(self, rows: list[dict], on_conflict: str = "") -> FakeQuery:
        self._client.upsert_calls.append(
            FakeUpsertCall(self._table_name, rows, on_conflict)
        )
        # 실제 Supabase는 upsert된 행 표현을 그대로 돌려준다.
        self._response_data = list(rows)
        return self

    def execute(self) -> FakeResponse:
        return FakeResponse(self._response_data)


class FakeClient:
    def __init__(self, select_response_data: list[dict] | None = None) -> None:
        self._select_response_data = select_response_data or []
        self.upsert_calls: list[FakeUpsertCall] = []

    def table(self, table_name: str) -> FakeQuery:
        query = FakeQuery(self, table_name)
        query._response_data = self._select_response_data
        return query


def test_upsert_daily_prices_uses_table_conflict_and_serialized_dates() -> None:
    client = FakeClient()
    price_rows = [
        {
            "indicator_id": "stock:005930",
            "price_date": date(2026, 7, 10),
            "close_price": 80000,
        }
    ]

    inserted_count = upsert_daily_prices(client, price_rows)

    assert inserted_count == 1
    assert len(client.upsert_calls) == 1
    call = client.upsert_calls[0]
    assert call.table_name == "daily_prices"
    assert call.on_conflict == "indicator_id,price_date"
    assert call.rows[0]["price_date"] == "2026-07-10"
    assert isinstance(call.rows[0]["price_date"], str)


def test_upsert_exchange_rates_uses_table_and_conflict() -> None:
    client = FakeClient()
    rate_rows = [
        {"currency_pair": "USD_KRW", "rate_date": date(2026, 7, 10), "close_rate": 1350}
    ]

    inserted_count = upsert_exchange_rates(client, rate_rows)

    assert inserted_count == 1
    call = client.upsert_calls[0]
    assert call.table_name == "exchange_rates"
    assert call.on_conflict == "currency_pair,rate_date"
    assert call.rows[0]["rate_date"] == "2026-07-10"


def test_upsert_daily_prices_splits_into_batches() -> None:
    client = FakeClient()
    row_count = UPSERT_BATCH_SIZE * 2 + 1
    price_rows = [
        {
            "indicator_id": "stock:005930",
            "price_date": date(2026, 1, 1),
            "close_price": index,
        }
        for index in range(row_count)
    ]

    inserted_count = upsert_daily_prices(client, price_rows)

    assert inserted_count == row_count
    batch_sizes = [len(call.rows) for call in client.upsert_calls]
    assert batch_sizes == [UPSERT_BATCH_SIZE, UPSERT_BATCH_SIZE, 1]


def test_upsert_daily_prices_empty_returns_zero_without_call() -> None:
    client = FakeClient()

    inserted_count = upsert_daily_prices(client, [])

    assert inserted_count == 0
    assert client.upsert_calls == []


def test_upsert_exchange_rates_empty_returns_zero_without_call() -> None:
    client = FakeClient()

    inserted_count = upsert_exchange_rates(client, [])

    assert inserted_count == 0
    assert client.upsert_calls == []


def test_fetch_latest_price_date_parses_date_when_present() -> None:
    client = FakeClient(select_response_data=[{"price_date": "2026-07-10"}])

    latest_date = fetch_latest_price_date(client, "stock:005930")

    assert latest_date == date(2026, 7, 10)


def test_fetch_latest_price_date_returns_none_when_empty() -> None:
    client = FakeClient(select_response_data=[])

    latest_date = fetch_latest_price_date(client, "stock:005930")

    assert latest_date is None


def test_fetch_latest_exchange_rate_date_parses_date_when_present() -> None:
    client = FakeClient(select_response_data=[{"rate_date": "2026-07-10"}])

    latest_date = fetch_latest_exchange_rate_date(client)

    assert latest_date == date(2026, 7, 10)


def test_fetch_latest_exchange_rate_date_returns_none_when_empty() -> None:
    client = FakeClient(select_response_data=[])

    latest_date = fetch_latest_exchange_rate_date(client)

    assert latest_date is None
