"""Scrape 2026_special J.League match schedule/results."""

from __future__ import annotations

import re
from io import StringIO
from pathlib import Path
from typing import Any

import pandas as pd

from src.config import CompetitionProfile, PROCESSED_DATA_DIR, RAW_DATA_DIR, get_competition
from src.data.scraping import empty_frame, fetch_html, safe_write_csv, soup_from_html
from src.data.team_master import to_dataset_code


MATCH_COLUMNS = [
    "season",
    "league",
    "competition",
    "category",
    "section",
    "section_label",
    "match_date",
    "kickoff_time",
    "home_team",
    "away_team",
    "home_score",
    "away_score",
    "stadium",
    "attendance",
    "status",
    "match_url",
    "match_id",
]


DATA_SITE_URL = "https://data.j-league.or.jp/SFMS01/search?competition_years=20261&competition_frame_ids=35&tv_relay_station_name="
MATCH_SEARCH_URL = "https://www.jleague.jp/match/search/?category%5B%5D=100yj1&year=2026&section="
REGULAR_J1_MATCH_SEARCH_URL = "https://www.jleague.jp/match/search/j1/all/"


def _profile_values(profile: CompetitionProfile) -> dict[str, str]:
    return {
        "season": profile.season,
        "league": profile.league,
        "competition": profile.competition,
        "category": profile.category,
    }


