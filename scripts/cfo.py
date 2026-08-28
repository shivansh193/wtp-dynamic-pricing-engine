"""
Runner for the Cash Flow Oracle scaffold without needing `pip install -e .`.

    python scripts/cfo.py seed             # generate + persist settlements
    python scripts/cfo.py forecast m_fashion_01 [horizon_days]
    python scripts/cfo.py serve [port]     # uvicorn cash_flow_oracle.main:app
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _register(folder: str, name: str) -> None:
    init = ROOT / folder / "__init__.py"
    spec = importlib.util.spec_from_file_location(
        name, init, submodule_search_locations=[str(ROOT / folder)]
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)


_register("cash-flow-oracle", "cash_flow_oracle")


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "seed"

    if cmd == "seed":
        from cash_flow_oracle.seed import main as seed_main

        asyncio.run(seed_main())

    elif cmd == "forecast":
        mid = sys.argv[2] if len(sys.argv) > 2 else "m_fashion_01"
        horizon = int(sys.argv[3]) if len(sys.argv) > 3 else 30
        from cash_flow_oracle.db import store
        from cash_flow_oracle.service import build_forecast

        async def run():
            await store.connect()
            resp = await build_forecast(mid, horizon)
            await store.close()
            return resp

        resp = asyncio.run(run())
        d = resp.model_dump()
        d["forecast_curve"] = f"<{len(d['forecast_curve'])} daily points>"
        print(json.dumps(d, indent=2, default=str))

    elif cmd == "serve":
        port = int(sys.argv[2]) if len(sys.argv) > 2 else 8010
        import uvicorn

        from cash_flow_oracle.main import app

        uvicorn.run(app, host="0.0.0.0", port=port)

    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
