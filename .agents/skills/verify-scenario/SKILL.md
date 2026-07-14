---
name: verify-scenario
description: Verify a Blast Radius scenario against its cited template and immutable evidence before it can be shown to a learner.
---

# Verify Scenario

Use this skill before adding or changing a scenario, template, receipt, or gate rule.

1. Parse the scenario with `Scenario.model_validate`.
2. Confirm `template_ref` exists in `blast_radius/data/templates.json`.
3. Confirm every tell is backed by at least one concrete evidence record with a source,
   claim, excerpt, and retrieval date.
4. Confirm the presented artifacts support `correct_action` and the safe sandbox policy.
5. Confirm no executable artifact is invoked during verification.
6. Run `python -m pytest tests/test_gate.py tests/test_bank.py`.

A failed verification is terminal for that generated scenario. The runtime must discard it
and select a compatible verified scenario from the fallback bank.

