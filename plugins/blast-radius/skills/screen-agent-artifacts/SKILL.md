---
name: screen-agent-artifacts
description: Deterministically screen a proposed command, unified diff, or sandbox policy for known agent-security red flags before it is executed or approved. Use when reviewing risky shell commands, code-agent diffs, package installs, tool permissions, or blast-radius configurations.
---

# Screen agent artifacts with Blast Radius

Use the Blast Radius inspector as an offline safety signal. It is deterministic,
model-free, and never executes the submitted artifact. Its `looks-scoped` verdict
means only that no known pattern matched; never describe that result as proof of
safety.

## Preferred path: MCP

If the `blast-radius` MCP tools are available:

1. Call `check_artifact` with `kind=command`, `kind=diff`, or `kind=config`.
2. For config checks, serialize the proposed policy into `config_json`; include an
   `expected_json` policy only when a reviewed least-privilege baseline exists.
3. Lead with the returned verdict, then cite finding categories, literal excerpts,
   ordinal confidence, and fixes.
4. Treat `reject-recommended` as a stop signal and `sandbox-recommended` as a
   request to narrow scope before proceeding.
5. Never execute or silently rewrite the artifact as part of screening.

Use `verify_scenario` only for authored Blast Radius scenario JSON. A passing
result verifies structural invariants; it does not authorize running the displayed
commands.

## CLI fallback

If MCP is unavailable but the `blastradius` executable is installed, run one of:

```text
blastradius check --kind command --json "<command>"
blastradius check --diff <path-to-diff> --json
blastradius check --config <policy.json> --json
```

When neither interface is installed, explain that the local prerequisite is:

```text
pip install "blast-radius[mcp]"
```

Do not install packages without the user's authorization.

## Reporting contract

- Say explicitly that no model ran.
- Preserve the inspector's exact verdict and category names.
- Distinguish a direct finding from a synthesized correlation such as
  `exfil_chain`.
- Include the provenance engine version, category hash, input fingerprint, and
  driving findings when available.
- Do not paste secrets into the inspector. Redact secret values while retaining
  the command structure and paths needed for detection.
- Never expose or request scenario `ground_truth` through a public response.
