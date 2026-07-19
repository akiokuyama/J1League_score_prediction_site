"""Train and save score prediction models."""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.multioutput import MultiOutputRegressor

from src.evaluation.metrics import evaluate_base_models, evaluate_final_scores


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODEL_FILENAMES = [
    "model_step1_goals.pkl",
    "model_step2_clf.pkl",
    "model_step2_diff.pkl",
    "model_features.pkl",
]

DROP_COLS_BASE = [
    "Season",
    "Section",
    "Date",
    "Score",
    "Home",
    "Away",
    "Stadium",
    "Home_Goals",
    "Away_Goals",
    "Goal_Diff",
    "Match_Result",
    # These values are only known after kick-off.  Capacity can remain as a
    # venue attribute, but realised attendance and its derivative must never
    # be training or inference features.
    "Attendance",
    "Stadium_Fill_Rate",
]

CAT_COLS_WITH_WEATHER = [
    "Weather",
    "Backline_Matchup",
    "Home_Formation",
    "Away_Formation",
]

CAT_COLS_NO_WEATHER = [
    "Backline_Matchup",
    "Home_Formation",
    "Away_Formation",
]

FEATURE_POLICY = {
    "exclude_weather": True,
    "categorical_columns": CAT_COLS_NO_WEATHER,
    "ignored_raw_columns": ["Weather"],
    "forbidden_feature_prefixes": ["Weather_"],
    "goal_pattern_policy": "use_previous_season_prev_features_only",
    "team_style_policy": "use_previous_season_prev_features_only",
    "post_match_features_excluded": ["Attendance", "Stadium_Fill_Rate"],
}


@dataclass(frozen=True)
class TrainResult:
    metrics: dict[str, float]
    feature_names: list[str]
    train_rows: int
    test_rows: int
    models: dict[str, Any]


def season_year(value: Any) -> int:
    match = re.search(r"\d{4}", str(value))
    if not match:
        raise ValueError(f"Seasonから年を解釈できません: {value}")
    return int(match.group(0))


def season_label(value: Any) -> str:
    text = str(value)
    if text.endswith(".0"):
        return text[:-2]
    return text


def default_model_params() -> dict[str, dict[str, Any]]:
    return {
        "step1": {
            "boosting_type": "gbdt",
            "colsample_bytree": 0.7694855488360749,
            "learning_rate": 0.012322537859458825,
            "max_depth": 9,
            "min_child_samples": 35,
            "n_estimators": 116,
            "num_leaves": 10,
            "random_state": 42,
            "subsample": 0.9667197761559129,
            "verbosity": -1,
        },
        "step2_clf": {
            "boosting_type": "gbdt",
            "colsample_bytree": 0.7599882132567581,
            "learning_rate": 0.05335428270903498,
            "max_depth": 9,
            "min_child_samples": 45,
            "n_estimators": 257,
            "num_leaves": 36,
            "random_state": 42,
            "subsample": 0.6151065475512765,
            "verbosity": -1,
        },
        "step2_diff": {
            "boosting_type": "gbdt",
            "colsample_bytree": 0.6023897947653992,
            "learning_rate": 0.026706019216521316,
            "max_depth": 5,
            "min_child_samples": 41,
            "n_estimators": 385,
            "num_leaves": 24,
            "random_state": 42,
            "subsample": 0.6619772464782415,
            "verbosity": -1,
        },
    }


def build_training_frame(
    dataset_path: str | Path,
    *,
    exclude_weather: bool,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series, pd.DataFrame]:
    df = pd.read_csv(dataset_path)
    drop_cols = list(DROP_COLS_BASE)
    cat_cols = list(CAT_COLS_NO_WEATHER if exclude_weather else CAT_COLS_WITH_WEATHER)
    if exclude_weather:
        drop_cols.append("Weather")

    X = df.drop(columns=[col for col in drop_cols if col in df.columns], errors="ignore")
    X = pd.get_dummies(X, columns=[col for col in cat_cols if col in X.columns])
    if exclude_weather:
        X = X[[col for col in X.columns if not str(col).startswith("Weather_")]]
    X = X.apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(0)

    return X, df[["Home_Goals", "Away_Goals"]], df["Match_Result"], df["Goal_Diff"], df


