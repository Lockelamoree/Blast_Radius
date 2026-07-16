# Engine guidance

Ground truth is the authority. A model may recognize an allowed tell and write follow-up
prose, but it must never alter the correct action, evidence, receipts, or safe sandbox policy.

- Compute the deterministic grade first.
- Validate model-matched tells against `scenario.ground_truth.tells` before merging.
- Convert timeouts, malformed output, budget exhaustion, and provider errors to the
  deterministic fallback.
- Pass every generated presentation through both the deterministic gate and the model critic.
- Never send a generated presentation to the reasoning critic; grade it deterministically.
- Never execute scenario artifacts or expose ground truth through a public response.
- Add a regression test for every trust-boundary change.
