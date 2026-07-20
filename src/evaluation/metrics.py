"""Metrics for score prediction evaluation."""

from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.metrics import accuracy_score, log_loss, mean_absolute_error

from src.predict.score_distribution import predict_score_distribution


def result_from_score(home_goals: int, away_goals: int) -> int:
    if home_goals > away_goals:
        return 1
    if home_goals == away_goals:
        return 0
    return -1


def evaluate_base_models(
    y_goals_true: Any,
    y_result_true: Any,
    y_diff_true: Any,
    pred_goals: Any,
    pred_result: Any,
    pred_result_proba: Any,
    pred_diff: Any,
    result_classes: Any,
) -> dict[str, float]:
    y_goals = np.asarray(y_goals_true)
    pred_goals_arr = np.asarray(pred_goals)
    y_result = np.asarray(y_result_true)

    return {
        "home_mae": float(mean_absolute_error(y_goals[:, 0], pred_goals_arr[:, 0])),
        "away_mae": float(mean_absolute_error(y_goals[:, 1], pred_goals_arr[:, 1])),
        "avg_goals_mae": float(mean_absolute_error(y_goals, pred_goals_arr)),
        "result_accuracy": float(accuracy_score(y_result, pred_result)),
        "result_log_loss": float(log_loss(y_result, pred_result_proba, labels=list(result_classes))),
        "goal_diff_mae": float(mean_absolute_error(y_diff_true, pred_diff)),
    }


def evaluate_final_scores(
    y_goals_true: Any,
    y_result_true: Any,
    pred_goals: Any,
    max_goals: int = 8,
    temperature: float = 1.0,
) -> dict[str, float]:
    y_goals = np.asarray(y_goals_true, dtype=int)
    final_scores: list[tuple[int, int]] = []
    result_probabilities: list[list[float]] = []

    for idx, goals in enumerate(np.asarray(pred_goals)):
        prediction = predict_score_distribution(
            expected_home_goals=float(goals[0]),
            expected_away_goals=float(goals[1]),
            temperature=temperature,
            max_goals=max_goals,
            top_n=1,
        )
        best = prediction.score_candidates[0]
        final_scores.append((int(best["home_goals"]), int(best["away_goals"])))
        result_probabilities.append(
            [
                prediction.result_probabilities["away_win"],
                prediction.result_probabilities["draw"],
                prediction.result_probabilities["home_win"],
            ]
        )

    final_arr = np.asarray(final_scores, dtype=int)
    final_results = np.asarray([result_from_score(h, a) for h, a in final_arr], dtype=int)
    y_result = np.asarray(y_result_true, dtype=int)
    result_probability_array = np.asarray(result_probabilities)
    probability_results = np.asarray([-1, 0, 1], dtype=int)[
        np.argmax(result_probability_array, axis=1)
    ]

    return {
        "final_score_emr": float(
            np.mean((final_arr[:, 0] == y_goals[:, 0]) & (final_arr[:, 1] == y_goals[:, 1]))
        ),
        "final_home_mae": float(mean_absolute_error(y_goals[:, 0], final_arr[:, 0])),
        "final_away_mae": float(mean_absolute_error(y_goals[:, 1], final_arr[:, 1])),
        "final_result_accuracy": float(accuracy_score(y_result, final_results)),
        "score_distribution_result_accuracy": float(
            accuracy_score(y_result, probability_results)
        ),
        "score_distribution_result_log_loss": float(
            log_loss(y_result, result_probability_array, labels=[-1, 0, 1])
        ),
    }
