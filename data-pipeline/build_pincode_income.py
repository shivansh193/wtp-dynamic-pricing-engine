"""
Step 2 - Pin code -> income tier mapping.

There is no clean public census/SECC dataset that maps every Indian PIN to a
household-income tier at a usable granularity and licence. Rather than ship a
scraped-and-stale artefact, we *construct* a defensible synthetic mapping:

  - Anchored to the well-known tier 1/2/3 city classification (config.CITY_TIERS)
    and the real first-3-digit PIN prefixes for those cities.
  - For each city we enumerate a realistic block of PINs under its prefix and
    assign an `income_tier` (high / upper_mid / mid / lower_mid / low) drawn
    from a tier-conditioned distribution (Tier 1 skews high, Tier 3 skews low).
  - We also emit `median_household_income_inr` (annual) sampled around
    tier-typical values reported in consumer-economy surveys.

Output: data/raw/pincode_income_tier.csv
Columns: pin_code, city, state_zone, city_tier, income_tier,
         median_household_income_inr
"""

from __future__ import annotations

import numpy as np

import config as C
from _util import log, require_pandas, write_source_sidecar

OUT = C.RAW_DIR / "pincode_income_tier.csv"

# income tier -> (annual household income centre INR, spread)
INCOME_TIER_INR = {
    "high":       (2_800_000, 900_000),
    "upper_mid":  (1_400_000, 400_000),
    "mid":        (   800_000, 220_000),
    "lower_mid":  (   450_000, 120_000),
    "low":        (   240_000,  70_000),
}

# probability of each income tier conditioned on city tier
INCOME_MIX_BY_CITY_TIER = {
    1: {"high": 0.22, "upper_mid": 0.33, "mid": 0.28, "lower_mid": 0.13, "low": 0.04},
    2: {"high": 0.09, "upper_mid": 0.24, "mid": 0.34, "lower_mid": 0.24, "low": 0.09},
    3: {"high": 0.04, "upper_mid": 0.13, "mid": 0.30, "lower_mid": 0.33, "low": 0.20},
}

# how many synthetic PINs to enumerate per city (keeps file a few thousand rows)
PINS_PER_CITY = 60


def main() -> None:
    pd = require_pandas()
    rng = np.random.default_rng(C.RANDOM_SEED + 2)
    log("Building PIN code -> income tier mapping (constructed, tier-anchored)...")

    rows = []
    for tier, meta in C.CITY_TIERS.items():
        mix = INCOME_MIX_BY_CITY_TIER[tier]
        tiers_list = list(mix)
        tiers_prob = np.array(list(mix.values()))
        for city, prefixes in meta["cities"].items():
            for _ in range(PINS_PER_CITY):
                prefix = rng.choice(prefixes)
                # last 3 digits of a 6-digit PIN
                pin = f"{prefix}{rng.integers(1, 999):03d}"
                inc_tier = rng.choice(tiers_list, p=tiers_prob)
                centre, spread = INCOME_TIER_INR[inc_tier]
                income = max(120_000, int(rng.normal(centre, spread)))
                rows.append(
                    {
                        "pin_code": pin,
                        "city": city,
                        "state_zone": prefix[0],  # first PIN digit ~ postal zone
                        "city_tier": tier,
                        "income_tier": inc_tier,
                        "median_household_income_inr": income,
                    }
                )

    df = pd.DataFrame(rows).drop_duplicates(subset="pin_code").reset_index(drop=True)
    df.to_csv(OUT, index=False)
    log(f"  wrote {OUT}  ({len(df)} unique PINs across {df.city.nunique()} cities)")
    write_source_sidecar(
        OUT,
        source="Constructed mapping anchored to tier 1/2/3 city classification "
        "+ real PIN prefixes; income tiers sampled from tier-conditioned mix",
        live=False,
        note="Not census/SECC microdata. Distributions calibrated to reported "
        "Indian household-income surveys.",
    )


if __name__ == "__main__":
    main()
