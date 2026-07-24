"""Build outputs/past_prediction_results.json from prediction history."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "soccer_score_app_matplotlib"))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.past_predictions import build_past_prediction_results, write_past_prediction_results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="過去予測結果JSONを生成します")
    parser.add_argument("--history-dir", default="outputs/prediction_history")
    parser.add_argument("--matches", default="Data/processed/matches_2026_special_clean.csv")
    parser.add_argument("--output", default="outputs/past_prediction_results.json")
    parser.add_argument(
        "--season-output-dir",
        default="outputs/past_prediction_results",
        help="シーズン別の過去予測結果JSONを保存するディレクトリ",
    )
    parser.add_argument(
        "--pwa-season-output-dir",
        default="docs/app/data/past_prediction_results",
        help="PWAから配信するシーズン別の過去予測結果JSONを保存するディレクトリ",
    )
    parser.add_argument("--allow-empty", action="store_true", help="生成件数が0件でも出力ファイルを上書きします")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    data = build_past_prediction_results(history_dir=args.history_dir, matches_path=args.matches)
    diagnostics = data.get("diagnostics", {})
    if not data.get("matches") and Path(args.output).exists() and not args.allow_empty:
        print(
            json.dumps(
                {
                    "output": str(Path(args.output).resolve()),
                    "match_count": 0,
                    "diagnostics": diagnostics,
                    "updated": False,
                    "reason": "match_idは一致していますが、finishedかつスコア確定済みの評価対象試合がないため、既存ファイルを保持しました。",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    output_path = write_past_prediction_results(data, args.output)
    season = str(data.get("season") or "unknown")
    season_key = "2026_27_j1" if season == "2026_27" else season
    season_output_path = write_past_prediction_results(
        data,
        Path(args.season_output_dir) / f"{season_key}.json",
    )
    pwa_season_output_path = write_past_prediction_results(
        data,
        Path(args.pwa_season_output_dir) / f"{season_key}.json",
    )
    print(
        json.dumps(
            {
                "output": str(output_path),
                "season_output": str(season_output_path),
                "pwa_season_output": str(pwa_season_output_path),
                "match_count": len(data.get("matches", [])),
                "diagnostics": diagnostics,
                "updated": True,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
