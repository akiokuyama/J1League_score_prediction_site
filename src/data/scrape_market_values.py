"""Load or fetch market values."""

from __future__ import annotations

from io import StringIO
import re
from typing import Any

import pandas as pd

from src.config import PROCESSED_DATA_DIR, PROJECT_ROOT, RAW_DATA_DIR, get_competition
from src.data.scraping import empty_frame, fetch_html, safe_write_csv


def _select_market_value_table(tables: list[pd.DataFrame]) -> pd.DataFrame | None:
    """Return the Transfermarkt club table, ignoring navigation/filter tables."""
    for table in tables:
        flattened_columns = " ".join(str(col).lower() for col in table.columns)
        first_row_text = " ".join(str(value).lower() for value in table.head(1).to_numpy().ravel())
        haystack = f"{flattened_columns} {first_row_text}"
        has_club_shape = "club" in haystack and len(table) >= 10
        has_market_value = "market value" in haystack or "market-value" in haystack
        if has_club_shape and has_market_value:
            return table.copy()
    return None


TRANSFERMARKT_TEAM_TO_CODE = {
    "Kashima Antlers": "kasm",
    "Mito HollyHock": "mito",
    "Urawa Red Diamonds": "uraw",
    "JEF United Chiba": "chib",
    "Kashiwa Reysol": "kasw",
    "FC Tokyo": "FCtk",
    "FC Machida Zelvia": "mcd",
    "Machida Zelvia": "mcd",
    "Tokyo Verdy": "tk-v",
    "Yokohama F. Marinos": "y-fm",
    "Yokohama FC": "y-fc",
    "Kawasaki Frontale": "ka-f",
    "Shonan Bellmare": "shon",
    "Shimizu S-Pulse": "shim",
    "Nagoya Grampus": "nago",
    "Kyoto Sanga FC": "kyot",
    "Kyoto Sanga": "kyot",
    "Gamba Osaka": "g-os",
    "Cerezo Osaka": "c-os",
    "Vissel Kobe": "kobe",
    "Fagiano Okayama": "okay",
    "Sanfrecce Hiroshima": "hiro",
    "Avispa Fukuoka": "fuku",
    "V-Varen Nagasaki": "ngsk",
}


def _parse_euro_value(value: object) -> float | None:
    text = str(value).strip()
    if not text or text in {"-", "nan", "None"}:
        return None
    text = text.replace("€", "").replace(",", "").strip()
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*([a-z]+)?", text, re.IGNORECASE)
    if not match:
        return None
    number = float(match.group(1))
    unit = (match.group(2) or "").lower()
    multiplier = {
        "": 1.0,
        "k": 1_000.0,
        "m": 1_000_000.0,
        "bn": 1_000_000_000.0,
    }.get(unit, 1.0)
    return number * multiplier


def _flatten_column_name(column: object) -> str:
    if isinstance(column, tuple):
        values = [str(part) for part in column if str(part) and not str(part).startswith("Unnamed")]
        return " ".join(values).strip()
    return str(column)


def _normalize_market_values(table: pd.DataFrame, *, source_url: str | None = None) -> pd.DataFrame:
    df = table.copy()
    df.columns = [_flatten_column_name(col) for col in df.columns]

    club_col = None
    best_matches = -1
    for col in df.columns:
        values = df[col].astype(str).str.strip()
        matches = int(values.isin(TRANSFERMARKT_TEAM_TO_CODE).sum())
        if matches > best_matches:
            best_matches = matches
            club_col = col
    if best_matches <= 0:
        for col in df.columns:
            if "club" in col.lower() and df[col].notna().any():
                club_col = col
                break

    money_columns: list[str] = []
    for col in df.columns:
        parsed = df[col].map(_parse_euro_value)
        if parsed.notna().sum() >= 5:
            money_columns.append(col)
    if not money_columns:
        raise ValueError("Transfermarktテーブル内に市場価値の金額列がありません。")
    total_value_col = money_columns[-1]

    normalized = pd.DataFrame()
    normalized["team_name"] = df[club_col].astype(str).str.strip() if club_col else ""
    normalized["team"] = normalized["team_name"].map(TRANSFERMARKT_TEAM_TO_CODE).fillna(normalized["team_name"])
    normalized["market_value"] = df[total_value_col].map(_parse_euro_value)
    normalized["currency"] = "EUR"
    normalized["source"] = "transfermarkt"
    normalized["source_url"] = source_url or TRANSFERMARKT_URL
    normalized["as_of_date"] = pd.Timestamp.now(tz="Asia/Tokyo").date().isoformat()
    normalized = normalized.dropna(subset=["market_value"])
    normalized = normalized[normalized["market_value"] > 0]
    normalized = normalized[normalized["team_name"].str.lower().ne("nan")]
    normalized = normalized[normalized["team"].str.lower().ne("nan")]
    return normalized.reset_index(drop=True)


