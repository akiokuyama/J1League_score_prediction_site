"""UI labels kept compatible with hot-reloaded evaluation helpers."""

from __future__ import annotations

from app.utils.evaluation import get_confidence_label, get_strongest_outcome


def get_display_insight_label(probabilities: dict | None) -> str | None:
    """Return the match trend without depending on a reloaded helper signature."""
    strongest = get_strongest_outcome(probabilities)
    values = _valid_probability_values(probabilities)
    if len(values) >= 2:
        ordered = sorted(values, reverse=True)
        if ordered[0] < 0.45 or ordered[0] - ordered[1] < 0.10:
            return {
                "home": "拮抗（ホーム寄り）",
                "away": "拮抗（アウェイ寄り）",
                "draw": "拮抗（引き分け寄り）",
            }.get(str(strongest["key"]))
    return {
        "home": "ホーム優勢",
        "away": "アウェイ優勢",
        "draw": "引き分け濃厚",
    }.get(str(strongest["key"]))


def get_display_confidence_label(
    probability: float | int | str | None,
    probabilities: dict | None,
) -> dict[str, str]:
    """Use the stable one-argument confidence API and apply the close-match rule."""
    insight = get_display_insight_label(probabilities)
    if insight and insight.startswith("拮抗"):
        return {"label": "拮抗", "class": "badge-confidence-low"}
    return get_confidence_label(probability)


def _valid_probability_values(probabilities: dict | None) -> list[float]:
    if not isinstance(probabilities, dict):
        return []
    values: list[float] = []
    for key in ("home_win", "draw", "away_win"):
        try:
            value = float(probabilities.get(key))
        except (TypeError, ValueError):
            continue
        values.append(value / 100 if value > 1 else value)
    return values