def _text(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def _normalize_digits(value: str) -> str:
    return value.translate(str.maketrans("０１２３４５６７８９", "0123456789"))


def _parse_data_site_date(value: Any) -> str | None:
    text = _normalize_digits(_text(value))
    match = re.search(r"(\d{2})/(\d{1,2})/(\d{1,2})", text)
    if not match:
        return None
    year = 2000 + int(match.group(1))
    return f"{year:04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"


def _section_from_label(value: Any) -> int | None:
    text = _normalize_digits(_text(value))
    section_match = re.search(r"第(\d+)節", text)
    if section_match:
        return int(section_match.group(1))
    playoff_match = re.search(r"第(\d+)戦第(\d+)日", text)
    if playoff_match:
        return int(playoff_match.group(1)) * 100 + int(playoff_match.group(2))
    return None


def _score_pair(value: Any) -> tuple[int | None, int | None]:
    text = _normalize_digits(_text(value))
    score_match = re.search(r"(\d+)\s*[-－]\s*(\d+)", text)
    if not score_match:
        return None, None
    return int(score_match.group(1)), int(score_match.group(2))


def _match_id_section(value: Any) -> str:
    if pd.isna(value):
        return "unknown"
    try:
        return str(int(float(value)))
    except (TypeError, ValueError):
        return str(value)


def _status_from_scores(home_score: Any, away_score: Any, text: str) -> str:
    if pd.notna(home_score) and pd.notna(away_score):
        return "finished"
    if any(word in text for word in ["中止", "延期", "未定"]):
        return "postponed_or_tbd"
    return "unplayed"


def _parse_tables(html: str, url: str, profile: CompetitionProfile | None = None) -> pd.DataFrame:
    profile = profile or get_competition("2026_special")
    try:
        tables = pd.read_html(StringIO(html))
    except ValueError:
        tables = []

    rows: list[dict[str, Any]] = []
    for table in tables:
        table.columns = [str(col) for col in table.columns]
        joined_cols = " ".join(table.columns)
        if not any(token in joined_cols for token in ["ホーム", "アウェイ", "試合", "会場", "スコア"]):
            continue
        for _, raw in table.iterrows():
            text = " ".join(str(v) for v in raw.to_list())
            score_match = re.search(r"(\d+)\s*[-－]\s*(\d+)", text)
            home_score = int(score_match.group(1)) if score_match else None
            away_score = int(score_match.group(2)) if score_match else None
            teams = re.split(r"\s+(?:VS|vs|対)\s+", text)
            if len(teams) >= 2:
                home_team = teams[0].split()[-1]
                away_team = teams[1].split()[0]
            else:
                continue
            date_match = re.search(r"(2026[/-]\d{1,2}[/-]\d{1,2})", text)
            kickoff_match = re.search(r"(\d{1,2}:\d{2})", text)
            section_match = re.search(r"第?(\d+)節", text)
            rows.append(
                {
                    **_profile_values(profile),
                    "section": int(section_match.group(1)) if section_match else None,
                    "match_date": date_match.group(1).replace("/", "-") if date_match else None,
                    "kickoff_time": kickoff_match.group(1) if kickoff_match else None,
                    "home_team": to_dataset_code(home_team),
                    "away_team": to_dataset_code(away_team),
                    "home_score": home_score,
                    "away_score": away_score,
                    "stadium": None,
                    "attendance": None,
                    "status": _status_from_scores(home_score, away_score, text),
                    "match_url": url,
                }
            )
    return pd.DataFrame(rows)


def _parse_match_links(html: str, url: str, profile: CompetitionProfile | None = None) -> pd.DataFrame:
    profile = profile or get_competition("2026_special")
    soup = soup_from_html(html)
    rows: list[dict[str, Any]] = []
    for node in soup.select("a[href*='/match/']"):
        text = " ".join(node.get_text(" ", strip=True).split())
        if "VS" not in text and "vs" not in text and not re.search(r"\d+\s*[-－]\s*\d+", text):
            continue
        score_match = re.search(r"(\d+)\s*[-－]\s*(\d+)", text)
        home_score = int(score_match.group(1)) if score_match else None
        away_score = int(score_match.group(2)) if score_match else None
        teams = re.split(r"\s+(?:VS|vs)\s+", text)
        if len(teams) < 2:
            continue
        href = node.get("href", "")
        match_url = href if href.startswith("http") else f"https://www.jleague.jp{href}"
        rows.append(
            {
                **_profile_values(profile),
                "section": None,
                "match_date": None,
                "kickoff_time": None,
                "home_team": to_dataset_code(teams[0].strip()),
                "away_team": to_dataset_code(teams[1].strip()),
                "home_score": home_score,
                "away_score": away_score,
                "stadium": None,
                "attendance": None,
                "status": _status_from_scores(home_score, away_score, text),
                "match_url": match_url,
            }
        )
    return pd.DataFrame(rows)


def _parse_data_site_tables(html: str, url: str, profile: CompetitionProfile | None = None) -> pd.DataFrame:
    profile = profile or get_competition("2026_special")
    try:
        tables = pd.read_html(StringIO(html))
    except ValueError:
        tables = []

    rows: list[dict[str, Any]] = []
    for table in tables:
        table.columns = [str(col) for col in table.columns]
        required = {"シーズン", "大会", "節", "試合日", "K/O時刻", "ホーム", "スコア", "アウェイ", "スタジアム"}
        if not required.issubset(set(table.columns)):
            continue
        for _, raw in table.iterrows():
            home_score, away_score = _score_pair(raw.get("スコア"))
            section_label = _text(raw.get("節")) or None
            home_team = to_dataset_code(_text(raw.get("ホーム")))
            away_team = to_dataset_code(_text(raw.get("アウェイ")))
            row_text = " ".join(_text(value) for value in raw.to_list())
            rows.append(
                {
                    **_profile_values(profile),
                    "competition": _text(raw.get("大会")) or profile.competition,
                    "section": _section_from_label(section_label),
                    "section_label": section_label,
                    "match_date": _parse_data_site_date(raw.get("試合日")),
                    "kickoff_time": _text(raw.get("K/O時刻")) or None,
                    "home_team": home_team,
                    "away_team": away_team,
                    "home_score": home_score,
                    "away_score": away_score,
                    "stadium": _text(raw.get("スタジアム")) or None,
                    "attendance": raw.get("入場者数") if pd.notna(raw.get("入場者数")) else None,
                    "status": _status_from_scores(home_score, away_score, row_text),
                    "match_url": url,
                }
            )
    return pd.DataFrame(rows)


def _parse_matchlist_sections(html: str, profile: CompetitionProfile | None = None) -> pd.DataFrame:
    profile = profile or get_competition("2026_special")
    soup = soup_from_html(html)
    rows: list[dict[str, Any]] = []
    for section_node in soup.select("section.matchlistWrap"):
        date_text = section_node.select_one(".timeStamp h4")
        date_value = None
        if date_text:
            match = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", date_text.get_text(strip=True))
            if match:
                date_value = f"{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"

        section_text = section_node.select_one(".leagAccTit h5")
        competition_label = section_text.get_text(" ", strip=True) if section_text else profile.competition
        section_value = None
        if section_text:
            match = re.search(r"第(\d+)節", section_text.get_text(" ", strip=True))
            if match:
                section_value = int(match.group(1))

        for tr in section_node.select("table.matchTable > tbody > tr"):
            match_cell = tr.select_one("td.match")
            stadium_cell = tr.select_one("td.stadium")
            if match_cell is None:
                continue
            clubs = match_cell.select("td.clubName")
            points = match_cell.select("td.point")
            if len(clubs) < 2:
                continue
            home_text = clubs[0].get_text(" ", strip=True)
            away_text = clubs[1].get_text(" ", strip=True)
            home_score = None
            away_score = None
            if len(points) >= 2:
                if points[0].get_text(strip=True).isdigit():
                    home_score = int(points[0].get_text(strip=True))
                if points[1].get_text(strip=True).isdigit():
                    away_score = int(points[1].get_text(strip=True))
            status_text = match_cell.select_one("td.status")
            text = status_text.get_text(" ", strip=True) if status_text else match_cell.get_text(" ", strip=True)
            link = match_cell.select_one("a[href*='/match/']")
            href = link.get("href", "") if link else ""
            match_url = href if href.startswith("http") else f"https://www.jleague.jp{href}"
            stadium_text = stadium_cell.get_text(" ", strip=True) if stadium_cell else ""
            kickoff_match = re.search(r"(\d{1,2}:\d{2})", stadium_text)
            stadium = re.sub(r"\d{1,2}:\d{2}", "", stadium_text).strip() or None
            rows.append(
                {
                    **_profile_values(profile),
                    "competition": competition_label,
                    "section": section_value,
                    "section_label": f"第{section_value}節" if section_value else None,
                    "match_date": date_value,
                    "kickoff_time": kickoff_match.group(1) if kickoff_match else None,
                    "home_team": to_dataset_code(home_text),
                    "away_team": to_dataset_code(away_text),
                    "home_score": home_score,
                    "away_score": away_score,
                    "stadium": stadium,
                    "attendance": None,
                    "status": _status_from_scores(home_score, away_score, text),
                    "match_url": match_url,
                }
            )
    return pd.DataFrame(rows)


def _parse_next_schedule(html: str, profile: CompetitionProfile | None = None) -> pd.DataFrame:
    """Parse the React/Next.js schedule cards used by the current J.League site."""
    profile = profile or get_competition("2026_27_j1")
    soup = soup_from_html(html)
    rows: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for link in soup.select("a.m-schedule__link[href*='/match/j1/']"):
        href = str(link.get("href", ""))
        if not href or href in seen_urls:
            continue
        seen_urls.add(href)
        date_match = re.search(r"/match/j1/(\d{4})/(\d{2})(\d{2})\d{2}/", href)
        teams = link.select(".m-schedule__team-name[data-media='pc']")
        if not date_match or len(teams) < 2:
            continue
        time_node = link.select_one(".m-schedule__time-text")
        time_text = time_node.get_text(" ", strip=True) if time_node else ""
        score_pair = re.search(r"(\d+)\s*[-－]\s*(\d+)", time_text)
        home_score = int(score_pair.group(1)) if score_pair else None
        away_score = int(score_pair.group(2)) if score_pair else None
        kickoff = None if score_pair else (re.search(r"\d{1,2}:\d{2}", time_text).group(0) if re.search(r"\d{1,2}:\d{2}", time_text) else None)
        stadium_node = link.select_one(".m-schedule__info-stadium[data-media='pc']") or link.select_one(
            ".m-schedule__info-stadium"
        )
        group = link.find_parent(class_="p-game-schedule__group")
        group_text = group.get_text(" ", strip=True) if group else ""
        section_match = re.search(r"第(\d+)節", group_text)
        section = int(section_match.group(1)) if section_match else None
        match_url = href if href.startswith("http") else f"https://www.jleague.jp{href}"
        rows.append(
            {
                **_profile_values(profile),
                "section": section,
                "section_label": f"第{section}節" if section else None,
                "match_date": f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}",
                "kickoff_time": kickoff,
                "home_team": to_dataset_code(teams[0].get_text(" ", strip=True)),
                "away_team": to_dataset_code(teams[1].get_text(" ", strip=True)),
                "home_score": home_score,
                "away_score": away_score,
                "stadium": stadium_node.get_text(" ", strip=True) if stadium_node else None,
                "attendance": None,
                "status": _status_from_scores(home_score, away_score, link.get_text(" ", strip=True)),
                "match_url": match_url,
            }
        )
    return pd.DataFrame(rows)