TRANSFERMARKT_URL = "https://www.transfermarkt.com/j1-100-year-vision-league/startseite/wettbewerb/J1YV"
TRANSFERMARKT_URLS = {
    "2026_special": TRANSFERMARKT_URL,
    "2026_27_j1": "https://www.transfermarkt.com/j1-league/startseite/wettbewerb/JAP1",
}


def scrape_market_values(
    competition_key: str = "2026_special", *, use_cache: bool = False
) -> tuple[pd.DataFrame, dict[str, Any]]:
    profile = get_competition(competition_key)
    url = TRANSFERMARKT_URLS.get(profile.key)
    if not url:
        raise ValueError(f"市場価値取得URLが未設定です: {profile.key}")
    manual_path = PROJECT_ROOT / "Data" / "manual" / f"market_values_{profile.key}.csv"
    info: dict[str, Any] = {"url": url, "manual_path": str(manual_path), "warnings": []}
    if manual_path.exists():
        df = pd.read_csv(manual_path)
        info["source"] = "manual"
    else:
        try:
            fetched = fetch_html(url, use_cache=use_cache)
            info["cache_path"] = str(fetched.cache_path)
            info["from_cache"] = fetched.from_cache
            tables = pd.read_html(StringIO(fetched.html))
            selected = _select_market_value_table(tables)
            if selected is None:
                info["warnings"].append("Transfermarktから市場価値テーブルを特定できませんでした。フィルタ表などの非データ表は採用していません。")
                df = empty_frame(["team", "market_value"])
                info["source"] = "empty"
            else:
                df = _normalize_market_values(selected, source_url=url)
                info["source"] = "transfermarkt"
        except Exception as exc:  # noqa: BLE001
            info["warnings"].append(str(exc))
            df = empty_frame(["team", "market_value"])
            info["source"] = "empty"

    raw_path = RAW_DATA_DIR / "market_values" / f"market_values_{profile.key}.csv"
    processed_path = PROCESSED_DATA_DIR / f"market_values_{profile.key}_clean.csv"
    if df.empty and processed_path.exists() and processed_path.stat().st_size > 0:
        info["warnings"].append("取得結果が空のため、直前の市場価値スナップショットを保持しました。")
        df = pd.read_csv(processed_path)
        info["used_existing"] = True
    safe_write_csv(df, raw_path)
    safe_write_csv(df, processed_path)
    if not df.empty:
        as_of = str(df.get("as_of_date", pd.Series([pd.Timestamp.now(tz="Asia/Tokyo").date().isoformat()])).iloc[0])
        snapshot_path = RAW_DATA_DIR / "market_values" / f"market_values_{profile.key}_asof_{as_of.replace('-', '')}.csv"
        safe_write_csv(df, snapshot_path)
        info["snapshot_path"] = str(snapshot_path)
    info["rows"] = int(len(df))
    info["raw_path"] = str(raw_path)
    info["processed_path"] = str(processed_path)
    return df, info


def scrape_market_values_2026_special(*, use_cache: bool = False) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Backward-compatible special-season entry point."""
    return scrape_market_values("2026_special", use_cache=use_cache)
