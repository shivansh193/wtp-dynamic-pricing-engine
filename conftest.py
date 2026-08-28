"""
Pytest bootstrap: make the two brief-mandated hyphenated directories importable
as `ip_enrichment` and `cash_flow_oracle` without requiring `pip install -e .`.
Mirrors api/_bootstrap.py.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _register(folder: str, name: str) -> None:
    if name in sys.modules:
        return
    init = _ROOT / folder / "__init__.py"
    if not init.exists():
        return
    spec = importlib.util.spec_from_file_location(
        name, init, submodule_search_locations=[str(_ROOT / folder)]
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)


_register("ip-enrichment", "ip_enrichment")
_register("cash-flow-oracle", "cash_flow_oracle")
