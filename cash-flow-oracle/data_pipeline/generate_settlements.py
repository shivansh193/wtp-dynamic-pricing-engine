"""
Synthetic merchant settlement generator (Track 04 scaffold).

5 archetypes x MERCHANTS_PER_ARCHETYPE merchants, HISTORY_YEARS of *daily*
net-settlement data, calibrated to Indian seasonality:

  * Diwali / Dussehra spikes           (config.FESTIVAL_DATES, tag="diwali")
  * wedding-season lift (Nov-Feb)      (tag="wedding")
  * monsoon dip (Jun-Sep)              (config.MONSOON_MONTHS)
  * March financial-year-end surge     (config.MARCH_FY_END)
  * June back-to-school bump           (config.JUNE_SCHOOL)
  * weekly pattern + lognormal daily noise + occasional "stress" shocks
    (chargeback wave / platform outage) so the HMM has a stress regime to find

Returns a list of settlement rows ready for db.bulk_insert_settlements():
    (merchant_id, date, gross_inr, refunds_inr, fees_inr, net_settled_inr, txn_count)
"""

from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np

from .. import config as C


def _festival_multiplier(d: date, arch: dict) -> float:
    m = 0.0
    for _name, mmdd, window, tag in C.FESTIVAL_DATES:
        mm, dd = map(int, mmdd.split("-"))
        try:
            peak = date(d.year, mm, dd)
        except ValueError:
            continue
        dist = abs((d - peak).days)
        if dist <= window:
            gain = arch["diwali_gain"] if tag == "diwali" else arch["wedding_gain"]
            # triangular falloff from the peak
            m += gain * (1 - dist / (window + 1))
    return m


def _seasonal_multiplier(d: date, arch: dict) -> float:
    mult = 1.0
    mult += _festival_multiplier(d, arch)
    if d.month in C.MONSOON_MONTHS:
        # deepest in Jul/Aug
        depth = {6: 0.5, 7: 1.0, 8: 1.0, 9: 0.5}[d.month]
        mult += arch["monsoon_dip"] * depth
    mm, sd, em, ed = *C.MARCH_FY_END[:2], *C.MARCH_FY_END[2:]
    if d.month == mm and sd <= d.day <= ed:
        mult += arch["march_fy_gain"]
    jm, jsd, jem, jed = *C.JUNE_SCHOOL[:2], *C.JUNE_SCHOOL[2:]
    if d.month == jm and jsd <= d.day <= jed:
        mult += arch["june_school_gain"]
    if d.weekday() >= 5:
        mult += arch["weekend_gain"]
    # gentle secular growth over the history window
    return max(0.15, mult)


def generate_for_merchant(merchant_id: str, archetype: str, rng: np.random.Generator,
                          start: date, end: date) -> list[tuple]:
    arch = C.ARCHETYPES[archetype]
    base = arch["base_daily_inr"]
    sigma = arch["noise_sigma"]

    rows: list[tuple] = []
    n_days = (end - start).days + 1
    # secular growth: ~18% / year, merchant-specific
    yearly_growth = rng.uniform(0.10, 0.28)

    # inject 2-4 "stress" episodes (3-9 days each): sharp drop + refund spike
    stress_days: set[date] = set()
    for _ in range(rng.integers(2, 5)):
        s0 = start + timedelta(days=int(rng.integers(30, n_days - 15)))
        for k in range(int(rng.integers(3, 10))):
            stress_days.add(s0 + timedelta(days=k))

    for i in range(n_days):
        d = start + timedelta(days=i)
        growth = (1 + yearly_growth) ** (i / 365.0)
        seasonal = _seasonal_multiplier(d, arch)
        noise = rng.lognormal(mean=0.0, sigma=sigma)
        gross = base * growth * seasonal * noise

        in_stress = d in stress_days
        if in_stress:
            gross *= rng.uniform(0.35, 0.6)

        refund_rate = rng.uniform(0.02, 0.05) + (0.10 if in_stress else 0.0)
        refunds = gross * refund_rate
        fees = gross * 0.02  # ~2% MDR-ish
        net = max(0.0, gross - refunds - fees)
        avg_ticket = {"fashion": 1900, "electronics": 8200, "grocery": 1100,
                      "home": 2600, "services": 900}[archetype]
        txn_count = int(max(1, gross / (avg_ticket * rng.uniform(0.8, 1.2))))

        rows.append((merchant_id, d, round(gross, 2), round(refunds, 2),
                     round(fees, 2), round(net, 2), txn_count))
    return rows


def generate_all() -> tuple[list[dict], list[tuple]]:
    """Returns (merchant_meta_rows, settlement_rows)."""
    rng = np.random.default_rng(C.RANDOM_SEED)
    end = date.today()
    start = date(end.year - C.HISTORY_YEARS, end.month, 1)

    merchants: list[dict] = []
    settlements: list[tuple] = []
    for archetype in C.ARCHETYPES:
        for k in range(1, C.MERCHANTS_PER_ARCHETYPE + 1):
            mid = f"m_{archetype}_{k:02d}"
            merchants.append({
                "merchant_id": mid,
                "archetype": archetype,
                "display_name": f"{archetype.title()} Merchant {k}",
                "onboarded_on": start,
            })
            settlements.extend(generate_for_merchant(mid, archetype, rng, start, end))
    return merchants, settlements


if __name__ == "__main__":
    m, s = generate_all()
    print(f"{len(m)} merchants, {len(s):,} settlement-days "
          f"({len(s) // max(len(m), 1)} days each)")
