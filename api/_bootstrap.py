"""
Import shim.

The brief mandates the directory name `ip-enrichment` (with a hyphen), which is
not a legal Python module name. This registers that folder as the importable
package `ip_enrichment` so the rest of the API can simply
`from ip_enrichment import get_service`.

Import this module before anything that needs `ip_enrichment` or `model`.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _register_hyphen_pkg(folder_name: str, module_name: str) -> None:
    if module_name in sys.modules:
        return
    pkg_dir = _REPO_ROOT / folder_name
    init_py = pkg_dir / "__init__.py"
    if not init_py.exists():
        return
    spec = importlib.util.spec_from_file_location(
        module_name, init_py, submodule_search_locations=[str(pkg_dir)]
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)


# make the repo root importable (so `import model` works from any CWD)
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_register_hyphen_pkg("ip-enrichment", "ip_enrichment")
_register_hyphen_pkg("cash-flow-oracle", "cash_flow_oracle")
