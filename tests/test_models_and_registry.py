from __future__ import annotations

import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "python-sidecar" / "tests" / "test_models_and_registry.py"
SPEC = importlib.util.spec_from_file_location("sandflow_sidecar_test_models", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(MODULE)

globals().update({name: value for name, value in vars(MODULE).items() if name.startswith("test_")})
