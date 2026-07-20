"""Coherent score and result probabilities derived from expected goals."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


RESULT_KEYS = ("away_win", "draw", "home_win")


@dataclass(frozen=True)
class ScoreDistributionPrediction:
    """A single normalized distribution used by every public prediction."""

    result_probabilities: dict[str, float]
    score_candidates: list[dict[str, Any]]


def _poisson_pmf(k: int, lam: float) -> float:
    return math.exp(-lam) * (lam**k) / math.factorial(k)


def result_key(home_goals: int, away_goals: int) -> str:
    if home_goals > away_goals:
        return "home_win"
    if home_goals == away_goals:
        return "draw"
    return "away_win"


def temperature_scale_probabilities(
    probabilities: dict[str, float],
    temperature: float,
) -> dict[str, float]:
    """Apply one-parameter temperature scaling to a three-way probability."""

    temperature = float(temperature)
    if not math.isfinite(temperature) or temperature <= 0:
        raise ValueError("temperature must be a finite value greater than 0.")

    clipped = {
        key: max(float(probabilities.get(key, 0.0)), 1e-15)
        for key in RESULT_KEYS
    }
    logits = {key: math.log(value) / temperature for key, value in clipped.items()}
    max_logit = max(logits.values())
    weights = {key: math.exp(value - max_logit) for key, value in logits.items()}
    total = sum(weights.values())
    return {key: float(weights[key] / total) for key in RESULT_KEYS}


def predict_score_distribution(
    expected_home_goals: float,
    expected_away_goals: float,
    *,
    temperature: float = 1.0,
    max_goals: int = 8,
    top_n: int = 5,
) -> ScoreDistributionPrediction:
    """Build a coherent exact-score distribution and calibrated result totals.

    The independent Poisson matrix supplies the within-result score shape.
    Temperature scaling is applied to the three result totals, after which the
    calibrated total for each result is redistributed to its exact scores.
    """

    if max_goals < 1:
        raise ValueError("max_goals must be 1 or greater.")
    if top_n <= 0:
        raise ValueError("top_n must be greater than 0.")

    home_lambda = max(float(expected_home_goals), 0.05)
    away_lambda = max(float(expected_away_goals), 0.05)
    if not math.isfinite(home_lambda) or not math.isfinite(away_lambda):
        raise ValueError("expected goals must be finite values.")

    candidates: list[dict[str, Any]] = []
    for home_goals in range(max_goals + 1):
        for away_goals in range(max_goals + 1):
            base_probability = _poisson_pmf(home_goals, home_lambda) * _poisson_pmf(
                away_goals, away_lambda
            )
            candidates.append(
                {
                    "score": f"{home_goals}-{away_goals}",
                    "home_goals": int(home_goals),
                    "away_goals": int(away_goals),
                    "result": result_key(home_goals, away_goals),
                    "poisson_probability": float(base_probability),
                }
            )

    # The finite matrix omits a very small high-score tail. Normalize before
    # deriving result totals so the public distribution always sums to one.
    base_total = sum(float(item["poisson_probability"]) for item in candidates)
    if base_total <= 0:
        raise ValueError("score distribution has zero probability mass.")
    for item in candidates:
        item["poisson_probability"] = float(item["poisson_probability"] / base_total)

    raw_result_probabilities = {key: 0.0 for key in RESULT_KEYS}
    for item in candidates:
        key = str(item["result"])
        raw_result_probabilities[key] += float(item["poisson_probability"])

    calibrated = temperature_scale_probabilities(raw_result_probabilities, temperature)
    for item in candidates:
        key = str(item["result"])
        within_result_probability = (
            float(item["poisson_probability"]) / raw_result_probabilities[key]
        )
        final_probability = calibrated[key] * within_result_probability
        item["probability"] = float(final_probability)
        # Keep this field for consumers of the previous schema. It is now a
        # real normalized score probability, not an arbitrary combined weight.
        item["combined_score"] = float(final_probability)

    candidates.sort(key=lambda item: float(item["probability"]), reverse=True)
    return ScoreDistributionPrediction(
        result_probabilities={key: float(calibrated[key]) for key in RESULT_KEYS},
        score_candidates=candidates[:top_n],
    )
