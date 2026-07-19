from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from scripts.build_point_in_time_training_dataset import build_point_in_time_training_dataset
from src.features.point_in_time import (
    align_legacy_model_units,
    load_legacy_aggregate_priors,
    rebuild_historical_training_features,
)
from src.features.snapshots import save_upcoming_feature_snapshot


def test_save_upcoming_feature_snapshot(tmp_path: Path) -> None:
    features = pd.DataFrame(
        [
            {
                "match_id": "m1",
                "Season": "2026_special",
                "Section": 18,
                "Home": "home",
                "Away": "away",
            }
        ]
    )
    sources = pd.DataFrame([{"match_id": "actual_schedule", "Season": "actual_schedule"}])

    paths = save_upcoming_feature_snapshot(
        features,
        sources=sources,
        snapshot_dir=tmp_path,
        created_at=datetime(2026, 5, 24, 12, 0, 0),
    )

    assert paths.features.exists()
    assert paths.sources is not None and paths.sources.exists()
    assert paths.metadata.exists()
    assert paths.features.name == "upcoming_features_2026_special_asof_20260524_120000.csv"
    saved = pd.read_csv(paths.features)
    assert saved.loc[0, "feature_as_of"] == "20260524_120000"
    assert saved.loc[0, "season_key"] == "2026_special"
    assert saved.loc[0, "feature_snapshot_source"] == "weekly_prediction_snapshot"


def test_build_point_in_time_training_dataset_uses_snapshot_then_reconstructed_features(tmp_path: Path) -> None:
    reference = pd.DataFrame(
        columns=[
            "Season",
            "Section",
            "Date",
            "Home",
            "Score",
            "Away",
            "Weather",
            "Home_Goals",
            "Away_Goals",
            "Goal_Diff",
            "Match_Result",
            "Home_Current_Rank",
        ]
    )
    reference_path = tmp_path / "ML_dataset.csv"
    reference.to_csv(reference_path, index=False)

    matches = pd.DataFrame(
        [
            {
                "season": "2026_special",
                "section": 1,
                "match_date": "2026-02-06",
                "kickoff_time": "19:00",
                "home_team": "a",
                "away_team": "b",
                "home_score": 2,
                "away_score": 1,
                "status": "finished",
                "match_id": "m1",
            },
            {
                "season": "2026_special",
                "section": 18,
                "match_date": "2026-05-30",
                "kickoff_time": "14:00",
                "home_team": "c",
                "away_team": "d",
                "home_score": 0,
                "away_score": 0,
                "status": "finished",
                "match_id": "m2",
            },
        ]
    )
    matches_path = tmp_path / "matches.csv"
    matches.to_csv(matches_path, index=False)

    fallback = pd.DataFrame(
        [
            {
                "match_id": "m1",
                "Season": "2026_special",
                "Section": 1,
                "Date": "2026-02-06",
                "Home": "a",
                "Score": "0-0",
                "Away": "b",
                "Home_Goals": 0,
                "Away_Goals": 0,
                "Goal_Diff": 0,
                "Match_Result": 0,
                "Home_Current_Rank": 9,
            }
        ]
    )
    fallback_path = tmp_path / "fallback.csv"
    fallback.to_csv(fallback_path, index=False)

    save_upcoming_feature_snapshot(
        pd.DataFrame(
            [
                {
                    "match_id": "m2",
                    "Season": "2026_special",
                    "Section": 18,
                    "Date": "2026-05-30",
                    "Home": "c",
                    "Score": "0-0",
                    "Away": "d",
                    "Home_Goals": 0,
                    "Away_Goals": 0,
                    "Goal_Diff": 0,
                    "Match_Result": 0,
                    "Home_Current_Rank": 3,
                }
            ]
        ),
        snapshot_dir=tmp_path / "snapshots",
        created_at=datetime(2026, 5, 24, 12, 0, 0),
    )

    dataset, sources, report = build_point_in_time_training_dataset(
        season="2026_special",
        reference_dataset=reference_path,
        matches_path=matches_path,
        fallback_features_path=fallback_path,
        snapshot_dir=tmp_path / "snapshots",
    )

    assert len(dataset) == 2
    assert report["snapshot_rows"] == 1
    assert report["fallback_rows"] == 0
    assert report["reconstructed_rows"] == 1
    assert report["season_key"] == "2026_special"
    assert report["season_label"] == "2026_special"
    assert sources["feature_source"].tolist() == [
        "reconstructed_pre_match",
        "snapshot_overlay_on_reconstructed_pre_match",
    ]
    assert dataset["Season"].tolist() == ["2026_special", "2026_special"]
    assert dataset["Score"].tolist() == ["2-1", "0-0"]
    assert dataset["Match_Result"].tolist() == [1, 0]
    # The legacy fallback contains a season-end rank of 9. Strict mode must
    # rebuild the opening match before any result is known instead.
    # Dynamic standings are always reconstructed; snapshots only overlay
    # external pre-match measurements such as xG/AGI/KAGI and formation.
    assert dataset["Home_Current_Rank"].tolist() == [1.0, 2.0]


