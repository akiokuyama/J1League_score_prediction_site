from __future__ import annotations

import pandas as pd

from src.data.scrape_player_stats import normalize_player_table_columns, normalize_player_stats


def test_normalize_player_table_columns_repairs_mojibake_headers() -> None:
    # The values are in the normal Football Lab order, but the last five
    # headers intentionally represent the mojibake seen in the failed run.
    table = pd.DataFrame(
        [[1, "FW", "選手A", 10.0, 2.0, 2, 1, 0]],
        columns=["順位", "Unnamed: 1", "Unnamed: 2", "broken-cbp", "broken-cbp90", "broken-games", "broken-goals", "broken-assists"],
    )

    normalized = normalize_player_stats(normalize_player_table_columns(table))

    row = normalized.iloc[0]
    assert row["player"] == "選手A"
    assert row["cbp"] == 10.0
    assert row["cbp_90"] == 2.0
    assert row["played_games"] == 2
    assert row["goals"] == 1
    assert row["assists"] == 0
    assert row["scorer_score"] > 0