def _merge_with_existing(fresh: pd.DataFrame, existing: pd.DataFrame) -> pd.DataFrame:
    if existing.empty:
        return fresh
    if fresh.empty:
        return existing.copy()
    keys = ["match_date", "home_team", "away_team"]
    old = existing.copy()
    for col in fresh.columns:
        if col in old.columns and fresh[col].dtype == object and old[col].dtype != object:
            old[col] = old[col].astype(object)
    old = old.set_index(keys)
    new = fresh.copy().set_index(keys)
    for index, row in new.iterrows():
        if index not in old.index:
            old.loc[index, row.index] = row
            continue
        for col, value in row.items():
            if pd.notna(value) and str(value) != "":
                old.loc[index, col] = value
    return old.reset_index()


def _filter_profile_matches(df: pd.DataFrame, profile: CompetitionProfile) -> pd.DataFrame:
    """Keep only rows belonging to the selected competition.

    The official J1 schedule endpoint contains both the completed special
    competition and the regular 2026-27 season.  The date/label guard keeps
    the two datasets from being mixed when the page layout changes.
    """
    if df.empty:
        return df
    labels = df["competition"].fillna("").astype(str)
    if profile.key == "2026_27_j1":
        dates = pd.to_datetime(df["match_date"], errors="coerce")
        mask = ~labels.str.contains("百年構想", na=False)
        mask &= dates >= pd.Timestamp("2026-08-01")
    else:
        mask = labels.str.contains("百年構想", na=False)
    filtered = df.loc[mask].copy()
    for key, value in _profile_values(profile).items():
        filtered[key] = value
    return filtered


