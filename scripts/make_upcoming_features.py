"""Generate upcoming match feature rows."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.features.build_match_features import build_match_features
from src.features.build_upcoming_features import build_upcoming_features
from src.features.snapshots import save_upcoming_feature_snapshot
from src.features.validation import validate_feature_frame

import joblib
import pandas as pd


def _read_sources_csv(path: Path) -> pd.DataFrame | None:
    if not path.exists() or path.stat().st_size == 0:
        return None
    try:
        sources = pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return None
    if sources.empty:
        return None
    return sources


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
    return {
        "path": str(output_path),
        "rows": int(len(report)),
        "overall_actual_rate": float(report["actual_count"].sum() / report["total_rows"].sum()) if not report.empty else 0,
        "overall_fallback_rate": float(report["fallback_count"].sum() / report["total_rows"].sum()) if not report.empty else 0,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="未来試合用特徴量を生成します")
    parser.add_argument("--season", default="2026_special")
    parser.add_argument("--category", default="100yj1")
    parser.add_argument("--season-key", default="2026_special", help="保存用のシーズン識別子")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    match_df = build_match_features()
    upcoming_df = build_upcoming_features()
    model_features = joblib.load(PROJECT_ROOT / "Models" / "model_features.pkl")
    validation = validate_feature_frame(upcoming_df, model_features)
    source_report = write_source_report(
        PROJECT_ROOT / "Data" / "features" / "upcoming_features_2026_special_sources.csv",
        PROJECT_ROOT / "Data" / "features" / "upcoming_features_2026_special_source_report.csv",
    )
    sources_path = PROJECT_ROOT / "Data" / "features" / "upcoming_features_2026_special_sources.csv"
    sources_df = _read_sources_csv(sources_path)
    snapshot = save_upcoming_feature_snapshot(upcoming_df, sources=sources_df, season_key=args.season_key)
    print(
        json.dumps(
            {
                "match_features_rows": int(len(match_df)),
                "upcoming_features_rows": int(len(upcoming_df)),
                "validation": validation,
                "source_report": source_report,
                "snapshot": {
                    "features": str(snapshot.features.relative_to(PROJECT_ROOT)),
                    "sources": str(snapshot.sources.relative_to(PROJECT_ROOT)) if snapshot.sources else None,
                    "metadata": str(snapshot.metadata.relative_to(PROJECT_ROOT)),
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
