"""Leakage-safe feature reconstruction for completed matches.

Dynamic match-state values are rebuilt from information available before
each kick-off.  Where no historical third-party snapshot exists, explicitly
approved season estimates may be assigned in their published units and are
labelled as estimates in the generated provenance manifest.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.features.elo import expected_score
from src.features.tactical import backline_matchup


TARGET_COLUMNS = ["Score", "Home_Goals", "Away_Goals", "Goal_Diff", "Match_Result"]
IDENTITY_TO_MODEL = {
    "season": "Season",
    "section": "Section",
    "match_date": "Date",
    "home_team": "Home",
    "away_team": "Away",
    "stadium": "Stadium",
}
DEFAULT_ELO = 1500.0
ELO_K = 20.0
LEGACY_AGGREGATE_DIVISOR = 38.0
POST_MATCH_FEATURES = {"Attendance", "Stadium_Fill_Rate"}


@dataclass(frozen=True)
class RebuiltFeatures:
    features: pd.DataFrame
    sources: pd.DataFrame


def align_legacy_model_units(source: pd.Series) -> pd.Series:
    """Restore snapshots to the corrected point-in-time feature units.

    Football Lab's expected-goals column is already a per-match rate and
    AGI/KAGI are indices.  Older app snapshots sometimes divided these values
    by 38 to match the legacy notebook; restore those snapshots here.  Market
    values remain normalized to EUR millions.
    """
    row = source.copy()
    for column in ["Home_Market_Value", "Away_Market_Value", "Market_Value_Diff"]:
        if column in row.index and abs(_as_number(row[column])) >= 1_000:
            row[column] = _as_number(row[column]) / 1_000_000
    for column in ["Home_Rolling_xG", "Away_Rolling_xG"]:
        value = _as_number(row.get(column))
        if column in row.index and 0 < abs(value) < 0.2:
            row[column] = value * LEGACY_AGGREGATE_DIVISOR
    for column in ["Home_AGI", "Home_KAGI", "Away_AGI", "Away_KAGI"]:
        value = _as_number(row.get(column))
        if column in row.index and 0 < abs(value) < 10:
            row[column] = value * LEGACY_AGGREGATE_DIVISOR
    return row


def load_legacy_aggregate_priors(
    matches: pd.DataFrame,
    *,
    project_root: str | Path,
    normalization_divisor: float = 38.0,
) -> dict[str, dict[str, Any]]:
    """Load the season-end estimates needed when snapshots are unavailable.

    Football Lab xG is already a per-match value and AGI/KAGI are published
    indices, so these three fields must not be divided by the round count.
    Final team-stat totals are converted to per-match figures.  A single
    season formation/market-value value is retained only as a compatibility
    estimate and every use is identified in the generated source manifest.
    """
    del normalization_divisor  # retained for backward-compatible CLI calls
    root = Path(project_root)
    priors: dict[str, dict[str, Any]] = defaultdict(dict)

    def read_csv(relative_path: str) -> pd.DataFrame:
        path = root / relative_path
        return pd.read_csv(path) if path.exists() else pd.DataFrame()

    market = read_csv("Data/processed/market_values_2026_special_clean.csv")
    for _, item in market.dropna(subset=["team", "market_value"]).iterrows():
        value = _as_number(item.market_value)
        # Historical ML_dataset stores Transfermarkt values in EUR millions
        # (for example 17.79), whereas the current scraper stores EUR units.
        priors[str(item.team)]["Market_Value"] = value / 1_000_000 if value >= 1_000 else value

    formations = read_csv("Data/processed/formations_2026_special_clean.csv")
    if {"team", "formation"}.issubset(formations.columns):
        for _, item in formations.dropna(subset=["team", "formation"]).iterrows():
            formation = str(item.formation)
            if formation and formation != "Unknown":
                priors[str(item.team)]["Formation"] = formation

    expected = read_csv("Data/raw/football_lab/expected_2026_special.csv")
    if not expected.empty and {"team", "期待値"}.issubset(expected.columns):
        attacking = expected[expected.get("table_index", 0) == 0]
        for _, item in attacking.dropna(subset=["team", "期待値"]).iterrows():
            priors[str(item.team)]["Rolling_xG"] = _as_number(item["期待値"])

    agi_kagi = read_csv("Data/raw/football_lab/kagi_2026_special.csv")
    if not agi_kagi.empty and "team" in agi_kagi.columns:
        agi_rows = agi_kagi[agi_kagi.get("table_index", 0) == 0]
        for _, item in agi_rows.dropna(subset=["team", "AGI"]).iterrows():
            priors[str(item.team)]["AGI"] = _as_number(item.AGI)
        kagi_rows = agi_kagi[agi_kagi.get("table_index", 0) == 1]
        for _, item in kagi_rows.dropna(subset=["team", "KAGI"]).iterrows():
            priors[str(item.team)]["KAGI"] = _as_number(item.KAGI)

    team_match_counts = pd.concat(
        [matches["home_team"].astype(str), matches["away_team"].astype(str)], ignore_index=True
    ).value_counts()
    stats = read_csv("Data/processed/team_stats_2026_special_clean.csv")
    if not stats.empty and {"team", "stat_label", "value"}.issubset(stats.columns):
        for _, item in stats.dropna(subset=["team", "stat_label", "value"]).iterrows():
            team = str(item.team)
            games = max(int(team_match_counts.get(team, 0)), 1)
            priors[team][f"Prev_{str(item.stat_label)}"] = _as_number(item.value) / games

    return dict(priors)


def _result(home_goals: int, away_goals: int) -> int:
    return 1 if home_goals > away_goals else -1 if home_goals < away_goals else 0


def _score_points(result: int) -> tuple[int, int]:
    if result > 0:
        return 3, 0
    if result < 0:
        return 0, 3
    return 1, 1


def _as_number(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if np.isfinite(result) else default


def _historical_prior(reference: pd.DataFrame, team: str, side: str) -> dict[str, Any]:
    """Build a pre-2026 prior from the legacy dataset only.

    Team-specific legacy values are allowed as a cold-start prior.  They are
    intentionally not derived from 2026_special rows.
    """
    rows = reference[reference[side].astype(str) == team]
    source = rows if not rows.empty else reference
    values: dict[str, Any] = {}
    prefix = f"{side}_"
    for column in reference.columns:
        if not column.startswith(prefix):
            continue
        series = source[column]
        if pd.api.types.is_numeric_dtype(series):
            values[column] = _as_number(series.median()) if series.notna().any() else 0.0
        else:
            mode = series.dropna().mode()
            values[column] = mode.iloc[0] if not mode.empty else "Unknown"
    return values


def _base_row(reference: pd.DataFrame) -> tuple[dict[str, Any], dict[str, str]]:
    row: dict[str, Any] = {}
    sources: dict[str, str] = {}
    for column in reference.columns:
        if column in TARGET_COLUMNS:
            continue
        series = reference[column]
        if pd.api.types.is_numeric_dtype(series):
            row[column] = _as_number(series.median()) if series.notna().any() else 0.0
        else:
            mode = series.dropna().mode()
            row[column] = mode.iloc[0] if not mode.empty else "Unknown"
        sources[column] = "historical_league_prior"
    return row, sources


def _rankings(teams: set[str], points: dict[str, int], goal_diff: dict[str, int], goals_for: dict[str, int]) -> dict[str, int]:
    ordered = sorted(teams, key=lambda team: (-points[team], -goal_diff[team], -goals_for[team], team))
    return {team: index + 1 for index, team in enumerate(ordered)}


def _urgency_score(
    team: str,
    *,
    ranked_teams: set[str],
    points: dict[str, int],
    goal_diff: dict[str, int],
    goals_for: dict[str, int],
    season_progress: float,
    mode: str,
) -> float:
    """Calculate urgency from the standings available before kick-off.

    Normal J1 uses the nearer of the title and 18th-place boundaries, which
    preserves the legacy definition without using the current match result.
    The special group stage has no relegation boundary, so only proximity to
    the group leader is used.  Play-off rows deliberately use ``none`` until
    a verified competition boundary is available.
    """
    if mode == "none" or team not in ranked_teams or not ranked_teams:
        return 0.0
    ranks = _rankings(ranked_teams, points, goal_diff, goals_for)
    leader_points = max(points[candidate] for candidate in ranked_teams)
    distances = [max(leader_points - points[team], 0)]
    if mode == "normal" and len(ranks) >= 18:
        rank18_team = next(candidate for candidate, rank in ranks.items() if rank == 18)
        distances.append(max(points[team] - points[rank18_team], 0))
    distance = min(distances)
    return float((1.0 / (distance + 1.0)) * (season_progress**2))


def _parse_formation(formation: Any) -> tuple[int, int, int]:
    parts = [int(value) for value in str(formation).split("-") if value.isdigit()]
    if len(parts) < 3:
        return 4, 4, 2
    return parts[0], sum(parts[1:-1]), parts[-1]


def _apply_formation_values(
    row: dict[str, Any],
    sources: dict[str, str],
    *,
    home_formation: str,
    away_formation: str,
    source: str,
) -> None:
    home_df, home_mf, home_fw = _parse_formation(home_formation)
    away_df, away_mf, away_fw = _parse_formation(away_formation)
    values = {
        "Home_Formation": home_formation,
        "Away_Formation": away_formation,
        "is_Mirror_Game": int(home_formation == away_formation),
        "Home_DF_count": home_df,
        "Home_MF_count": home_mf,
        "Home_FW_count": home_fw,
        "Away_DF_count": away_df,
        "Away_MF_count": away_mf,
        "Away_FW_count": away_fw,
        "Home_Midfield_Advantage": home_mf - away_mf,
        "Defense_Margin_Home": home_df - away_fw,
        "Defense_Margin_Away": away_df - home_fw,
        "Backline_Matchup": backline_matchup(home_formation, away_formation),
    }
    for column, value in values.items():
        if column in row:
            row[column] = value
            sources[column] = source


def _days_between(previous: pd.Timestamp | None, current: pd.Timestamp) -> float:
    if previous is None or pd.isna(previous) or pd.isna(current):
        return 0.0
    return float(max((current.normalize() - previous.normalize()).days, 0))


def _apply_dynamic_values(
    row: dict[str, Any],
    sources: dict[str, str],
    *,
    home: str,
    away: str,
    teams: set[str],
    points: dict[str, int],
    goal_diff: dict[str, int],
    goals_for: dict[str, int],
    elo: dict[str, float],
    form: dict[str, list[int]],
    last_played: dict[str, pd.Timestamp | None],
    h2h_goals: dict[tuple[str, str], list[int]],
    current_date: pd.Timestamp,
    team_total_games: dict[str, int],
    team_completed_games: dict[str, int],
    rank_history: dict[str, list[int]],
    home_ranked_teams: set[str],
    away_ranked_teams: set[str],
    urgency_mode: str,
) -> None:
    del teams
    home_ranks = _rankings(home_ranked_teams, points, goal_diff, goals_for)
    away_ranks = _rankings(away_ranked_teams, points, goal_diff, goals_for)
    home_rank = home_ranks[home]
    away_rank = away_ranks[away]
    home_h2h = h2h_goals[(home, away)]
    away_h2h = h2h_goals[(away, home)]
    h2h_values = home_h2h + away_h2h
    home_progress = float(team_completed_games[home] / team_total_games[home]) if team_total_games[home] else 0.0
    away_progress = float(team_completed_games[away] / team_total_games[away]) if team_total_games[away] else 0.0
    dynamic = {
        "Home_Rest_Days": _days_between(last_played[home], current_date),
        "Away_Rest_Days": _days_between(last_played[away], current_date),
        "Home_Current_Rank": float(home_rank),
        "Away_Current_Rank": float(away_rank),
        "Rank_Diff": float(home_rank - away_rank),
        # At section N, compare the last known rank (N-1) with the rank after
        # N-4.  Four stored pre-match snapshots are therefore required.
        "Home_Rank_Delta_3": float(home_rank - rank_history[home][-4]) if len(rank_history[home]) >= 4 else 0.0,
        "Away_Rank_Delta_3": float(away_rank - rank_history[away][-4]) if len(rank_history[away]) >= 4 else 0.0,
        "Home_Elo_Before": float(elo[home]),
        "Away_Elo_Before": float(elo[away]),
        "Elo_Diff": float(elo[home] - elo[away]),
        "Home_Current_Points": float(points[home]),
        "Away_Current_Points": float(points[away]),
        "Home_Rolling_Points_5": float(sum(form[home][-5:])),
        "Away_Rolling_Points_5": float(sum(form[away][-5:])),
        "H2H_Score_Avg": float(np.mean(h2h_values)) if h2h_values else 0.0,
        "Home_Season_Progress": home_progress,
        "Away_Season_Progress": away_progress,
        "Home_Urgency_Score": _urgency_score(
            home, ranked_teams=home_ranked_teams, points=points, goal_diff=goal_diff,
            goals_for=goals_for, season_progress=home_progress, mode=urgency_mode,
        ),
        "Away_Urgency_Score": _urgency_score(
            away, ranked_teams=away_ranked_teams, points=points, goal_diff=goal_diff,
            goals_for=goals_for, season_progress=away_progress, mode=urgency_mode,
        ),
    }
    for column, value in dynamic.items():
        if column in row:
            row[column] = value
            sources[column] = "reconstructed_pre_match_results"


def _update_states(
    rows: pd.DataFrame,
    *,
    points: dict[str, int],
    goal_diff: dict[str, int],
    goals_for: dict[str, int],
    elo: dict[str, float],
    form: dict[str, list[int]],
    last_played: dict[str, pd.Timestamp | None],
    h2h_goals: dict[tuple[str, str], list[int]],
    current_date: pd.Timestamp,
) -> None:
    """Apply a date batch only after every row's feature state is frozen."""
    for _, match in rows.iterrows():
        home, away = str(match.home_team), str(match.away_team)
        home_goals, away_goals = int(match.home_score), int(match.away_score)
        outcome = _result(home_goals, away_goals)
        home_points, away_points = _score_points(outcome)
        home_expected = expected_score(elo[home], elo[away])
        actual_home = 1.0 if outcome > 0 else 0.5 if outcome == 0 else 0.0
        adjustment = ELO_K * (actual_home - home_expected)
        elo[home] += adjustment
        elo[away] -= adjustment
        points[home] += home_points
        points[away] += away_points
        goal_diff[home] += home_goals - away_goals
        goal_diff[away] += away_goals - home_goals
        goals_for[home] += home_goals
        goals_for[away] += away_goals
        form[home].append(home_points)
        form[away].append(away_points)
        h2h_goals[(home, away)].append(home_goals)
        h2h_goals[(away, home)].append(away_goals)
        last_played[home] = current_date
        last_played[away] = current_date


