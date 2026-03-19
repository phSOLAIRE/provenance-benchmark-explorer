from datetime import datetime, timezone

NS_PER_SEC = 1_000_000_000

def ns_timestamp_to_datetime(ts: int, tz: timezone = timezone.utc) -> datetime:
    return datetime.fromtimestamp(ts / NS_PER_SEC, tz=tz)

def ns_timestamp_to_date_string(ts: int, tz: timezone = timezone.utc) -> str:
    return ns_timestamp_to_datetime(ts, tz=tz).strftime('%Y-%m-%d %H:%M:%S')

def date_string_to_ns_timestamp(date_string: str, tz: timezone = timezone.utc) -> int:
    dt = datetime.strptime(date_string, '%Y-%m-%d %H:%M:%S').replace(tzinfo=tz)
    return int(dt.timestamp() * NS_PER_SEC)

def date_string_to_datetime(date_string: str, tz: timezone = timezone.utc) -> datetime:
    """E.g. '2018-04-02 23:00:00' """
    return datetime.strptime(date_string, '%Y-%m-%d %H:%M:%S').replace(tzinfo=tz)

def datetime_to_ns_timestamp(dt: datetime, tz: timezone = timezone.utc) -> int:
    if dt.tzinfo is None:
        raise ValueError("datetime must be timezone-aware UTC")
    return int(dt.astimezone(tz).timestamp() * NS_PER_SEC)

def get_time_interval_tuples_as_ns_timestamp(
    start_date: str,
    end_date: str,
    interval_seconds: int
) -> list[tuple[int, int]]:

    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be > 0")

    start_ns = date_string_to_ns_timestamp(start_date)
    end_ns = date_string_to_ns_timestamp(end_date)

    assert end_ns >= start_ns

    step_ns = interval_seconds * NS_PER_SEC

    intervals: list[tuple[int, int]] = []
    cur = start_ns

    while cur < end_ns:
        nxt = min(cur + step_ns, end_ns)
        intervals.append((cur, nxt))
        cur = nxt

    return intervals