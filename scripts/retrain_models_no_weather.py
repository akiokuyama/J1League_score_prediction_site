"""Retrain score models without Weather features."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "soccer_score_app_matplotlib"))
os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.models.train_score_models import (
    activate_models,
    build_training_frame,
    model_metadata,
    save_models,
    train_and_evaluate,
    train_full_models,
)
from src.models.score_model_selection import CANDIDATE_WEIGHTS, evaluate_goal_model_candidates


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="天候なしモデルを再学習します")
    parser.add_argument("--dataset", default="Data/ML_dataset.csv")
    parser.add_argument("--output-dir", default="Models/score_distribution_2026_27_v1")
    parser.add_argument("--test-season", default="2025", help="評価用に取り分けるシーズン。例: 2025, 2026_special")
    parser.add_argument(
        "--test-start-date",
        help="指定時は同一シーズンのこの日以降を時系列ホールドアウトとして評価します。",
    )
    parser.add_argument(
        "--exclude-test-season-history",
        action="store_true",
        help="時系列評価でテストシーズンの分割日前データも学習から除外します。",
    )
    parser.add_argument("--model-version", default="score_distribution_2026_27_v1")
    parser.add_argument(
        "--score-model",
        choices=["auto", *CANDIDATE_WEIGHTS],
        default="auto",
        help="期待得点モデル。auto は時系列Log lossが最小の候補を選びます。",
    )
    parser.add_argument(
        "--max-goals",
        type=int,
        default=8,
        help="確率分布内部で列挙する片側最大得点。",
    )
    parser.add_argument("--activate", action="store_true", help="既存モデルをバックアップ後に正式反映する")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        X, y_goals, y_result, _, raw_df = build_training_frame(
            args.dataset,
            exclude_weather=True,
        )
        selection = evaluate_goal_model_candidates(
            X,
            y_goals,
            y_result,
            raw_df,
            max_goals=args.max_goals,
        )
        selected_candidate = (
            selection["selected_candidate"] if args.score_model == "auto" else args.score_model
        )
        poisson_weight = float(CANDIDATE_WEIGHTS[selected_candidate])
        calibration_temperature = float(
            selection["candidates"][selected_candidate]["deployment_temperature"]
        )

        eval_result = train_and_evaluate(
            args.dataset,
            exclude_weather=True,
            test_season=args.test_season,
            test_start_date=args.test_start_date,
            include_test_season_history=not args.exclude_test_season_history,
            poisson_weight=poisson_weight,
        )
        full_result = train_full_models(
            args.dataset,
            exclude_weather=True,
            poisson_weight=poisson_weight,
        )
        metadata = model_metadata(
            version=args.model_version,
            dataset_path=args.dataset,
            evaluation={
                "train_rows": eval_result.train_rows,
                "test_rows": eval_result.test_rows,
                "metrics": eval_result.metrics,
            },
            feature_count=len(full_result.feature_names),
            test_season=args.test_season,
            test_start_date=args.test_start_date,
        )
        metadata["feature_lineage"] = {
            "policy": "point_in_time_or_reconstructed_pre_match",
            "historical_football_lab_without_snapshot": "final_snapshot_estimate_restored_unit",
            "realised_attendance": "excluded",
            "test_season_history_included": not args.exclude_test_season_history,
        }
        metadata["prediction_strategy"] = "expected_goals_score_distribution_v1"
        metadata["goal_model"] = {
            "candidate": selected_candidate,
            "poisson_weight": poisson_weight,
        }
        metadata["probability_calibration"] = {
            "method": "temperature_scaling",
            "temperature": calibration_temperature,
            "fitted_temperature": float(
                selection["candidates"][selected_candidate]["fitted_temperature"]
            ),
            "applied": bool(
                selection["candidates"][selected_candidate][
                    "calibration_improves_walk_forward"
                ]
            ),
            "fit_source": "walk_forward_out_of_fold_predictions",
            "selection_metric": selection["selection_metric"],
        }
        metadata["score_distribution"] = {
            "distribution": "independent_poisson",
            "max_goals": int(args.max_goals),
            "result_probability_source": "sum_of_exact_score_probabilities",
        }
        metadata["model_selection"] = {
            "selected_candidate": selected_candidate,
            "selected_poisson_weight": poisson_weight,
            "selected_temperature": calibration_temperature,
            "selection_metric": selection["selection_metric"],
            "weighted_raw": selection["candidates"][selected_candidate]["weighted_raw"],
            "weighted_progressive_calibrated": selection["candidates"][selected_candidate][
                "weighted_progressive_calibrated"
            ],
            "calibration_improves_walk_forward": selection["candidates"][selected_candidate][
                "calibration_improves_walk_forward"
            ],
        }
        save_models(full_result, args.output_dir, metadata)
        selection_path = Path(args.output_dir) / "score_model_selection.json"
        selection_path.write_text(
            json.dumps(selection, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        output = {
            "output_dir": str(args.output_dir),
            "feature_count": len(full_result.feature_names),
            "selected_candidate": selected_candidate,
            "poisson_weight": poisson_weight,
            "calibration_temperature": calibration_temperature,
            "selection_report": str(selection_path),
            "evaluation": metadata["evaluation"],
            "activated": False,
            "backup_dir": None,
        }
        if args.activate:
            backup_dir = activate_models(args.output_dir, "Models")
            output["activated"] = True
            output["backup_dir"] = str(backup_dir)

        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(f"[ERROR] 天候なしモデル再学習に失敗しました: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
