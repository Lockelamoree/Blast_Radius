"""Check whether the Blast Radius plugin's local executables are available."""

from __future__ import annotations

import json
import importlib.util
import sys


def main() -> int:
    modules = {
        name: importlib.util.find_spec(name) is not None
        for name in ("blast_radius", "mcp")
    }
    ready = all(modules.values())
    print(
        json.dumps(
            {
                "ready": ready,
                "modules": modules,
                "launch": [sys.executable, "-m", "blast_radius.mcp_server"],
                "remediation": None
                if ready
                else 'From the Blast Radius repository root, run: python -m pip install ".[mcp]"',
            },
            indent=2,
        )
    )
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
