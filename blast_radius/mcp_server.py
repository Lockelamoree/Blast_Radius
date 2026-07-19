"""Optional MCP server exposing Blast Radius's deterministic tools to Codex and
other MCP-aware coding agents. Install the extra to use it:

    pip install "blast-radius[mcp]"

Register in an agent via .mcp.json:

    {"mcpServers": {"blast-radius": {"command": "blastradius-mcp"}}}

Everything runs in-process against the packaged bank — no server, no network,
no model. stdio is reserved for the MCP protocol, so this module never writes
to stdout; diagnostics go to stderr.
"""

from __future__ import annotations

import sys
from pathlib import Path

from blast_radius.engine import inspector
from blast_radius.engine.bank import ScenarioBank
from blast_radius.engine.gate import CorrectnessGate
from blast_radius.models import BlastRadiusConfig, Scenario

_DATA_DIR = Path(__file__).resolve().parent / "data"


def build_server():
    """Construct the FastMCP server. Imports the MCP SDK lazily so the package
    stays importable without the optional dependency."""
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("blast-radius")
    bank = ScenarioBank(_DATA_DIR)
    gate = CorrectnessGate(bank)
    learn = {card["family"]: card for card in _load(_DATA_DIR / "learn.json")}
    toolkit = {card["family"]: card for card in _load(_DATA_DIR / "toolkit.json")}

    @server.tool()
    def check_artifact(
        kind: str, content: str = "", config_json: str = "", expected_json: str = ""
    ) -> dict:
        """Deterministically screen a real command, diff, or sandbox config for
        known red-flag patterns. No model runs; it cannot prove safety."""
        try:
            if kind == "config":
                config = BlastRadiusConfig.model_validate_json(config_json)
                expected = (
                    BlastRadiusConfig.model_validate_json(expected_json)
                    if expected_json
                    else None
                )
                report = inspector.inspect_config(config, expected)
            elif kind in {"command", "diff"}:
                if inspector.fingerprint_text(content) in inspector.bank_artifact_fingerprints(bank):
                    return {"error": "This artifact is a Blast Radius drill scenario."}
                report = inspector.inspect_text(content, kind=kind)
            else:
                return {"error": "kind must be 'command', 'diff', or 'config'"}
        except Exception as error:  # noqa: BLE001 - surface validation errors to the agent
            return {"error": str(error)}
        return report.model_dump(mode="json")

    @server.tool()
    def verify_scenario(scenario_json: str) -> dict:
        """Run the production CorrectnessGate against an author's draft scenario
        (JSON). Returns {passed, reasons, scenario_id}."""
        try:
            scenario = Scenario.model_validate_json(scenario_json)
        except Exception as error:  # noqa: BLE001
            return {"error": str(error)}
        return gate.verify(scenario).model_dump(mode="json")

    @server.tool()
    def get_learn_module(family: str) -> dict:
        """Return the field-guide module for a threat family."""
        card = learn.get(family)
        return card if card else {"error": f"unknown family: {family}"}

    @server.tool()
    def get_toolkit_card(family: str) -> dict:
        """Return the defense toolkit card for a threat family."""
        card = toolkit.get(family)
        return card if card else {"error": f"unknown family: {family}"}

    return server


def _load(path: Path) -> list[dict]:
    import json

    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def main() -> int:
    try:
        server = build_server()
    except ImportError:
        print(
            "The MCP extra is not installed. Install it with: "
            'pip install "blast-radius[mcp]"',
            file=sys.stderr,
        )
        return 2
    server.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
