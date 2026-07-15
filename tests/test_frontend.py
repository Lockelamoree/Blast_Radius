from pathlib import Path


def test_results_render_measured_values_without_hardcoded_zero_scores() -> None:
    root = Path(__file__).parents[1]
    template = (root / "blast_radius" / "templates" / "index.html").read_text(
        encoding="utf-8"
    )
    app = (root / "blast_radius" / "static" / "app.js").read_text(encoding="utf-8")

    assert 'id="result-summary-line">—</' in template
    assert 'id="result-tests">—</' in template
    assert "results-summary.js" not in template
    assert "Pre 0/5" not in template
    assert "data.pretest_score" in app
    assert "data.posttest_score" in app
    assert "data.test_total" in app
    assert "value.label" in app
    assert "value.pre_score" in app
    assert "value.post_score" in app