def _apply_legacy_aggregate_values(
    row: dict[str, Any],
    sources: dict[str, str],
    *,
    home: str,
    away: str,
    priors: dict[str, dict[str, Any]],
) -> None:
    for side, team in [("Home", home), ("Away", away)]:
        for name, value in priors.get(team, {}).items():
            column = f"{side}_{name}"
            if column in row:
                row[column] = value
                sources[column] = "legacy_season_aggregate_allocation"
    for home_column, away_column, diff_column in [
        ("Home_Market_Value", "Away_Market_Value", "Market_Value_Diff"),
    ]:
        if all(column in row for column in [home_column, away_column, diff_column]):
            row[diff_column] = _as_number(row[home_column]) - _as_number(row[away_column])
            sources[diff_column] = "derived_from_legacy_aggregate"


def rebuild_pre_match_features(
    matches: pd.DataFrame,
    reference: pd.DataFrame,
    *,
    season_name: str,
    legacy_aggregate_priors: dict[str, dict[str, Any]] | None = None,
) -> RebuiltFeatures:
    """Return one target-complete, no-lookahead row per finished match."""
    finished = matches[
        (matches["status"].astype(str) == "finished")
        & matches["home_score"].notna()
        & matches["away_score"].notna()
    ].copy()
    finished["_date"] = pd.to_datetime(finished["match_date"], errors="coerce")
    finished = finished.dropna(subset=["_date"]).sort_values(["_date", "kickoff_time", "match_id"])
    teams = set(finished["home_team"].astype(str)) | set(finished["away_team"].astype(str))
    points: dict[str, int] = defaultdict(int)
    goal_diff: dict[str, int] = defaultdict(int)
    goals_for: dict[str, int] = defaultdict(int)
    elo: dict[str, float] = defaultdict(lambda: DEFAULT_ELO)
    form: dict[str, list[int]] = defaultdict(list)
    rank_history: dict[str, list[int]] = defaultdict(list)
    last_played: dict[str, pd.Timestamp | None] = defaultdict(lambda: None)
    h2h_goals: dict[tuple[str, str], list[int]] = defaultdict(list)
    base, base_sources = _base_row(reference)
    rows: list[dict[str, Any]] = []
    source_rows: list[dict[str, str]] = []
    team_total_games = pd.concat(
        [finished["home_team"].astype(str), finished["away_team"].astype(str)], ignore_index=True
    ).value_counts().astype(int).to_dict()
    team_completed_games: dict[str, int] = defaultdict(int)
    east_teams: set[str] = set()
    west_teams: set[str] = set()
    if "competition" in finished.columns:
        east_rows = finished[finished["competition"].astype(str).str.contains("EAST", case=False, na=False)]
        west_rows = finished[finished["competition"].astype(str).str.contains("WEST", case=False, na=False)]
        east_teams = set(east_rows["home_team"].astype(str)) | set(east_rows["away_team"].astype(str))
        west_teams = set(west_rows["home_team"].astype(str)) | set(west_rows["away_team"].astype(str))

    def ranked_teams_for(team: str) -> set[str]:
        if team in east_teams:
            return east_teams
        if team in west_teams:
            return west_teams
        return teams

    for current_date, day_matches in finished.groupby("_date", sort=True):
        pending: list[tuple[dict[str, Any], dict[str, str]]] = []
        for _, match in day_matches.iterrows():
            home, away = str(match.home_team), str(match.away_team)
            competition = str(match.get("competition", ""))
            urgency_mode = "none" if "プレーオフ" in competition else "group" if (east_teams or west_teams) else "normal"
            row, sources = dict(base), dict(base_sources)
            row.update(_historical_prior(reference, home, "Home"))
            row.update(_historical_prior(reference, away, "Away"))
            for column in row:
                if column.startswith("Home_") or column.startswith("Away_"):
                    sources[column] = "historical_team_prior"
            for column in POST_MATCH_FEATURES:
                if column in row:
                    row[column] = 0.0
                    sources[column] = "excluded_post_match_feature"
            if legacy_aggregate_priors is not None:
                _apply_legacy_aggregate_values(
                    row,
                    sources,
                    home=home,
                    away=away,
                    priors=legacy_aggregate_priors,
                )
            for identity, column in IDENTITY_TO_MODEL.items():
                if column in row:
                    row[column] = season_name if column == "Season" else match.get(identity)
                    sources[column] = "actual_schedule"
            row["Season"] = season_name
            row["Score"] = f"{int(match.home_score)}-{int(match.away_score)}"
            row["Home_Goals"] = int(match.home_score)
            row["Away_Goals"] = int(match.away_score)
            row["Goal_Diff"] = int(match.home_score) - int(match.away_score)
            row["Match_Result"] = _result(int(match.home_score), int(match.away_score))
            for column in TARGET_COLUMNS:
                sources[column] = "post_match_target"
            _apply_dynamic_values(
                row,
                sources,
                home=home,
                away=away,
                teams=teams,
                points=points,
                goal_diff=goal_diff,
                goals_for=goals_for,
                elo=elo,
                form=form,
                last_played=last_played,
                h2h_goals=h2h_goals,
                current_date=current_date,
                team_total_games=team_total_games,
                team_completed_games=team_completed_games,
                rank_history=rank_history,
                home_ranked_teams=ranked_teams_for(home),
                away_ranked_teams=ranked_teams_for(away),
                urgency_mode=urgency_mode,
            )
            home_formation = str(row.get("Home_Formation", "4-4-2"))
            away_formation = str(row.get("Away_Formation", "4-4-2"))
            _apply_formation_values(
                row,
                sources,
                home_formation=home_formation,
                away_formation=away_formation,
                source="derived_from_pre_match_formation_prior",
            )
            rows.append(row)
            source_rows.append(sources)
            pending.append((row, sources))
        _update_states(
            day_matches,
            points=points,
            goal_diff=goal_diff,
            goals_for=goals_for,
            elo=elo,
            form=form,
            last_played=last_played,
            h2h_goals=h2h_goals,
            current_date=current_date,
        )
        played_teams = set(day_matches["home_team"].astype(str)) | set(day_matches["away_team"].astype(str))
        for team in played_teams:
            team_completed_games[team] += 1
            team_ranks = _rankings(ranked_teams_for(team), points, goal_diff, goals_for)
            rank_history[team].append(team_ranks[team])

    feature_frame = pd.DataFrame(rows).reindex(columns=reference.columns)
    source_frame = pd.DataFrame(source_rows).reindex(columns=reference.columns, fill_value="not_tracked")
    return RebuiltFeatures(features=feature_frame, sources=source_frame)


