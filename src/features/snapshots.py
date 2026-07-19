"""Point-in-time feature snapshot helpers."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from src.config import FEATURE_DATA_DIR, PROJECT_ROOT
from src.data.scraping import safe_write_csv


SNAPSHOT_DIR = FEATURE_DATA_DIR / "snapshots"
DEFAULT_SEASON_KEY = "2026_special"


@dataclass(frozen=True)
class SnapshotPaths:
    features: Path
    sources: Path | None
    metadata: Path


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def timestamp_for_path(now: datetime | None = None) -> str:
    current = now or datetime.now(ZoneInfo("Asia/Tokyo"))
    return current.strftime("%Y%m%d_%H%M%S")


def save_upcoming_feature_snapshot(
    features: pd.DataFrame,
    *,
    sources: pd.DataFrame | None = None,
    snapshot_dir: str | Path = SNAPSHOT_DIR,
    season_key: str = DEFAULT_SEASON_KEY,
    created_at: datetime | None = None,
) -> SnapshotPaths:
    """Persist the current upcoming feature rows for future point-in-time training."""
    timestamp = timestamp_for_path(created_at)
    out_dir = Path(snapshot_dir)
    if not out_dir.is_absolute():
        out_dir = PROJECT_ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    feature_frame = features.copy()
    feature_frame["feature_as_of"] = timestamp
    feature_frame["season_key"] = season_key
    feature_frame["feature_snapshot_source"] = "weekly_prediction_snapshot"
    features_path = out_dir / f"upcoming_features_{season_key}_asof_{timestamp}.csv"
    safe_write_csv(feature_frame, features_path)

    sources_path = None
    if sources is not None:
        source_frame = sources.copy()
        source_frame["feature_as_of"] = timestamp
        source_frame["season_key"] = season_key
        source_frame["feature_snapshot_source"] = "weekly_prediction_snapshot"
        sources_path = out_dir / f"upcoming_features_{season_key}_sources_asof_{timestamp}.csv"
        safe_write_csv(source_frame, sources_path)

    metadata_path = out_dir / f"upcoming_features_{season_key}_asof_{timestamp}.json"
    metadata = {
        "created_at": datetime.now(ZoneInfo("Asia/Tokyo")).isoformat(timespec="seconds"),
        "feature_as_of": timestamp,
        "season_key": season_key,
        "season_label": season_key,
        "features_path": _display_path(features_path),
        "sources_path": _display_path(sources_path) if sources_path else None,
        "rows": int(len(feature_frame)),
        "match_ids": feature_frame["match_id"].dropna().astype(str).tolist() if "match_id" in feature_frame.columns else [],
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return SnapshotPaths(features=features_path, sources=sources_path, metadata=metadata_path)


def snapshot_timestamp(path: str | Path) -> str | None:
    match = re.search(r"_asof_(\d{8}_\d{6})\.csv$", Path(path).name)
    return match.group(1) if match else None


def list_feature_snapshots(snapshot_dir: str | Path = SNAPSHOT_DIR, *, season_key: str = DEFAULT_SEASON_KEY) -> list[Path]:
    directory = Path(snapshot_dir)
    if not directory.is_absolute():
        directory = PROJECT_ROOT / directory
    if not directory.exists():
        return []
    return sorted(directory.glob(f"upcoming_features_{season_key}_asof_*.csv"))


def load_feature_snapshots(snapshot_dir: str | Path = SNAPSHOT_DIR, *, season_key: str = DEFAULT_SEASON_KEY) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for path in list_feature_snapshots(snapshot_dir, season_key=season_key):
        timestamp = snapshot_timestamp(path)
        if timestamp is None:
            continue
        frame = pd.read_csv(path)
        frame["feature_as_of"] = frame.get("feature_as_of", timestamp)
        frame["season_key"] = frame.get("season_key", season_key)
        frame["feature_snapshot_path"] = _display_path(path) if path.is_absolute() else str(path)
        frames.append(frame)
    return pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame()
