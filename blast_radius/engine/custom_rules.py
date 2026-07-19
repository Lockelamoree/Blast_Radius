"""Load a repo's ``.blastradius.toml`` team custom-rule set.

Stdlib only (``tomllib``, Python 3.11+) so the engine/CLI/hook import path keeps
no new dependency. Loading is **fail-open**: any error (missing file, bad TOML,
schema violation, invalid regex) returns no config plus a message the caller can
surface on stderr, so a malformed rule file can never silently disable the screen.

The config can only ADD coverage or drop *caution* noise; the schema
(`CustomRulesConfig`) has no way to suppress a built-in critical finding.
"""

from __future__ import annotations

import hashlib
import json
import tomllib
from pathlib import Path

from pydantic import ValidationError

from blast_radius.models import CustomRulesConfig

DEFAULT_FILENAME = ".blastradius.toml"


def discover(start: Path | None = None) -> Path | None:
    """Return the nearest ``.blastradius.toml`` at or above ``start`` (cwd by
    default), stopping at the filesystem root. None if none is found."""
    base = (start or Path.cwd()).resolve()
    for directory in (base, *base.parents):
        candidate = directory / DEFAULT_FILENAME
        if candidate.is_file():
            return candidate
    return None


def load(path: Path) -> CustomRulesConfig:
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    return CustomRulesConfig.model_validate(data)


def load_safe(path: Path | None) -> tuple[CustomRulesConfig | None, str | None]:
    """Fail-open load. Returns (config, error_message). On any problem the config
    is None and the message explains why — the screen then runs with built-ins only."""
    if path is None:
        return None, None
    try:
        return load(path), None
    except FileNotFoundError:
        return None, None
    except (OSError, tomllib.TOMLDecodeError, ValidationError, ValueError) as error:
        return None, f"{path}: {type(error).__name__}: {error}"


def fingerprint(config: CustomRulesConfig | None) -> str:
    """Stable hash of the applied rule set, recorded in the inspection receipt so a
    verdict is reproducible with the same config. Empty when no config is applied."""
    if config is None or (not config.rules and not config.allowlist):
        return ""
    blob = json.dumps(config.model_dump(mode="json"), sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
