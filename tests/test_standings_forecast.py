from __future__ import annotations

import json
from datetime import datetime
from itertools import permutations
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from app.utils.standings_loader import load_standings_forecasts
from scripts.validate_standings_forecast import validate_standings_forecast
from src.predict.standings_forecast import build_standings_forecast, write_standings_forecast


TEAMS = ["kasm", "uraw", "kasw", "FCtk"]


def _write_inputs(tmp_path: Path, *, omit_pair: tuple[str, str] | None = None) -> tuple[Path, Path]:
    rows = []
    predictions = []
    for section, (home, away) in enumerate(permutations(TEAMS, 2), start=1):
        if (home, away) == omit_pair:
            continue
        match_id = f"m-{home}-{away}"
        rows.append(
            {
                "match_id": match_id,
                "match_date": f"2026-08-{section:02d}",
                "home_team": home,
                "away_team": away,
                "home_score": None,
                "away_score": None,
                "status": "unplayed",
            }
        )
        predictions.append(
            {
                "match_id": match_id,
                "home_team": home,
                "away_team": away,
                "expected_goals": {"home": 1.45, "away": 1.10},
                "result_probabilities": {"home_win": 0.45, "draw": 0.27, "away_win": 0.28},
            }
        )
    matches_path = tmp_path / "matches.csv"
    predictions_path = tmp_path / "predictions.json"
    pd.DataFrame(rows).to_csv(matches_path, index=False)
    predictions_path.write_text(
        json.dumps(
            {
                "last_updated": "2026-07-20T12:00:00+09:00",
                "season": "2026_27",
                "league": "J1",
                "competition": "test",
                "model_version": "test-model",
                "matches": predictions,
            }
        ),
        encoding="utf-8",
    )
    return matches_path, predictions_path


def test_build_standings_forecast_probabilities_are_coherent(tmp_path: Path) -> None:
    matches_path, predictions_path = _write_inputs(tmp_path)
    generated = datetime(2026, 7, 20, 12, 30, tzinfo=ZoneInfo("Asia/Tokyo"))

    forecast = build_standings_forecast(
        matches_path,
        predictions_path,
        simulations=500,
        seed=7,
        generated_at=generated,
        expected_team_count=4,
    )

    assert forecast["generated_at"] == "2026-07-20T12:30:00+09:00"
    assert forecast["fixture_summary"]["simulated_remaining_matches"] == 12
    assert forecast["warnings"] == []
    assert [team["predicted_rank"] for team in forecast["teams"]] == [1, 2, 3, 4]
    assert sum(team["champion_probability"] for team in forecast["teams"]) == 1.0
    assert sum(team["top3_probability"] for team in forecast["teams"]) == 3.0
    assert sum(team["bottom3_probability"] for team in forecast["teams"]) == 3.0
    assert all(team["current_rank"] is None for team in forecast["teams"])


def test_incomplete_schedule_is_supplemented_from_reverse_fixture(tmp_path: Path) -> None:
    matches_path, predictions_path = _write_inputs(tmp_path, omit_pair=("kasm", "uraw"))

    forecast = build_standings_forecast(
        matches_path,
        predictions_path,
        simulations=300,
        seed=11,
        expected_team_count=4,
    )

    summary = forecast["fixture_summary"]
    assert summary["official_schedule_matches"] == 11
    assert summary["supplemented_matches"] == 1
    assert summary["simulated_remaining_matches"] == 12
    warning = next(item for item in forecast["warnings"] if item["code"] == "missing_official_fixture_supplemented")
    assert warning["home_team"] == "kasm"
    assert warning["away_team"] == "uraw"
    assert warning["method"] == "reverse_fixture_probabilities_swapped"


def test_write_validate_and_load_forecast_history(tmp_path: Path) -> None:
    matches_path, predictions_path = _write_inputs(tmp_path)
    forecast = build_standings_forecast(
        matches_path,
        predictions_path,
        simulations=300,
        seed=3,
        generated_at=datetime(2026, 7, 20, 10, 0, tzinfo=ZoneInfo("Asia/Tokyo")),
        expected_team_count=4,
    )
    latest, history = write_standings_forecast(
        forecast,
        tmp_path / "standings" / "latest.json",
        tmp_path / "standings" / "history",
    )

    assert history is not None and history.exists()
    index_path = latest.parent / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    assert index["default_forecast"] == "2026-07-20T10:00:00+09:00"
    assert index["forecasts"] == [
        {
            "generated_at": "2026-07-20T10:00:00+09:00",
            "data_file": "history/standings_forecast_20260720_100000.json",
            "data_as_of": {"label": "開幕前", "completed_matches": 0},
        }
    ]
    assert validate_standings_forecast(latest)["simulation_count"] == 300
    loaded = load_standings_forecasts(latest, history.parent)
    assert len(loaded) == 1
    assert loaded[0]["generated_at"] == "2026-07-20T10:00:00+09:00"


def test_standings_forecast_index_keeps_snapshots_newest_first(tmp_path: Path) -> None:
    matches_path, predictions_path = _write_inputs(tmp_path)
    forecast = build_standings_forecast(
        matches_path,
        predictions_path,
        simulations=300,
        seed=3,
        generated_at=datetime(2026, 7, 20, 10, 0, tzinfo=ZoneInfo("Asia/Tokyo")),
        expected_team_count=4,
    )
    latest_path = tmp_path / "standings" / "latest.json"
    history_dir = tmp_path / "standings" / "history"
    write_standings_forecast(forecast, latest_path, history_dir)

    newer = {**forecast, "generated_at": "2026-07-27T10:00:00+09:00"}
    write_standings_forecast(newer, latest_path, history_dir)

    index = json.loads((latest_path.parent / "index.json").read_text(encoding="utf-8"))
    assert index["default_forecast"] == "2026-07-27T10:00:00+09:00"
    assert [item["generated_at"] for item in index["forecasts"]] == [
        "2026-07-27T10:00:00+09:00",
        "2026-07-20T10:00:00+09:00",
    ]
    assert [item["data_file"] for item in index["forecasts"]] == [
        "history/standings_forecast_20260727_100000.json",
        "history/standings_forecast_20260720_100000.json",
    ]
