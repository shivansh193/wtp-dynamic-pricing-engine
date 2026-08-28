"""
Dataset loading + deterministic 70/15/15 split.

The split is by row hash (not random shuffle) so it is stable across machines
and reproducible without carrying an index file around.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from . import schema as S

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = REPO_ROOT / "data" / "processed" / "transactions.csv"


@dataclass
class Split:
    X_train: pd.DataFrame
    X_val: pd.DataFrame
    X_test: pd.DataFrame
    y_train: pd.Series
    y_val: pd.Series
    y_test: pd.Series
    raw_train: pd.DataFrame
    raw_val: pd.DataFrame
    raw_test: pd.DataFrame
    category_maps: dict


def _bucket(row_id: int, seed: int = 42) -> str:
    h = int(hashlib.md5(f"{seed}:{row_id}".encode()).hexdigest(), 16) % 100
    if h < 70:
        return "train"
    if h < 85:
        return "val"
    return "test"


def load_raw(path: Path = DATA_PATH) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run `python data-pipeline/run_all.py --no-net` first."
        )
    return pd.read_csv(path)


def make_split(target: str, *, extra_features: list[str] | None = None,
               path: Path = DATA_PATH) -> Split:
    df = load_raw(path).reset_index(drop=True)
    df["_split"] = [_bucket(i) for i in range(len(df))]

    category_maps = S.build_category_maps(df)
    feature_cols = list(S.FEATURES) + list(extra_features or [])

    enc = S.encode(df, category_maps)
    for ef in extra_features or []:
        enc[ef] = pd.to_numeric(df[ef], errors="coerce").astype("float64")
    enc = enc[feature_cols]

    y = df[target]
    parts = {}
    for name in ("train", "val", "test"):
        mask = (df["_split"] == name).to_numpy()
        parts[name] = (enc[mask], y[mask], df[mask])

    return Split(
        X_train=parts["train"][0], X_val=parts["val"][0], X_test=parts["test"][0],
        y_train=parts["train"][1], y_val=parts["val"][1], y_test=parts["test"][1],
        raw_train=parts["train"][2], raw_val=parts["val"][2], raw_test=parts["test"][2],
        category_maps=category_maps,
    )
