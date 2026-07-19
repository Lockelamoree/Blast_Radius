import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "blast-radius"


def test_blast_radius_plugin_and_marketplace_are_publishable() -> None:
    manifest = json.loads(
        (PLUGIN / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    marketplace = json.loads(
        (ROOT / ".agents" / "plugins" / "marketplace.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["name"] == "blast-radius"
    assert manifest["mcpServers"] == "./.mcp.json"
    assert (PLUGIN / manifest["skills"]).is_dir()
    assert not any("TODO" in value for value in _strings(manifest))

    entry = next(item for item in marketplace["plugins"] if item["name"] == "blast-radius")
    assert entry["source"] == {"source": "local", "path": "./plugins/blast-radius"}
    assert entry["policy"] == {
        "installation": "AVAILABLE",
        "authentication": "ON_INSTALL",
    }


def test_plugin_mcp_registration_uses_packaged_entry_point() -> None:
    config = json.loads((PLUGIN / ".mcp.json").read_text(encoding="utf-8"))
    assert config["mcpServers"]["blast-radius"]["command"] == "blastradius-mcp"


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)
