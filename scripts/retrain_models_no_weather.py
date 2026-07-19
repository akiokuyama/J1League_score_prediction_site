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
    model_metadata,
    save_models,
    train_and_evaluate,
    train_full_models,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="天候なしモデルを再学習します")
    parser.add_argument("--dataset", default="Data/ML_dataset.csv")
    parser.add_argument("--output-dir", default="Models/point_in_time_2026_special_v1")
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
    parser.add_argument("--model-version", default="point_in_time_2026_special_v1")
    parser.add_argument("--activate", action="store_true", help="既存モデルをバックアップ後に正式反映する")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        eval_result = train_and_evaluate(
            args.dataset,
            exclude_weather=True,
            test_season=args.test_season,
            test_start_date=args.test_start_date,
            include_test_season_history=not args.exclude_test_season_history,
        )
        full_result = train_full_models(args.dataset, exclude_weather=True)
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
        save_models(full_result, args.output_dir, metadata)

        output = {
            "output_dir": str(args.output_dir),
            "feature_count": len(full_result.feature_names),
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
