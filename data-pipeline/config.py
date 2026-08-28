"""
Central configuration for the data pipeline.

Every path and constant used by the fetch / build / generate scripts lives here
so the individual scripts stay short and the data contract is easy to audit.

Design note: all network fetches degrade to a *calibrated synthetic fallback*
so the whole system builds and runs with zero external accounts or connectivity.
Each fetch script writes a small `<name>.source.json` sidecar recording whether
the data came from the live source or the fallback.
"""

from __future__ import annotations

import os
from pathlib import Path

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
GEOIP_DIR = RAW_DIR / "geoip"
DOCS_DIR = REPO_ROOT / "docs"

for _d in (RAW_DIR, PROCESSED_DIR, GEOIP_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------------------------------- #
# Reproducibility
# --------------------------------------------------------------------------- #
RANDOM_SEED = int(os.getenv("RANDOM_SEED", "42"))
SYNTHETIC_ROWS = int(os.getenv("SYNTHETIC_ROWS", "50000"))

# --------------------------------------------------------------------------- #
# Time window shared across every dataset
# --------------------------------------------------------------------------- #
START_YEAR = 2022
END_YEAR = 2026
# Real data is only available through mid-2026; synthetic months cover Jan22-Aug26
DATA_MAX_MONTH = "2026-08"

# --------------------------------------------------------------------------- #
# Ecommerce categories (used by Google Trends + synthetic generator)
# --------------------------------------------------------------------------- #
ECOMMERCE_CATEGORIES = ["fashion", "electronics", "grocery", "home", "beauty"]

# Rough real-world Google-Trends style seasonality shape per category
# (relative monthly multiplier, index 0 = January ... 11 = December).
# Calibrated to observed India retail search patterns: festival Q3/Q4 lift,
# grocery flat, fashion peaking around Diwali + wedding season.
CATEGORY_SEASONALITY = {
    "fashion":     [0.82, 0.80, 0.85, 0.88, 0.92, 0.90, 0.95, 1.05, 1.18, 1.35, 1.28, 1.10],
    "electronics": [0.85, 0.82, 0.88, 0.90, 0.95, 0.92, 0.98, 1.10, 1.30, 1.45, 1.20, 1.05],
    "grocery":     [0.97, 0.96, 0.98, 0.99, 1.00, 1.00, 1.01, 1.03, 1.06, 1.10, 1.05, 1.04],
    "home":        [0.88, 0.86, 0.95, 1.02, 1.00, 0.92, 0.90, 0.98, 1.12, 1.28, 1.10, 1.05],
    "beauty":      [0.84, 0.86, 0.90, 0.92, 0.94, 0.92, 0.96, 1.06, 1.20, 1.34, 1.22, 1.16],
}

# --------------------------------------------------------------------------- #
# City tier classification with realistic pin-code prefixes
# Pin codes in India: first digit = zone, first 2-3 digits = sub-region.
# We map well-known metro / city prefixes to a tier so synthetic pin codes are
# internally consistent with `city_tier`.
# --------------------------------------------------------------------------- #
CITY_TIERS = {
    1: {
        "label": "Tier 1 (metro)",
        "cities": {
            "Mumbai":     ["400"],
            "Delhi":      ["110"],
            "Bengaluru":  ["560"],
            "Hyderabad":  ["500"],
            "Chennai":    ["600"],
            "Kolkata":    ["700"],
            "Pune":       ["411"],
            "Ahmedabad":  ["380"],
            "Gurugram":   ["122"],
            "Noida":      ["201"],
        },
    },
    2: {
        "label": "Tier 2",
        "cities": {
            "Jaipur":     ["302"],
            "Lucknow":    ["226"],
            "Nagpur":     ["440"],
            "Indore":     ["452"],
            "Bhopal":     ["462"],
            "Coimbatore": ["641"],
            "Kochi":      ["682"],
            "Chandigarh": ["160"],
            "Visakhapatnam": ["530"],
            "Surat":      ["395"],
            "Vadodara":   ["390"],
            "Nashik":     ["422"],
        },
    },
    3: {
        "label": "Tier 3 / smaller towns",
        "cities": {
            "Patna":       ["800"],
            "Ranchi":      ["834"],
            "Guwahati":    ["781"],
            "Raipur":      ["492"],
            "Jodhpur":     ["342"],
            "Varanasi":    ["221"],
            "Madurai":     ["625"],
            "Aurangabad":  ["431"],
            "Dehradun":    ["248"],
            "Siliguri":    ["734"],
            "Gorakhpur":   ["273"],
            "Jhansi":      ["284"],
            "Belagavi":    ["590"],
            "Tirupati":    ["517"],
        },
    },
}

CITY_TIER_WEIGHTS = {1: 0.30, 2: 0.35, 3: 0.35}

# --------------------------------------------------------------------------- #
# Payment-method preference distribution by city tier
# Tier 1 skews credit card; Tier 3 skews COD. Calibrated loosely to
# NPCI / RBI retail payment-mix commentary.
# --------------------------------------------------------------------------- #
PAYMENT_PREF_BY_TIER = {
    1: {"UPI": 0.44, "Credit_Card": 0.28, "Debit_Card": 0.12, "COD": 0.06, "Wallet": 0.10},
    2: {"UPI": 0.50, "Credit_Card": 0.14, "Debit_Card": 0.15, "COD": 0.14, "Wallet": 0.07},
    3: {"UPI": 0.46, "Credit_Card": 0.06, "Debit_Card": 0.14, "COD": 0.28, "Wallet": 0.06},
}

# --------------------------------------------------------------------------- #
# Device mix (overall) - weighted 45/25/15/15 per the brief
# --------------------------------------------------------------------------- #
DEVICE_WEIGHTS = {
    "Android_budget": 0.45,
    "Android_premium": 0.25,
    "iPhone": 0.15,
    "Desktop": 0.15,
}

# --------------------------------------------------------------------------- #
# IP type distribution (residential dominant) + trust multipliers
# multipliers come straight from the brief (Step 2.5)
# --------------------------------------------------------------------------- #
IP_TYPE_WEIGHTS = {
    "residential": 0.62,
    "mobile_carrier": 0.24,
    "public_wifi": 0.05,
    "datacenter": 0.03,
    "vpn": 0.035,
    "tor": 0.005,
    "unknown": 0.02,
}

IP_TRUST_MULTIPLIER = {
    "residential": 1.00,
    "mobile_carrier": 0.95,
    "unknown": 0.80,
    "public_wifi": 0.70,
    "vpn": 0.60,
    "datacenter": 0.50,
    "tor": 0.30,
}

# --------------------------------------------------------------------------- #
# Category-level economics for the synthetic generator
# aov / cart-value centre (INR), return-rate centre, and cart-value spread.
# Calibrated to widely reported Indian ecommerce category AOVs.
# --------------------------------------------------------------------------- #
CATEGORY_ECONOMICS = {
    "fashion":     {"aov": 1900, "cart_lognorm_sigma": 0.55, "return_rate": 0.28, "return_sd": 0.08},
    "electronics": {"aov": 8200, "cart_lognorm_sigma": 0.70, "return_rate": 0.09, "return_sd": 0.04},
    "grocery":     {"aov": 1100, "cart_lognorm_sigma": 0.40, "return_rate": 0.05, "return_sd": 0.02},
    "home":        {"aov": 2600, "cart_lognorm_sigma": 0.60, "return_rate": 0.14, "return_sd": 0.05},
    "beauty":      {"aov": 1300, "cart_lognorm_sigma": 0.50, "return_rate": 0.17, "return_sd": 0.06},
}
CATEGORY_WEIGHTS = {
    "fashion": 0.34, "electronics": 0.20, "grocery": 0.22, "home": 0.13, "beauty": 0.11,
}

# --------------------------------------------------------------------------- #
# Festival calendar 2022-2026
# intensity_score 1-3 : 3 = Diwali-class demand event, 1 = minor.
# Dates are the principal shopping day; the generator widens each into a window.
# --------------------------------------------------------------------------- #
FESTIVALS = [
    # name, date (YYYY-MM-DD), intensity, pre-window days, post-window days
    ("Holi",            "2022-03-18", 1, 3, 1),
    ("Eid_ul_Fitr",     "2022-05-03", 2, 7, 1),
    ("Rakhi",           "2022-08-11", 1, 5, 1),
    ("Independence_Day","2022-08-15", 1, 3, 1),
    ("Diwali",          "2022-10-24", 3, 21, 3),
    ("Christmas",       "2022-12-25", 2, 10, 2),
    ("FY_End",          "2023-03-31", 2, 14, 0),

    ("Holi",            "2023-03-08", 1, 3, 1),
    ("Eid_ul_Fitr",     "2023-04-22", 2, 7, 1),
    ("Back_to_School",  "2023-06-15", 1, 21, 7),
    ("Rakhi",           "2023-08-30", 1, 5, 1),
    ("Independence_Day","2023-08-15", 1, 3, 1),
    ("Diwali",          "2023-11-12", 3, 21, 3),
    ("Christmas",       "2023-12-25", 2, 10, 2),
    ("FY_End",          "2024-03-31", 2, 14, 0),

    ("Holi",            "2024-03-25", 1, 3, 1),
    ("Eid_ul_Fitr",     "2024-04-11", 2, 7, 1),
    ("Back_to_School",  "2024-06-15", 1, 21, 7),
    ("Rakhi",           "2024-08-19", 1, 5, 1),
    ("Independence_Day","2024-08-15", 1, 3, 1),
    ("Diwali",          "2024-11-01", 3, 21, 3),
    ("Christmas",       "2024-12-25", 2, 10, 2),
    ("FY_End",          "2025-03-31", 2, 14, 0),

    ("Holi",            "2025-03-14", 1, 3, 1),
    ("Eid_ul_Fitr",     "2025-03-31", 2, 7, 1),
    ("Back_to_School",  "2025-06-15", 1, 21, 7),
    ("Rakhi",           "2025-08-09", 1, 5, 1),
    ("Independence_Day","2025-08-15", 1, 3, 1),
    ("Diwali",          "2025-10-21", 3, 21, 3),
    ("Christmas",       "2025-12-25", 2, 10, 2),
    ("FY_End",          "2026-03-31", 2, 14, 0),

    ("Holi",            "2026-03-04", 1, 3, 1),
    ("Eid_ul_Fitr",     "2026-03-20", 2, 7, 1),
    ("Back_to_School",  "2026-06-15", 1, 21, 7),
    ("Rakhi",           "2026-08-28", 1, 5, 1),
    ("Independence_Day","2026-08-15", 1, 3, 1),
]

# --------------------------------------------------------------------------- #
# Firehol blocklists to fetch (raw GitHub)
# --------------------------------------------------------------------------- #
FIREHOL_BASE = "https://raw.githubusercontent.com/firehol/blocklist-ipsets/master"
# The brief names four lists. Two (level1, tor_exits) exist verbatim in the
# repo. `datacenters.netset` / `vpn.netset` were retired from the repo root;
# we map them to the current equivalents and fall back to a curated sample.
# Each value is an ordered list of candidate URLs; first success wins.
FIREHOL_LISTS = {
    "firehol_level1.netset": [f"{FIREHOL_BASE}/firehol_level1.netset"],
    "datacenters.netset": [
        f"{FIREHOL_BASE}/datacenters.netset",
        f"{FIREHOL_BASE}/iblocklist_org_amazon.netset",  # representative DC ranges
    ],
    "vpn.netset": [
        f"{FIREHOL_BASE}/vpn.netset",
        f"{FIREHOL_BASE}/firehol_anonymous.netset",  # VPN + anonymiser aggregate
        f"{FIREHOL_BASE}/firehol_proxies.netset",
    ],
    "tor_exits.ipset": [
        f"{FIREHOL_BASE}/tor_exits.ipset",
        f"{FIREHOL_BASE}/iblocklist_onion_router.netset",
    ],
}

# MaxMind permalink pattern (needs licence key)
MAXMIND_PERMALINK = (
    "https://download.maxmind.com/app/geoip_download"
    "?edition_id={edition}&license_key={key}&suffix=tar.gz"
)

# --------------------------------------------------------------------------- #
# RBI DBIE - digital payments monthly. The DBIE portal is a stateful ASP.NET
# app that is painful to scrape headlessly, so `fetch_rbi.py` attempts the
# published CSV endpoint and otherwise emits a synthetic series calibrated to
# RBI's reported headline figures (UPI volume crossing ~10bn/month in 2024,
# ~16bn by mid-2025, card + wallet mix from RBI bulletin tables).
# --------------------------------------------------------------------------- #
RBI_DBIE_HINT_URL = "https://dbie.rbi.org.in"

# Anchor points (month -> UPI transactions in millions) from RBI / NPCI press
# releases. The fallback interpolates + adds seasonality between these.
RBI_UPI_ANCHORS_MN = {
    "2022-01": 4610,
    "2022-12": 7820,
    "2023-06": 9330,
    "2023-12": 12020,
    "2024-06": 13890,
    "2024-12": 16730,
    "2025-06": 18400,
    "2026-06": 22600,
}
