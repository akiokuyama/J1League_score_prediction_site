"""Utilities for loading the trained J1 score prediction models."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class ModelBundle:
    """Container for the trained models and feature metadata."""

    step1_goals: Any
    step2_clf: Any
    step2_diff: Any
    feature_names: list[str]
    model_dir: Path
    model_metadata: dict[str, Any]
    calibration_temperature: float
    prediction_strategy: str


MODEL_CANDIDATES = {
    "step1_goals": (
        "model_step1_goals.pkl",
        "step1_goals.pkl",
        "score_model.pkl",
        "goals_model.pkl",
    ),
    "step2_clf": (
        "model_step2_clf.pkl",
        "step2_clf.pkl",
        "result_classifier.pkl",
        "match_result_model.pkl",
    ),
    "step2_diff": (
        "model_step2_diff.pkl",
        "step2_diff.pkl",
        "goal_diff_model.pkl",
        "diff_model.pkl",
    ),
    "feature_names": (
        "model_features.pkl",
        "features.pkl",
        "feature_names.pkl",
        "model_feature_names.pkl",
    ),
}


def _candidate_model_dirs(model_dir: str | Path | None) -> list[Path]:
    if model_dir is not None:
        return [Path(model_dir).expanduser().resolve()]

    return [
        PROJECT_ROOT / "Models",
        PROJECT_ROOT / "models",
    ]


def _find_existing_model_dir(model_dir: str | Path | None) -> Path:
    candidates = _candidate_model_dirs(model_dir)
    for candidate in candidates:
        if candidate.is_dir():
            return candidate

    searched = ", ".join(str(path) for path in candidates)
    raise FileNotFoundError(f"Model directory not found. Searched: {searched}")


def _find_required_file(model_dir: Path, logical_name: str) -> Path:
    candidates = MODEL_CANDIDATES[logical_name]
    for filename in candidates:
        path = model_dir / filename
        if path.is_file():
            return path

    expected = ", ".join(candidates)
    raise FileNotFoundError(
        f"Required model file for '{logical_name}' was not found in {model_dir}. "
        f"Expected one of: {expected}"
    )


def _load_feature_names(path: Path) -> list[str]:
    raw_features = joblib.load(path)
    if not isinstance(raw_features, (list, tuple)):
        raise TypeError(
            f"Feature file must contain a list or tuple, got {type(raw_features).__name__}: {path}"
        )

    feature_names = [str(feature) for feature in raw_features]
    if not feature_names:
        raise ValueError(f"Feature file is empty: {path}")
    return feature_names


def _load_model_metadata(model_dir: Path) -> dict[str, Any]:
    path = model_dir / "model_metadata.json"
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def load_models(model_dir: str | Path | None = None) -> ModelBundle:
    """Load trained models from Models/ or a caller-provided directory."""

    resolved_model_dir = _find_existing_model_dir(model_dir)
    paths = {
        name: _find_required_file(resolved_model_dir, name)
        for name in MODEL_CANDIDATES
    }

    metadata = _load_model_metadata(resolved_model_dir)
    calibration = metadata.get("probability_calibration")
    if not isinstance(calibration, dict):
        calibration = {}
    try:
        temperature = float(calibration.get("temperature", 1.0))
    except (TypeError, ValueError):
        temperature = 1.0
    if not math.isfinite(temperature) or temperature <= 0:
        temperature = 1.0

    return ModelBundle(
        step1_goals=joblib.load(paths["step1_goals"]),
        step2_clf=joblib.load(paths["step2_clf"]),
        step2_diff=joblib.load(paths["step2_diff"]),
        feature_names=_load_feature_names(paths["feature_names"]),
        model_dir=resolved_model_dir,
        model_metadata=metadata,
        calibration_temperature=temperature,
        prediction_strategy=str(metadata.get("prediction_strategy") or "legacy_three_model_combination"),
    )