def _most_common_formation(values: list[str], fallback: str = "4-4-2") -> str:
    cleaned = [str(value) for value in values if str(value) not in {"", "nan", "None", "Unknown"}]
    if not cleaned:
        return fallback
    counts = Counter(cleaned)
    best_count = max(counts.values())
    # Prefer the most recently used system when multiple formations are tied.
    for value in reversed(cleaned):
        if counts[value] == best_count:
            return value
    return fallback


def rebuild_historical_training_features(reference: pd.DataFrame) -> RebuiltFeatures:
    """Rebuild legacy J1 rows with a single pre-match availability policy.

    Safe season/team attributes and explicitly accepted aggregate estimates
    (xG/AGI/KAGI) are retained from the original table.  Dynamic standings,
    form, Elo, urgency and tactical fields are regenerated chronologically.
    Realised attendance is blanked even though model training also excludes
    it, making accidental future reuse visible in the artifact itself.
    """
    required = {"Season", "Section", "Date", "Home", "Away", "Home_Goals", "Away_Goals"}
    missing = sorted(required - set(reference.columns))
    if missing:
        raise ValueError(f"履歴データに必要な列がありません: {missing}")

    work = reference.copy()
    work["_date"] = pd.to_datetime(work["Date"], errors="coerce")
    work["_original_index"] = np.arange(len(work))
    work = work.dropna(subset=["_date"]).sort_values(["_date", "Section", "_original_index"])

    rows: list[dict[str, Any]] = []
    source_rows: list[dict[str, str]] = []
    previous_season_formations: dict[str, str] = {}
    elo: dict[str, float] = defaultdict(lambda: DEFAULT_ELO)

    for season, season_rows in work.groupby("Season", sort=True):
        if rows:
            for team in list(elo):
                elo[team] = 0.75 * elo[team] + 0.25 * DEFAULT_ELO
        teams = set(season_rows["Home"].astype(str)) | set(season_rows["Away"].astype(str))
        points: dict[str, int] = defaultdict(int)
        goal_diff: dict[str, int] = defaultdict(int)
        goals_for: dict[str, int] = defaultdict(int)
        form: dict[str, list[int]] = defaultdict(list)
        rank_history: dict[str, list[int]] = defaultdict(list)
        last_played: dict[str, pd.Timestamp | None] = defaultdict(lambda: None)
        h2h_goals: dict[tuple[str, str], list[int]] = defaultdict(list)
        formation_history: dict[str, list[str]] = defaultdict(list)
        team_total_games = pd.concat(
            [season_rows["Home"].astype(str), season_rows["Away"].astype(str)], ignore_index=True
        ).value_counts().astype(int).to_dict()
        team_completed_games: dict[str, int] = defaultdict(int)
        season_divisor = max(_as_number(season_rows["Section"].max(), LEGACY_AGGREGATE_DIVISOR), 1.0)

        normalized = pd.DataFrame(
            {
                "home_team": season_rows["Home"].astype(str),
                "away_team": season_rows["Away"].astype(str),
                "home_score": season_rows["Home_Goals"].astype(int),
                "away_score": season_rows["Away_Goals"].astype(int),
                "match_date": season_rows["_date"],
            },
            index=season_rows.index,
        )

        for current_date, day_rows in season_rows.groupby("_date", sort=True):
            normalized_day = normalized.loc[day_rows.index]
            for idx, original in day_rows.iterrows():
                home, away = str(original.Home), str(original.Away)
                row = original.drop(labels=["_date", "_original_index"]).to_dict()
                sources = {column: "legacy_historical_value" for column in reference.columns}
                for column in POST_MATCH_FEATURES:
                    if column in row:
                        row[column] = 0.0
                        sources[column] = "excluded_post_match_feature"
                for column in [
                    "Home_Rolling_xG", "Away_Rolling_xG", "Home_AGI", "Home_KAGI", "Away_AGI", "Away_KAGI"
                ]:
                    if column in row:
                        row[column] = _as_number(row[column]) * season_divisor
                        sources[column] = "historical_final_snapshot_estimate_restored_unit"
                _apply_dynamic_values(
                    row,
                    sources,
                    home=home,
                    away=away,
                    teams=teams,
                    points=points,
                    goal_diff=goal_diff,
                    goals_for=goals_for,
                    elo=elo,
                    form=form,
                    last_played=last_played,
                    h2h_goals=h2h_goals,
                    current_date=current_date,
                    team_total_games=team_total_games,
                    team_completed_games=team_completed_games,
                    rank_history=rank_history,
                    home_ranked_teams=teams,
                    away_ranked_teams=teams,
                    urgency_mode="normal",
                )
                # The original H2H implementation already filters Date <
                # current Date and is therefore retained as a safe historical
                # feature with its cross-season three-year window.
                if "H2H_Score_Avg" in original.index:
                    row["H2H_Score_Avg"] = original["H2H_Score_Avg"]
                    sources["H2H_Score_Avg"] = "historical_pre_match_h2h"
                home_formation = _most_common_formation(
                    formation_history[home], previous_season_formations.get(home, "4-4-2")
                )
                away_formation = _most_common_formation(
                    formation_history[away], previous_season_formations.get(away, "4-4-2")
                )
                _apply_formation_values(
                    row,
                    sources,
                    home_formation=home_formation,
                    away_formation=away_formation,
                    source="historical_pre_match_modal_formation",
                )
                rows.append(row)
                source_rows.append(sources)

            _update_states(
                normalized_day,
                points=points,
                goal_diff=goal_diff,
                goals_for=goals_for,
                elo=elo,
                form=form,
                last_played=last_played,
                h2h_goals=h2h_goals,
                current_date=current_date,
            )
            for idx, original in day_rows.iterrows():
                home, away = str(original.Home), str(original.Away)
                team_completed_games[home] += 1
                team_completed_games[away] += 1
                ranks = _rankings(teams, points, goal_diff, goals_for)
                rank_history[home].append(ranks[home])
                rank_history[away].append(ranks[away])
                formation_history[home].append(str(original.get("Home_Formation", "Unknown")))
                formation_history[away].append(str(original.get("Away_Formation", "Unknown")))

        previous_season_formations = {
            team: _most_common_formation(values, previous_season_formations.get(team, "4-4-2"))
            for team, values in formation_history.items()
        }

    feature_frame = pd.DataFrame(rows).reindex(columns=reference.columns)
    source_frame = pd.DataFrame(source_rows).reindex(columns=reference.columns, fill_value="not_tracked")
    return RebuiltFeatures(features=feature_frame, sources=source_frame)
