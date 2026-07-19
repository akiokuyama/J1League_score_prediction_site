"""Build a leakage-safe 2026_special training dataset.

Saved pre-match snapshots are used when available.  Dynamic values for every
completed match are reconstructed from results available before kick-off.
The raw completed-match feature frame is never copied into training rows;
approved season estimates are opt-in and recorded in the source manifest.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.scraping import safe_write_csv
from src.features.point_in_time import (
    TARGET_COLUMNS,
    align_legacy_model_units,
    load_legacy_aggregate_priors,
    rebuild_pre_match_features,
)
from src.features.snapshots import SNAPSHOT_DIR, load_feature_snapshots


KNOWN_TBD_VALUES = {"", "nan", "none", "tbd", "未定"}
SNAPSHOT_OVERRIDE_COLUMNS = {
    "Home_Market_Value", "Away_Market_Value", "Market_Value_Diff",
    "Home_Rolling_xG", "Away_Rolling_xG",
    "Home_AGI", "Home_KAGI", "Away_AGI", "Away_KAGI",
    "Home_Formation", "Away_Formation",
    "is_Mirror_Game",
    "Home_DF_count", "Home_MF_count", "Home_FW_count",
    "Away_DF_count", "Away_MF_count", "Away_FW_count",
    "Home_Midfield_Advantage", "Defense_Margin_Home", "Defense_Margin_Away",
    "Backline_Matchup",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "保存済みの節別特徴量スナップショットと試合結果を結合し、"
            "シーズン終了後の再学習用データセットを作成します。"
        )
    )
    parser.add_argument("--season", default="2026_special")
    parser.add_argument("--season-key", default="2026_special", help="保存用のシーズン識別子")
    parser.add_argument("--season-label", default="2026_special", help="レポート表示用のシーズン名")
    parser.add_argument("--season-name", default="2026_special", help="学習データのSeason列に保存する値")
    parser.add_argument("--reference-dataset", default="Data/ML_dataset.csv")
    parser.add_argument("--matches", default="Data/processed/matches_2026_special_clean.csv")
    parser.add_argument(
        "--fallback-features",
        default="Data/features/match_features_2026_special.csv",
        help="互換性のために受け付けます。リーク防止のため通常実行では使いません。",
    )
    parser.add_argument("--snapshot-dir", default="Data/features/snapshots")
    parser.add_argument(
        "--strategy",
        choices=["strict", "snapshot_with_aggregate_estimate", "legacy_aggregate"],
        default="strict",
        help=(
            "strict は保存済み試合前情報のみ、snapshot_with_aggregate_estimate は"
            "スナップショットを優先し欠損だけシーズン集計推定、legacy_aggregate は全行を集計推定。"
        ),
    )
    parser.add_argument(
        "--aggregate-normalization-divisor",
        type=float,
        default=38.0,
        help=(
            "後方互換のためだけに残している非推奨オプション。"
            "xGは試合平均、AGI/KAGIは指数なので現在は除算しません。"
        ),
    )
    parser.add_argument("--output", default="Data/features/training_dataset_2026_special_point_in_time.csv")
    parser.add_argument(
        "--combined-output",
        default="Data/features/training_dataset_with_2026_special_point_in_time.csv",
        help="reference dataset に2026_special point-in-time行を追加した再学習用CSV",
    )
    parser.add_argument("--source-output", default="Data/features/training_dataset_2026_special_point_in_time_sources.csv")
    parser.add_argument("--report-output", default="Data/features/training_dataset_2026_special_point_in_time_report.json")
    return parser.parse_args()


def _resolve(path: str | Path) -> Path:
    target = Path(path)
    return target if target.is_absolute() else PROJECT_ROOT / target


def _is_known_team(value: Any) -> bool:
    return str(value).strip().lower() not in KNOWN_TBD_VALUES


def _match_result(home_goals: int, away_goals: int) -> int:
    if home_goals > away_goals:
        return 1
    if home_goals < away_goals:
        return -1
    return 0


def _actual_targets(match: pd.Series) -> dict[str, Any]:
    home_goals = int(match["home_score"])
    away_goals = int(match["away_score"])
    return {
        "Score": f"{home_goals}-{away_goals}",
        "Home_Goals": home_goals,
        "Away_Goals": away_goals,
        "Goal_Diff": home_goals - away_goals,
        "Match_Result": _match_result(home_goals, away_goals),
    }


def _snapshot_date_key(value: Any) -> str:
    text = str(value)
    return text[:8] if len(text) >= 8 else ""


def _match_date_key(value: Any) -> str:
    return str(value).replace("-", "")[:8]


def _latest_snapshot_for_match(snapshots: pd.DataFrame, match: pd.Series) -> pd.Series | None:
    if snapshots.empty or "match_id" not in snapshots.columns:
        return None
    match_id = str(match["match_id"])
    candidates = snapshots[snapshots["match_id"].astype(str) == match_id].copy()
    if candidates.empty:
        return None
    match_date = _match_date_key(match["match_date"])
    if "feature_as_of" in candidates.columns and match_date:
        kickoff_time = str(match.get("kickoff_time", "00:00") or "00:00")
        match_at = pd.to_datetime(
            f"{match.get('match_date')} {kickoff_time}", errors="coerce"
        )
        candidates["_snapshot_at"] = pd.to_datetime(
            candidates["feature_as_of"].astype(str), format="%Y%m%d_%H%M%S", errors="coerce"
        )
        if pd.notna(match_at):
            allowed = candidates[candidates["_snapshot_at"] < match_at]
        else:
            candidates["_snapshot_date"] = candidates["feature_as_of"].map(_snapshot_date_key)
            allowed = candidates[candidates["_snapshot_date"] < match_date]
        if not allowed.empty:
            candidates = allowed
        else:
            return None
    sort_col = "feature_as_of" if "feature_as_of" in candidates.columns else "match_id"
    return candidates.sort_values(sort_col).iloc[-1]


def _row_from_source(source: pd.Series, reference_columns: list[str], targets: dict[str, Any]) -> dict[str, Any]:
    row = {col: source[col] if col in source.index else None for col in reference_columns}
    for col, value in targets.items():
        if col in row:
            row[col] = value
    if "Weather" in row and pd.isna(row["Weather"]):
        row["Weather"] = "Unknown"
    return row


def build_point_in_time_training_dataset(
    *,
    season: str,
    reference_dataset: str | Path,
    matches_path: str | Path,
    fallback_features_path: str | Path,
    snapshot_dir: str | Path,
    season_key: str = "2026_special",
    season_label: str = "2026_special",
    season_name: str = "2026_special",
    strategy: str = "strict",
    aggregate_normalization_divisor: float = 38.0,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    reference = pd.read_csv(_resolve(reference_dataset))
    reference_columns = reference.columns.tolist()
    matches = pd.read_csv(_resolve(matches_path))
    # Do not read or use the season-end fallback frame here.  It includes
    # values that may only have become available after a match was played.
    # Keep the argument so existing manual invocations remain compatible.
    del fallback_features_path
    if strategy not in {"strict", "snapshot_with_aggregate_estimate", "legacy_aggregate"}:
        raise ValueError(f"未知のstrategyです: {strategy}")
    snapshots = (
        load_feature_snapshots(_resolve(snapshot_dir), season_key=season_key)
        if strategy in {"strict", "snapshot_with_aggregate_estimate"}
        else pd.DataFrame()
    )

    finished = matches[
        (matches["season"].astype(str) == str(season))
        & (matches["status"].astype(str) == "finished")
        & matches["home_score"].notna()
        & matches["away_score"].notna()
        & matches["home_team"].map(_is_known_team)
        & matches["away_team"].map(_is_known_team)
    ].copy()

    aggregate_priors = (
        load_legacy_aggregate_priors(
            finished,
            project_root=PROJECT_ROOT,
            normalization_divisor=aggregate_normalization_divisor,
        )
        if strategy in {"snapshot_with_aggregate_estimate", "legacy_aggregate"}
        else None
    )
    rebuilt = rebuild_pre_match_features(
        finished,
        reference,
        season_name=season_name,
        legacy_aggregate_priors=aggregate_priors,
    )
    rebuilt_by_match = {
        str(match_id): (rebuilt.features.iloc[index], rebuilt.sources.iloc[index])
        for index, match_id in enumerate(finished.sort_values(["match_date", "kickoff_time", "match_id"])["match_id"].astype(str))
    }
    rows: list[dict[str, Any]] = []
    source_rows: list[dict[str, Any]] = []
    skipped: list[str] = []
    for _, match in finished.sort_values(["match_date", "kickoff_time", "match_id"]).iterrows():
        match_id = str(match["match_id"])
        targets = _actual_targets(match)
        snapshot = _latest_snapshot_for_match(snapshots, match)
        if snapshot is not None:
            rebuilt_row = rebuilt_by_match.get(match_id)
            if rebuilt_row is None:
                skipped.append(match_id)
                continue
            feature_row, provenance = rebuilt_row
            row = _row_from_source(feature_row, reference_columns, targets)
            aligned_snapshot = align_legacy_model_units(snapshot)
            for column in SNAPSHOT_OVERRIDE_COLUMNS:
                if column in row and column in aligned_snapshot.index and pd.notna(aligned_snapshot[column]):
                    row[column] = aligned_snapshot[column]
            if "Season" in row:
                row["Season"] = season_name
            rows.append(row)
            source_rows.append(
                {
                    "match_id": match_id,
                    "section": int(match["section"]),
                    "match_date": match["match_date"],
                    "feature_source": "snapshot_overlay_on_reconstructed_pre_match",
                    "feature_as_of": snapshot.get("feature_as_of"),
                    "feature_snapshot_path": snapshot.get("feature_snapshot_path"),
                    "fallback_reason": "",
                }
            )
            continue

        rebuilt_row = rebuilt_by_match.get(match_id)
        if rebuilt_row is not None:
            feature_row, provenance = rebuilt_row
            row = _row_from_source(feature_row, reference_columns, targets)
            if "Season" in row:
                row["Season"] = season_name
            rows.append(row)
            source_rows.append(
                {
                    "match_id": match_id,
                    "section": int(match["section"]),
                    "match_date": match["match_date"],
                    "feature_source": (
                        "aggregate_estimate_reconstructed"
                        if strategy in {"snapshot_with_aggregate_estimate", "legacy_aggregate"}
                        else "reconstructed_pre_match"
                    ),
                    "feature_as_of": "",
                    "feature_snapshot_path": "",
                    "fallback_reason": "",
                    "provenance_summary": json.dumps(
                        pd.Series(provenance).value_counts().to_dict(), ensure_ascii=False, sort_keys=True
                    ),
                }
            )
            continue

        skipped.append(match_id)

    dataset = pd.DataFrame(rows, columns=reference_columns)
    source_frame = pd.DataFrame(source_rows)
    report = {
        "season": str(season),
        "season_key": season_key,
        "season_label": season_label,
        "season_name": season_name,
        "strategy": strategy,
        "aggregate_normalization_divisor": None,
        "football_lab_unit_policy": "expected_goals_rate_and_agi_kagi_index_as_published",
        "finished_matches": int(len(finished)),
        "training_rows": int(len(dataset)),
        "snapshot_rows": int((source_frame["feature_source"] == "snapshot_overlay_on_reconstructed_pre_match").sum()) if not source_frame.empty else 0,
        "reconstructed_rows": int(source_frame["feature_source"].isin(["reconstructed_pre_match", "aggregate_estimate_reconstructed"]).sum()) if not source_frame.empty else 0,
        "aggregate_estimate_rows": int((source_frame["feature_source"] == "aggregate_estimate_reconstructed").sum()) if not source_frame.empty else 0,
        "fallback_rows": 0,
        "skipped_rows": int(len(skipped)),
        "skipped_match_ids": skipped,
        "reference_columns": int(len(reference_columns)),
        "snapshot_files": (
            int(len(list(Path(_resolve(snapshot_dir)).glob(f"upcoming_features_{season_key}_asof_*.csv"))))
            if strategy in {"strict", "snapshot_with_aggregate_estimate"} and _resolve(snapshot_dir).exists()
            else 0
        ),
    }
    return dataset, source_frame, report


def main() -> int:
    args = parse_args()
    dataset, sources, report = build_point_in_time_training_dataset(
        season=args.season,
        reference_dataset=args.reference_dataset,
        matches_path=args.matches,
        fallback_features_path=args.fallback_features,
        snapshot_dir=args.snapshot_dir,
        season_key=args.season_key,
        season_label=args.season_label,
        season_name=args.season_name,
        strategy=args.strategy,
        aggregate_normalization_divisor=args.aggregate_normalization_divisor,
    )
    safe_write_csv(dataset, _resolve(args.output))
    reference = pd.read_csv(_resolve(args.reference_dataset))
    combined = pd.concat([reference, dataset], ignore_index=True, sort=False)
    safe_write_csv(combined, _resolve(args.combined_output))
    safe_write_csv(sources, _resolve(args.source_output))
    report["combined_rows"] = int(len(combined))
    report["combined_output"] = args.combined_output
    report_path = _resolve(args.report_output)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output": args.output,
                "combined_output": args.combined_output,
                "source_output": args.source_output,
                "report": report,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
