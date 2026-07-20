"""Build the public latest and historical final-standings forecasts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.predict.standings_forecast import build_standings_forecast, write_standings_forecast


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="J1の最終順位予測を生成します")
    parser.add_argument("--matches", default="Data/processed/matches_2026_27_j1_clean.csv")
    parser.add_argument("--predictions", default="outputs/all_unplayed_predictions.json")
    parser.add_argument("--latest", default="outputs/standings_forecast/latest.json")
    parser.add_argument("--history-dir", default="outputs/standings_forecast/history")
    parser.add_argument("--simulations", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=202_627)
    parser.add_argument("--no-history", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    forecast = build_standings_forecast(
        args.matches,
        args.predictions,
        simulations=args.simulations,
        seed=args.seed,
    )
    latest, history = write_standings_forecast(
        forecast,
        args.latest,
        None if args.no_history else args.history_dir,
    )
    print(
        json.dumps(
            {
                "latest": str(latest),
                "history": str(history) if history else None,
                "teams": len(forecast["teams"]),
                "simulation_count": forecast["simulation_count"],
                "fixture_summary": forecast["fixture_summary"],
                "warnings": forecast["warnings"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
