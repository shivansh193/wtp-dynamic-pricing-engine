"""
Step 2 - Indian festival calendar 2022-2026 as a features CSV.

Reads the authored FESTIVALS table in config.py (principal shopping date +
intensity 1-3 + pre/post shopping window) and expands it to a *daily* feature
table so the synthetic generator and the API can answer "is this date in a
festival period, and how intense?" with a single lookup.

Output: data/raw/festival_calendar.csv
Columns: date, is_festival_period, festival_name, intensity_score,
         days_to_peak (negative = before peak), phase (pre/peak/post)
"""

from __future__ import annotations

from datetime import date, timedelta

import config as C
from _util import log, require_pandas, write_source_sidecar

OUT = C.RAW_DIR / "festival_calendar.csv"
FEATURES_OUT = C.PROCESSED_DIR / "festival_features.csv"


def main() -> None:
    pd = require_pandas()
    log("Building Indian festival calendar 2022-2026...")

    # daily frame across the whole modelling window
    start = date(C.START_YEAR, 1, 1)
    end = date(C.END_YEAR, 12, 31)
    days = pd.date_range(start, end, freq="D")
    frame = pd.DataFrame({"date": days})
    frame["is_festival_period"] = False
    frame["festival_name"] = ""
    frame["intensity_score"] = 0
    frame["days_to_peak"] = 0
    frame["phase"] = "none"

    idx = {d.date(): i for i, d in enumerate(frame["date"])}

    # also keep a compact "one row per festival" calendar
    compact_rows = []

    for name, dstr, intensity, pre, post in C.FESTIVALS:
        peak = date.fromisoformat(dstr)
        compact_rows.append(
            {"festival_name": name, "peak_date": dstr, "intensity_score": intensity,
             "pre_window_days": pre, "post_window_days": post}
        )
        for offset in range(-pre, post + 1):
            d = peak + timedelta(days=offset)
            if d not in idx:
                continue
            i = idx[d]
            # if two festivals overlap, keep the higher-intensity one
            if intensity < frame.at[i, "intensity_score"]:
                continue
            frame.at[i, "is_festival_period"] = True
            frame.at[i, "festival_name"] = name
            frame.at[i, "intensity_score"] = intensity
            frame.at[i, "days_to_peak"] = offset
            frame.at[i, "phase"] = "peak" if offset == 0 else ("pre" if offset < 0 else "post")

    frame["date"] = frame["date"].dt.strftime("%Y-%m-%d")
    frame.to_csv(FEATURES_OUT, index=False)
    log(f"  wrote {FEATURES_OUT}  ({int(frame.is_festival_period.sum())} festival-days)")

    compact = pd.DataFrame(compact_rows)
    compact.to_csv(OUT, index=False)
    log(f"  wrote {OUT}  ({len(compact)} festivals)")

    write_source_sidecar(
        OUT,
        source="Authored from public Indian festival dates (Diwali/Holi/Eid/"
        "Christmas/Rakhi/Independence Day + FY-end March + back-to-school June)",
        live=False,
        note="intensity_score: 3=Diwali-class, 2=Eid/Christmas/FY-end, 1=minor",
    )


if __name__ == "__main__":
    main()
