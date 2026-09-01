"""
Major Indian festival / fiscal anchor dates used by the oracle for
fingerprint response curves, chart markers, and anomaly explanations.

Dates are approximate (Diwali / Holi / Eid drift with the lunar calendar);
good enough for a synthetic demo. Years outside the table reuse the nearest
known month/day.
"""

from __future__ import annotations

from datetime import date, timedelta

_DIWALI = {2022: (10, 24), 2023: (11, 12), 2024: (11, 1),
           2025: (10, 21), 2026: (11, 8), 2027: (10, 29)}
_HOLI = {2022: (3, 18), 2023: (3, 8), 2024: (3, 25),
         2025: (3, 14), 2026: (3, 4), 2027: (3, 22)}
_EID_FITR = {2022: (5, 3), 2023: (4, 22), 2024: (4, 10),
             2025: (3, 31), 2026: (3, 20), 2027: (3, 10)}


def _lookup(table: dict[int, tuple[int, int]], year: int) -> date:
    if year in table:
        mm, dd = table[year]
    else:  # nearest known year
        nearest = min(table, key=lambda y: abs(y - year))
        mm, dd = table[nearest]
    return date(year, mm, dd)


def major_festivals(year: int) -> list[tuple[str, date]]:
    """Named anchor dates for a calendar year, sorted."""
    out = [
        ("Diwali", _lookup(_DIWALI, year)),
        ("Holi", _lookup(_HOLI, year)),
        ("Eid", _lookup(_EID_FITR, year)),
        ("Christmas", date(year, 12, 25)),
        ("FY-end", date(year, 3, 31)),
    ]
    return sorted(out, key=lambda t: t[1])


# the four the fingerprint response-curve chart plots
FINGERPRINT_FESTIVALS = ("Diwali", "Holi", "Eid", "Christmas")


def upcoming_festivals(start: date, end: date) -> list[dict]:
    """Festivals whose date falls in [start, end], across the spanned years."""
    out: list[dict] = []
    for yr in range(start.year, end.year + 1):
        for name, d in major_festivals(yr):
            if start <= d <= end:
                out.append({"name": name, "date": d.isoformat(),
                            "days_out": (d - start).days})
    return sorted(out, key=lambda r: r["date"])


def nearest_festival(d: date, window_days: int = 12) -> str | None:
    """Name of a festival within +/- window_days of `d`, else None."""
    for yr in (d.year - 1, d.year, d.year + 1):
        for name, fd in major_festivals(yr):
            if abs((d - fd).days) <= window_days:
                return name
    return None


def festival_window_dates(name: str, year: int, weeks_each_side: int = 2
                          ) -> tuple[date, date, date]:
    """(anchor, window_start, window_end) for the +/- N week band."""
    table = {"Diwali": _DIWALI, "Holi": _HOLI, "Eid": _EID_FITR}
    if name == "Christmas":
        anchor = date(year, 12, 25)
    elif name in table:
        anchor = _lookup(table[name], year)
    else:
        anchor = date(year, 3, 31)
    return (anchor, anchor - timedelta(weeks=weeks_each_side),
            anchor + timedelta(weeks=weeks_each_side))
