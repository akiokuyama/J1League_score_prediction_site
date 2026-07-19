"""Run batch prediction for upcoming matches."""

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

from src.predict.predict_upcoming import (
    load_upcoming_features,
    predict_upcoming_matches,
    select_prediction_targets,
    write_predictions_safely,
)


def default_output_for_mode(mode: str) -> str:
    if mode == "all_unplayed":
        return "outputs/all_unplayed_predictions.json"
    return "outputs/latest_predictions.json"


def default_csv_for_output(output_path: str) -> str:
    path = Path(output_path)
    if path.name == "latest_predictions.json":
        return str(path.with_name("latest_predictions.csv"))
    return str(path.with_suffix(".csv"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="一括予測を実行します")
    parser.add_argument("--mode", default="next_section", choices=["next_section", "all_unplayed", "date_range"])
    parser.add_argument("--features", default="Data/features/upcoming_features_2026_special.csv")
    parser.add_argument("--model-dir", help="候補モデルを含むモデルディレクトリ。未指定時は Models/ を使います。")
    parser.add_argument(
        "--shadow-model-dir",
        help="比較用モデルディレクトリ。指定時は公開出力と分離して同じ対象を予測します。",
    )
    parser.add_argument(
        "--shadow-output",
        help="比較用予測JSON。未指定時は outputs/shadow/<公開JSON名> を使います。",
    )
    parser.add_argument(
        "--scorer-candidates",
        default="Data/processed/player_stats_2026_special_clean.csv",
        help="得点者候補に使う選手スタッツCSV。",
    )
    parser.add_argument("--output-dir", default="outputs", help="履歴JSONとlast_updated.txtの保存先。")
    parser.add_argument("--output", help="予測JSONの保存先。未指定時はmodeごとのデフォルトを使います。")
    parser.add_argument("--csv-output", help="確認用CSVの保存先。未指定時はJSON名に対応するCSVを使います。")
    parser.add_argument("--date-from")
    parser.add_argument("--date-to")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        features = load_upcoming_features(args.features)
        targets = select_prediction_targets(
            features,
            mode=args.mode,
            date_from=args.date_from,
            date_to=args.date_to,
        )
        predictions = predict_upcoming_matches(
            targets,
            model_dir=args.model_dir,
            feature_source=args.features,
            scorer_candidates_path=args.scorer_candidates,
        )
        output_path = args.output or default_output_for_mode(args.mode)
        csv_path = args.csv_output or default_csv_for_output(output_path)
        save_result = write_predictions_safely(predictions, output_dir=args.output_dir, output_path=output_path, csv_path=csv_path)
        shadow_result = None
        shadow_predictions = None
        if args.shadow_model_dir:
            shadow_predictions = predict_upcoming_matches(
                targets,
                model_dir=args.shadow_model_dir,
                feature_source=args.features,
                scorer_candidates_path=args.scorer_candidates,
            )
            shadow_output = args.shadow_output or str(
                Path("outputs") / "shadow" / Path(output_path).name
            )
            shadow_csv = default_csv_for_output(shadow_output)
            shadow_result = write_predictions_safely(
                shadow_predictions,
                output_dir=Path(shadow_output).parent,
                output_path=shadow_output,
                csv_path=shadow_csv,
            )
        print(
            json.dumps(
                {
                    "prediction_count": len(predictions["matches"]),
                    "save_result": save_result,
                    "shadow_prediction_count": len(shadow_predictions["matches"]) if shadow_predictions else 0,
                    "shadow_save_result": shadow_result,
                    "predictions": predictions,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except Exception as exc:
        print(f"[ERROR] 一括予測に失敗しました: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
