"""Batch prediction for upcoming matches."""

from __future__ import annotations

import csv
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from src.config import CATEGORY, COMPETITION, LEAGUE, OUTPUT_DIR, SEASON
from src.features.validation import validate_latest_predictions, validate_no_weather_columns
from src.predict.predict_match import predict_match
from src.predict.scorer_candidates import load_team_scorer_candidates


def load_upcoming_features(path: str | Path = "Data/features/upcoming_features_2026_special.csv") -> pd.DataFrame:
    return pd.read_csv(path)


def load_scorer_candidates(path: str | Path = "Data/processed/player_stats_2026_special_clean.csv", top_n: int = 5) -> dict[str, list[dict[str, Any]]]:
    return load_team_scorer_candidates(path, top_n=top_n)


def select_prediction_targets(
    df: pd.DataFrame,
    mode: str = "next_section",
    *,
    date_from: str | None = None,
    date_to: str | None = None,
) -> pd.DataFrame:
    if df.empty:
        return df
    targets = df.copy()
    if "status" in targets.columns:
        targets = targets[targets["status"].astype(str).isin(["unplayed", "postponed_or_tbd"])]

    if mode == "next_section":
        if "section" in targets.columns and not targets["section"].dropna().empty:
            section = targets["section"].dropna().astype(float).min()
            targets = targets[targets["section"].astype(float) == section]
    elif mode == "all_unplayed":
        pass
    elif mode == "date_range":
        if "match_date" not in targets.columns:
            return targets.iloc[0:0]
        dates = pd.to_datetime(targets["match_date"], errors="coerce")
        if date_from:
            targets = targets[dates >= pd.Timestamp(date_from)]
            dates = pd.to_datetime(targets["match_date"], errors="coerce")
        if date_to:
            targets = targets[dates <= pd.Timestamp(date_to)]
    else:
        raise ValueError(f"Unknown prediction mode: {mode}")

    return targets


def predict_upcoming_matches(
    features_df: pd.DataFrame,
    model_dir: str | Path | None = None,
    season: str | None = None,
    league: str | None = None,
    competition: str | None = None,
    category: str | None = None,
    feature_source: str | None = None,
    scorer_candidates_path: str | Path = "Data/processed/player_stats_2026_special_clean.csv",
) -> dict[str, Any]:
    matches: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    warnings: list[str] = []
    scorer_candidates = load_scorer_candidates(scorer_candidates_path)
    metadata = {
        "season": season or _metadata_value(features_df, "season", SEASON),
        "league": league or _metadata_value(features_df, "league", LEAGUE),
        "competition": competition or _metadata_value(features_df, "competition", COMPETITION),
        "category": category or _metadata_value(features_df, "category", CATEGORY),
    }
    model_version = _model_version(model_dir)

    for idx, row in features_df.iterrows():
        try:
            home = str(row.get("home_team") or row.get("Home"))
            away = str(row.get("away_team") or row.get("Away"))
            match_date = row.get("match_date") or row.get("Date")
            result = predict_match(
                home_team=home,
                away_team=away,
                match_date=str(match_date) if pd.notna(match_date) else None,
                model_dir=model_dir,
                feature_row=row,
            )
            result["match_id"] = str(row.get("match_id") or result["match_id"])
            result["section"] = int(row.get("section")) if pd.notna(row.get("section")) else None
            result["scorer_candidates"] = {
                "home": scorer_candidates.get(home, []),
                "away": scorer_candidates.get(away, []),
            }
            matches.append(result)
        except Exception as exc:  # noqa: BLE001
            skipped.append({"row_index": int(idx), "reason": str(exc)})

    if not matches:
        warnings.append("予測対象が空のため latest_predictions.json は更新しません。")

    return {
        "last_updated": datetime.now(ZoneInfo("Asia/Tokyo")).isoformat(timespec="seconds"),
        **metadata,
        "matchweek": int(features_df["section"].dropna().astype(float).min()) if "section" in features_df.columns and not features_df.empty and not features_df["section"].dropna().empty else None,
        "model_version": model_version,
        "feature_policy": {"exclude_weather": True},
        "matches": matches,
        "skipped_matches": skipped,
        "warnings": warnings,
        "data_sources": {
            "features": feature_source or "Data/features/upcoming_features_2026_special.csv",
        },
    }


def _metadata_value(features_df: pd.DataFrame, column: str, fallback: str) -> str:
    if column not in features_df.columns:
        return fallback
    values = features_df[column].dropna().astype(str)
    return values.iloc[0] if not values.empty else fallback


def _model_version(model_dir: str | Path | None) -> str:
    directory = Path(model_dir) if model_dir is not None else Path(__file__).resolve().parents[2] / "Models"
    metadata_path = directory / "model_metadata.json"
    if not metadata_path.exists():
        return directory.name or "unknown"
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return directory.name or "unknown"
    return str(metadata.get("model_version") or directory.name or "unknown")


def write_predictions_safely(
    data: dict[str, Any],
    output_dir: str | Path = OUTPUT_DIR,
    output_path: str | Path | None = None,
    csv_path: str | Path | None = None,
) -> dict[str, Any]:
    errors = validate_latest_predictions(data)
    if errors:
        return {"updated": False, "errors": errors}

    weather_columns = validate_no_weather_columns(list(data.keys()))
    if weather_columns:
        return {"updated": False, "errors": [f"Weather列が含まれています: {weather_columns}"]}

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    history_dir = out / "prediction_history"
    history_dir.mkdir(parents=True, exist_ok=True)
    latest_path = Path(output_path) if output_path is not None else out / "latest_predictions.json"
    if not latest_path.is_absolute():
        latest_path = Path.cwd() / latest_path
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = latest_path.with_suffix(latest_path.suffix + ".tmp")
    csv_output_path = Path(csv_path) if csv_path is not None else out / "latest_predictions.csv"
    if not csv_output_path.is_absolute():
        csv_output_path = Path.cwd() / csv_output_path
    csv_output_path.parent.mkdir(parents=True, exist_ok=True)
    updated_path = out / "last_updated.txt"
    timestamp = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y%m%d_%H%M%S")
    history_path = history_dir / f"{latest_path.stem}_{timestamp}.json"

    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    json.loads(tmp_path.read_text(encoding="utf-8"))
    tmp_path.replace(latest_path)
    shutil.copy2(latest_path, history_path)
    updated_path.write_text(str(data["last_updated"]) + "\n", encoding="utf-8")

    with csv_output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["match_id", "date", "home_team", "away_team", "predicted_home", "predicted_away"],
            lineterminator="\n",
        )
        writer.writeheader()
        for match in data["matches"]:
            writer.writerow(
                {
                    "match_id": match.get("match_id"),
                    "date": match.get("date"),
                    "home_team": match.get("home_team"),
                    "away_team": match.get("away_team"),
                    "predicted_home": match.get("predicted_score", {}).get("home"),
                    "predicted_away": match.get("predicted_score", {}).get("away"),
                }
            )

    return {
        "updated": True,
        "latest_path": str(latest_path),
        "csv_path": str(csv_output_path),
        "history_path": str(history_path),
    }
