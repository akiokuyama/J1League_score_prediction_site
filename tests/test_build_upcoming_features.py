from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.make_upcoming_features import write_source_report
from src.features.build_upcoming_features import IDENTITY_COLUMNS, build_upcoming_features


def test_build_upcoming_features_handles_no_unplayed_matches(tmp_path: Path) -> None:
    matches = pd.DataFrame(
        [
            {
                "season": "2026_special",
                "league": "J1",
                "competition": "test",
                "category": "100yj1",
                "section": 1,
                "section_label": "第1節",
                "match_date": "2026-02-06",
                "kickoff_time": "19:00",
                "home_team": "a",
                "away_team": "b",
                "home_score": 1,
                "away_score": 0,
                "stadium": "test",
                "attendance": 1000,
                "status": "finished",
                "match_url": "https://example.com",
                "match_id": "m1",
            }
        ]
    )
    matches_path = tmp_path / "matches.csv"
    features_path = tmp_path / "features.csv"
    sources_path = tmp_path / "sources.csv"
    matches.to_csv(matches_path, index=False)

    df = build_upcoming_features(
        matches_path=matches_path,
        output_path=features_path,
        sources_output_path=sources_path,
    )

    assert df.empty
    assert list(df.columns) == IDENTITY_COLUMNS
    pd.read_csv(features_path)
    pd.read_csv(sources_path)

    report = write_source_report(sources_path, tmp_path / "report.csv")
    assert report["rows"] == 0
