"""Human-vs-model oversight evaluation.

Runs a model as a *player* — it produces the same approve/sandbox/reject call
and one-sentence tell a human does — and grades it with the identical
deterministic gate (`grade_decision`). The model never gates anything and never
sees ground truth; it is scored on the exact evidence a human works from. That
keeps the human-vs-model scorecard honest and falsifiable.
"""

from blast_radius.eval.detection_eval import (
    DETECTION_NOTE,
    CorpusSample,
    DetectionEvalReport,
    SampleResult,
    evaluate_detection,
    load_corpus,
)
from blast_radius.eval.model_eval import (
    ModelChoice,
    ModelEvalReport,
    ScenarioEval,
    evaluate_model,
    player_view,
)

__all__ = [
    "DETECTION_NOTE",
    "CorpusSample",
    "DetectionEvalReport",
    "ModelChoice",
    "ModelEvalReport",
    "SampleResult",
    "ScenarioEval",
    "evaluate_detection",
    "evaluate_model",
    "load_corpus",
    "player_view",
]
