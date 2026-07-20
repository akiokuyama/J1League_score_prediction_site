"""Project configuration and competition profiles.

Code that consumes prediction data should read the competition metadata from
the data itself.  These profiles are the single place for pipeline defaults,
so a completed season is not hard-coded throughout the application.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CompetitionProfile:
    key: str
    season: str
    season_year: int
    league: str
    competition: str
    category: str


COMPETITIONS = {
    "2026_special": CompetitionProfile(
        key="2026_special",
        season="2026_special",
        season_year=2026,
        league="J1",
        competition="明治安田J1百年構想リーグ",
        category="100yj1",
    ),
    # The schedule importer will be added separately.  Keeping the profile
    # now lets output/UI code support the new season without assuming that a
    # fixture source has already been enabled.
    "2026_27_j1": CompetitionProfile(
        key="2026_27_j1",
        season="2026_27",
        season_year=2026,
        league="J1",
        competition="明治安田J1リーグ",
        category="j1",
    ),
}


def get_competition(key: str = "2026_special") -> CompetitionProfile:
    try:
        return COMPETITIONS[key]
    except KeyError as exc:
        choices = ", ".join(sorted(COMPETITIONS))
        raise ValueError(f"未知の大会設定です: {key} (選択肢: {choices})") from exc


PROJECT_ROOT = Path(__file__).resolve().parents[1]
# The 2026 special competition has finished.  New scheduled jobs and UI
# defaults must target the regular 2026-27 season.
ACTIVE_COMPETITION_KEY = "2026_27_j1"
ACTIVE_COMPETITION = get_competition(ACTIVE_COMPETITION_KEY)
SEASON = ACTIVE_COMPETITION.season
SEASON_YEAR = ACTIVE_COMPETITION.season_year
LEAGUE = ACTIVE_COMPETITION.league
COMPETITION = ACTIVE_COMPETITION.competition
CATEGORY = ACTIVE_COMPETITION.category

RAW_DATA_DIR = PROJECT_ROOT / "Data" / "raw"
PROCESSED_DATA_DIR = PROJECT_ROOT / "Data" / "processed"
FEATURE_DATA_DIR = PROJECT_ROOT / "Data" / "features"
HTML_CACHE_DIR = RAW_DATA_DIR / "html_cache"
OUTPUT_DIR = PROJECT_ROOT / "outputs"


def competition_matches_path(key: str = ACTIVE_COMPETITION_KEY) -> Path:
    return PROCESSED_DATA_DIR / f"matches_{key}_clean.csv"


def competition_upcoming_features_path(key: str = ACTIVE_COMPETITION_KEY) -> Path:
    return FEATURE_DATA_DIR / f"upcoming_features_{key}.csv"


def competition_upcoming_sources_path(key: str = ACTIVE_COMPETITION_KEY) -> Path:
    return FEATURE_DATA_DIR / f"upcoming_features_{key}_sources.csv"
