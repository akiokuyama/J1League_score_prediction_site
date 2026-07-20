"""Loader isolated from long-lived Streamlit modules for safe hot reloads."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.utils.load_predictions import PROJECT_ROOT, load_json_file


def load_standings_forecasts(
    latest_path: str | Path = "outputs/standings_forecast/latest.json",
    history_dir: str | Path = "outputs/standings_forecast/history",
) -> list[dict[str, Any]]:
    """Load current and historical standings snapshots, newest first."""

    latest = Path(latest_path)
    if not latest.is_absolute():
        latest = PROJECT_ROOT / latest
    history = Path(history_dir)
    if not history.is_absolute():
        history = PROJECT_ROOT / history

    candidates = [latest]
    if history.exists():
        candidates.extend(sorted(history.glob("standings_forecast_*.json"), reverse=True))

    forecasts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in candidates:
        data = load_json_file(path)
        if not isinstance(data.get("teams"), list) or not data.get("teams"):
            continue
        identity = str(data.get("generated_at") or path.resolve())
        if identity in seen:
            continue
        seen.add(identity)
        forecasts.append(data)
    forecasts.sort(key=lambda item: str(item.get("generated_at") or ""), reverse=True)
    return forecasts
