"""Single-match prediction entry point."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from src.models.load_model import load_models
from src.predict.feature_preprocess import (
    load_reference_dataset,
    prepare_features_for_model,
    resolve_dataset_path,
)
from src.predict.score_distribution import predict_score_distribution


TEAM_NAME_ALIASES = {
    "名古屋": "名古屋グランパス",
    "横浜FM": "横浜 F・マリノス",
    "横浜Ｆ・マリノス": "横浜 F・マリノス",
}

TEAM_NAME_TO_DATASET_CODE = {
    "鹿島アントラーズ": "kasm",
    "浦和レッズ": "uraw",
    "柏レイソル": "kasw",
    "東京ヴェルディ": "tk-v",
    "川崎フロンターレ": "ka-f",
    "清水エスパルス": "shim",
    "京都サンガF.C.": "kyot",
    "セレッソ大阪": "c-os",
    "岡山": "okay",
    "ファジアーノ岡山": "okay",
    "アビスパ福岡": "fuku",
    "水戸ホーリーホック": "mito",
    "ジェフユナイテッド千葉": "chib",
    "FC東京": "FCtk",
    "ＦＣ東京": "FCtk",
    "FC町田ゼルビア": "mcd",
    "ＦＣ町田ゼルビア": "mcd",
    "横浜 F・マリノス": "y-fm",
    "横浜Ｆ・マリノス": "y-fm",
    "横浜FM": "y-fm",
    "名古屋グランパス": "nago",
    "ガンバ大阪": "g-os",
    "ヴィッセル神戸": "kobe",
    "サンフレッチェ広島": "hiro",
    "Ｖ・ファーレン長崎": "ngsk",
    "横浜FC": "y-fc",
    "横浜ＦＣ": "y-fc",
    "湘南ベルマーレ": "shon",
    "アルビレックス新潟": "niig",
    "ジュビロ磐田": "iwat",
    "北海道コンサドーレ札幌": "sapp",
    "サガン鳥栖": "tosu",
    "大分トリニータ": "oita",
    "徳島ヴォルティス": "toku",
    "ベガルタ仙台": "send",
}

def normalize_team_name(name: str) -> str:
    """Normalize a small set of team aliases used by the app interface."""

    stripped = str(name).strip()
    return TEAM_NAME_ALIASES.get(stripped, stripped)


def _python_scalar(value: Any) -> Any:
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def _row_to_context(row: pd.Series) -> dict[str, Any]:
    return {str(key): _python_scalar(value) for key, value in row.to_dict().items()}


def _candidate_names(name: str) -> list[str]:
    normalized = normalize_team_name(name)
    original = str(name).strip()
    candidates = [
        normalized,
        original,
        TEAM_NAME_TO_DATASET_CODE.get(normalized),
        TEAM_NAME_TO_DATASET_CODE.get(original),
    ]
    candidates = [candidate for candidate in candidates if candidate]
    return list(dict.fromkeys(candidates))


def _select_dataset_row(
    df: pd.DataFrame,
    home_team: str,
    away_team: str,
    match_date: str | None,
) -> tuple[pd.Series, int, list[str]]:
    if "Home" not in df.columns or "Away" not in df.columns:
        raise ValueError("Dataset must contain Home and Away columns.")

    home_candidates = _candidate_names(home_team)
    away_candidates = _candidate_names(away_team)
    warnings: list[str] = []

    card_mask = df["Home"].astype(str).isin(home_candidates) & df["Away"].astype(str).isin(
        away_candidates
    )
    candidate_df = df[card_mask].copy()

    if match_date and "Date" in df.columns:
        dated = candidate_df[candidate_df["Date"].astype(str) == str(match_date)]
        if not dated.empty:
            candidate_df = dated
        elif not candidate_df.empty:
            warnings.append(
                "指定日の完全一致行がないため、同一ホーム・アウェイカードの最新行を参照しています。"
            )

    if candidate_df.empty:
        raise ValueError(
            "予測に使える特徴量行が見つかりません。Week2では未来試合の特徴量自動生成は未実装です。"
        )

    if "Date" in candidate_df.columns:
        candidate_df["_sort_date"] = pd.to_datetime(candidate_df["Date"], errors="coerce")
        candidate_df = candidate_df.sort_values("_sort_date", ascending=False)
    row_index = int(candidate_df.index[0])
    row = df.loc[row_index]

    row_date = pd.to_datetime(row.get("Date"), errors="coerce") if "Date" in row.index else pd.NaT
    today = pd.Timestamp(date.today())
    if pd.notna(row_date) and row_date.normalize() < today:
        warnings.append(
            "Data/ML_dataset.csv の過去試合行を参照しているため、未来試合用の最新特徴量ではありません。"
        )

    return row, row_index, warnings


def _match_id(match_date: str | None, home_team: str, away_team: str) -> str:
    date_part = match_date or "unknown-date"
    return f"{date_part}-J1-unknown-{home_team}-vs-{away_team}"


def predict_match(
    home_team: str,
    away_team: str,
    match_date: str | None = None,
    *,
    dataset_path: str | Path | None = None,
    model_dir: str | Path | None = None,
    feature_row: pd.Series | dict[str, Any] | None = None,
    max_goals: int = 8,
    top_n_scores: int = 5,
) -> dict[str, Any]:
    """Return a JSON-compatible prediction result for one match."""

    normalized_home = normalize_team_name(home_team)
    normalized_away = normalize_team_name(away_team)
    bundle = load_models(model_dir=model_dir)

    if feature_row is not None:
        row = feature_row if isinstance(feature_row, pd.Series) else pd.Series(feature_row)
        row_index: int | None = None
        source_type = "feature_row"
        source_dataset_path = None
        source_warnings: list[str] = []
    else:
        resolved_dataset_path = resolve_dataset_path(dataset_path)
        df = load_reference_dataset(resolved_dataset_path)
        row, row_index, source_warnings = _select_dataset_row(
            df=df,
            home_team=home_team,
            away_team=away_team,
            match_date=match_date,
        )
        source_type = "dataset_row"
        source_dataset_path = str(resolved_dataset_path)

    X, diagnostics = prepare_features_for_model(row, bundle.feature_names)
    source_warnings.extend(
        f"学習時特徴量にあるが入力にない非カテゴリ列: {len(diagnostics['missing_non_dummy_columns'])}"
        for _ in [None]
        if diagnostics["missing_non_dummy_columns"]
    )
    source_warnings.extend(
        f"入力にあるが学習時特徴量にない列: {len(diagnostics['extra_columns'])}"
        for _ in [None]
        if diagnostics["extra_columns"]
    )
    source_warnings.extend(
        f"数値変換できない値を0で補完した列: {diagnostics['non_numeric_columns']}"
        for _ in [None]
        if diagnostics["non_numeric_columns"]
    )

    expected_goals = bundle.step1_goals.predict(X)[0]
    expected_home_goals = float(expected_goals[0])
    expected_away_goals = float(expected_goals[1])
    score_prediction = predict_score_distribution(
        expected_home_goals=expected_home_goals,
        expected_away_goals=expected_away_goals,
        temperature=bundle.calibration_temperature,
        max_goals=max_goals,
        top_n=top_n_scores,
    )
    result_probabilities = score_prediction.result_probabilities
    score_candidates = score_prediction.score_candidates
    predicted_goal_diff = expected_home_goals - expected_away_goals
    best_score = score_candidates[0]

    row_context = _row_to_context(row)
    result_date = match_date or row_context.get("Date")

    return {
        "match_id": _match_id(str(result_date) if result_date else None, normalized_home, normalized_away),
        "date": str(result_date) if result_date is not None else None,
        "home_team": normalized_home,
        "away_team": normalized_away,
        "predicted_score": {
            "home": int(best_score["home_goals"]),
            "away": int(best_score["away_goals"]),
        },
        "expected_goals": {
            "home": float(expected_home_goals),
            "away": float(expected_away_goals),
        },
        "result_probabilities": result_probabilities,
        "score_candidates": score_candidates,
        "predicted_goal_diff": float(predicted_goal_diff),
        "scorer_candidates": {
            "home": [],
            "away": [],
        },
        "feature_source": {
            "type": source_type,
            "dataset_path": source_dataset_path,
            "row_index": row_index,
            "warnings": source_warnings,
            "diagnostics": diagnostics,
        },
        "model_info": {
            "feature_count": int(len(bundle.feature_names)),
            "max_goals": int(max_goals),
            "top_n_scores": int(top_n_scores),
            "prediction_strategy": bundle.prediction_strategy,
            "probability_calibration": {
                "method": "temperature_scaling",
                "temperature": float(bundle.calibration_temperature),
            },
        },
    }
