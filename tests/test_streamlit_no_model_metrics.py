from __future__ import annotations

from pathlib import Path


def test_streamlit_does_not_display_model_metrics() -> None:
    app_text = Path("app/streamlit_app.py").read_text(encoding="utf-8")

    forbidden = [
        "load_model_metrics",
        "model_metrics",
        "勝敗Accuracy",
        "Home MAE",
        "Away MAE",
    ]
    for pattern in forbidden:
        assert pattern not in app_text


def test_streamlit_exposes_final_standings_view() -> None:
    app_text = Path("app/streamlit_app.py").read_text(encoding="utf-8")

    assert '"最終順位予測"' in app_text
    assert "render_standings_forecast" in app_text
    assert "load_standings_forecasts" in app_text
