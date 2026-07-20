"""Backward-compatible score candidate helper."""

from __future__ import annotations

from typing import Any

from src.predict.score_distribution import predict_score_distribution


def generate_score_candidates(
    expected_home_goals: float,
    expected_away_goals: float,
    result_probabilities: dict[str, float] | None = None,
    predicted_goal_diff: float | None = None,
    max_goals: int = 8,
    top_n: int = 5,
    diff_sigma: float = 1.0,
    temperature: float = 1.0,
) -> list[dict[str, Any]]:
    """Return top exact scores from the coherent score distribution.

    ``result_probabilities``, ``predicted_goal_diff`` and ``diff_sigma`` are
    accepted so older callers do not fail, but public score probabilities are
    now derived only from expected goals and the stored calibration value.
    """

    del result_probabilities, predicted_goal_diff, diff_sigma
    return predict_score_distribution(
        expected_home_goals,
        expected_away_goals,
        temperature=temperature,
        max_goals=max_goals,
        top_n=top_n,
    ).score_candidates
