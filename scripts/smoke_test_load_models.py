"""Smoke test for loading trained models and running one sample prediction."""

from __future__ import annotations

import os
import sys
import tempfile
import warnings
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "soccer_score_app_matplotlib"))
os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")
warnings.filterwarnings(
    "ignore",
    message="Could not find the number of physical cores.*",
    category=UserWarning,
)

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.models.load_model import ModelBundle, load_models
from src.predict.feature_preprocess import prepare_features_for_model, resolve_dataset_path
from src.predict.score_distribution import predict_score_distribution

SAMPLE_CONTEXT_COLS = ["Season", "Section", "Date", "Home", "Away", "Score"]


def build_feature_frame(df: pd.DataFrame, feature_names: list[str]) -> pd.DataFrame:
    X, diagnostics = prepare_features_for_model(df, feature_names)
    if diagnostics["missing_columns"]:
        print(f"[WARN] 学習時特徴量にあるが現在データにない列: {len(diagnostics['missing_columns'])}")
        print(f"       {diagnostics['missing_columns'][:20]}")
    if diagnostics["extra_columns"]:
        print(f"[WARN] 現在データにあるが学習時特徴量にない列: {len(diagnostics['extra_columns'])}")
        print(f"       {diagnostics['extra_columns'][:20]}")
    if diagnostics["non_numeric_columns"]:
        print(f"[WARN] 数値変換できない値を0で補完した列: {diagnostics['non_numeric_columns'][:20]}")
    return X


def run_prediction(bundle: ModelBundle, X_sample: pd.DataFrame) -> dict[str, object]:
    goals = bundle.step1_goals.predict(X_sample)[0]
    score_prediction = predict_score_distribution(
        expected_home_goals=float(goals[0]),
        expected_away_goals=float(goals[1]),
        temperature=bundle.calibration_temperature,
        max_goals=8,
        top_n=5,
    )

    return {
        "expected_goals_home": float(goals[0]),
        "expected_goals_away": float(goals[1]),
        "result_probabilities": score_prediction.result_probabilities,
        "predicted_goal_diff": float(goals[0] - goals[1]),
        "top_score_candidates": [item["score"] for item in score_prediction.score_candidates],
        "prediction_strategy": bundle.prediction_strategy,
        "calibration_temperature": bundle.calibration_temperature,
    }


def to_python_scalar(value: object) -> object:
    if hasattr(value, "item"):
        return value.item()
    return value


def main() -> int:
    try:
        bundle = load_models()
        print(f"[OK] model_dir: {bundle.model_dir}")
        print("[OK] モデル読み込み成功")
        print(f"[INFO] feature count: {len(bundle.feature_names)}")

        dataset_path = resolve_dataset_path()
        df = pd.read_csv(dataset_path)
        print(f"[OK] dataset: {dataset_path}")
        print(f"[OK] ML_dataset 読み込み成功: shape={df.shape}")

        X = build_feature_frame(df, bundle.feature_names)
        sample = df.tail(1)
        X_sample = X.tail(1)

        sample_context = {
            col: to_python_scalar(sample.iloc[0][col])
            for col in SAMPLE_CONTEXT_COLS
            if col in sample.columns
        }
        print("\n[INFO] sample match:")
        print(sample_context)

        prediction = run_prediction(bundle, X_sample)
        print("\n[OK] 予測テスト成功")
        for key, value in prediction.items():
            print(f"  {key}: {value}")
        return 0
    except Exception as exc:
        print(f"[ERROR] smoke test failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