def scrape_matches(
    competition_key: str = "2026_special", *, use_cache: bool = False
) -> tuple[pd.DataFrame, dict[str, Any]]:
    profile = get_competition(competition_key)
    raw_path = RAW_DATA_DIR / "matches" / f"schedule_{profile.key}_{profile.category}.csv"
    processed_path = PROCESSED_DATA_DIR / f"matches_{profile.key}_clean.csv"
    existing = pd.read_csv(processed_path) if processed_path.exists() and processed_path.stat().st_size > 0 else empty_frame(MATCH_COLUMNS)
    use_data_site = profile.key == "2026_special"
    schedule_url = MATCH_SEARCH_URL if use_data_site else REGULAR_J1_MATCH_SEARCH_URL
    info: dict[str, Any] = {"url": schedule_url, "warnings": [], "competition_key": profile.key}
    try:
        if use_data_site:
            fetched = fetch_html(DATA_SITE_URL, use_cache=use_cache)
            info["cache_path"] = str(fetched.cache_path)
            info["from_cache"] = fetched.from_cache
            df = _parse_data_site_tables(fetched.html, DATA_SITE_URL, profile)
        else:
            df = empty_frame(MATCH_COLUMNS)
        if df.empty:
            info["warnings"].append("J.League Data Siteから試合行を抽出できませんでした。jleague.jp側にフォールバックします。")
            fetched = fetch_html(schedule_url, use_cache=use_cache)
            info["fallback_cache_path"] = str(fetched.cache_path)
            info["fallback_from_cache"] = fetched.from_cache
            df = _parse_matchlist_sections(fetched.html, profile)
        if df.empty:
            df = _parse_tables(fetched.html, schedule_url, profile)
        if df.empty:
            df = _parse_match_links(fetched.html, schedule_url, profile)
        if df.empty:
            df = _parse_next_schedule(fetched.html, profile)
        if df.empty:
            info["warnings"].append("Jリーグ公式HTMLから試合行を抽出できませんでした。")
            df = empty_frame(MATCH_COLUMNS)
    except Exception as exc:  # noqa: BLE001
        info["warnings"].append(str(exc))
        df = empty_frame(MATCH_COLUMNS)

    if not df.empty:
        df = _filter_profile_matches(df, profile)
    if df.empty and not existing.empty:
        info["warnings"].append("新規取得が空のため、直前の正常な日程データを保持しました。")
        info["used_existing"] = True
    df = _merge_with_existing(df, existing)
    if not df.empty:
        df = df.reindex(columns=[col for col in MATCH_COLUMNS if col != "match_id"])
        df["match_id"] = (
            df["season"].astype(str)
            + "-"
            + df["category"].astype(str)
            + "-"
            + df["section"].map(_match_id_section)
            + "-"
            + df["home_team"].astype(str)
            + "-vs-"
            + df["away_team"].astype(str)
        )
    else:
        df = empty_frame(MATCH_COLUMNS)

    safe_write_csv(df, raw_path)
    safe_write_csv(df, processed_path)
    info["rows"] = int(len(df))
    info["raw_path"] = str(raw_path)
    info["processed_path"] = str(processed_path)
    return df, info


def scrape_matches_2026_special(*, use_cache: bool = False) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Backward-compatible entry point for the completed special season."""
    return scrape_matches("2026_special", use_cache=use_cache)
