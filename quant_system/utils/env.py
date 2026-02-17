from __future__ import annotations

from pathlib import Path
from typing import Dict


def load_dotenv(path: str | Path = ".env", *, override: bool = False) -> Dict[str, str]:
    """Lightweight .env loader.

    This project runs on plain Python without requiring python-dotenv.
    It loads KEY=VALUE pairs into os.environ.

    Rules:
    - ignores blank lines and lines starting with '#'
    - supports optional single/double quoted values
    - does not expand variables
    """

    import os

    p = Path(path)
    if not p.exists():
        return {}

    loaded: Dict[str, str] = {}
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
            v = v[1:-1]
        if not override and k in os.environ:
            continue
        os.environ[k] = v
        loaded[k] = v

    return loaded
