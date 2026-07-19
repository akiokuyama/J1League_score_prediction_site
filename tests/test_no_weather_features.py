from __future__ import annotations

import json
from pathlib import Path

import joblib
import pandas as pd

from src.models.train_score_models import build_training_frame


def test_active_model_features_do_not_include_post_match_or_weather_data() -> None:
    features = joblib.load("Models/model_features.pkl")
    weather_features = [feature for feature in features if str(feature) == "Weather" or str(feature).startswith("Weather_")]
    assert weather_features == []
    assert "Attendance" not in features
    assert "Stadium_Fill_Rate" not in features


def test_latest_predictions_do_not_include_weather_text() -> None:
    path = Path("outputs/latest_predictions.json")
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    json.loads(text)
    assert "Weather" not in text


def test_training_frame_excludes_realised_attendance(tmp_path: Path) -> None:
    dataset = pd.DataFrame(
        [
            {
                "Season": 2025,
                "Section": 1,
                "Date": "2025-02-01",
                "Home": "a",
                "Away": "b",
                "Score": "1-0",
                "Stadium": "s",
                "Weather": "Sunny",
                "Attendance": 10000,
                "Stadium_Fill_Rate": 0.5,
                "Home_Goals": 1,
                "Away_Goals": 0,
                "Goal_Diff": 1,
                "Match_Result": 1,
                "Home_Elo_Before": 1500,
            }
        ]
    )
    path = tmp_path / "training.csv"
    dataset.to_csv(path, index=False)
    features, *_ = build_training_frame(path, exclude_weather=True)

    assert "Attendance" not in features.columns
    assert "Stadium_Fill_Rate" not in features.columns
