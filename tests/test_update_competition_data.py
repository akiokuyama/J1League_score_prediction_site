from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from scripts.update_competition_data import overdue_unplayed_matches


def test_overdue_unplayed_matches_detects_stale_result() -> None:
    matches = pd.DataFrame(
        [
            {
                "match_id": "past",
                "match_date": "2026-08-08",
                "kickoff_time": "19:00",
                "home_team": "kasw",
                "away_team": "mito",
                "status": "unplayed",
            },
            {
                "match_id": "future",
                "match_date": "2026-08-15",
                "kickoff_time": "19:00",
                "home_team": "kasm",
                "away_team": "nago",
                "status": "unplayed",
            },
            {
                "match_id": "finished",
                "match_date": "2026-08-08",
                "kickoff_time": "19:00",
                "home_team": "FCtk",
                "away_team": "mcd",
                "status": "finished",
            },
        ]
    )

    overdue = overdue_unplayed_matches(
        matches,
        now=datetime(2026, 8, 13, 12, 0, tzinfo=ZoneInfo("Asia/Tokyo")),
    )

    assert [row["match_id"] for row in overdue] == ["past"]
