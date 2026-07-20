"""Validate the final-standings forecast consumed by Streamlit."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any


def validate_standings_forecast(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        raise ValueError(f"missing file: {target}")
    data = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("top-level JSON must be an object")
    teams = data.get("teams")
    if not isinstance(teams, list) or len(teams) < 2:
        raise ValueError("teams must contain at least two teams")
    if int(data.get("simulation_count") or 0) < 100:
        raise ValueError("simulation_count must be at least 100")

    ranks = sorted(int(team.get("predicted_rank")) for team in teams if isinstance(team, dict))
    if ranks != list(range(1, len(teams) + 1)):
        raise ValueError("predicted_rank must be unique and consecutive")
    codes = [str(team.get("team")) for team in teams]
    if len(set(codes)) != len(codes):
        raise ValueError("team codes must be unique")

    for team in teams:
        for key in ("champion_probability", "top3_probability", "bottom3_probability"):
            probability = float(team.get(key))
            if not math.isfinite(probability) or not 0 <= probability <= 1:
                raise ValueError(f"{key} must be between 0 and 1")
        rank_probabilities = team.get("rank_probabilities")
        if not isinstance(rank_probabilities, dict):
            raise ValueError("rank_probabilities must be an object")
        if not math.isclose(sum(float(value) for value in rank_probabilities.values()), 1.0, abs_tol=2e-4):
            raise ValueError("rank_probabilities must sum to 1")
    return data


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate final standings forecast JSON")
    parser.add_argument("--path", default="outputs/standings_forecast/latest.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        data = validate_standings_forecast(args.path)
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] standings forecast validation failed: {exc}", file=sys.stderr)
        return 1
    print(f"[OK] standings forecast teams: {len(data['teams'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