def train_and_evaluate(
    dataset_path: str | Path,
    *,
    exclude_weather: bool = True,
    test_season: str | int = 2025,
    test_start_date: str | None = None,
    include_test_season_history: bool = True,
) -> TrainResult:
    X, y_goals, y_result, y_diff, df = build_training_frame(dataset_path, exclude_weather=exclude_weather)
    test_label = season_label(test_season)
    test_year = season_year(test_season)
    season_labels = df["Season"].map(season_label)
    season_years = df["Season"].map(season_year)
    test_mask = season_labels == test_label
    if not test_mask.any():
        test_mask = season_years == test_year
    if test_start_date:
        dates = pd.to_datetime(df.get("Date"), errors="coerce")
        split_date = pd.Timestamp(test_start_date)
        test_mask = test_mask & (dates >= split_date)
        train_mask = season_years < test_year
        if include_test_season_history:
            train_mask = train_mask | ((season_labels == test_label) & (dates < split_date))
    else:
        train_mask = season_years < test_year
    if not train_mask.any() or not test_mask.any():
        raise ValueError("学習用または評価用の行がありません。test season/date を確認してください。")
    params = default_model_params()

    X_train, X_test = X[train_mask], X[test_mask]
    y_goals_train, y_goals_test = y_goals[train_mask], y_goals[test_mask]
    y_result_train, y_result_test = y_result[train_mask], y_result[test_mask]
    y_diff_train, y_diff_test = y_diff[train_mask], y_diff[test_mask]

    step1 = MultiOutputRegressor(lgb.LGBMRegressor(**params["step1"]))
    step1.fit(X_train, y_goals_train)
    pred_goals = step1.predict(X_test)

    step2_clf = lgb.LGBMClassifier(**params["step2_clf"])
    step2_clf.fit(X_train, y_result_train)
    pred_result = step2_clf.predict(X_test)
    pred_result_proba = step2_clf.predict_proba(X_test)

    step2_diff = lgb.LGBMRegressor(**params["step2_diff"])
    step2_diff.fit(X_train, y_diff_train)
    pred_diff = step2_diff.predict(X_test)

    metrics = evaluate_base_models(
        y_goals_true=y_goals_test,
        y_result_true=y_result_test,
        y_diff_true=y_diff_test,
        pred_goals=pred_goals,
        pred_result=pred_result,
        pred_result_proba=pred_result_proba,
        pred_diff=pred_diff,
        result_classes=step2_clf.classes_,
    )
    metrics.update(
        evaluate_final_scores(
            y_goals_true=y_goals_test,
            y_result_true=y_result_test,
            pred_goals=pred_goals,
            pred_result_proba=pred_result_proba,
            pred_diff=pred_diff,
            result_classes=step2_clf.classes_,
        )
    )

    return TrainResult(
        metrics=metrics,
        feature_names=[str(col) for col in X.columns],
        train_rows=int(train_mask.sum()),
        test_rows=int(test_mask.sum()),
        models={
            "step1_goals": step1,
            "step2_clf": step2_clf,
            "step2_diff": step2_diff,
        },
    )


def train_full_models(dataset_path: str | Path, *, exclude_weather: bool = True) -> TrainResult:
    X, y_goals, y_result, y_diff, df = build_training_frame(dataset_path, exclude_weather=exclude_weather)
    params = default_model_params()

    step1 = MultiOutputRegressor(lgb.LGBMRegressor(**params["step1"]))
    step1.fit(X, y_goals)
    step2_clf = lgb.LGBMClassifier(**params["step2_clf"])
    step2_clf.fit(X, y_result)
    step2_diff = lgb.LGBMRegressor(**params["step2_diff"])
    step2_diff.fit(X, y_diff)

    return TrainResult(
        metrics={},
        feature_names=[str(col) for col in X.columns],
        train_rows=len(df),
        test_rows=0,
        models={
            "step1_goals": step1,
            "step2_clf": step2_clf,
            "step2_diff": step2_diff,
        },
    )


def model_metadata(
    *,
    version: str,
    dataset_path: str | Path,
    evaluation: dict[str, Any],
    feature_count: int,
    test_season: str | int = 2025,
    test_start_date: str | None = None,
) -> dict[str, Any]:
    now = datetime.now(ZoneInfo("Asia/Tokyo")).isoformat(timespec="seconds")
    return {
        "model_version": version,
        "trained_at": now,
        "dataset_path": str(dataset_path),
        "feature_count": int(feature_count),
        "exclude_weather": True,
        "training_split": (
            {
                "train": f"year(Season) < {season_year(test_season)} or (Season == {season_label(test_season)} and Date < {test_start_date})",
                "test": f"Season == {season_label(test_season)} and Date >= {test_start_date}",
            }
            if test_start_date
            else {
                "train": f"year(Season) < {season_year(test_season)}",
                "test": f"Season == {season_label(test_season)}",
            }
        ),
        "evaluation": evaluation,
    }


def save_models(result: TrainResult, output_dir: str | Path, metadata: dict[str, Any]) -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    joblib.dump(result.models["step1_goals"], out / "model_step1_goals.pkl")
    joblib.dump(result.models["step2_clf"], out / "model_step2_clf.pkl")
    joblib.dump(result.models["step2_diff"], out / "model_step2_diff.pkl")
    joblib.dump(result.feature_names, out / "model_features.pkl")
    (out / "model_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (out / "feature_policy.json").write_text(
        json.dumps(FEATURE_POLICY, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def backup_active_models(model_dir: str | Path = "Models") -> Path:
    model_path = Path(model_dir)
    timestamp = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y%m%d_%H%M%S")
    backup_dir = model_path / f"legacy_weather_{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=False)

    for filename in MODEL_FILENAMES + ["model_metadata.json", "feature_policy.json"]:
        src = model_path / filename
        if src.exists():
            shutil.copy2(src, backup_dir / filename)
    return backup_dir


def activate_models(source_dir: str | Path, model_dir: str | Path = "Models") -> Path:
    backup_dir = backup_active_models(model_dir)
    source = Path(source_dir)
    target = Path(model_dir)
    for filename in MODEL_FILENAMES + ["model_metadata.json", "feature_policy.json"]:
        src = source / filename
        if src.exists():
            shutil.copy2(src, target / filename)
    return backup_dir
