"""Refresh the official fixture/results feed for a configured competition."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import ACTIVE_COMPETITION_KEY, get_competition
from src.data.scrape_market_values import scrape_market_values
from src.data.scrape_matches import scrape_matches
from src.data.scrape_football_lab_team import scrape_football_lab_team
from src.data.scrape_formations import scrape_formations
from src.data.scrape_player_stats import scrape_player_stats
from src.data.scraping import write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="大会の日程・結果を公式ソースから更新します")
    parser.add_argument("--competition-key", default=ACTIVE_COMPETITION_KEY)
    parser.add_argument("--scope", choices=["all", "results"], default="all")
    parser.add_argument("--use-cache", action="store_true")
    return parser.parse_args()


def overdue_unplayed_matches(
    matches: pd.DataFrame,
    *,
    now: datetime | None = None,
    grace_hours: int = 6,
) -> list[dict[str, object]]:
    """Return fixtures that should have a result but are still unplayed.

    A non-empty schedule is not sufficient proof that a refresh succeeded: a
    partial upstream page can be merged into an old full schedule while all
    completed matches remain stale.  This guard makes that state fail loudly.
    """
    now = now or datetime.now(ZoneInfo("Asia/Tokyo"))
    if now.tzinfo is None:
        now = now.replace(tzinfo=ZoneInfo("Asia/Tokyo"))
    cutoff = now - timedelta(hours=grace_hours)
    overdue: list[dict[str, object]] = []
    for _, match in matches.iterrows():
        if str(match.get("status", "")) != "unplayed":
            continue
        date_text = str(match.get("match_date", "") or "")
        time_text = str(match.get("kickoff_time", "") or "")
        try:
            kickoff = datetime.strptime(
                f"{date_text} {time_text}", "%Y-%m-%d %H:%M"
            ).replace(tzinfo=ZoneInfo("Asia/Tokyo"))
        except ValueError:
            continue
        if kickoff > cutoff:
            continue
        overdue.append(
            {
                "match_id": str(match.get("match_id", "")),
                "match_date": date_text,
                "kickoff_time": time_text,
                "home_team": str(match.get("home_team", "")),
                "away_team": str(match.get("away_team", "")),
            }
        )
    return overdue


def main() -> int:
    args = parse_args()
    profile = get_competition(args.competition_key)
    report: dict[str, object] = {
        "updated_at": datetime.now(ZoneInfo("Asia/Tokyo")).isoformat(timespec="seconds"),
        "competition_key": profile.key,
        "season": profile.season,
        "category": profile.category,
        "use_cache": args.use_cache,
        "scope": args.scope,
    }
    matches, info = scrape_matches(profile.key, use_cache=args.use_cache)
    overdue = overdue_unplayed_matches(matches)
    info["overdue_unplayed_count"] = len(overdue)
    info["overdue_unplayed_matches"] = overdue
    report["matches"] = info
    if args.scope == "all":
        market_values, market_info = scrape_market_values(profile.key, use_cache=args.use_cache)
        report["market_values"] = market_info
        football_lab, football_lab_info = scrape_football_lab_team(profile.key, use_cache=args.use_cache)
        report["football_lab"] = football_lab_info
        formations, formations_info = scrape_formations(profile.key, use_cache=args.use_cache)
        report["formations"] = formations_info
        player_stats, player_stats_info = scrape_player_stats(profile.key, use_cache=args.use_cache)
        report["player_stats"] = player_stats_info
        current_lab_ready = bool(len(football_lab.get("expected", [])) and len(football_lab.get("kagi", [])))
        report["snapshot_readiness"] = {
            "market_values": "actual" if not market_values.empty else "unavailable",
            "xg_agi_kagi": "actual" if current_lab_ready else "fallback_until_current_season_source_is_published",
            "formations": "actual" if not formations.empty else "fallback_until_current_season_matches_exist",
            "player_stats": "actual" if not player_stats.empty else "fallback_to_latest_completed_season",
        }
    report_path = PROJECT_ROOT / "Data" / "processed" / f"update_{profile.key}_report.json"
    write_json(report_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))

    # An empty fixture response is not a successful update: otherwise Actions
    # could silently keep displaying stale predictions after an upstream change.
    if matches.empty:
        print("[ERROR] 公式日程から対象大会の試合を取得できませんでした。既存の予測は更新していません。")
        return 1
    if overdue:
        print(
            "[ERROR] キックオフから6時間以上経過した試合が未消化のままです。"
            "結果取得元の更新失敗として処理を中止します。"
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
