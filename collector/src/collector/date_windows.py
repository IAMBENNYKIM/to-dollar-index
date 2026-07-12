from __future__ import annotations

from datetime import date, timedelta


def split_date_range(
    start_date: date,
    end_date: date,
    window_days: int = 120,
) -> list[tuple[date, date]]:
    # KIS 기간별시세 API는 1회 최대 100건(거래일)을 반환하므로, 긴 백필 구간을
    # window_days 캘린더일 이하의 연속·비중첩 구간으로 나눠 순차 호출한다.
    if window_days < 1:
        raise ValueError(f"window_days는 1 이상이어야 합니다: {window_days}")
    if start_date > end_date:
        raise ValueError(
            f"start_date({start_date})가 end_date({end_date})보다 늦습니다."
        )

    date_windows: list[tuple[date, date]] = []
    window_start_date = start_date
    while window_start_date <= end_date:
        window_end_candidate = window_start_date + timedelta(days=window_days - 1)
        window_end_date = min(window_end_candidate, end_date)
        date_windows.append((window_start_date, window_end_date))
        window_start_date = window_end_date + timedelta(days=1)

    return date_windows
