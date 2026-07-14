---
name: verify-scenario
description: Verify Blast Radius scenarios with the production ScenarioBank and CorrectnessGate. Use before adding or changing a scenario, template, receipt, immutable ground truth, or gate rule.
---

# Verify Scenario

Run the production gate rather than recreating its logic:

```powershell
python .agents/skills/verify-scenario/scripts/verify_scenarios.py
```

For one curated scenario:

```powershell
python .agents/skills/verify-scenario/scripts/verify_scenarios.py --scenario cmd-exfil-1
```

Treat a nonzero exit as a release blocker. Never weaken the gate to make a scenario pass.
Fix the template, evidence, immutable truth, or presented artifact, then rerun the script and
`python -m pytest tests/test_gate.py tests/test_bank.py`.

Never execute scenario artifacts during verification. A generated scenario that fails is
discarded in favor of a compatible curated fallback.