def test_rebuilt_features_do_not_let_same_day_results_change_each_other(tmp_path: Path) -> None:
    reference = pd.DataFrame(
        columns=[
            "Season", "Section", "Date", "Home", "Score", "Away", "Weather",
            "Home_Goals", "Away_Goals", "Goal_Diff", "Match_Result",
            "Home_Current_Points", "Away_Current_Points", "Home_Elo_Before", "Away_Elo_Before",
        ]
    )
    reference_path = tmp_path / "ML_dataset.csv"
    reference.to_csv(reference_path, index=False)
    matches = pd.DataFrame(
        [
            {"season": "2026_special", "section": 1, "match_date": "2026-02-06", "kickoff_time": "19:00", "home_team": "a", "away_team": "b", "home_score": 3, "away_score": 0, "status": "finished", "match_id": "m1"},
            {"season": "2026_special", "section": 1, "match_date": "2026-02-06", "kickoff_time": "19:00", "home_team": "c", "away_team": "d", "home_score": 0, "away_score": 1, "status": "finished", "match_id": "m2"},
        ]
    )
    matches_path = tmp_path / "matches.csv"
    matches.to_csv(matches_path, index=False)
    empty_fallback = tmp_path / "unused.csv"
    pd.DataFrame().to_csv(empty_fallback, index=False)

    dataset, _, report = build_point_in_time_training_dataset(
        season="2026_special",
        reference_dataset=reference_path,
        matches_path=matches_path,
        fallback_features_path=empty_fallback,
        snapshot_dir=tmp_path / "snapshots",
    )

    assert report["reconstructed_rows"] == 2
    assert dataset["Home_Current_Points"].tolist() == [0.0, 0.0]
    assert dataset["Away_Current_Points"].tolist() == [0.0, 0.0]
    assert dataset["Home_Elo_Before"].tolist() == [1500.0, 1500.0]


def test_legacy_aggregate_priors_keep_historical_feature_units(tmp_path: Path) -> None:
    processed = tmp_path / "Data" / "processed"
    football_lab = tmp_path / "Data" / "raw" / "football_lab"
    processed.mkdir(parents=True)
    football_lab.mkdir(parents=True)
    pd.DataFrame([{"team": "a", "market_value": 23_000_000}]).to_csv(
        processed / "market_values_2026_special_clean.csv", index=False
    )
    pd.DataFrame([{"team": "a", "期待値": 1.9, "table_index": 0}]).to_csv(
        football_lab / "expected_2026_special.csv", index=False
    )
    pd.DataFrame([{"team": "a", "AGI": 57.0, "KAGI": None, "table_index": 0}, {"team": "a", "AGI": None, "KAGI": 51.0, "table_index": 1}]).to_csv(
        football_lab / "kagi_2026_special.csv", index=False
    )
    matches = pd.DataFrame([{"home_team": "a", "away_team": "b"}])

    priors = load_legacy_aggregate_priors(matches, project_root=tmp_path)

    assert priors["a"]["Market_Value"] == 23.0
    assert priors["a"]["Rolling_xG"] == 1.9
    assert priors["a"]["AGI"] == 57.0
    assert priors["a"]["KAGI"] == 51.0


def test_snapshot_unit_alignment_restores_legacy_divided_values() -> None:
    raw = pd.Series(
        {
            "Home_Market_Value": 23_000_000,
            "Away_Market_Value": 10_000_000,
            "Market_Value_Diff": 13_000_000,
            "Home_Rolling_xG": 1.9 / 38,
            "Home_AGI": 57.0 / 38,
            "Away_KAGI": 51.0 / 38,
        }
    )
    aligned = align_legacy_model_units(raw)

    assert aligned["Home_Market_Value"] == 23.0
    assert aligned["Market_Value_Diff"] == 13.0
    assert aligned["Home_Rolling_xG"] == 1.9
    assert aligned["Home_AGI"] == 57.0
    assert aligned["Away_KAGI"] == 51.0


def test_historical_rebuild_excludes_attendance_and_uses_prior_modal_formation() -> None:
    rows = []
    for section, date, home_formation in [
        (1, "2025-02-01", "3-4-2-1"),
        (2, "2025-02-08", "4-4-2"),
        (3, "2025-02-15", "3-4-2-1"),
    ]:
        rows.append(
            {
                "Season": 2025,
                "Section": section,
                "Date": date,
                "Home": "a",
                "Away": "b",
                "Score": "1-0",
                "Home_Goals": 1,
                "Away_Goals": 0,
                "Goal_Diff": 1,
                "Match_Result": 1,
                "Attendance": 12345,
                "Stadium_Fill_Rate": 0.5,
                "Home_Formation": home_formation,
                "Away_Formation": "4-4-2",
                "Home_Rolling_xG": 1.9 / 3,
                "Away_Rolling_xG": 1.2 / 3,
                "Home_AGI": 57 / 3,
                "Home_KAGI": 50 / 3,
                "Away_AGI": 49 / 3,
                "Away_KAGI": 48 / 3,
                "Home_Current_Rank": 0,
                "Away_Current_Rank": 0,
                "Rank_Diff": 0,
                "Home_Rank_Delta_3": 0,
                "Away_Rank_Delta_3": 0,
                "Home_Elo_Before": 1500,
                "Away_Elo_Before": 1500,
                "Elo_Diff": 0,
                "Home_Current_Points": 0,
                "Away_Current_Points": 0,
                "Home_Rolling_Points_5": 0,
                "Away_Rolling_Points_5": 0,
                "H2H_Score_Avg": 0,
                "Home_Season_Progress": 0,
                "Away_Season_Progress": 0,
                "Home_Urgency_Score": 0,
                "Away_Urgency_Score": 0,
                "Backline_Matchup": "4_vs_4",
            }
        )
    rebuilt = rebuild_historical_training_features(pd.DataFrame(rows))

    assert rebuilt.features["Attendance"].eq(0).all()
    assert rebuilt.features["Stadium_Fill_Rate"].eq(0).all()
    assert rebuilt.features["Home_Formation"].tolist() == ["4-4-2", "3-4-2-1", "4-4-2"]
    assert rebuilt.features["Home_Rolling_xG"].tolist() == [1.9, 1.9, 1.9]
    assert rebuilt.sources["Home_Rolling_xG"].eq("historical_final_snapshot_estimate_restored_unit").all()
