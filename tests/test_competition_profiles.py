from __future__ import annotations

import pandas as pd

from src.config import get_competition
from src.predict.predict_upcoming import _metadata_value


def test_competition_profiles_include_current_and_next_j1_seasons() -> None:
    special = get_competition("2026_special")
    next_j1 = get_competition("2026_27_j1")

    assert special.category == "100yj1"
    assert next_j1.season == "2026_27"
    assert next_j1.competition == "明治安田J1リーグ"


def test_prediction_metadata_prefers_feature_frame_values() -> None:
    features = pd.DataFrame(
        [{"season": "2026_27", "league": "J1", "competition": "明治安田J1リーグ", "category": "j1"}]
    )

    assert _metadata_value(features, "season", "fallback") == "2026_27"
    assert _metadata_value(features, "competition", "fallback") == "明治安田J1リーグ"
