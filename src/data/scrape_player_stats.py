"""Fetch Football Lab player stat pages."""

from __future__ import annotations

from io import StringIO
from pathlib import Path
from datetime import date
import re
from typing import Any

import pandas as pd

from src.config import PROCESSED_DATA_DIR, RAW_DATA_DIR, get_competition
from src.data.scraping import empty_frame, fetch_html, safe_write_csv
from src.data.team_master import FOOTBALL_LAB_CODES
from src.predict.scorer_candidates import add_scorer_score


PLAYER_COLUMN_MAP = {
    "順位": "rank",
    "Unnamed: 1": "position",
    "Unnamed: 2": "player",
    "ポイントCBP": "cbp",
    "90分平均": "cbp_90",
    "出場試合出場": "played_games",
    "ゴール": "goals",
    "アシスト": "assists",
}


def normalize_player_stats(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return empty_frame(
            [
                "rank",
                "position",
                "player",
                "cbp",
                "cbp_90",
                "played_games",
                "goals",
                "assists",
                "team",
                "source_url",
                "scorer_score",
            ]
        )
    normalized = df.rename(columns={col: PLAYER_COLUMN_MAP.get(str(col), str(col)) for col in df.columns}).copy()
    for col in ["rank", "cbp", "cbp_90", "played_games", "goals", "assists"]:
        if col in normalized.columns:
            normalized[col] = pd.to_numeric(normalized[col], errors="coerce").fillna(0)
    for col in ["position", "player", "team", "source_url"]:
        if col not in normalized.columns:
            normalized[col] = ""
        normalized[col] = normalized[col].astype(str).str.strip()
    normalized = add_scorer_score(normalized)
    columns = [
        "rank",
        "position",
        "player",
        "cbp",
        "cbp_90",
        "played_games",
        "goals",
        "assists",
        "team",
        "source_url",
        "scorer_score",
    ]
    return normalized[[col for col in columns if col in normalized.columns]]


def scrape_player_stats_2026_special(*, use_cache: bool = False) -> tuple[pd.DataFrame, dict[str, Any]]:
    frames: list[pd.DataFrame] = []
    info: dict[str, Any] = {"warnings": []}
    for team_code, lab_code in FOOTBALL_LAB_CODES.items():
        # Football Lab's 2026 player ranking is served from the current page.
        # Adding ?year=2026 redirects/returns the 2025 season page.
        url = f"https://www.football-lab.jp/{lab_code}/ranking"
        try:
            fetched = fetch_html(url, use_cache=use_cache, delay_seconds=0.2, retries=1, timeout=10)
            tables = pd.read_html(StringIO(fetched.html))
            if tables:
                table = tables[0].copy()
                table.columns = [str(col) for col in table.columns]
                table["team"] = team_code
                table["source_url"] = url
                frames.append(table)
        except Exception as exc:  # noqa: BLE001
            info["warnings"].append(f"{team_code}: {exc}")

    raw_path = RAW_DATA_DIR / "player_stats" / "player_stats_2026_special.csv"
    processed_path = PROCESSED_DATA_DIR / "player_stats_2026_special_clean.csv"
    if not frames:
        info["warnings"].append("全チームの選手スタッツ取得に失敗したため、既存CSVは上書きしません")
        existing = _read_existing_processed(processed_path)
        info["rows"] = int(len(existing))
        info["raw_path"] = str(raw_path)
        info["processed_path"] = str(processed_path)
        info["used_existing"] = True
        return existing, info

    raw_df = pd.concat(frames, ignore_index=True)
    df = normalize_player_stats(raw_df)
    safe_write_csv(raw_df, raw_path)
    safe_write_csv(df, processed_path)
    info["rows"] = int(len(df))
    info["raw_path"] = str(raw_path)
    info["processed_path"] = str(processed_path)
    return df, info


def _read_existing_processed(path: str | Path) -> pd.DataFrame:
    existing_path = Path(path)
    if existing_path.exists() and existing_path.stat().st_size > 0:
        return pd.read_csv(existing_path)
    return normalize_player_stats(empty_frame(["team", "player"]))


def _page_update_date(html: str) -> date | None:
    match = re.search(r"(\d{4})\.(\d{1,2})\.(\d{1,2})\s+update", html)
    if not match:
        return None
    return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))


def scrape_player_stats(
    competition_key: str = "2026_special", *, use_cache: bool = False
) -> tuple[pd.DataFrame, dict[str, Any]]:
    if competition_key == "2026_special":
        return scrape_player_stats_2026_special(use_cache=use_cache)
    profile = get_competition(competition_key)
    if profile.key != "2026_27_j1":
        raise ValueError(f"選手スタッツ取得設定が未定義です: {profile.key}")

    season_start = date(2026, 8, 8)
    raw_path = RAW_DATA_DIR / "player_stats" / f"player_stats_{profile.key}.csv"
    processed_path = PROCESSED_DATA_DIR / f"player_stats_{profile.key}_clean.csv"
    info: dict[str, Any] = {"warnings": [], "available_from": season_start.isoformat()}
    if date.today() < season_start:
        info.update({"rows": 0, "status": "not_published_before_season_start"})
        return normalize_player_stats(empty_frame(["team", "player"])), info

    frames: list[pd.DataFrame] = []
    for team_code, lab_code in FOOTBALL_LAB_CODES.items():
        url = f"https://www.football-lab.jp/{lab_code}/ranking"
        try:
            fetched = fetch_html(url, use_cache=use_cache, delay_seconds=0.2, retries=1, timeout=10)
            updated = _page_update_date(fetched.html)
            if updated is None or updated < season_start:
                info["warnings"].append(f"{team_code}: 新シーズン更新前のページなので採用しません。")
                continue
            tables = pd.read_html(StringIO(fetched.html))
            if tables:
                table = tables[0].copy()
                table.columns = [str(col) for col in table.columns]
                table["team"] = team_code
                table["source_url"] = url
                table["source_updated_at"] = updated.isoformat()
                frames.append(table)
        except Exception as exc:  # noqa: BLE001
            info["warnings"].append(f"{team_code}: {exc}")

    if frames:
        raw_df = pd.concat(frames, ignore_index=True)
        df = normalize_player_stats(raw_df)
        safe_write_csv(raw_df, raw_path)
        safe_write_csv(df, processed_path)
    else:
        df = _read_existing_processed(processed_path)
        if not df.empty:
            info["warnings"].append("新規取得が空のため既存スナップショットを保持しました。")
    info.update({"rows": int(len(df)), "raw_path": str(raw_path), "processed_path": str(processed_path)})
    return df, info
