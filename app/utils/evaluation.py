"""Prediction evaluation and interpretation helpers."""

from __future__ import annotations

from typing import Literal

Outcome = Literal["home", "draw", "away", "unknown"]


def get_score_outcome(score: dict | None) -> Outcome:
    if not isinstance(score, dict):
        return "unknown"
    try:
        home = int(score.get("home"))
        away = int(score.get("away"))
    except (TypeError, ValueError):
        return "unknown"
    if home > away:
        return "home"
    if home < away:
        return "away"
    return "draw"


def get_strongest_outcome(probabilities: dict | None) -> dict:
    """
    戻り値例:
    {
        "key": "away",
        "label": "アウェイ勝利",
        "value": 0.5121
    }
    """
    if not isinstance(probabilities, dict):
        return {"key": "unknown", "label": "-", "value": None}
    candidates = [
        ("home", "ホーム勝利", probabilities.get("home_win")),
        ("draw", "引き分け", probabilities.get("draw")),
        ("away", "アウェイ勝利", probabilities.get("away_win")),
    ]
    valid: list[tuple[str, str, float]] = []
    for key, label, value in candidates:
        try:
            valid.append((key, label, float(value)))
        except (TypeError, ValueError):
            continue
    if not valid:
        return {"key": "unknown", "label": "-", "value": None}
    key, label, value = max(valid, key=lambda item: item[2])
    return {"key": key, "label": label, "value": value}


def get_match_insight_label(probabilities: dict | None) -> str | None:
    """
    最大確率が45%未満、または上位2結果の差が10pt未満なら拮抗表示。
    """
    strongest = get_strongest_outcome(probabilities)
    values = _valid_probability_values(probabilities)
    if len(values) >= 2:
        ordered = sorted(values.values(), reverse=True)
        is_close = ordered[0] < 0.45 or ordered[0] - ordered[1] < 0.10
        if is_close:
            return {
                "home": "拮抗（ホーム寄り）",
                "away": "拮抗（アウェイ寄り）",
                "draw": "拮抗（引き分け寄り）",
            }.get(str(strongest["key"]))
    if strongest["key"] == "home":
        return "ホーム優勢"
    if strongest["key"] == "away":
        return "アウェイ優勢"
    if strongest["key"] == "draw":
        return "引き分け濃厚"
    return None


def get_confidence_label(
    probability: float | int | str | None,
    probabilities: dict | None = None,
) -> dict[str, str]:
    insight = get_match_insight_label(probabilities) if probabilities is not None else None
    if insight and insight.startswith("拮抗"):
        return {"label": "拮抗", "class": "badge-confidence-low"}
    try:
        value = float(probability)
    except (TypeError, ValueError):
        value = 0.0
    if value > 1:
        value /= 100
    if value >= 0.60:
        return {"label": "確度高め", "class": "badge-confidence-high"}
    if value >= 0.45:
        return {"label": "やや優勢", "class": "badge-confidence-medium"}
    return {"label": "拮抗", "class": "badge-confidence-low"}


def _valid_probability_values(probabilities: dict | None) -> dict[str, float]:
    if not isinstance(probabilities, dict):
        return {}
    values: dict[str, float] = {}
    for key in ("home_win", "draw", "away_win"):
        try:
            value = float(probabilities.get(key))
        except (TypeError, ValueError):
            continue
        if value > 1:
            value /= 100
        values[key] = value
    return values


def build_score_probability_explanation(predicted_score: dict | None, result_probabilities: dict | None) -> str:
    score_outcome = get_score_outcome(predicted_score)
    strongest = get_strongest_outcome(result_probabilities)
    probability_outcome = strongest.get("key")

    if score_outcome == "unknown" or probability_outcome == "unknown":
        return "予測スコアと勝敗確率トップは、計算単位が異なる参考情報です。"
    if score_outcome == probability_outcome:
        return "予測スコアと勝敗確率トップは同じ方向を示しています。"

    score_label = outcome_label(score_outcome)
    probability_label = outcome_label(str(probability_outcome))
    if score_outcome == "draw":
        return f"スコア候補では引き分けが最有力ですが、勝敗カテゴリ全体では{probability_label}が最も高くなっています。"
    return f"単一スコアでは{score_label}が最有力ですが、勝敗カテゴリ全体では{probability_label}が最も高くなっています。"


def evaluate_prediction(predicted_score: dict | None, actual_score: dict | None) -> dict:
    """
    戻り値例:
    {
        "result_hit": True,
        "score_hit": False,
        "result_label": "勝敗的中",
        "score_label": "スコア外れ",
        "predicted_outcome": "home",
        "actual_outcome": "home",
    }
    """
    predicted_outcome = get_score_outcome(predicted_score)
    actual_outcome = get_score_outcome(actual_score)
    result_hit = predicted_outcome != "unknown" and predicted_outcome == actual_outcome
    score_hit = _score_values(predicted_score) == _score_values(actual_score) and _score_values(actual_score) is not None
    return {
        "result_hit": result_hit,
        "score_hit": score_hit,
        "result_label": "勝敗的中" if result_hit else "勝敗外れ",
        "score_label": "スコア的中" if score_hit else "スコア外れ",
        "predicted_outcome": predicted_outcome,
        "actual_outcome": actual_outcome,
    }


def outcome_label(outcome: Outcome | str) -> str:
    return {
        "home": "ホーム勝利",
        "draw": "引き分け",
        "away": "アウェイ勝利",
        "unknown": "-",
    }.get(str(outcome), "-")


def _score_values(score: dict | None) -> tuple[int, int] | None:
    if not isinstance(score, dict):
        return None
    try:
        return int(score.get("home")), int(score.get("away"))
    except (TypeError, ValueError):
        return None
