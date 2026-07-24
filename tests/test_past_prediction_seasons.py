from __future__ import annotations

import json
from pathlib import Path

from app.utils.load_predictions import load_past_prediction_seasons


def test_load_past_prediction_seasons_reads_index_and_season_files(tmp_path: Path) -> None:
    index = {
        "default_season": "current",
        "seasons": [
            {"key": "current", "label": "Current", "data_file": "current.json"},
            {
                "key": "archive",
                "label": "Archive",
                "data_file": "archive.json",
                "coverage": {"note": "一部期間のみ"},
            },
        ],
    }
    (tmp_path / "index.json").write_text(json.dumps(index), encoding="utf-8")
    (tmp_path / "current.json").write_text(json.dumps({"season": "current", "matches": []}), encoding="utf-8")
    (tmp_path / "archive.json").write_text(
        json.dumps({"season": "archive", "matches": [{"match_id": "m1"}]}),
        encoding="utf-8",
    )

    loaded = load_past_prediction_seasons(tmp_path / "index.json")

    assert loaded["default_season"] == "current"
    assert [season["key"] for season in loaded["metadata"]] == ["current", "archive"]
    assert loaded["results"]["current"]["matches"] == []
    assert loaded["results"]["archive"]["matches"] == [{"match_id": "m1"}]


def test_load_past_prediction_seasons_uses_first_available_default(tmp_path: Path) -> None:
    index = {
        "default_season": "missing",
        "seasons": [{"key": "archive", "label": "Archive", "data_file": "archive.json"}],
    }
    (tmp_path / "index.json").write_text(json.dumps(index), encoding="utf-8")
    (tmp_path / "archive.json").write_text(json.dumps({"matches": []}), encoding="utf-8")

    loaded = load_past_prediction_seasons(tmp_path / "index.json")

    assert loaded["default_season"] == "archive"
