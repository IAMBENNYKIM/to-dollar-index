from __future__ import annotations

from datetime import date

from supabase import Client, create_client

from collector.config import CollectorConfig

# Supabase 요청 크기 제한을 방어하기 위한 upsert 분할 단위.
UPSERT_BATCH_SIZE = 500


def create_supabase_client(config: CollectorConfig) -> Client:
    return create_client(config.supabase_url, config.supabase_service_role_key)


def fetch_active_stock_indicators(client: Client) -> list[dict]:
    response = (
        client.table("indicators")
        .select("id, source_code, display_name")
        .eq("indicator_type", "stock")
        .eq("is_active", True)
        .execute()
    )
    return list(response.data)


def fetch_latest_price_date(client: Client, indicator_id: str) -> date | None:
    response = (
        client.table("daily_prices")
        .select("price_date")
        .eq("indicator_id", indicator_id)
        .order("price_date", desc=True)
        .limit(1)
        .execute()
    )
    rows = response.data
    if not rows:
        return None
    return date.fromisoformat(rows[0]["price_date"])


def fetch_latest_exchange_rate_date(
    client: Client, currency_pair: str = "USD_KRW"
) -> date | None:
    response = (
        client.table("exchange_rates")
        .select("rate_date")
        .eq("currency_pair", currency_pair)
        .order("rate_date", desc=True)
        .limit(1)
        .execute()
    )
    rows = response.data
    if not rows:
        return None
    return date.fromisoformat(rows[0]["rate_date"])


def _serialize_date_values(rows: list[dict]) -> list[dict]:
    # date 객체는 JSON 직렬화가 안 되므로 ISO 문자열로 변환한다.
    serialized_rows: list[dict] = []
    for row in rows:
        serialized_row = {
            key: (value.isoformat() if isinstance(value, date) else value)
            for key, value in row.items()
        }
        serialized_rows.append(serialized_row)
    return serialized_rows


def _upsert_in_batches(
    client: Client, table_name: str, rows: list[dict], on_conflict: str
) -> int:
    inserted_count = 0
    for batch_start in range(0, len(rows), UPSERT_BATCH_SIZE):
        batch_rows = rows[batch_start : batch_start + UPSERT_BATCH_SIZE]
        response = (
            client.table(table_name)
            .upsert(batch_rows, on_conflict=on_conflict)
            .execute()
        )
        inserted_count += len(response.data)
    return inserted_count


def upsert_daily_prices(client: Client, price_rows: list[dict]) -> int:
    if not price_rows:
        return 0
    serialized_rows = _serialize_date_values(price_rows)
    return _upsert_in_batches(
        client, "daily_prices", serialized_rows, on_conflict="indicator_id,price_date"
    )


def upsert_exchange_rates(client: Client, rate_rows: list[dict]) -> int:
    if not rate_rows:
        return 0
    serialized_rows = _serialize_date_values(rate_rows)
    return _upsert_in_batches(
        client, "exchange_rates", serialized_rows, on_conflict="currency_pair,rate_date"
    )
