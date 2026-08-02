"""Plot gain-based feature importance for the production goal models."""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path
from typing import Any

os.environ.setdefault(
    "MPLCONFIGDIR",
    str(Path(tempfile.gettempdir()) / "soccer_score_app_matplotlib"),
)

import joblib
import matplotlib.pyplot as plt
import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_DIR = PROJECT_ROOT / "models" / "score_distribution_2026_27_v1"
DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "docs"
    / "articles"
    / "assets"
    / "qiita_feature_importance_expected_goals.png"
)


def _unwrap_multioutput_model(model: Any) -> Any:
    """Return the MultiOutputRegressor used for the selected production model."""
    if hasattr(model, "estimators_"):
        return model
    if hasattr(model, "l2_model") and hasattr(model.l2_model, "estimators_"):
        return model.l2_model
    raise TypeError(f"Unsupported goal model type: {type(model)!r}")


def _normalized_gain(estimator: Any) -> np.ndarray:
    gain = np.asarray(
        estimator.booster_.feature_importance(importance_type="gain"),
        dtype=float,
    )
    total = gain.sum()
    if total <= 0:
        raise ValueError("The model returned no positive gain importance.")
    return gain / total * 100.0


def plot_feature_importance(
    model_dir: Path,
    output_path: Path,
    *,
    top_n: int = 20,
) -> None:
    model = joblib.load(model_dir / "model_step1_goals.pkl")
    feature_names = np.asarray(joblib.load(model_dir / "model_features.pkl"))
    multioutput_model = _unwrap_multioutput_model(model)

    if len(multioutput_model.estimators_) != 2:
        raise ValueError("Expected separate home-goal and away-goal estimators.")

    home_gain = _normalized_gain(multioutput_model.estimators_[0])
    away_gain = _normalized_gain(multioutput_model.estimators_[1])
    if len(feature_names) != len(home_gain):
        raise ValueError("Feature-name count does not match model importance count.")

    mean_gain = (home_gain + away_gain) / 2.0
    selected = np.argsort(mean_gain)[::-1][:top_n][::-1]

    labels = feature_names[selected]
    y = np.arange(len(selected))
    bar_height = 0.34

    fig, ax = plt.subplots(figsize=(14, 10))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("#f7f9fb")

    ax.barh(
        y + bar_height / 2,
        home_gain[selected],
        height=bar_height,
        color="#0f8b8d",
        label="Home goals model",
    )
    ax.barh(
        y - bar_height / 2,
        away_gain[selected],
        height=bar_height,
        color="#e07a5f",
        label="Away goals model",
    )
    ax.scatter(
        mean_gain[selected],
        y,
        color="#172a3a",
        marker="D",
        s=30,
        zorder=3,
        label="Mean",
    )

    ax.set_yticks(y, labels)
    ax.set_xlabel("Normalized gain importance (%)", fontsize=12)
    ax.set_title(
        "Top 20 Feature Importances for Expected Goals",
        fontsize=17,
        fontweight="bold",
        pad=16,
    )
    ax.text(
        0.0,
        1.01,
        "LightGBM gain; each goal model is normalized to 100%, sorted by the mean",
        transform=ax.transAxes,
        color="#536471",
        fontsize=10,
    )
    ax.grid(axis="x", color="#d9e1e8", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.legend(loc="lower right", frameon=False)
    ax.tick_params(axis="y", labelsize=9)
    ax.tick_params(axis="x", labelsize=10)
    ax.margins(y=0.02)

    fig.text(
        0.99,
        0.01,
        f"Model: {model_dir.name}",
        ha="right",
        color="#718096",
        fontsize=9,
    )
    fig.subplots_adjust(left=0.38, right=0.97, top=0.90, bottom=0.08)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)

    print(f"Saved: {output_path}")
    print("Top features by mean normalized gain:")
    for rank, index in enumerate(np.argsort(mean_gain)[::-1][:top_n], start=1):
        print(
            f"{rank:2d}. {feature_names[index]:50s} "
            f"mean={mean_gain[index]:6.2f}% "
            f"home={home_gain[index]:6.2f}% "
            f"away={away_gain[index]:6.2f}%"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--top-n", type=int, default=20)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    plot_feature_importance(args.model_dir, args.output, top_n=args.top_n)
