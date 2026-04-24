"""Shared test fixtures for Sentinel-X."""

import sys
from pathlib import Path

# Ensure sentinel_modules is importable in tests
_project_root = Path(__file__).resolve().parent.parent
_user_data = _project_root / "user_data"
for p in [str(_project_root), str(_user_data)]:
    if p not in sys.path:
        sys.path.insert(0, p)
