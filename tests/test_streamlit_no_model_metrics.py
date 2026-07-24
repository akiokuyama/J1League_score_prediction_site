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


def test_streamlit_uses_separate_mobile_standings_cards() -> None:
    app_text = Path("app/streamlit_app.py").read_text(encoding="utf-8")

    assert ".standings-table--desktop { display: none; }" in app_text
    assert ".standings-mobile { display: grid; gap: 10px; }" in app_text
    assert "standings-mobile-card" in app_text
    assert "standings-mobile-card--my-team" in app_text
    assert "使用モデル：" not in app_text


def test_streamlit_exposes_seasonal_past_results_with_coverage_note() -> None:
    app_text = Path("app/streamlit_app.py").read_text(encoding="utf-8")

    assert "load_past_prediction_seasons" in app_text
    assert '"シーズン"' in app_text
    assert "掲載範囲について" in app_text
    assert "今シーズンの試合結果はまだありません" in app_text
