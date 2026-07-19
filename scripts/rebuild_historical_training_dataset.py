"""Rebuild 2021-2025 J1 training rows with pre-match feature timing."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.scraping import safe_write_csv
from src.features.point_in_time import POST_MATCH_FEATURES, rebuild_historical_training_features


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="通常J1履歴を試合前時点の特徴量へ再構築します")
    parser.add_argument("--input", default="Data/ML_dataset.csv")
    parser.add_argument("--output", default="Data/features/training_dataset_2021_2025_point_in_time.csv")
    parser.add_argument("--source-output", default="Data/features/training_dataset_2021_2025_point_in_time_sources.csv")
    parser.add_argument("--report-output", default="Data/features/training_dataset_2021_2025_point_in_time_report.json")
    return parser.parse_args()


def resolve(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def main() -> int:
    args = parse_args()
    original = pd.read_csv(resolve(args.input))
    rebuilt = rebuild_historical_training_features(original)
    safe_write_csv(rebuilt.features, resolve(args.output))
    safe_write_csv(rebuilt.sources, resolve(args.source_output))
    source_counts = {
        column: rebuilt.sources[column].value_counts().to_dict()
        for column in [
            "Attendance",
            "Stadium_Fill_Rate",
            "Home_Rank_Delta_3",
            "Away_Rank_Delta_3",
            "Home_Urgency_Score",
            "Away_Urgency_Score",
            "Home_Formation",
            "Away_Formation",
            "Home_Rolling_xG",
            "Home_AGI",
            "Home_KAGI",
        ]
        if column in rebuilt.sources.columns
    }
    report = {
        "input": args.input,
        "output": args.output,
        "rows": int(len(rebuilt.features)),
        "seasons": sorted(rebuilt.features["Season"].astype(str).unique().tolist()),
        "excluded_post_match_features": sorted(POST_MATCH_FEATURES),
        "historical_xg_agi_kagi_policy": "season_aggregate_estimate_when_snapshot_unavailable",
        "source_counts": source_counts,
    }
    report_path = resolve(args.report_output)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
