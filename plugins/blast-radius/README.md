# Blast Radius Codex plugin

This plugin exposes Blast Radius's deterministic, offline agent-security screen
through its MCP server and teaches Codex when and how to use it. It never runs a
model, executes an artifact, or claims that an unmatched artifact is safe.

## Prerequisite

Clone the repository, then install the package and MCP extra in the Python
environment used by Codex. The project is not currently published on PyPI, so
the repository checkout is the supported installation source:

```bash
python -m pip install ".[mcp]"
python plugins/blast-radius/scripts/preflight.py
```

The repo-local catalog is `.agents/plugins/marketplace.json`. Open Codex's Plugins
Directory for this repository and install **Blast Radius**; its MCP server starts
with `python -m blast_radius.mcp_server`, so it does not depend on a console-script
directory being present on `PATH`.

Source and issue tracker: <https://github.com/Lockelamoree/Blast_Radius>
