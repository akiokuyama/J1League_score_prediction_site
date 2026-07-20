"""Build feature rows for upcoming matches using historical fallbacks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from src.config import FEATURE_DATA_DIR, PROJECT_ROOT
from src.data.scraping import safe_write_csv
from src.data.team_master import to_dataset_code
from src.features.tactical import backline_matchup


IDENTITY_COLUMNS = [
    "season",
    "league",
    "competition",
    "category",
    "section",
    "match_date",
    "kickoff_time",
    "home_team",
    "away_team",
    "status",
    "match_id",
]


def _base_row(history: pd.DataFrame) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for col in history.columns:
        series = history[col]
        if pd.api.types.is_numeric_dtype(series):
            row[col] = float(series.median()) if series.notna().any() else 0.0
        else:
            mode = series.dropna().mode()
            row[col] = mode.iloc[0] if not mode.empty else None
    return row


def _apply_team_side_values(row: dict[str, Any], history: pd.DataFrame, team: str, side: str) -> None:
    team_df = history[history[side].astype(str) == team]
    if team_df.empty:
        return
    prefix = f"{side}_"
    for col in history.columns:
        if not col.startswith(prefix):
            continue
        series = team_df[col]
        if pd.api.types.is_numeric_dtype(series):
            row[col] = float(series.median()) if series.notna().any() else row.get(col, 0)
        else:
            mode = series.dropna().mode()
            if not mode.empty:
                row[col] = mode.iloc[0]


def _recompute_simple_diffs(row: dict[str, Any]) -> None:
    for home_key, away_key, diff_key in [
        ("Home_Current_Rank", "Away_Current_Rank", "Rank_Diff"),
        ("Home_Elo_Before", "Away_Elo_Before", "Elo_Diff"),
        ("Home_Market_Value", "Away_Market_Value", "Market_Value_Diff"),
    ]:
        if home_key in row and away_key in row and diff_key in row:
            try:
                row[diff_key] = float(row[home_key]) - float(row[away_key])
            except Exception:  # noqa: BLE001
                pass


def _load_market_values(path: str | Path = "Data/processed/market_values_2026_special_clean.csv") -> dict[str, float]:
    file = Path(path)
    if not file.is_absolute():
        file = PROJECT_ROOT / file
    if not file.exists():
        return {}
    df = pd.read_csv(file)
    if "team" not in df.columns or "market_value" not in df.columns:
        return {}
    values = df.dropna(subset=["team", "market_value"])
    normalized: dict[str, float] = {}
    for _, row in values.iterrows():
        value = float(row["market_value"])
        # ML_dataset stores Transfermarkt values in EUR millions.  The current
        # scraper stores raw EUR, so align the unit before model inference.
        normalized[str(row["team"])] = value / 1_000_000 if value >= 1_000 else value
    return normalized


def _load_football_lab_values(
    *,
    kagi_path: str | Path = "Data/raw/football_lab/kagi_2026_special.csv",
    expected_path: str | Path = "Data/raw/football_lab/expected_2026_special.csv",
) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
    agi: dict[str, float] = {}
    kagi: dict[str, float] = {}
    expected: dict[str, float] = {}

    kagi_file = Path(kagi_path)
    if not kagi_file.is_absolute():
        kagi_file = PROJECT_ROOT / kagi_file
    if kagi_file.exists():
        df = pd.read_csv(kagi_file)
        if "team" in df.columns:
            if "AGI" in df.columns:
                for _, row in df.dropna(subset=["team", "AGI"]).iterrows():
                    agi[str(row["team"])] = float(row["AGI"])
            if "KAGI" in df.columns:
                for _, row in df.dropna(subset=["team", "KAGI"]).iterrows():
                    kagi[str(row["team"])] = float(row["KAGI"])

    expected_file = Path(expected_path)
    if not expected_file.is_absolute():
        expected_file = PROJECT_ROOT / expected_file
    if expected_file.exists():
        df = pd.read_csv(expected_file)
        if "team" in df.columns and "期待値" in df.columns:
            attacking = df[df.get("table_index", 0) == 0] if "table_index" in df.columns else df
            for _, row in attacking.dropna(subset=["team", "期待値"]).iterrows():
                # Football Lab publishes expected goals as a per-match rate.
                expected[str(row["team"])] = float(row["期待値"])

    return agi, kagi, expected


def _load_formations(path: str | Path = "Data/processed/formations_2026_special_clean.csv") -> dict[str, str]:
    file = Path(path)
    if not file.is_absolute():
        file = PROJECT_ROOT / file
    if not file.exists():
        return {}
    df = pd.read_csv(file)
    if "team" not in df.columns or "formation" not in df.columns:
        return {}
    values = df.dropna(subset=["team", "formation"])
    values = values[values["formation"].astype(str) != "Unknown"]
    return {str(row["team"]): str(row["formation"]) for _, row in values.iterrows()}


def _apply_current_season_values(row: dict[str, Any], home: str, away: str, market_values: dict[str, float], agi: dict[str, float], kagi: dict[str, float], expected: dict[str, float]) -> None:
    if home in market_values and "Home_Market_Value" in row:
        row["Home_Market_Value"] = market_values[home]
    if away in market_values and "Away_Market_Value" in row:
        row["Away_Market_Value"] = market_values[away]
    if home in agi and "Home_AGI" in row:
        row["Home_AGI"] = agi[home]
    if away in agi and "Away_AGI" in row:
        row["Away_AGI"] = agi[away]
    if home in kagi and "Home_KAGI" in row:
        row["Home_KAGI"] = kagi[home]
    if away in kagi and "Away_KAGI" in row:
        row["Away_KAGI"] = kagi[away]
    if home in expected and "Home_Rolling_xG" in row:
        row["Home_Rolling_xG"] = expected[home]
    if away in expected and "Away_Rolling_xG" in row:
        row["Away_Rolling_xG"] = expected[away]


def _apply_current_formations(row: dict[str, Any], home: str, away: str, formations: dict[str, str]) -> None:
    if home in formations:
        row["Home_Formation"] = formations[home]
    if away in formations:
        row["Away_Formation"] = formations[away]


def _write_empty_upcoming_outputs(
    output_path: str | Path,
    sources_output_path: str | Path,
) -> pd.DataFrame:
    df = pd.DataFrame(columns=IDENTITY_COLUMNS)
    safe_write_csv(df, output_path)
    safe_write_csv(pd.DataFrame(columns=IDENTITY_COLUMNS), sources_output_path)
    return df


def build_upcoming_features(
    *,
    matches_path: str | Path = "Data/processed/matches_2026_special_clean.csv",
    history_path: str | Path = "Data/ML_dataset.csv",
    model_features_path: str | Path = "Models/model_features.pkl",
    output_path: str | Path = FEATURE_DATA_DIR / "upcoming_features_2026_special.csv",
    sources_output_path: str | Path = FEATURE_DATA_DIR / "upcoming_features_2026_special_sources.csv",
    market_values_path: str | Path = "Data/processed/market_values_2026_special_clean.csv",
    kagi_path: str | Path = "Data/raw/football_lab/kagi_2026_special.csv",
    expected_path: str | Path = "Data/raw/football_lab/expected_2026_special.csv",
    formations_path: str | Path = "Data/processed/formations_2026_special_clean.csv",
    only_unplayed: bool = True,
) -> pd.DataFrame:
    matches_file = Path(matches_path)
    if not matches_file.is_absolute():
        matches_file = PROJECT_ROOT / matches_file
    if not matches_file.exists():
        return _write_empty_upcoming_outputs(output_path, sources_output_path)

    matches = pd.read_csv(matches_file)
    if matches.empty:
        return _write_empty_upcoming_outputs(output_path, sources_output_path)

    if only_unplayed and "status" in matches.columns:
        matches = matches[matches["status"].astype(str).isin(["unplayed", "postponed_or_tbd"])]
    if {"home_team", "away_team"}.issubset(matches.columns):
        known_home = ~matches["home_team"].astype(str).isin(["tbd", "未定", "nan", ""])
        known_away = ~matches["away_team"].astype(str).isin(["tbd", "未定", "nan", ""])
        matches = matches[known_home & known_away]
    if matches.empty:
        return _write_empty_upcoming_outputs(output_path, sources_output_path)

    history_file = Path(history_path)
    if not history_file.is_absolute():
        history_file = PROJECT_ROOT / history_file
    history = pd.read_csv(history_file)
    model_features = joblib.load(model_features_path)
    base = _base_row(history)
    market_values = _load_market_values(market_values_path)
    agi, kagi, expected = _load_football_lab_values(kagi_path=kagi_path, expected_path=expected_path)
    formations = _load_formations(formations_path)

    rows: list[dict[str, Any]] = []
    source_rows: list[dict[str, Any]] = []
    for _, match in matches.iterrows():
        home = to_dataset_code(str(match.get("home_team", "")))
        away = to_dataset_code(str(match.get("away_team", "")))
        row = dict(base)
        sources: dict[str, str] = {}
        for col in row:
            if pd.api.types.is_numeric_dtype(history[col]) if col in history.columns else False:
                sources[col] = "fallback_league_median"
            else:
                sources[col] = "fallback_mode"
        for col in ["Attendance", "Stadium_Fill_Rate"]:
            if col in row:
                row[col] = 0.0
                sources[col] = "excluded_post_match_feature"
        _apply_team_side_values(row, history, home, "Home")
        if not history[history["Home"].astype(str) == home].empty:
            for col in history.columns:
                if col.startswith("Home_"):
                    sources[col] = "fallback_team_median" if pd.api.types.is_numeric_dtype(history[col]) else "fallback_team_mode"
        _apply_team_side_values(row, history, away, "Away")
        if not history[history["Away"].astype(str) == away].empty:
            for col in history.columns:
                if col.startswith("Away_"):
                    sources[col] = "fallback_team_median" if pd.api.types.is_numeric_dtype(history[col]) else "fallback_team_mode"
        _apply_current_season_values(row, home, away, market_values, agi, kagi, expected)
        for side, team in [("Home", home), ("Away", away)]:
            if team in market_values and f"{side}_Market_Value" in row:
                sources[f"{side}_Market_Value"] = "actual_latest_pre_match_snapshot"
            if team in agi and f"{side}_AGI" in row:
                sources[f"{side}_AGI"] = "actual_latest_pre_match_snapshot"
            if team in kagi and f"{side}_KAGI" in row:
                sources[f"{side}_KAGI"] = "actual_latest_pre_match_snapshot"
            if team in expected and f"{side}_Rolling_xG" in row:
                sources[f"{side}_Rolling_xG"] = "actual_latest_pre_match_snapshot"
        _apply_current_formations(row, home, away, formations)
        if home in formations and "Home_Formation" in row:
            sources["Home_Formation"] = "actual_current_season_modal_formation"
        if away in formations and "Away_Formation" in row:
            sources["Away_Formation"] = "actual_current_season_modal_formation"
        row.update(
            {
                "Season": str(match.get("season", "2026_special") or "2026_special"),
                "Section": int(float(match.get("section", 0) or 0)),
                "Date": match.get("match_date"),
                "Home": home,
                "Away": away,
                "Score": "0-0",
                "Home_Goals": 0,
                "Away_Goals": 0,
                "Goal_Diff": 0,
                "Match_Result": 0,
                "Backline_Matchup": backline_matchup(
                    str(row.get("Home_Formation", "4-4-2")),
                    str(row.get("Away_Formation", "4-4-2")),
                ),
            }
        )
        for col in ["Season", "Section", "Date", "Home", "Away", "Score", "Home_Goals", "Away_Goals", "Goal_Diff", "Match_Result"]:
            sources[col] = "actual_schedule" if col in ["Season", "Section", "Date", "Home", "Away"] else "prediction_placeholder"
        sources["Backline_Matchup"] = "derived_from_modal_formation_snapshot"
        _recompute_simple_diffs(row)
        for col in ["Rank_Diff", "Elo_Diff", "Market_Value_Diff"]:
            if col in row:
                sources[col] = "derived"
        for col in model_features:
            row.setdefault(col, 0)
            sources.setdefault(col, "model_fill_zero")
        for col in IDENTITY_COLUMNS:
            row[col] = match.get(col)
            sources[col] = "actual_schedule"
        rows.append(row)
        source_rows.append(sources)

    df = pd.DataFrame(rows)
    # Attendance and stadium fill rate are post-match facts.  Do not retain
    # even zero-filled placeholders in inference files, so they cannot be
    # accidentally reintroduced into a future model or UI data flow.
    excluded = {"Attendance", "Stadium_Fill_Rate", "Weather"}
    df = df[[col for col in df.columns if col not in excluded and not str(col).startswith("Weather_")]]
    sources_df = pd.DataFrame(source_rows)
    sources_df = sources_df.reindex(columns=df.columns, fill_value="not_tracked")
    safe_write_csv(df, output_path)
    safe_write_csv(sources_df, sources_output_path)
    return df
