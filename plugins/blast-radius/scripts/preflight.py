"""Check whether the Blast Radius plugin's local executables are available."""

from __future__ import annotations

import json
import shutil


def main() -> int:
    commands = {
        name: shutil.which(name)
        for name in ("blastradius", "blastradius-mcp")
    }
    print(json.dumps({"ready": all(commands.values()), "commands": commands}, indent=2))
    return 0 if all(commands.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
