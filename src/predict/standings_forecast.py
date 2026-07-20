"""Monte Carlo final-standings forecasts for the active J1 competition."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from scipy.stats import poisson

from src.data.team_master import to_dataset_code, to_display_name


JST = ZoneInfo("Asia/Tokyo")
RESULT_KEYS = ("home_win", "draw", "away_win")


def build_standings_forecast(
    matches_path: str | Path,
    predictions_path: str | Path,
    *,
    simulations: int = 10_000,
    seed: int = 202_627,
    generated_at: datetime | None = None,
    expected_team_count: int = 20,
) -> dict[str, Any]:
    """Build a reproducible final-table forecast from results and match predictions."""

    if simulations < 100:
        raise ValueError("simulations must be at least 100")

    match_path = Path(matches_path)
    prediction_path = Path(predictions_path)
    matches = _load_matches(match_path)
    predictions_data = _load_json(prediction_path)
    predictions = [item for item in predictions_data.get("matches", []) if isinstance(item, dict)]
    if matches.empty:
        raise ValueError(f"match schedule is empty: {match_path}")
    if not predictions:
        raise ValueError(f"prediction matches are empty: {prediction_path}")

    teams = _resolve_teams(matches, predictions)
    if expected_team_count and len(teams) != expected_team_count:
        raise ValueError(f"expected {expected_team_count} teams, found {len(teams)}")

    team_index = {team: index for index, team in enumerate(teams)}
    current = _current_records(matches, teams, team_index)
    remaining, warnings, inferred_count = _remaining_predictions(matches, predictions, teams)
    if not remaining:
        raise ValueError("no remaining match predictions are available")

    rng = np.random.default_rng(seed)
    points = np.broadcast_to(current["points"], (simulations, len(teams))).copy()
    goals_for = np.broadcast_to(current["goals_for"], (simulations, len(teams))).copy()
    goals_against = np.broadcast_to(current["goals_against"], (simulations, len(teams))).copy()

    for match in remaining:
        home = team_index[match["home_team"]]
        away = team_index[match["away_team"]]
        score_values, score_probabilities = _score_distribution(match)
        sampled = rng.choice(len(score_probabilities), size=simulations, p=score_probabilities)
        home_goals = score_values[sampled, 0]
        away_goals = score_values[sampled, 1]

        goals_for[:, home] += home_goals
        goals_against[:, home] += away_goals
        goals_for[:, away] += away_goals
        goals_against[:, away] += home_goals
        home_wins = home_goals > away_goals
        away_wins = home_goals < away_goals
        draws = home_goals == away_goals
        points[:, home] += (home_wins * 3 + draws).astype(np.int16)
        points[:, away] += (away_wins * 3 + draws).astype(np.int16)

    goal_difference = goals_for - goals_against
    ranks = np.empty((simulations, len(teams)), dtype=np.int16)
    tie_breakers = rng.random((simulations, len(teams)))
    rank_values = np.arange(1, len(teams) + 1, dtype=np.int16)
    for simulation in range(simulations):
        order = np.lexsort(
            (
                tie_breakers[simulation],
                -goals_for[simulation],
                -goal_difference[simulation],
                -points[simulation],
            )
        )
        ranks[simulation, order] = rank_values

    current_ranks = _current_ranks(current, teams) if current["completed_matches"] else {}
    team_summaries = _summarize_teams(
        teams,
        points,
        goals_for,
        goal_difference,
        ranks,
        current,
        current_ranks,
    )
    team_summaries.sort(
        key=lambda item: (
            -item["expected_points"],
            -item["expected_goal_difference"],
            -item["expected_goals_for"],
            item["team"],
        )
    )
    for predicted_rank, item in enumerate(team_summaries, start=1):
        item["predicted_rank"] = predicted_rank
        current_rank = item.get("current_rank")
        item["rank_change"] = current_rank - predicted_rank if current_rank is not None else None

    generated = generated_at or datetime.now(JST)
    if generated.tzinfo is None:
        generated = generated.replace(tzinfo=JST)
    generated = generated.astimezone(JST)
    completed_dates = pd.to_datetime(
        matches.loc[_finished_mask(matches), "match_date"], errors="coerce"
    ).dropna()
    completed_through = completed_dates.max().date().isoformat() if not completed_dates.empty else None
    expected_fixture_count = len(teams) * (len(teams) - 1)

    return {
        "schema_version": 1,
        "generated_at": generated.isoformat(timespec="seconds"),
        "season": predictions_data.get("season"),
        "league": predictions_data.get("league"),
        "competition": predictions_data.get("competition"),
        "model_version": predictions_data.get("model_version"),
        "simulation_count": simulations,
        "random_seed": seed,
        "ranking_method": [
            "points",
            "goal_difference",
            "goals_for",
            "seeded_random_for_exact_ties",
        ],
        "data_as_of": {
            "completed_through": completed_through,
            "completed_matches": current["completed_matches"],
            "label": completed_through or "開幕前",
        },
        "fixture_summary": {
            "official_schedule_matches": int(len(matches)),
            "expected_round_robin_matches": expected_fixture_count,
            "completed_matches": current["completed_matches"],
            "model_predicted_remaining_matches": len(remaining) - inferred_count,
            "supplemented_matches": inferred_count,
            "simulated_remaining_matches": len(remaining),
        },
        "probability_zones": {"champion": [1, 1], "top3": [1, 3], "bottom3": [18, 20]},
        "sources": {
            "matches": str(match_path),
            "predictions": str(prediction_path),
            "predictions_updated_at": predictions_data.get("last_updated"),
        },
        "warnings": warnings,
        "teams": team_summaries,
    }


def write_standings_forecast(
    forecast: dict[str, Any],
    latest_path: str | Path,
    history_dir: str | Path | None = None,
) -> tuple[Path, Path | None]:
    """Write the latest forecast and an optional timestamped history snapshot."""

    latest = Path(latest_path)
    latest.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(forecast, ensure_ascii=False, indent=2) + "\n"
    latest.write_text(serialized, encoding="utf-8")

    history_path: Path | None = None
    if history_dir is not None:
        directory = Path(history_dir)
        directory.mkdir(parents=True, exist_ok=True)
        generated = datetime.fromisoformat(str(forecast["generated_at"]).replace("Z", "+00:00"))
        timestamp = generated.astimezone(JST).strftime("%Y%m%d_%H%M%S")
        history_path = directory / f"standings_forecast_{timestamp}.json"
        history_path.write_text(serialized, encoding="utf-8")
    return latest, history_path


def _load_matches(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise ValueError(f"missing match schedule: {path}")
    frame = pd.read_csv(path)
    required = {"home_team", "away_team", "home_score", "away_score", "status", "match_date"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"match schedule is missing columns: {sorted(missing)}")
    frame = frame.copy()
    frame["home_team"] = frame["home_team"].map(lambda value: to_dataset_code(str(value)))
    frame["away_team"] = frame["away_team"].map(lambda value: to_dataset_code(str(value)))
    frame["home_score"] = pd.to_numeric(frame["home_score"], errors="coerce")
    frame["away_score"] = pd.to_numeric(frame["away_score"], errors="coerce")
    return frame


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ValueError(f"missing predictions: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("predictions JSON must be an object")
    return data


def _resolve_teams(matches: pd.DataFrame, predictions: list[dict[str, Any]]) -> list[str]:
    teams = {
        to_dataset_code(str(team))
        for team in pd.concat([matches["home_team"], matches["away_team"]]).dropna()
    }
    for prediction in predictions:
        for key in ("home_team", "away_team"):
            if prediction.get(key):
                teams.add(to_dataset_code(str(prediction[key])))
    teams.discard("tbd")
    return sorted(teams)


def _finished_mask(matches: pd.DataFrame) -> pd.Series:
    return (
        matches["status"].fillna("").astype(str).str.strip().str.lower().eq("finished")
        & matches["home_score"].notna()
        & matches["away_score"].notna()
    )


def _current_records(
    matches: pd.DataFrame,
    teams: list[str],
    team_index: dict[str, int],
) -> dict[str, Any]:
    size = len(teams)
    record: dict[str, Any] = {
        "played": np.zeros(size, dtype=np.int16),
        "wins": np.zeros(size, dtype=np.int16),
        "draws": np.zeros(size, dtype=np.int16),
        "losses": np.zeros(size, dtype=np.int16),
        "points": np.zeros(size, dtype=np.int16),
        "goals_for": np.zeros(size, dtype=np.int16),
        "goals_against": np.zeros(size, dtype=np.int16),
        "completed_matches": 0,
    }
    for _, match in matches.loc[_finished_mask(matches)].iterrows():
        home_team = to_dataset_code(str(match["home_team"]))
        away_team = to_dataset_code(str(match["away_team"]))
        if home_team not in team_index or away_team not in team_index:
            continue
        home = team_index[home_team]
        away = team_index[away_team]
        home_goals = int(match["home_score"])
        away_goals = int(match["away_score"])
        record["played"][[home, away]] += 1
        record["goals_for"][home] += home_goals
        record["goals_against"][home] += away_goals
        record["goals_for"][away] += away_goals
        record["goals_against"][away] += home_goals
        if home_goals > away_goals:
            record["wins"][home] += 1
            record["losses"][away] += 1
            record["points"][home] += 3
        elif away_goals > home_goals:
            record["wins"][away] += 1
            record["losses"][home] += 1
            record["points"][away] += 3
        else:
            record["draws"][[home, away]] += 1
            record["points"][[home, away]] += 1
        record["completed_matches"] += 1
    return record


def _remaining_predictions(
    matches: pd.DataFrame,
    predictions: list[dict[str, Any]],
    teams: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    finished_ids = {
        str(value)
        for value in matches.loc[_finished_mask(matches), "match_id"].dropna()
        if str(value)
    } if "match_id" in matches.columns else set()
    finished_pairs = {
        (to_dataset_code(str(row.home_team)), to_dataset_code(str(row.away_team)))
        for row in matches.loc[_finished_mask(matches)].itertuples()
    }
    scheduled_pairs = {
        (to_dataset_code(str(row.home_team)), to_dataset_code(str(row.away_team)))
        for row in matches.itertuples()
    }
    remaining: list[dict[str, Any]] = []
    prediction_by_pair: dict[tuple[str, str], dict[str, Any]] = {}
    for prediction in predictions:
        normalized = _normalize_prediction(prediction)
        if normalized is None:
            continue
        pair = (normalized["home_team"], normalized["away_team"])
        prediction_by_pair[pair] = normalized
        match_id = str(prediction.get("match_id") or "")
        if match_id in finished_ids or pair in finished_pairs:
            continue
        remaining.append(normalized)

    predicted_remaining_pairs = {
        (match["home_team"], match["away_team"])
        for match in remaining
    }
    missing_predictions = sorted((scheduled_pairs - finished_pairs) - predicted_remaining_pairs)
    if missing_predictions:
        examples = ", ".join(f"{home} vs {away}" for home, away in missing_predictions[:5])
        raise ValueError(f"missing predictions for {len(missing_predictions)} scheduled matches: {examples}")

    missing_pairs = [(home, away) for home in teams for away in teams if home != away and (home, away) not in scheduled_pairs]
    warnings: list[dict[str, Any]] = []
    inferred_count = 0
    for home, away in missing_pairs:
        if (home, away) in finished_pairs:
            continue
        reverse = prediction_by_pair.get((away, home))
        if reverse is not None:
            inferred = _reverse_prediction(reverse, home, away)
            method = "reverse_fixture_probabilities_swapped"
        else:
            inferred = _league_average_prediction(predictions, home, away)
            method = "league_average_probabilities"
        remaining.append(inferred)
        inferred_count += 1
        warnings.append(
            {
                "code": "missing_official_fixture_supplemented",
                "message": "公式日程データに未収録の対戦を順位予測上のみ暫定補完しました。",
                "home_team": home,
                "away_team": away,
                "method": method,
            }
        )

    expected_count = len(teams) * (len(teams) - 1)
    if len(scheduled_pairs) != expected_count:
        warnings.append(
            {
                "code": "official_schedule_incomplete",
                "message": f"公式日程データは{len(scheduled_pairs)}試合で、2回戦総当たりの{expected_count}試合に達していません。",
            }
        )
    return remaining, warnings, inferred_count


def _normalize_prediction(prediction: dict[str, Any]) -> dict[str, Any] | None:
    home = prediction.get("home_team")
    away = prediction.get("away_team")
    expected = prediction.get("expected_goals")
    probabilities = prediction.get("result_probabilities")
    if not home or not away or not isinstance(expected, dict) or not isinstance(probabilities, dict):
        return None
    try:
        home_xg = max(float(expected["home"]), 0.01)
        away_xg = max(float(expected["away"]), 0.01)
    except (KeyError, TypeError, ValueError):
        return None
    return {
        "match_id": prediction.get("match_id"),
        "home_team": to_dataset_code(str(home)),
        "away_team": to_dataset_code(str(away)),
        "expected_goals": {"home": home_xg, "away": away_xg},
        "result_probabilities": {key: max(float(probabilities.get(key, 0.0)), 0.0) for key in RESULT_KEYS},
        "supplemented": False,
    }


def _reverse_prediction(reverse: dict[str, Any], home: str, away: str) -> dict[str, Any]:
    expected = reverse["expected_goals"]
    probabilities = reverse["result_probabilities"]
    return {
        "match_id": f"supplemented-{home}-vs-{away}",
        "home_team": home,
        "away_team": away,
        "expected_goals": {"home": expected["away"], "away": expected["home"]},
        "result_probabilities": {
            "home_win": probabilities["away_win"],
            "draw": probabilities["draw"],
            "away_win": probabilities["home_win"],
        },
        "supplemented": True,
    }


def _league_average_prediction(
    predictions: list[dict[str, Any]], home: str, away: str
) -> dict[str, Any]:
    normalized = [item for item in (_normalize_prediction(p) for p in predictions) if item]
    if not normalized:
        raise ValueError("cannot supplement an incomplete schedule without valid predictions")
    home_xg = float(np.mean([item["expected_goals"]["home"] for item in normalized]))
    away_xg = float(np.mean([item["expected_goals"]["away"] for item in normalized]))
    probabilities = {
        key: float(np.mean([item["result_probabilities"][key] for item in normalized]))
        for key in RESULT_KEYS
    }
    return {
        "match_id": f"supplemented-{home}-vs-{away}",
        "home_team": home,
        "away_team": away,
        "expected_goals": {"home": home_xg, "away": away_xg},
        "result_probabilities": probabilities,
        "supplemented": True,
    }


def _score_distribution(match: dict[str, Any], max_goals: int = 10) -> tuple[np.ndarray, np.ndarray]:
    expected = match["expected_goals"]
    home_goals, away_goals = np.meshgrid(
        np.arange(max_goals + 1, dtype=np.int16),
        np.arange(max_goals + 1, dtype=np.int16),
        indexing="ij",
    )
    raw = np.outer(
        poisson.pmf(np.arange(max_goals + 1), float(expected["home"])),
        poisson.pmf(np.arange(max_goals + 1), float(expected["away"])),
    )
    supplied = np.array([match["result_probabilities"].get(key, 0.0) for key in RESULT_KEYS], dtype=float)
    if not np.isfinite(supplied).all() or supplied.sum() <= 0:
        supplied = np.array(
            [raw[home_goals > away_goals].sum(), raw[home_goals == away_goals].sum(), raw[home_goals < away_goals].sum()]
        )
    supplied = supplied / supplied.sum()

    probabilities = np.zeros_like(raw, dtype=float)
    masks = (home_goals > away_goals, home_goals == away_goals, home_goals < away_goals)
    for target, mask in zip(supplied, masks):
        category_sum = raw[mask].sum()
        if category_sum > 0:
            probabilities[mask] = raw[mask] * target / category_sum
    probabilities = probabilities.ravel()
    probabilities /= probabilities.sum()
    scores = np.column_stack((home_goals.ravel(), away_goals.ravel())).astype(np.int16)
    return scores, probabilities


def _current_ranks(current: dict[str, Any], teams: list[str]) -> dict[str, int]:
    goal_difference = current["goals_for"] - current["goals_against"]
    order = sorted(
        range(len(teams)),
        key=lambda index: (
            -int(current["points"][index]),
            -int(goal_difference[index]),
            -int(current["goals_for"][index]),
            teams[index],
        ),
    )
    return {teams[index]: rank for rank, index in enumerate(order, start=1)}


def _summarize_teams(
    teams: list[str],
    points: np.ndarray,
    goals_for: np.ndarray,
    goal_difference: np.ndarray,
    ranks: np.ndarray,
    current: dict[str, Any],
    current_ranks: dict[str, int],
) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for index, team in enumerate(teams):
        team_ranks = ranks[:, index]
        probabilities = {
            str(rank): round(float(np.mean(team_ranks == rank)), 6)
            for rank in range(1, len(teams) + 1)
        }
        summaries.append(
            {
                "predicted_rank": None,
                "team": team,
                "team_name": to_display_name(team),
                "current_rank": current_ranks.get(team),
                "rank_change": None,
                "current_record": {
                    "played": int(current["played"][index]),
                    "wins": int(current["wins"][index]),
                    "draws": int(current["draws"][index]),
                    "losses": int(current["losses"][index]),
                    "points": int(current["points"][index]),
                    "goals_for": int(current["goals_for"][index]),
                    "goals_against": int(current["goals_against"][index]),
                },
                "expected_points": round(float(points[:, index].mean()), 2),
                "expected_goal_difference": round(float(goal_difference[:, index].mean()), 2),
                "expected_goals_for": round(float(goals_for[:, index].mean()), 2),
                "average_rank": round(float(team_ranks.mean()), 2),
                "median_rank": int(np.median(team_ranks)),
                "likely_rank_low": int(np.quantile(team_ranks, 0.10, method="nearest")),
                "likely_rank_high": int(np.quantile(team_ranks, 0.90, method="nearest")),
                "champion_probability": round(float(np.mean(team_ranks == 1)), 6),
                "top3_probability": round(float(np.mean(team_ranks <= 3)), 6),
                "bottom3_probability": round(float(np.mean(team_ranks >= len(teams) - 2)), 6),
                "rank_probabilities": probabilities,
            }
        )
    return summaries
