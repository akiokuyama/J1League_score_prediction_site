"""Generate model-ready feature rows for an upcoming competition schedule."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import joblib
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import (  # noqa: E402
    ACTIVE_COMPETITION_KEY,
    FEATURE_DATA_DIR,
    PROCESSED_DATA_DIR,
    competition_matches_path,
    competition_upcoming_features_path,
    competition_upcoming_sources_path,
    get_competition,
)
from src.features.build_upcoming_features import build_upcoming_features  # noqa: E402
from src.features.snapshots import save_upcoming_feature_snapshot  # noqa: E402
from src.features.validation import validate_feature_frame  # noqa: E402


DEFAULT_HISTORY = PROJECT_ROOT / "Data" / "features" / "training_dataset_with_2026_special_point_in_time.csv"


def _read_sources_csv(path: Path) -> pd.DataFrame | None:
    if not path.exists() or path.stat().st_size == 0:
        return None
    try:
        sources = pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return None
    return None if sources.empty else sources


def write_source_report(path: Path, output_path: Path) -> dict[str, object]:
    sources = _read_sources_csv(path)
    if sources is None:
        return {"path": str(output_path), "rows": 0}
    rows = []
    for col in sources.columns:
        counts = sources[col].value_counts(dropna=False).to_dict()
        total = len(sources)
        actual = sum(count for label, count in counts.items() if str(label).startswith("actual"))
        fallback = sum(count for label, count in counts.items() if str(label).startswith("fallback"))
        rows.append(
            {
                "column": col,
                "total_rows": total,
                "actual_count": actual,
                "fallback_count": fallback,
                "actual_rate": actual / total if total else 0,
                "fallback_rate": fallback / total if total else 0,
                "top_source": max(counts, key=counts.get) if counts else "",
                "source_counts": json.dumps(counts, ensure_ascii=False, sort_keys=True),
            }
        )
    report = pd.DataFrame(rows)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(output_path, index=False)
    return {"path": str(output_path), "rows": int(len(report))}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="未来試合用特徴量を生成します")
    parser.add_argument("--competition-key", default=ACTIVE_COMPETITION_KEY)
    parser.add_argument("--history", default=str(DEFAULT_HISTORY))
    parser.add_argument("--model-features", default=str(PROJECT_ROOT / "Models" / "model_features.pkl"))
    parser.add_argument("--matches")
    parser.add_argument("--output")
    parser.add_argument("--sources-output")
    parser.add_argument("--match-output")
    parser.add_argument("--source-report-output")
    parser.add_argument("--market-values")
    parser.add_argument("--kagi")
    parser.add_argument("--expected")
    parser.add_argument("--formations")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    profile = get_competition(args.competition_key)
    matches_path = Path(args.matches) if args.matches else competition_matches_path(profile.key)
    output_path = Path(args.output) if args.output else competition_upcoming_features_path(profile.key)
    sources_path = Path(args.sources_output) if args.sources_output else competition_upcoming_sources_path(profile.key)
    match_output = Path(args.match_output) if args.match_output else FEATURE_DATA_DIR / f"match_features_{profile.key}.csv"
    source_report_output = (
        Path(args.source_report_output)
        if args.source_report_output
        else FEATURE_DATA_DIR / f"upcoming_features_{profile.key}_source_report.csv"
    )
    asset_kwargs = {
        "market_values_path": args.market_values or str(PROCESSED_DATA_DIR / f"market_values_{profile.key}_clean.csv"),
        "kagi_path": args.kagi or str(PROJECT_ROOT / "Data" / "raw" / "football_lab" / f"kagi_{profile.key}.csv"),
        "expected_path": args.expected or str(PROJECT_ROOT / "Data" / "raw" / "football_lab" / f"expected_{profile.key}.csv"),
        "formations_path": args.formations or str(PROCESSED_DATA_DIR / f"formations_{profile.key}_clean.csv"),
    }
    common_kwargs = {
        "matches_path": matches_path,
        "history_path": args.history,
        "model_features_path": args.model_features,
        **asset_kwargs,
    }
    match_df = build_upcoming_features(
        **common_kwargs,
        output_path=match_output,
        sources_output_path=FEATURE_DATA_DIR / f"match_features_{profile.key}_sources.csv",
        only_unplayed=False,
    )
    upcoming_df = build_upcoming_features(
        **common_kwargs,
        output_path=output_path,
        sources_output_path=sources_path,
        only_unplayed=True,
    )
    model_features = joblib.load(args.model_features)
    validation = validate_feature_frame(upcoming_df, model_features)
    source_report = write_source_report(sources_path, source_report_output)
    sources_df = _read_sources_csv(sources_path)
    snapshot = save_upcoming_feature_snapshot(upcoming_df, sources=sources_df, season_key=profile.key)
    print(
        json.dumps(
            {
                "competition_key": profile.key,
                "match_features_rows": int(len(match_df)),
                "upcoming_features_rows": int(len(upcoming_df)),
                "validation": validation,
                "source_report": source_report,
                "snapshot": {"features": str(snapshot.features), "sources": str(snapshot.sources) if snapshot.sources else None},
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
