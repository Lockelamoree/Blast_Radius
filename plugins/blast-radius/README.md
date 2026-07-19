# Blast Radius Codex plugin

This plugin exposes Blast Radius's deterministic, offline agent-security screen
through its MCP server and teaches Codex when and how to use it. It never runs a
model, executes an artifact, or claims that an unmatched artifact is safe.

## Prerequisite

Install the package and MCP extra in the Python environment used by Codex:

```bash
pip install "blast-radius[mcp]"
python plugins/blast-radius/scripts/preflight.py
```

The repo-local catalog is `.agents/plugins/marketplace.json`. Open Codex's Plugins
Directory for this repository and install **Blast Radius**; its MCP server starts
with the `blastradius-mcp` entry point.

Source and issue tracker: <https://github.com/Lockelamoree/Blast_Radius>
