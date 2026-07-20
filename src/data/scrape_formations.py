"""Fetch Football Lab formation pages."""

from __future__ import annotations

from io import StringIO
from datetime import date
import re
from typing import Any

import pandas as pd

from src.config import PROCESSED_DATA_DIR, RAW_DATA_DIR, get_competition
from src.data.scraping import empty_frame, fetch_html, safe_write_csv
from src.data.team_master import FOOTBALL_LAB_CODES


def _parse_primary_formation(html: str) -> tuple[str, int | None]:
    try:
        tables = pd.read_html(StringIO(html))
    except ValueError:
        return "Unknown", None
    for table in tables:
        df = table.copy()
        df.columns = [str(col) for col in df.columns]
        if "システム名" not in df.columns or "試合" not in df.columns:
            continue
        df = df[df["システム名"].astype(str) != "合計"].copy()
        df["matches"] = pd.to_numeric(df["試合"], errors="coerce")
        df = df.dropna(subset=["matches"])
        if df.empty:
            continue
        top = df.sort_values("matches", ascending=False).iloc[0]
        return str(top["システム名"]), int(top["matches"])
    return "Unknown", None


def scrape_formations_2026_special(*, use_cache: bool = False) -> tuple[pd.DataFrame, dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    info: dict[str, Any] = {"warnings": []}
    for team_code, lab_code in FOOTBALL_LAB_CODES.items():
        url = f"https://www.football-lab.jp/{lab_code}/formation/"
        try:
            fetched = fetch_html(url, use_cache=use_cache, delay_seconds=0.2, retries=1, timeout=10)
            formation, starts = _parse_primary_formation(fetched.html)
            rows.append(
                {
                    "team": team_code,
                    "formation": formation,
                    "formation_starts": starts,
                    "source_url": url,
                    "html_length": len(fetched.html),
                }
            )
        except Exception as exc:  # noqa: BLE001
            info["warnings"].append(f"{team_code}: {exc}")

    df = pd.DataFrame(rows) if rows else empty_frame(["team", "formation", "formation_starts", "source_url", "html_length"])
    raw_path = RAW_DATA_DIR / "formations" / "formations_2026_special.csv"
    processed_path = PROCESSED_DATA_DIR / "formations_2026_special_clean.csv"
    safe_write_csv(df, raw_path)
    safe_write_csv(df, processed_path)
    info["rows"] = int(len(df))
    info["raw_path"] = str(raw_path)
    info["processed_path"] = str(processed_path)
    return df, info


def _page_update_date(html: str) -> date | None:
    match = re.search(r"(\d{4})\.(\d{1,2})\.(\d{1,2})\s+update", html)
    if not match:
        return None
    return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))


def scrape_formations(
    competition_key: str = "2026_special", *, use_cache: bool = False
) -> tuple[pd.DataFrame, dict[str, Any]]:
    if competition_key == "2026_special":
        return scrape_formations_2026_special(use_cache=use_cache)
    profile = get_competition(competition_key)
    if profile.key != "2026_27_j1":
        raise ValueError(f"フォーメーション取得設定が未定義です: {profile.key}")

    season_start = date(2026, 8, 8)
    processed_path = PROCESSED_DATA_DIR / f"formations_{profile.key}_clean.csv"
    raw_path = RAW_DATA_DIR / "formations" / f"formations_{profile.key}.csv"
    info: dict[str, Any] = {"warnings": [], "available_from": season_start.isoformat()}
    if date.today() < season_start:
        info.update({"rows": 0, "status": "not_published_before_season_start"})
        return empty_frame(["team", "formation", "formation_starts"]), info

    rows: list[dict[str, Any]] = []
    for team_code, lab_code in FOOTBALL_LAB_CODES.items():
        url = f"https://www.football-lab.jp/{lab_code}/formation/"
        try:
            fetched = fetch_html(url, use_cache=use_cache, delay_seconds=0.2, retries=1, timeout=10)
            updated = _page_update_date(fetched.html)
            if updated is None or updated < season_start:
                info["warnings"].append(f"{team_code}: 新シーズン更新前のページなので採用しません。")
                continue
            formation, starts = _parse_primary_formation(fetched.html)
            rows.append(
                {
                    "team": team_code,
                    "formation": formation,
                    "formation_starts": starts,
                    "source_url": url,
                    "source_updated_at": updated.isoformat(),
                }
            )
        except Exception as exc:  # noqa: BLE001
            info["warnings"].append(f"{team_code}: {exc}")

    df = pd.DataFrame(rows)
    if not df.empty:
        safe_write_csv(df, raw_path)
        safe_write_csv(df, processed_path)
    elif processed_path.exists() and processed_path.stat().st_size > 0:
        df = pd.read_csv(processed_path)
        info["warnings"].append("新規取得が空のため既存スナップショットを保持しました。")
    info.update({"rows": int(len(df)), "raw_path": str(raw_path), "processed_path": str(processed_path)})
    return df, info
