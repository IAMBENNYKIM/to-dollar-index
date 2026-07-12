from __future__ import annotations

from datetime import date, timedelta

import pytest

from collector.date_windows import split_date_range


def test_exact_window_length_yields_single_window() -> None:
    start_date = date(2024, 1, 1)
    window_days = 120
    end_date = start_date + timedelta(days=window_days - 1)

    date_windows = split_date_range(start_date, end_date, window_days=window_days)

    assert date_windows == [(start_date, end_date)]


def test_window_length_plus_one_yields_two_adjacent_windows() -> None:
    start_date = date(2024, 1, 1)
    window_days = 120
    end_date = start_date + timedelta(days=window_days)  # window_days + 1일 길이

    date_windows = split_date_range(start_date, end_date, window_days=window_days)

    assert len(date_windows) == 2
    first_window_start, first_window_end = date_windows[0]
    second_window_start, second_window_end = date_windows[1]

    assert first_window_start == start_date
    assert second_window_end == end_date
    # 경계 인접성: 겹침·공백 없이 이어진다.
    assert second_window_start == first_window_end + timedelta(days=1)
    # 첫 구간은 정확히 window_days 길이, 둘째 구간은 하루.
    assert (first_window_end - first_window_start).days + 1 == window_days
    assert second_window_start == second_window_end


def test_multiple_windows_cover_range_without_gaps_or_overlaps() -> None:
    start_date = date(2020, 3, 15)
    end_date = date(2024, 11, 30)
    window_days = 120

    date_windows = split_date_range(start_date, end_date, window_days=window_days)

    # 전체 커버리지: 첫 시작=start, 끝=end.
    assert date_windows[0][0] == start_date
    assert date_windows[-1][1] == end_date

    for window_start, window_end in date_windows:
        # 각 구간은 유효하고(시작<=종료) 길이가 window_days 이하.
        assert window_start <= window_end
        assert (window_end - window_start).days + 1 <= window_days

    # 인접 구간 사이에 겹침·공백이 없다.
    for previous_window, next_window in zip(date_windows, date_windows[1:]):
        assert next_window[0] == previous_window[1] + timedelta(days=1)


def test_single_day_range_yields_single_window() -> None:
    single_day = date(2024, 6, 10)

    date_windows = split_date_range(single_day, single_day)

    assert date_windows == [(single_day, single_day)]


def test_reversed_range_raises_value_error_with_both_dates() -> None:
    start_date = date(2024, 6, 10)
    end_date = date(2024, 6, 1)

    with pytest.raises(ValueError) as error_info:
        split_date_range(start_date, end_date)

    error_message = str(error_info.value)
    assert str(start_date) in error_message
    assert str(end_date) in error_message


def test_zero_window_days_raises_value_error() -> None:
    with pytest.raises(ValueError):
        split_date_range(date(2024, 1, 1), date(2024, 12, 31), window_days=0)
