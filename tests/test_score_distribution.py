from __future__ import annotations

import pytest

from src.predict.score_distribution import (
    predict_score_distribution,
    temperature_scale_probabilities,
)


def test_score_distribution_is_coherent_with_result_probabilities() -> None:
    prediction = predict_score_distribution(1.4, 1.1, max_goals=8, top_n=81)

    assert sum(item["probability"] for item in prediction.score_candidates) == pytest.approx(1.0)
    for result, probability in prediction.result_probabilities.items():
        score_total = sum(
            item["probability"]
            for item in prediction.score_candidates
            if item["result"] == result
        )
        assert score_total == pytest.approx(probability)


def test_top_candidates_keep_absolute_probability() -> None:
    prediction = predict_score_distribution(1.4, 1.1, max_goals=8, top_n=5)

    assert len(prediction.score_candidates) == 5
    assert sum(item["probability"] for item in prediction.score_candidates) < 1.0
    assert prediction.score_candidates == sorted(
        prediction.score_candidates,
        key=lambda item: item["probability"],
        reverse=True,
    )


def test_temperature_scaling_softens_probabilities_without_changing_top_result() -> None:
    raw = {"home_win": 0.60, "draw": 0.25, "away_win": 0.15}
    scaled = temperature_scale_probabilities(raw, 1.5)

    assert max(raw, key=raw.get) == max(scaled, key=scaled.get)
    assert scaled["home_win"] < raw["home_win"]
    assert sum(scaled.values()) == pytest.approx(1.0)
