"""Safely refresh fixtures, features and prediction outputs for one competition."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import ACTIVE_COMPETITION_KEY, competition_upcoming_features_path, get_competition
from src.data.scraping import write_json


DEFAULT_HISTORY = PROJECT_ROOT / "Data" / "features" / "training_dataset_with_2026_special_point_in_time.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="大会別の予測更新パイプラインを実行します")
    parser.add_argument("--competition-key", default=ACTIVE_COMPETITION_KEY)
    parser.add_argument("--history", default=str(DEFAULT_HISTORY))
    parser.add_argument("--model-dir", default="Models")
    parser.add_argument("--shadow-model-dir")
    parser.add_argument("--use-cache", action="store_true")
    return parser.parse_args()


def _run(command: list[str]) -> None:
    print("[RUN]", " ".join(command))
    subprocess.run(command, cwd=PROJECT_ROOT, check=True)


def _prediction_command(
    *, mode: str, features: Path, model_dir: str, shadow_model_dir: str | None, competition_key: str
) -> list[str]:
    current_scorers = PROJECT_ROOT / "Data" / "processed" / f"player_stats_{competition_key}_clean.csv"
    # At the opening round the new-season player ranking does not exist yet.
    # Reuse the latest completed-season ranking until the current file is
    # available; this affects only scorer suggestions, not match probabilities.
    scorer_candidates = (
        current_scorers
        if current_scorers.exists()
        else PROJECT_ROOT / "Data" / "processed" / "player_stats_2026_special_clean.csv"
    )
    command = [
        sys.executable,
        "scripts/run_prediction.py",
        "--mode",
        mode,
        "--features",
        str(features),
        "--model-dir",
        model_dir,
        # This file is optional before season start; the predictor falls back
        # to empty scorer candidates instead of failing the prediction job.
        "--scorer-candidates",
        str(scorer_candidates),
    ]
    if shadow_model_dir:
        command.extend(["--shadow-model-dir", shadow_model_dir])
    return command


def main() -> int:
    args = parse_args()
    profile = get_competition(args.competition_key)
    report: dict[str, object] = {
        "updated_at": datetime.now(ZoneInfo("Asia/Tokyo")).isoformat(timespec="seconds"),
        "competition_key": profile.key,
        "steps": [],
    }
    try:
        update_cmd = [sys.executable, "scripts/update_competition_data.py", "--competition-key", profile.key]
        if args.use_cache:
            update_cmd.append("--use-cache")
        _run(update_cmd)
        report["steps"].append("fixtures_updated")

        _run(
            [
                sys.executable,
                "scripts/make_upcoming_features.py",
                "--competition-key",
                profile.key,
                "--history",
                args.history,
            ]
        )
        report["steps"].append("features_generated")
        features_path = competition_upcoming_features_path(profile.key)
        features = pd.read_csv(features_path) if features_path.exists() else pd.DataFrame()
        report["upcoming_feature_rows"] = int(len(features))

        # Never call the writer with an empty target.  This deliberately
        # preserves the last valid public prediction when there are no known
        # future fixtures (for example, before all postponed matches are set).
        if features.empty:
            report["prediction_updated"] = False
            report["reason"] = "予測対象の未消化試合がありません。既存予測は保持しました。"
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0

        _run(
            _prediction_command(
                mode="next_section",
                features=features_path,
                model_dir=args.model_dir,
                shadow_model_dir=args.shadow_model_dir,
                competition_key=profile.key,
            )
        )
        _run(
            _prediction_command(
                mode="all_unplayed",
                features=features_path,
                model_dir=args.model_dir,
                shadow_model_dir=args.shadow_model_dir,
                competition_key=profile.key,
            )
        )
        report["steps"].extend(["next_section_predicted", "all_unplayed_predicted"])
        report["prediction_updated"] = True
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except subprocess.CalledProcessError as exc:
        report["error"] = f"step failed with exit code {exc.returncode}: {exc.cmd}"
        write_json(PROJECT_ROOT / "Data" / "processed" / f"pipeline_{profile.key}_report.json", report)
        print(json.dumps(report, ensure_ascii=False, indent=2), file=sys.stderr)
        return exc.returncode or 1
    finally:
        if "error" not in report:
            write_json(PROJECT_ROOT / "Data" / "processed" / f"pipeline_{profile.key}_report.json", report)


if __name__ == "__main__":
    sys.exit(main())
