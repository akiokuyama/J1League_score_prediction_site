from pathlib import Path


def read_workflow(name: str) -> str:
    return Path(".github/workflows", name).read_text(encoding="utf-8")


def test_results_after_matches_workflow_is_results_only() -> None:
    text = read_workflow("update_results_after_matches.yml")

    assert "name: Update 2026-27 J1 Results" in text
    assert "workflow_dispatch:" in text
    assert 'cron: "0 22 * * 0"' in text
    assert "FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true" in text
    assert "python -m compileall app src scripts" in text
    assert "python -m pytest" in text
    assert "git fetch origin main" in text
    assert "git reset --hard origin/main" in text
    assert "git clean -fd" in text
    assert 'tmp_dir="$(mktemp -d)"' in text
    assert "python scripts/update_competition_data.py --competition-key 2026_27_j1 --scope results" in text
    assert "group: j1-2026-27-data-update" in text
    assert "python scripts/build_past_prediction_results.py" in text
    assert "python scripts/validate_past_prediction_results.py" in text
    assert "run_competition_pipeline.py" not in text
    assert "run_prediction.py --mode all_unplayed" not in text
    assert "Data/features" not in text
    assert "build_model_metrics.py" not in text
    assert "git add outputs/local" not in text


def test_scheduled_prediction_workflow_updates_predictions() -> None:
    text = read_workflow("update_predictions_scheduled.yml")

    assert "name: Update 2026-27 J1 Predictions" in text
    assert "workflow_dispatch:" in text
    assert 'cron: "0 22 * * 2"' in text
    assert "FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true" in text
    assert "python -m compileall app src scripts" in text
    assert "python -m pytest" in text
    assert "git fetch origin main" in text
    assert "git reset --hard origin/main" in text
    assert "git clean -fd" in text
    assert 'tmp_dir="$(mktemp -d)"' in text
    assert "python scripts/run_competition_pipeline.py" in text
    assert "--competition-key 2026_27_j1" in text
    assert "Data/processed/market_values_2026_27_j1_clean.csv" in text
    assert "group: j1-2026-27-data-update" in text
    assert "python scripts/build_past_prediction_results.py" in text
    assert "python scripts/validate_prediction_outputs.py" in text
    assert "python scripts/validate_past_prediction_results.py" in text
    assert "build_model_metrics.py" not in text
    assert "git add outputs/local" not in text


def test_manual_workflow_remains_manual_only() -> None:
    text = read_workflow("update_predictions_manual.yml")

    assert "name: Manual Prediction Update" in text
    assert "workflow_dispatch:" in text
    assert "schedule:" not in text
    assert "FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true" in text
    assert "git fetch origin main" in text
    assert "git reset --hard origin/main" in text
    assert "git clean -fd" in text
    assert 'tmp_dir="$(mktemp -d)"' in text
    assert "python scripts/run_competition_pipeline.py" in text
    assert "group: j1-2026-27-data-update" in text
    assert "python scripts/build_model_metrics.py" not in text
    assert "python scripts/validate_prediction_outputs.py" in text
    assert "python scripts/validate_past_prediction_results.py" in text
    assert "git add outputs/local" not in text
