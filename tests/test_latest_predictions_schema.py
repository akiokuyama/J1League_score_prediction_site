from __future__ import annotations

import json
from pathlib import Path


def test_latest_predictions_schema() -> None:
    path = Path("outputs/latest_predictions.json")
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))

    for key in ["last_updated", "season", "league", "matches"]:
        assert key in data

    assert data.get("warnings") == []
    assert data.get("skipped_matches") == []
    assert data["matches"]

    required_match_keys = [
        "predicted_score",
        "expected_goals",
        "result_probabilities",
        "score_candidates",
        "scorer_candidates",
    ]
    for match in data["matches"]:
        for key in required_match_keys:
            assert key in match
        assert "home" in match["scorer_candidates"]
        assert "away" in match["scorer_candidates"]
        # Scorer candidates are an optional supplementary data source.  A
        # team's player-stats page can be unavailable or contain no usable
        # numeric values (for example immediately after a season starts),
        # while the match prediction itself remains valid.  The UI handles an
        # empty list by displaying "候補なし", so the schema contract is the
        # presence of a list rather than a non-empty list.
        assert isinstance(match["scorer_candidates"]["home"], list)
        assert isinstance(match["scorer_candidates"]["away"], list)
