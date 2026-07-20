"""Walk-forward comparison for coherent expected-goal score models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, log_loss, mean_absolute_error

from src.models.probability_calibration import (
    RESULT_CLASSES,
    fit_temperature,
    temperature_scale_matrix,
)
from src.models.train_score_models import train_goal_regressor
from src.predict.score_distribution import predict_score_distribution


CANDIDATE_WEIGHTS = {
    "l2": 0.0,
    "blend_poisson_25": 0.25,
    "blend_poisson_50": 0.50,
    "blend_poisson_75": 0.75,
    "poisson": 1.0,
}


@dataclass(frozen=True)
class WalkForwardFold:
    name: str
    train_mask: np.ndarray
    test_mask: np.ndarray


def default_walk_forward_folds(df: pd.DataFrame) -> list[WalkForwardFold]:
    season_text = df["Season"].astype(str).str.replace(r"\.0$", "", regex=True)
    season_year = season_text.str.extract(r"(\d{4})")[0].astype(int)
    dates = pd.to_datetime(df.get("Date"), errors="coerce")
    special_split = pd.Timestamp("2026-05-01")

    definitions = [
        ("2023", season_year < 2023, season_text == "2023"),
        ("2024", season_year < 2024, season_text == "2024"),
        ("2025", season_year < 2025, season_text == "2025"),
        (
            "2026_special_after_2026-05-01",
            (season_year < 2026) | ((season_text == "2026_special") & (dates < special_split)),
            (season_text == "2026_special") & (dates >= special_split),
        ),
    ]
    folds: list[WalkForwardFold] = []
    for name, train_mask, test_mask in definitions:
        train_values = train_mask.to_numpy(dtype=bool)
        test_values = test_mask.to_numpy(dtype=bool)
        if train_values.any() and test_values.any():
            folds.append(WalkForwardFold(name, train_values, test_values))
    return folds


def result_probability_matrix(
    predicted_goals: np.ndarray,
    *,
    temperature: float = 1.0,
    max_goals: int = 8,
) -> np.ndarray:
    rows: list[list[float]] = []
    for home_goals, away_goals in np.asarray(predicted_goals, dtype=float):
        prediction = predict_score_distribution(
            home_goals,
            away_goals,
            temperature=temperature,
            max_goals=max_goals,
            top_n=1,
        )
        probabilities = prediction.result_probabilities
        rows.append(
            [
                probabilities["away_win"],
                probabilities["draw"],
                probabilities["home_win"],
            ]
        )
    return np.asarray(rows, dtype=float)


def _metrics(
    *,
    true_goals: np.ndarray,
    true_results: np.ndarray,
    predicted_goals: np.ndarray,
    probabilities: np.ndarray,
    temperature: float,
    max_goals: int,
) -> dict[str, float]:
    modal_scores: list[list[int]] = []
    for home_goals, away_goals in predicted_goals:
        candidate = predict_score_distribution(
            home_goals,
            away_goals,
            temperature=temperature,
            max_goals=max_goals,
            top_n=1,
        ).score_candidates[0]
        modal_scores.append([int(candidate["home_goals"]), int(candidate["away_goals"])])
    modal = np.asarray(modal_scores, dtype=int)
    predicted_results = RESULT_CLASSES[np.argmax(probabilities, axis=1)]
    return {
        "result_accuracy": float(accuracy_score(true_results, predicted_results)),
        "result_log_loss": float(log_loss(true_results, probabilities, labels=RESULT_CLASSES)),
        "result_brier": float(
            np.mean(
                np.sum(
                    (
                        probabilities
                        - (true_results[:, None] == RESULT_CLASSES[None, :]).astype(float)
                    )
                    ** 2,
                    axis=1,
                )
            )
        ),
        "expected_home_mae": float(mean_absolute_error(true_goals[:, 0], predicted_goals[:, 0])),
        "expected_away_mae": float(mean_absolute_error(true_goals[:, 1], predicted_goals[:, 1])),
        "score_exact_match_rate": float(np.mean(np.all(modal == true_goals, axis=1))),
        "modal_home_mae": float(mean_absolute_error(true_goals[:, 0], modal[:, 0])),
        "modal_away_mae": float(mean_absolute_error(true_goals[:, 1], modal[:, 1])),
    }


def _weighted_metrics(fold_reports: list[dict[str, Any]], key: str) -> dict[str, float]:
    metric_names = list(fold_reports[0][key])
    total = sum(int(report["test_rows"]) for report in fold_reports)
    return {
        metric: float(
            sum(int(report["test_rows"]) * float(report[key][metric]) for report in fold_reports)
            / total
        )
        for metric in metric_names
    }


def evaluate_goal_model_candidates(
    X: pd.DataFrame,
    y_goals: pd.DataFrame,
    y_result: pd.Series,
    raw_df: pd.DataFrame,
    *,
    max_goals: int = 8,
) -> dict[str, Any]:
    """Compare L2/Poisson blends and fit a deployment temperature."""

    folds = default_walk_forward_folds(raw_df)
    if len(folds) < 2:
        raise ValueError("at least two walk-forward folds are required.")

    predictions_by_candidate: dict[str, list[dict[str, Any]]] = {
        name: [] for name in CANDIDATE_WEIGHTS
    }
    for fold in folds:
        l2_model = train_goal_regressor(X.loc[fold.train_mask], y_goals.loc[fold.train_mask])
        poisson_model = train_goal_regressor(
            X.loc[fold.train_mask],
            y_goals.loc[fold.train_mask],
            poisson_weight=1.0,
        )
        l2_predictions = np.asarray(l2_model.predict(X.loc[fold.test_mask]), dtype=float)
        poisson_predictions = np.asarray(poisson_model.predict(X.loc[fold.test_mask]), dtype=float)
        true_goals = y_goals.loc[fold.test_mask].to_numpy(dtype=int)
        true_results = y_result.loc[fold.test_mask].to_numpy(dtype=int)

        for name, weight in CANDIDATE_WEIGHTS.items():
            predicted_goals = (1.0 - weight) * l2_predictions + weight * poisson_predictions
            raw_probabilities = result_probability_matrix(
                predicted_goals,
                temperature=1.0,
                max_goals=max_goals,
            )
            predictions_by_candidate[name].append(
                {
                    "fold": fold.name,
                    "train_rows": int(fold.train_mask.sum()),
                    "test_rows": int(fold.test_mask.sum()),
                    "true_goals": true_goals,
                    "true_results": true_results,
                    "predicted_goals": predicted_goals,
                    "raw_probabilities": raw_probabilities,
                }
            )

    candidate_reports: dict[str, Any] = {}
    for name, fold_predictions in predictions_by_candidate.items():
        fold_reports: list[dict[str, Any]] = []
        preceding_probabilities: list[np.ndarray] = []
        preceding_labels: list[np.ndarray] = []
        for prediction in fold_predictions:
            if preceding_probabilities:
                temperature = fit_temperature(
                    np.vstack(preceding_probabilities),
                    np.concatenate(preceding_labels),
                )
            else:
                temperature = 1.0
            calibrated_probabilities = temperature_scale_matrix(
                prediction["raw_probabilities"], temperature
            )
            fold_reports.append(
                {
                    "fold": prediction["fold"],
                    "train_rows": prediction["train_rows"],
                    "test_rows": prediction["test_rows"],
                    "temperature_from_preceding_folds": float(temperature),
                    "raw": _metrics(
                        true_goals=prediction["true_goals"],
                        true_results=prediction["true_results"],
                        predicted_goals=prediction["predicted_goals"],
                        probabilities=prediction["raw_probabilities"],
                        temperature=1.0,
                        max_goals=max_goals,
                    ),
                    "calibrated": _metrics(
                        true_goals=prediction["true_goals"],
                        true_results=prediction["true_results"],
                        predicted_goals=prediction["predicted_goals"],
                        probabilities=calibrated_probabilities,
                        temperature=temperature,
                        max_goals=max_goals,
                    ),
                }
            )
            preceding_probabilities.append(prediction["raw_probabilities"])
            preceding_labels.append(prediction["true_results"])

        all_probabilities = np.vstack(
            [prediction["raw_probabilities"] for prediction in fold_predictions]
        )
        all_labels = np.concatenate(
            [prediction["true_results"] for prediction in fold_predictions]
        )
        fitted_temperature = fit_temperature(all_probabilities, all_labels)
        weighted_raw = _weighted_metrics(fold_reports, "raw")
        weighted_calibrated = _weighted_metrics(fold_reports, "calibrated")
        calibration_improves = (
            weighted_calibrated["result_log_loss"] < weighted_raw["result_log_loss"]
            and weighted_calibrated["result_brier"] <= weighted_raw["result_brier"]
        )
        candidate_reports[name] = {
            "poisson_weight": float(CANDIDATE_WEIGHTS[name]),
            "fitted_temperature": float(fitted_temperature),
            "calibration_improves_walk_forward": bool(calibration_improves),
            "deployment_temperature": float(fitted_temperature if calibration_improves else 1.0),
            "weighted_raw": weighted_raw,
            "weighted_progressive_calibrated": weighted_calibrated,
            "selected_metrics": weighted_calibrated if calibration_improves else weighted_raw,
            "folds": fold_reports,
        }

    # Treat sub-0.001 Log loss differences as practically tied and prefer the
    # simpler model. This prevents a negligible validation fluctuation from
    # introducing and maintaining a second production regressor.
    best_loss = min(
        report["selected_metrics"]["result_log_loss"]
        for report in candidate_reports.values()
    )
    practically_tied = [
        name
        for name, report in candidate_reports.items()
        if report["selected_metrics"]["result_log_loss"] <= best_loss + 0.001
    ]
    selected_name = min(
        practically_tied,
        key=lambda name: (
            CANDIDATE_WEIGHTS[name],
            -candidate_reports[name]["selected_metrics"]["result_accuracy"],
        ),
    )
    return {
        "selection_metric": "selected_metrics.result_log_loss_with_0.001_simplicity_tolerance",
        "selected_candidate": selected_name,
        "selected_poisson_weight": float(CANDIDATE_WEIGHTS[selected_name]),
        "selected_temperature": float(candidate_reports[selected_name]["deployment_temperature"]),
        "max_goals": int(max_goals),
        "candidates": candidate_reports,
    }
