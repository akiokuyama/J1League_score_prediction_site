from pathlib import Path


def test_manual_update_workflow_excludes_local_model_metrics() -> None:
    workflow = Path(".github/workflows/update_predictions_manual.yml")
    text = workflow.read_text(encoding="utf-8")

    assert "name: Manual Prediction Update" in text
    assert "workflow_dispatch:" in text
    assert "schedule:" not in text
    assert "python scripts/build_model_metrics.py" not in text
    assert "GITHUB_ENV" in text
    assert "FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true" in text
    assert "ln -s Data data" not in text
    assert "python -m pytest" in text
    assert "git fetch origin main" in text
    assert "git reset --hard origin/main" in text
    assert "git clean -fd" in text
    assert 'tmp_dir="$(mktemp -d)"' in text
    assert "git add outputs/local" not in text
    assert "outputs/local/model_metrics.json must not be generated in Actions" in text
    assert "python scripts/build_past_prediction_results.py" in text
    assert "python scripts/run_competition_pipeline.py" in text
    assert "python scripts/build_standings_forecast.py" in text
    assert "python scripts/validate_standings_forecast.py" in text
    assert "outputs/standings_forecast" in text
