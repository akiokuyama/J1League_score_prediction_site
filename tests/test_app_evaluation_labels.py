from app.utils.display_labels import get_display_confidence_label, get_display_insight_label
from app.utils.evaluation import build_score_probability_explanation, get_confidence_label, get_match_insight_label


def test_match_insight_label_for_home_away_and_draw() -> None:
    assert get_match_insight_label({"home_win": 0.5, "draw": 0.3, "away_win": 0.2}) == "ホーム優勢"
    assert get_match_insight_label({"home_win": 0.2, "draw": 0.3, "away_win": 0.5}) == "アウェイ優勢"
    assert get_match_insight_label({"home_win": 0.2, "draw": 0.5, "away_win": 0.3}) == "引き分け濃厚"


def test_match_insight_label_marks_low_or_narrow_probabilities_as_close() -> None:
    assert get_match_insight_label({"home_win": 0.44, "draw": 0.31, "away_win": 0.25}) == "拮抗（ホーム寄り）"
    assert get_match_insight_label({"home_win": 0.46, "draw": 0.41, "away_win": 0.13}) == "拮抗（ホーム寄り）"
    assert get_match_insight_label({"home_win": 0.20, "draw": 0.39, "away_win": 0.41}) == "拮抗（アウェイ寄り）"


def test_confidence_label_thresholds() -> None:
    assert get_confidence_label(0.60)["label"] == "確度高め"
    assert get_confidence_label(0.45)["label"] == "やや優勢"
    assert get_confidence_label(0.44)["label"] == "拮抗"
    assert get_confidence_label(0.46, {"home_win": 0.46, "draw": 0.41, "away_win": 0.13})["label"] == "拮抗"


def test_display_labels_use_stable_confidence_api() -> None:
    probabilities = {"home_win": 0.46, "draw": 0.41, "away_win": 0.13}
    assert get_display_insight_label(probabilities) == "拮抗（ホーム寄り）"
    assert get_display_confidence_label(0.46, probabilities)["label"] == "拮抗"
    assert get_display_confidence_label(
        0.61,
        {"home_win": 0.61, "draw": 0.22, "away_win": 0.17},
    )["label"] == "確度高め"


def test_score_probability_explanation() -> None:
    same = build_score_probability_explanation({"home": 2, "away": 1}, {"home_win": 0.6, "draw": 0.2, "away_win": 0.2})
    assert same == "予測スコアと勝敗確率トップは同じ方向を示しています。"

    mismatch = build_score_probability_explanation({"home": 1, "away": 1}, {"home_win": 0.3, "draw": 0.2, "away_win": 0.5})
    assert mismatch == "スコア候補では引き分けが最有力ですが、勝敗カテゴリ全体ではアウェイ勝利が最も高くなっています。"
