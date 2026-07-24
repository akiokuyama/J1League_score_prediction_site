"""Safe loaders for generated prediction outputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_json_file(path: str | Path) -> dict[str, Any]:
    """JSONを安全に読み込む。存在しない、壊れている場合は空dictを返す。"""
    target = Path(path)
    if not target.is_absolute():
        target = PROJECT_ROOT / target
    if not target.exists() or target.stat().st_size == 0:
        return {}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _with_matches(data: dict[str, Any]) -> dict[str, Any]:
    if "matches" not in data or not isinstance(data.get("matches"), list):
        data = dict(data)
        data["matches"] = []
    return data


def load_latest_predictions(path: str | Path = "outputs/latest_predictions.json") -> dict[str, Any]:
    return _with_matches(load_json_file(path))


def load_all_unplayed_predictions(path: str | Path = "outputs/all_unplayed_predictions.json") -> dict[str, Any]:
    return _with_matches(load_json_file(path))


def load_past_prediction_results(path: str | Path = "outputs/past_prediction_results.json") -> dict[str, Any]:
    """過去予測結果を読み込む。存在しなければ空のmatchesを返す。"""
    return _with_matches(load_json_file(path))


def load_past_prediction_seasons(
    index_path: str | Path = "outputs/past_prediction_results/index.json",
) -> dict[str, Any]:
    """シーズン一覧と各シーズンの過去予測結果を読み込む。"""
    target = Path(index_path)
    if not target.is_absolute():
        target = PROJECT_ROOT / target
    index = load_json_file(target)
    metadata = [
        season
        for season in index.get("seasons", [])
        if isinstance(season, dict) and season.get("key") and season.get("data_file")
    ]
    results: dict[str, dict[str, Any]] = {}
    for season in metadata:
        results[str(season["key"])] = _with_matches(load_json_file(target.parent / str(season["data_file"])))

    default_season = str(index.get("default_season") or "")
    if default_season not in results and results:
        default_season = next(iter(results))
    return {
        "default_season": default_season,
        "metadata": metadata,
        "results": results,
    }
