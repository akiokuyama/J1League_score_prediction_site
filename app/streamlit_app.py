"""Streamlit MVP for viewing generated J1 prediction outputs."""

from __future__ import annotations

import sys
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.utils.evaluation import (  # noqa: E402
    build_score_probability_explanation,
    evaluate_prediction,
    get_score_outcome,
    get_strongest_outcome,
    outcome_label,
)
from app.utils.display_labels import (  # noqa: E402
    get_display_confidence_label,
    get_display_insight_label,
)
from app.utils.formatters import (  # noqa: E402
    format_accuracy,
    format_date,
    format_datetime_jp,
    format_optional_parts,
    format_percent,
    format_score,
)
from app.utils.load_predictions import (  # noqa: E402
    load_all_unplayed_predictions,
    load_json_file,
    load_latest_predictions,
    load_past_prediction_results,
)
from app.utils.standings_loader import load_standings_forecasts  # noqa: E402
from app.utils.team_preferences import (  # noqa: E402
    normalize_storage_action,
    sync_team_preference,
)
from app.utils.team_logos import team_logo_html, team_matchup_html  # noqa: E402
from src.data.team_master import to_dataset_code, to_display_name  # noqa: E402


st.set_page_config(
    page_title="Jリーグ試合予想AI｜スコア予測・勝敗予想",
    page_icon="⚽",
    layout="centered",
    initial_sidebar_state="collapsed",
)


def load_past_prediction_seasons(
    index_path: str | Path = "outputs/past_prediction_results/index.json",
) -> dict[str, Any]:
    """Load seasonal past-results files without depending on hot-reloaded helper APIs.

    Streamlit can keep a previously imported utility module alive while it reloads
    this page. Keeping this small adapter here prevents a newly added utility
    function from causing an ImportError during that transition.
    """

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
        data = load_json_file(target.parent / str(season["data_file"]))
        if not isinstance(data.get("matches"), list):
            data = {**data, "matches": []}
        results[str(season["key"])] = data

    default_season = str(index.get("default_season") or "")
    if default_season not in results and results:
        default_season = next(iter(results))
    return {
        "default_season": default_season,
        "metadata": metadata,
        "results": results,
    }


def main() -> None:
    inject_css()
    latest = load_latest_predictions()
    all_unplayed = load_all_unplayed_predictions()
    past_seasons = load_past_prediction_seasons()
    default_past_season = past_seasons.get("default_season")
    past = past_seasons.get("results", {}).get(default_past_season) or load_past_prediction_results()
    standings_forecasts = load_standings_forecasts()

    initialize_state()
    available_teams = collect_available_team_codes(latest, all_unplayed, past, standings_forecasts)
    if not initialize_my_team_preference(available_teams):
        st.caption("マイチーム設定を読み込んでいます…")
        return
    render_header(latest, past, all_unplayed)
    render_my_team_settings(available_teams)

    tab = "これからの試合"
    if st.session_state.view != "detail":
        tab = st.radio(
            "表示切替",
            ["これからの試合", "過去の予測結果", "最終順位予測"],
            horizontal=True,
            label_visibility="collapsed",
        )

    if tab == "これからの試合":
        if st.session_state.view != "detail":
            render_prediction_logic_summary(latest)
        render_future_matches(latest, all_unplayed)
    elif tab == "過去の予測結果":
        render_past_predictions(past_seasons)
    else:
        render_standings_forecast(standings_forecasts)


def initialize_state() -> None:
    if "view" not in st.session_state:
        st.session_state.view = "list"
    if "selected_match_id" not in st.session_state:
        st.session_state.selected_match_id = None
    query_params = st.query_params
    if query_params.get("view") == "detail" and query_params.get("match_id"):
        st.session_state.view = "detail"
        st.session_state.selected_match_id = query_params.get("match_id")
    elif query_params.get("view") == "list":
        st.session_state.view = "list"
        st.session_state.selected_match_id = None


def initialize_my_team_preference(available_teams: list[str]) -> bool:
    """Load the browser preference and initialize team filters once per session."""

    pending = st.session_state.pop("_my_team_storage_action", None)
    action, pending_value = normalize_storage_action(pending)
    snapshot = sync_team_preference(action=action, value=pending_value)
    if not snapshot.loaded and action == "read":
        return False

    if action == "set":
        saved_team = pending_value
    elif action == "clear":
        saved_team = None
    else:
        saved_team = snapshot.value

    st.session_state.my_team_code = saved_team
    st.session_state.my_team_storage_error = snapshot.error

    if not st.session_state.get("_my_team_filters_initialized"):
        saved_display = display_team(saved_team) if saved_team in available_teams else None
        explicit_future = query_value("upcoming_team")
        if explicit_future == "すべてのチーム":
            explicit_future = None
        st.session_state.future_team_filter = explicit_future or saved_display or "すべてのチーム"
        st.session_state.past_team_filter = saved_display or "すべてのチーム"
        st.session_state._my_team_filters_initialized = True
    return True


def inject_css() -> None:
    st.markdown(
        """
        <style>
        [data-testid="stAppViewContainer"] {
            background: var(--background-color);
        }
        html, body, [class*="css"] {
            font-family: -apple-system, BlinkMacSystemFont, "Hiragino Sans", "Yu Gothic", "Noto Sans JP", "Segoe UI", sans-serif;
            color: var(--text-color);
        }
        .block-container { max-width: 760px; padding-top: 2rem; padding-bottom: 2rem; }
        div[data-testid="stRadio"] > div { gap: .45rem; }
        div[data-testid="stRadio"] label,
        div[data-testid="stRadio"] p {
            color: var(--text-color);
        }
        .app-header, .summary-card {
            border: 1px solid rgba(128, 128, 128, 0.25);
            border-radius: 8px;
            padding: 18px;
            background: var(--secondary-background-color);
            color: var(--text-color);
            margin-bottom: 14px;
            box-shadow: 0 8px 22px rgba(0, 0, 0, 0.10);
        }
        .app-header {
            border-left: 6px solid var(--primary-color);
        }
        .my-team-card {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 14px;
            border: 1px solid color-mix(in srgb, var(--primary-color) 42%, rgba(128, 128, 128, 0.25));
            border-left: 6px solid var(--primary-color);
            border-radius: 8px;
            padding: 13px 16px;
            margin-bottom: 10px;
            background: color-mix(in srgb, var(--primary-color) 8%, var(--secondary-background-color));
            color: var(--text-color);
        }
        .my-team-identity {
            display: flex;
            align-items: center;
            gap: 10px;
            min-width: 0;
        }
        .my-team-label {
            color: color-mix(in srgb, var(--text-color) 62%, transparent);
            font-size: .72rem;
            font-weight: 750;
        }
        .my-team-name {
            display: block;
            margin-top: 2px;
            font-size: 1rem;
            font-weight: 850;
            overflow-wrap: anywhere;
        }
        .app-title {
            margin: 0 0 .45rem 0;
            font-size: 1.9rem;
            line-height: 1.2;
            letter-spacing: 0;
            font-weight: 850;
            color: var(--text-color);
        }
        .muted { color: color-mix(in srgb, var(--text-color) 70%, transparent); font-size: .88rem; }
        .small { color: color-mix(in srgb, var(--text-color) 70%, transparent); font-size: .8rem; }
        .section-title {
            display: flex;
            align-items: center;
            gap: 8px;
            margin: 18px 0 10px;
            font-size: 1.08rem;
            font-weight: 800;
            color: var(--text-color);
        }
        .section-title::before {
            content: "";
            width: 4px;
            height: 20px;
            border-radius: 99px;
            background: var(--primary-color);
        }
        .header-meta {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 8px;
            margin-top: 12px;
        }
        .meta-chip {
            border: 1px solid rgba(128, 128, 128, 0.25);
            border-radius: 8px;
            padding: 9px 10px;
            background: var(--background-color);
            color: var(--text-color);
            font-size: .86rem;
            font-weight: 700;
        }
        .match-card-link {
            text-decoration: none !important;
            color: inherit !important;
            display: block;
        }
        .match-card {
            border: 1px solid rgba(128, 128, 128, 0.25);
            border-left: 5px solid #0f766e;
            border-radius: 8px;
            padding: 18px 18px 16px;
            background: var(--secondary-background-color);
            color: var(--text-color);
            margin-bottom: 14px;
            box-shadow: 0 7px 18px rgba(0, 0, 0, 0.10);
            cursor: pointer;
            transition: border-color .12s ease, background .12s ease, box-shadow .12s ease, transform .12s ease;
        }
        .match-card:hover {
            border-color: color-mix(in srgb, var(--primary-color) 55%, rgba(128, 128, 128, 0.35));
            background: color-mix(in srgb, var(--secondary-background-color) 88%, var(--primary-color) 12%);
            box-shadow: 0 10px 24px rgba(0, 0, 0, 0.16);
            transform: translateY(-1px);
        }
        .teams { margin: .65rem 0 .75rem; }
        .team-matchup {
            display: grid;
            grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
            align-items: center;
            gap: 12px;
        }
        .team-identity {
            display: flex;
            align-items: center;
            gap: 9px;
            min-width: 0;
        }
        .team-identity--home {
            justify-content: flex-end;
            text-align: right;
        }
        .team-identity--away {
            justify-content: flex-start;
            text-align: left;
        }
        .team-copy { min-width: 0; }
        .team-name {
            display: block;
            font-size: 1rem;
            font-weight: 850;
            line-height: 1.25;
            overflow-wrap: anywhere;
        }
        .team-side-label {
            display: block;
            margin-top: 3px;
            color: color-mix(in srgb, var(--text-color) 58%, transparent);
            font-size: .64rem;
            font-weight: 750;
            letter-spacing: .08em;
        }
        .versus {
            color: color-mix(in srgb, var(--text-color) 58%, transparent);
            font-size: .72rem;
            font-weight: 850;
            letter-spacing: .05em;
        }
        .team-logo {
            display: inline-block;
            flex: 0 0 40px;
            width: 40px;
            height: 40px;
            background-image: url("https://www.jleague.jp/img/common/2026_27/team_emb_l.webp");
            background-repeat: no-repeat;
            background-size: 400px 240px;
            filter: drop-shadow(0 2px 3px rgba(0, 0, 0, .18));
        }
        .team-logo--fallback {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            border: 1px solid rgba(128, 128, 128, .25);
            border-radius: 50%;
            background: var(--background-color);
            font-size: 1.35rem;
            filter: none;
        }
        .score-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            border-top: 1px solid rgba(128, 128, 128, 0.22);
            padding-top: 12px;
            margin-top: 10px;
        }
        .score, .score-pill {
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
            letter-spacing: 0;
        }
        .score { font-size: 1.65rem; font-weight: 850; color: var(--text-color); }
        .score-pill {
            display: inline-block;
            border-radius: 8px;
            padding: 7px 10px;
            background: color-mix(in srgb, var(--primary-color) 16%, var(--secondary-background-color));
            color: var(--text-color);
            font-size: 1.35rem;
            font-weight: 850;
            line-height: 1;
        }
        .prob-line {
            color: color-mix(in srgb, var(--text-color) 78%, transparent);
            font-size: .88rem;
            font-weight: 650;
            text-align: right;
        }
        .label {
            display: inline-block;
            border-radius: 999px;
            padding: 4px 10px;
            font-size: .78rem;
            font-weight: 700;
            background: var(--background-color);
            color: var(--text-color);
            border: 1px solid rgba(128, 128, 128, 0.22);
            margin-right: 4px;
            margin-top: 6px;
        }
        .home-advantage {
            background: color-mix(in srgb, #3b82f6 16%, var(--secondary-background-color)) !important;
            color: color-mix(in srgb, #1d4ed8 82%, var(--text-color)) !important;
            border-color: rgba(59, 130, 246, 0.42) !important;
        }
        .away-advantage {
            background: color-mix(in srgb, #ef4444 16%, var(--secondary-background-color)) !important;
            color: color-mix(in srgb, #b91c1c 82%, var(--text-color)) !important;
            border-color: rgba(239, 68, 68, 0.42) !important;
        }
        .draw-badge {
            background: color-mix(in srgb, #22c55e 16%, var(--secondary-background-color)) !important;
            color: color-mix(in srgb, #15803d 82%, var(--text-color)) !important;
            border-color: rgba(34, 197, 94, 0.42) !important;
        }
        .badge-confidence-high {
            background: color-mix(in srgb, #6366f1 16%, var(--secondary-background-color)) !important;
            color: color-mix(in srgb, #4338ca 82%, var(--text-color)) !important;
            border-color: rgba(99, 102, 241, 0.42) !important;
        }
        .badge-confidence-medium {
            background: color-mix(in srgb, #0ea5e9 16%, var(--secondary-background-color)) !important;
            color: color-mix(in srgb, #0369a1 82%, var(--text-color)) !important;
            border-color: rgba(14, 165, 233, 0.42) !important;
        }
        .badge-confidence-low {
            background: color-mix(in srgb, #6b7280 16%, var(--secondary-background-color)) !important;
            color: color-mix(in srgb, #374151 82%, var(--text-color)) !important;
            border-color: rgba(107, 114, 128, 0.42) !important;
        }
        .result-badge-correct {
            background: color-mix(in srgb, #22c55e 16%, var(--secondary-background-color)) !important;
            color: color-mix(in srgb, #15803d 82%, var(--text-color)) !important;
            border-color: rgba(34, 197, 94, 0.42) !important;
        }
        .result-badge-wrong {
            background: color-mix(in srgb, #ef4444 16%, var(--secondary-background-color)) !important;
            color: color-mix(in srgb, #b91c1c 82%, var(--text-color)) !important;
            border-color: rgba(239, 68, 68, 0.42) !important;
        }
        .metric-line { display: flex; justify-content: space-between; gap: 10px; }
        .summary-card {
            border-left: 5px solid #f59e0b;
        }
        .logic-card {
            border: 1px solid rgba(128, 128, 128, 0.25);
            border-left: 5px solid var(--primary-color);
            border-radius: 8px;
            padding: 16px;
            background: var(--secondary-background-color);
            color: var(--text-color);
            margin-bottom: 16px;
            box-shadow: 0 7px 18px rgba(0, 0, 0, 0.10);
        }
        .logic-card-title {
            font-weight: 850;
            font-size: 1.02rem;
            margin-bottom: 8px;
            color: var(--text-color);
        }
        .logic-card ul {
            margin: 8px 0 0 1.1rem;
            padding: 0;
            color: color-mix(in srgb, var(--text-color) 78%, transparent);
            font-size: .9rem;
            line-height: 1.65;
        }
        .beta-note {
            border: 1px solid rgba(245, 158, 11, 0.45);
            border-left: 5px solid #f59e0b;
            border-radius: 8px;
            background: color-mix(in srgb, #f59e0b 14%, var(--secondary-background-color));
            color: var(--text-color);
            padding: 12px 14px;
            margin: 0 0 16px 0;
            font-size: .9rem;
            line-height: 1.55;
            font-weight: 650;
        }
        .summary-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 10px;
        }
        .summary-item {
            border: 1px solid rgba(128, 128, 128, 0.25);
            border-radius: 8px;
            background: var(--background-color);
            color: var(--text-color);
            padding: 10px;
        }
        .summary-label {
            color: color-mix(in srgb, var(--text-color) 70%, transparent);
            font-size: .78rem;
            margin-bottom: 4px;
        }
        .summary-value {
            color: var(--text-color);
            font-size: 1.05rem;
            font-weight: 850;
        }
        .standings-table {
            border: 1px solid rgba(128, 128, 128, 0.25);
            border-radius: 8px;
            overflow: hidden;
            background: var(--secondary-background-color);
            box-shadow: 0 7px 18px rgba(0, 0, 0, 0.10);
        }
        .standings-header, .standings-row {
            display: grid;
            grid-template-columns: 44px minmax(165px, 1fr) 54px 54px 68px 64px 64px 64px;
            align-items: center;
            gap: 9px;
            padding: 10px 11px;
        }
        .standings-header {
            border-bottom: 1px solid rgba(128, 128, 128, 0.25);
            background: color-mix(in srgb, var(--primary-color) 10%, var(--secondary-background-color));
            color: color-mix(in srgb, var(--text-color) 70%, transparent);
            font-size: .68rem;
            font-weight: 800;
            text-align: center;
        }
        .standings-header div:nth-child(2) { text-align: left; }
        .standings-row {
            border-bottom: 1px solid rgba(128, 128, 128, 0.18);
            color: var(--text-color);
            min-height: 64px;
        }
        .standings-row:last-child { border-bottom: 0; }
        .standings-row--my-team {
            border-left: 5px solid var(--primary-color);
            background: color-mix(in srgb, var(--primary-color) 12%, var(--secondary-background-color)) !important;
        }
        .standings-row:nth-child(2),
        .standings-row:nth-child(3),
        .standings-row:nth-child(4) {
            background: color-mix(in srgb, #f59e0b 6%, var(--secondary-background-color));
        }
        .standings-rank {
            grid-column: 1;
            grid-row: 1;
            text-align: center;
            font-size: 1.08rem;
            font-weight: 900;
        }
        .standings-team {
            grid-column: 2;
            grid-row: 1;
            display: flex;
            align-items: center;
            gap: 8px;
            min-width: 0;
        }
        .standings-team-copy { min-width: 0; }
        .standings-team-name {
            display: block;
            font-size: .82rem;
            font-weight: 850;
            line-height: 1.25;
            overflow-wrap: anywhere;
        }
        .standings-range {
            display: block;
            margin-top: 3px;
            color: color-mix(in srgb, var(--text-color) 60%, transparent);
            font-size: .67rem;
        }
        .standings-points, .standings-metric {
            text-align: center;
            font-size: .78rem;
            font-weight: 800;
        }
        .standings-current { grid-column: 3; grid-row: 1; }
        .standings-change { grid-column: 4; grid-row: 1; }
        .standings-points { grid-column: 5; grid-row: 1; font-size: .9rem; }
        .standings-champion { grid-column: 6; grid-row: 1; }
        .standings-top3 { grid-column: 7; grid-row: 1; }
        .standings-bottom3 { grid-column: 8; grid-row: 1; }
        .standings-change-up { color: #16a34a; }
        .standings-change-down { color: #dc2626; }
        .standings-mobile { display: none; }
        .standings-mobile-card {
            border: 1px solid rgba(128, 128, 128, 0.25);
            border-radius: 10px;
            padding: 14px;
            background: var(--secondary-background-color);
            color: var(--text-color);
            box-shadow: 0 6px 16px rgba(0, 0, 0, 0.09);
        }
        .standings-mobile-card--top3 {
            border-color: color-mix(in srgb, #f59e0b 45%, rgba(128, 128, 128, 0.25));
            background: color-mix(in srgb, #f59e0b 7%, var(--secondary-background-color));
        }
        .standings-mobile-card--my-team {
            border: 2px solid var(--primary-color);
            background: color-mix(in srgb, var(--primary-color) 12%, var(--secondary-background-color));
        }
        .standings-mobile-main {
            display: grid;
            grid-template-columns: 58px minmax(0, 1fr) auto;
            align-items: center;
            gap: 10px;
        }
        .standings-mobile-rank {
            text-align: center;
            font-size: 1.55rem;
            font-weight: 900;
            line-height: 1;
        }
        .standings-mobile-rank-label,
        .standings-mobile-points-label,
        .standings-mobile-prob-label {
            display: block;
            margin-bottom: 4px;
            color: color-mix(in srgb, var(--text-color) 58%, transparent);
            font-size: .62rem;
            font-weight: 750;
        }
        .standings-mobile-team {
            display: flex;
            align-items: center;
            gap: 9px;
            min-width: 0;
        }
        .standings-mobile-team-name {
            font-size: .9rem;
            font-weight: 850;
            line-height: 1.25;
            overflow-wrap: anywhere;
        }
        .standings-mobile-points {
            min-width: 58px;
            text-align: right;
            font-size: 1.05rem;
            font-weight: 900;
        }
        .standings-mobile-context {
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            margin-top: 12px;
            padding-top: 10px;
            border-top: 1px solid rgba(128, 128, 128, 0.2);
        }
        .standings-mobile-chip {
            border-radius: 999px;
            padding: 4px 8px;
            background: var(--background-color);
            color: color-mix(in srgb, var(--text-color) 78%, transparent);
            font-size: .68rem;
            font-weight: 750;
        }
        .standings-mobile-probs {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 7px;
            margin-top: 9px;
        }
        .standings-mobile-prob {
            border-radius: 8px;
            padding: 8px 5px;
            background: var(--background-color);
            text-align: center;
            font-size: .8rem;
            font-weight: 850;
        }
        @media (max-width: 640px) {
            .block-container { padding-left: 1rem; padding-right: 1rem; }
            .score { font-size: 1.45rem; }
            .app-header { padding: 18px 16px; }
            .app-title { font-size: 1.55rem; }
            .my-team-card { align-items: flex-start; padding: 12px 13px; }
            .header-meta, .summary-grid { grid-template-columns: 1fr; }
            .score-row { align-items: flex-start; flex-direction: column; }
            .prob-line { text-align: left; }
            .standings-table--desktop { display: none; }
            .standings-mobile { display: grid; gap: 10px; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_prediction_logic_summary(data: dict[str, Any]) -> None:
    feature_count = resolve_feature_count(data)
    feature_text = f"{feature_count}個" if feature_count is not None else "複数"
    st.markdown(
        f"""
        <div class="beta-note">
          このアプリの予測は、過去データと機械学習モデルに基づく参考情報です。実際の試合結果を保証するものではありません。
        </div>
        <div class="logic-card">
          <div class="logic-card-title">このアプリの予測について</div>
          <ul>
            <li>試合ごとのチーム状態・直近成績・戦術情報など、{feature_text}の特徴量を使って機械学習モデルが試合結果を予測しています。</li>
            <li>期待得点から全スコアの確率分布を作り、予測スコアと勝敗確率を同じ分布から一貫して算出しています。</li>
            <li>勝敗確率が45%未満、または上位2結果の差が10ポイント未満の試合は「拮抗」と表示します。</li>
            <li>得点者候補は、チームのゴール期待値を選手の得点実績・アシスト・攻撃指標に応じて配分した参考予測です。</li>
          </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _parse_update_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=ZoneInfo("Asia/Tokyo"))
    return dt.astimezone(ZoneInfo("Asia/Tokyo"))


def _latest_update_value(*values: Any) -> Any:
    parsed = [(_parse_update_datetime(value), value) for value in values if value]
    valid = [(dt, value) for dt, value in parsed if dt is not None]
    if not valid:
        return next((value for value in values if value), None)
    return max(valid, key=lambda item: item[0])[1]


def _target_matchweek_text(data: dict[str, Any], all_unplayed: dict[str, Any] | None = None) -> str:
    matches = safe_matches(all_unplayed or {})
    sections = sorted({safe_int(match_section(match)) for match in matches if safe_int(match_section(match)) is not None})
    if sections:
        if len(sections) <= 3:
            return "・".join(f"第{section}節" for section in sections)
        return f"第{sections[0]}節〜第{sections[-1]}節"
    matchweek = data.get("matchweek", "-")
    return f"第{matchweek}節" if matchweek not in (None, "-") else "-"


def render_header(data: dict[str, Any], past_data: dict[str, Any] | None = None, all_unplayed: dict[str, Any] | None = None) -> None:
    season = data.get("season", "-")
    competition = data.get("competition") or (all_unplayed or {}).get("competition") or "Jリーグ"
    updated_value = _latest_update_value(
        data.get("last_updated"),
        (all_unplayed or {}).get("last_updated"),
        (past_data or {}).get("generated_at"),
    )
    updated = format_datetime_jp(updated_value)
    matchweek_text = _target_matchweek_text(data, all_unplayed)
    st.markdown(
        f"""
        <div class="app-header">
          <h1 class="app-title">Jリーグ試合予想AI</h1>
          <div class="muted">{escape(str(competition))}のスコア予測・勝敗確率・得点者候補を確認できます。試合予想、スコア予測、勝敗予想、得点者候補をAIモデルで算出しています。</div>
          <div class="header-meta">
            <div class="meta-chip">シーズン：{escape(str(season))}</div>
            <div class="meta-chip">対象節：{escape(str(matchweek_text))}</div>
            <div class="meta-chip">最終更新：{escape(str(updated))}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def collect_available_team_codes(
    latest: dict[str, Any],
    all_unplayed: dict[str, Any],
    past: dict[str, Any],
    standings_forecasts: list[dict[str, Any]],
) -> list[str]:
    """Return current-season team codes in display-name order."""

    matches = safe_matches(all_unplayed) or safe_matches(latest)
    if not matches:
        matches = safe_matches(past)

    teams = {
        to_dataset_code(str(team))
        for match in matches
        for team in (match.get("home_team"), match.get("away_team"))
        if team not in (None, "", "tbd", "未定")
    }
    if not teams and standings_forecasts:
        for item in standings_forecasts[0].get("teams", []):
            if not isinstance(item, dict):
                continue
            team = item.get("team") or item.get("team_name")
            if team not in (None, "", "tbd", "未定"):
                teams.add(to_dataset_code(str(team)))
    return sorted(teams, key=display_team)


def render_my_team_settings(available_teams: list[str]) -> None:
    """Render the saved team summary and controls."""

    current = st.session_state.get("my_team_code")
    current_is_available = current in available_teams
    storage_error = st.session_state.get("my_team_storage_error")

    if storage_error:
        st.warning("このブラウザではマイチーム設定を保存できません。現在のタブ内では引き続き利用できます。")

    if current_is_available:
        name = display_team(current)
        logo = team_logo_html(current, name)
        st.markdown(
            f'<div class="my-team-card"><div class="my-team-identity">{logo}'
            f'<span><span class="my-team-label">マイチーム</span>'
            f'<span class="my-team-name">{escape(name)}</span></span></div>'
            f'<span class="small">起動時にこのクラブで絞り込みます</span></div>',
            unsafe_allow_html=True,
        )
    elif current:
        st.warning(
            f"設定中の「{display_team(current)}」は現在のJ1予測対象に含まれていません。マイチームを変更してください。"
        )

    if not available_teams:
        return

    with st.expander("マイチームを設定・変更", expanded=not current_is_available):
        default_index = available_teams.index(current) if current_is_available else 0
        selected = st.selectbox(
            "応援しているクラブ",
            available_teams,
            index=default_index,
            format_func=display_team,
            key="my_team_setting_select",
        )
        save_col, clear_col = st.columns(2)
        if save_col.button("マイチームに設定", type="primary", use_container_width=True):
            set_my_team_preference(selected)
        if clear_col.button(
            "設定を解除",
            disabled=not bool(current),
            use_container_width=True,
        ):
            clear_my_team_preference()

    if not current_is_available:
        st.info("マイチームを設定すると、次回からそのクラブの試合を最初に表示します。")


def set_my_team_preference(team_code: str) -> None:
    """Queue a browser save and immediately apply the preference."""

    display_name = display_team(team_code)
    st.session_state._my_team_storage_action = {"action": "set", "value": team_code}
    st.session_state.my_team_code = team_code
    st.session_state.future_team_filter = display_name
    st.session_state.past_team_filter = display_name
    st.session_state._future_team_filter_initialized = True
    st.session_state._past_team_filter_initialized = True
    st.session_state._my_team_filters_initialized = True
    if st.session_state.view != "detail":
        set_query_params_if_changed(
            {
                "view": "list",
                "upcoming_team": display_name,
                "upcoming_section": str(current_future_section_filter()),
            }
        )
    st.rerun()


def clear_my_team_preference() -> None:
    """Queue removal of the saved team and reset both team filters."""

    st.session_state._my_team_storage_action = {"action": "clear"}
    st.session_state.my_team_code = None
    st.session_state.future_team_filter = "すべてのチーム"
    st.session_state.past_team_filter = "すべてのチーム"
    st.session_state._future_team_filter_initialized = True
    st.session_state._past_team_filter_initialized = True
    st.session_state._my_team_filters_initialized = True
    if st.session_state.view != "detail":
        set_query_params_if_changed(
            {
                "view": "list",
                "upcoming_team": "すべてのチーム",
                "upcoming_section": str(current_future_section_filter()),
            }
        )
    st.rerun()


def render_future_matches(latest: dict[str, Any], all_unplayed: dict[str, Any]) -> None:
    matches = safe_matches(all_unplayed) or safe_matches(latest)
    if st.session_state.view == "detail":
        selected = find_match(matches, st.session_state.selected_match_id)
        if selected:
            render_match_detail(selected)
            return
        st.session_state.view = "list"
        st.session_state.selected_match_id = None

    st.markdown('<div class="section-title">試合一覧</div>', unsafe_allow_html=True)
    if not matches:
        st.info("予測データが見つかりません。")
        return
    filtered_matches = filter_future_matches(matches)
    st.caption(f"表示中：{len(filtered_matches)} / {len(matches)} 試合")
    if not filtered_matches:
        st.info("条件に一致する試合はありません。")
        return
    for match in filtered_matches:
        render_match_card(match)


def filter_future_matches(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    st.markdown('<div class="section-title">絞り込み</div>', unsafe_allow_html=True)
    teams = sorted({display_team(team) for match in matches for team in [match.get("home_team"), match.get("away_team")] if team})
    sections = sorted({int(match_section(match)) for match in matches if _is_int_like(match_section(match))})

    team_options = ["すべてのチーム", *teams]
    section_options = ["すべての節", *sections]
    if not st.session_state.get("_future_team_filter_initialized"):
        requested_team = query_value("upcoming_team")
        if requested_team == "すべてのチーム":
            requested_team = None
        my_team_name = display_team(st.session_state.get("my_team_code"))
        preferred_team = requested_team or my_team_name
        st.session_state.future_team_filter = preferred_team if preferred_team in team_options else "すべてのチーム"
        st.session_state._future_team_filter_initialized = True
    elif st.session_state.get("future_team_filter") not in team_options:
        st.session_state.future_team_filter = "すべてのチーム"
    if st.session_state.get("future_section_filter") not in section_options:
        requested_section = query_value("upcoming_section")
        st.session_state.future_section_filter = next(
            (option for option in section_options if str(option) == str(requested_section)),
            "すべての節",
        )
    team = st.selectbox(
        "チーム",
        team_options,
        key="future_team_filter",
    )
    section = st.selectbox(
        "試合が行われる節",
        section_options,
        key="future_section_filter",
    )
    update_future_filter_query_params(team, section)

    filtered: list[dict[str, Any]] = []
    for match in matches:
        names = {display_team(match.get("home_team")), display_team(match.get("away_team"))}

        if team != "すべてのチーム" and team not in names:
            continue
        if section != "すべての節" and safe_int(match_section(match)) != int(section):
            continue
        filtered.append(match)
    return filtered


def render_match_card(match: dict[str, Any]) -> None:
    probabilities = match.get("result_probabilities")
    strongest = get_strongest_outcome(probabilities)
    confidence = get_display_confidence_label(strongest.get("value"), probabilities)
    insight = get_display_insight_label(probabilities)
    match_id = str(match.get("match_id") or id(match))
    home = display_team(match.get("home_team"))
    away = display_team(match.get("away_team"))
    matchup = team_matchup_html(match.get("home_team"), match.get("away_team"), home, away)
    score = format_score(match.get("predicted_score"))
    meta = format_match_meta(match)
    href = build_detail_href(match_id)
    insight_class = (
        "badge-confidence-low"
        if insight and insight.startswith("拮抗")
        else "home-advantage"
        if insight == "ホーム優勢"
        else "away-advantage"
        if insight == "アウェイ優勢"
        else "draw-badge"
        if insight == "引き分け濃厚"
        else ""
    )
    insight_html = f'<span class="label {insight_class}">{escape(insight)}</span>' if insight else ""
    confidence_html = f'<span class="label {confidence["class"]}">{escape(confidence["label"])}</span>'
    explanation = build_score_probability_explanation(match.get("predicted_score"), probabilities)

    st.markdown(
        f"""
        <a href="{href}" target="_self" class="match-card-link">
          <div class="match-card">
            <div class="small">{escape(meta)}</div>
            {matchup}
            <div class="score-row">
              <div class="score-pill">{escape(score)}</div>
              <div class="prob-line">勝敗確率トップ：{escape(str(strongest["label"]))}<br>{escape(format_percent(strongest["value"]))}（{escape(confidence["label"])}）</div>
            </div>
            {insight_html}{confidence_html}
            <div class="small">{escape(explanation)}</div>
          </div>
        </a>
        """,
        unsafe_allow_html=True,
    )


def render_match_detail(match: dict[str, Any]) -> None:
    if st.button("← 試合一覧に戻る", use_container_width=True):
        st.session_state.view = "list"
        st.session_state.selected_match_id = None
        set_query_params_if_changed(
            {
                "view": "list",
                "upcoming_team": current_future_team_filter(),
                "upcoming_section": str(current_future_section_filter()),
            }
        )
        st.rerun()

    home = display_team(match.get("home_team"))
    away = display_team(match.get("away_team"))
    matchup = team_matchup_html(match.get("home_team"), match.get("away_team"), home, away)
    probabilities = match.get("result_probabilities")
    strongest = get_strongest_outcome(probabilities)
    insight = get_display_insight_label(probabilities)
    predicted_score = match.get("predicted_score")
    score_text = format_score(predicted_score)

    st.markdown('<div class="section-title">対戦カード</div>', unsafe_allow_html=True)
    st.markdown(matchup, unsafe_allow_html=True)
    st.caption(format_match_meta(match))
    st.markdown(f"<div class='score'>{score_text}</div>", unsafe_allow_html=True)

    render_conclusion(match, strongest, insight)
    render_expected_goals(match)
    render_probability_bars(probabilities)
    render_probability_note(match, strongest)
    render_score_candidates(match.get("score_candidates"))
    render_scorer_candidates(match, home, away)


def render_conclusion(match: dict[str, Any], strongest: dict[str, Any], insight: str | None) -> None:
    score_text = format_score(match.get("predicted_score"))
    confidence = get_display_confidence_label(
        strongest.get("value"),
        match.get("result_probabilities"),
    )
    trend = f'試合傾向は「{insight}」です。' if insight else ""
    explanation = build_score_probability_explanation(match.get("predicted_score"), match.get("result_probabilities"))
    message = (
        f"この試合の見立て：予測スコアは {score_text}、勝敗確率トップは "
        f"{strongest['label']} {format_percent(strongest.get('value'))}（{confidence['label']}）です。"
        f"{trend} {explanation}"
    )

    st.markdown(f"<div class='summary-card'><strong>{message}</strong></div>", unsafe_allow_html=True)


def render_expected_goals(match: dict[str, Any]) -> None:
    expected = match.get("expected_goals") if isinstance(match.get("expected_goals"), dict) else {}
    home_xg = safe_float(expected.get("home"))
    away_xg = safe_float(expected.get("away"))
    st.markdown('<div class="section-title">期待得点</div>', unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    col1.metric("ホーム期待得点", f"{home_xg:.2f}" if home_xg is not None else "-")
    col2.metric("アウェイ期待得点", f"{away_xg:.2f}" if away_xg is not None else "-")

    candidates = match.get("score_candidates") or []
    if candidates:
        st.caption(f"最有力スコア候補：{candidates[0].get('score', '-')}（全スコア中 {format_percent(candidates[0].get('probability'))}）")


def render_probability_bars(probabilities: dict | None) -> None:
    st.markdown('<div class="section-title">勝敗確率</div>', unsafe_allow_html=True)
    values = [
        ("ホーム勝利", _probability_value(probabilities, "home_win")),
        ("引き分け", _probability_value(probabilities, "draw")),
        ("アウェイ勝利", _probability_value(probabilities, "away_win")),
    ]
    for label, value in values:
        st.markdown(f"<div class='metric-line'><span>{label}</span><strong>{format_percent(value)}</strong></div>", unsafe_allow_html=True)
        st.progress(max(0.0, min(float(value or 0), 1.0)))


def render_probability_note(match: dict[str, Any], strongest: dict[str, Any]) -> None:
    score_text = format_score(match.get("predicted_score"))
    explanation = build_score_probability_explanation(match.get("predicted_score"), match.get("result_probabilities"))
    st.caption("勝敗確率は「勝ち・引き分け・負け」という結果カテゴリごとの合算値です。予測スコアとは計算単位が異なります。")
    predicted_outcome = get_score_outcome(match.get("predicted_score"))
    if strongest.get("key") in {"home", "away"} and predicted_outcome != strongest.get("key"):
        st.info(
            f"なぜ「{score_text}」なのに{strongest['label']}が高いのか？\n\n"
            f"予測スコアは、個別のスコア候補の中で最も選ばれやすい1つを表示しています。"
            f"一方、勝敗確率は複数のスコア候補を合算した確率です。"
            f"そのため、単一スコアでは {score_text} が最上位でも、勝敗全体では{strongest['label']}が最も高くなる場合があります。"
        )
    else:
        st.info(explanation)


def render_score_candidates(candidates: Any) -> None:
    with st.expander("スコア候補 Top 5", expanded=False):
        if not isinstance(candidates, list) or not candidates:
            st.write("スコア候補はありません。")
            return
        top_probability = sum(
            max(safe_float(candidate.get("probability")) or 0.0, 0.0)
            for candidate in candidates[:5]
            if isinstance(candidate, dict)
        )
        st.caption(
            "各行は、その試合が該当スコアで終わる全体確率です。"
            f"Top 5の合計は {format_percent(top_probability)} で、残りは他のスコア候補です。"
        )
        for index, candidate in enumerate(candidates[:5], start=1):
            score = candidate.get("score", "-") if isinstance(candidate, dict) else "-"
            probability = candidate.get("probability") if isinstance(candidate, dict) else None
            st.write(f"{index}. 予測スコア {score} ({format_percent(probability)})")


def render_scorer_candidates(match: dict[str, Any], home: str, away: str) -> None:
    candidates = match.get("scorer_candidates") if isinstance(match.get("scorer_candidates"), dict) else {}
    expected = match.get("expected_goals") if isinstance(match.get("expected_goals"), dict) else {}
    with st.expander("得点者候補 Top 5", expanded=False):
        render_team_scorers(home, candidates.get("home"), safe_float(expected.get("home")))
        st.divider()
        render_team_scorers(away, candidates.get("away"), safe_float(expected.get("away")))


def render_team_scorers(team: str, scorers: Any, team_expected_goals: float | None) -> None:
    st.markdown(f"**{team}**")
    if not isinstance(scorers, list) or not scorers:
        st.write("得点者候補はまだありません。")
        return
    total_weight = sum(max(safe_float(scorer.get("scorer_score")) or 0.0, 0.0) for scorer in scorers if isinstance(scorer, dict))
    for index, scorer in enumerate(scorers[:5], start=1):
        if not isinstance(scorer, dict):
            continue
        parts = [scorer.get("player", "-")]
        if scorer.get("position"):
            parts.append(str(scorer["position"]))
        if scorer.get("probability") is not None:
            parts.append(format_percent(scorer.get("probability")))
        goals = safe_float(scorer.get("goals"))
        if goals is not None:
            parts.append(f"今季{int(goals)}得点")
        scorer_expected_goals = estimate_scorer_expected_goals(scorer, total_weight, team_expected_goals)
        if scorer_expected_goals is not None:
            parts.append(f"ゴール期待値 {scorer_expected_goals:.2f}")
        st.write(f"{index}. " + " / ".join(parts))


def render_past_predictions(archive: dict[str, Any]) -> None:
    st.markdown('<div class="section-title">過去の予測結果</div>', unsafe_allow_html=True)
    metadata = [
        season
        for season in archive.get("metadata", [])
        if isinstance(season, dict) and season.get("key")
    ]
    results = archive.get("results") if isinstance(archive.get("results"), dict) else {}
    metadata_by_key = {str(season["key"]): season for season in metadata}
    season_keys = [key for key in metadata_by_key if key in results]
    if not season_keys:
        st.info("表示できるシーズン別の過去予測結果がありません。")
        return

    default_season = str(archive.get("default_season") or season_keys[0])
    if st.session_state.get("past_season_filter") not in season_keys:
        st.session_state.past_season_filter = default_season if default_season in season_keys else season_keys[0]
    selected_season = st.selectbox(
        "シーズン",
        season_keys,
        format_func=lambda key: str(
            metadata_by_key[key].get("short_label")
            or metadata_by_key[key].get("label")
            or key
        ),
        key="past_season_filter",
    )
    season_meta = metadata_by_key[selected_season]
    data = results.get(selected_season) if isinstance(results.get(selected_season), dict) else {}
    coverage = season_meta.get("coverage") if isinstance(season_meta.get("coverage"), dict) else {}
    if coverage.get("note"):
        st.warning(f"掲載範囲について：{coverage['note']}")

    matches = safe_matches(data)
    if not matches:
        st.info("今シーズンの試合結果はまだありません。試合終了後に結果データが更新されると、予測との比較をここに表示します。")
        return

    st.caption("判定の見方：「勝敗」は勝ち・引き分け・負けの方向性で判定し、「スコア」は点数まで完全一致したかで判定します。")
    filtered = filter_past_matches(matches)
    render_past_summary(filtered)
    if not filtered:
        st.info("条件に一致する過去予測はありません。")
        return
    for match in filtered:
        render_past_card(match)


def render_standings_forecast(forecasts: list[dict[str, Any]]) -> None:
    st.markdown('<div class="section-title">シーズン最終順位予測</div>', unsafe_allow_html=True)
    if not forecasts:
        st.info("最終順位予測はまだ生成されていません。")
        return

    selected_index = st.selectbox(
        "予測した日時",
        list(range(len(forecasts))),
        format_func=lambda index: _standings_snapshot_label(forecasts[index]),
        key="standings_snapshot",
    )
    forecast = forecasts[int(selected_index)]
    teams = [team for team in forecast.get("teams", []) if isinstance(team, dict)]
    if not teams:
        st.info("選択した時点の順位予測データがありません。")
        return

    data_as_of = forecast.get("data_as_of") if isinstance(forecast.get("data_as_of"), dict) else {}
    fixture_summary = forecast.get("fixture_summary") if isinstance(forecast.get("fixture_summary"), dict) else {}
    st.markdown(
        f"""
        <div class="summary-card">
          <div class="summary-grid">
            <div class="summary-item">
              <div class="summary-label">予測日時</div>
              <div class="summary-value">{escape(format_datetime_jp(forecast.get('generated_at')))}</div>
            </div>
            <div class="summary-item">
              <div class="summary-label">実績の基準</div>
              <div class="summary-value">{escape(str(data_as_of.get('label') or '-'))}</div>
            </div>
            <div class="summary-item">
              <div class="summary-label">シミュレーション</div>
              <div class="summary-value">{int(forecast.get('simulation_count') or 0):,}回</div>
            </div>
            <div class="summary-item">
              <div class="summary-label">終了済み試合</div>
              <div class="summary-value">{int(data_as_of.get('completed_matches') or 0)}試合</div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if int(fixture_summary.get("supplemented_matches") or 0) > 0:
        official = int(fixture_summary.get("official_schedule_matches") or 0)
        expected = int(fixture_summary.get("expected_round_robin_matches") or 0)
        st.warning(
            f"現在の公式日程データは {official} / {expected} 試合です。未収録の1試合は、正式日程が反映されるまで逆カードの予測確率を入れ替えて暫定補完しています。"
        )

    rows = []
    mobile_rows = []
    for team in teams:
        name = str(team.get("team_name") or display_team(team.get("team")))
        logo = team_logo_html(team.get("team"), name)
        predicted_rank = safe_int(team.get("predicted_rank")) or 0
        current_rank = safe_int(team.get("current_rank"))
        current_text = str(current_rank) if current_rank is not None else "-"
        current_label = f"現在 {current_rank}位" if current_rank is not None else "現在 -"
        change_text, change_class = _format_rank_change(team.get("rank_change"))
        points = safe_float(team.get("expected_points"))
        points_text = f"{points:.1f}" if points is not None else "-"
        low = safe_int(team.get("likely_rank_low"))
        high = safe_int(team.get("likely_rank_high"))
        range_text = f"想定 {low}〜{high}位" if low is not None and high is not None else ""
        team_is_my_team = is_my_team(team.get("team") or name)
        row_class = "standings-row standings-row--my-team" if team_is_my_team else "standings-row"
        rows.append(
            f'<div class="{row_class}">'
            f'<div class="standings-rank">{predicted_rank}</div>'
            f'<div class="standings-team">{logo}'
            f'<span class="standings-team-copy"><span class="standings-team-name">{escape(name)}</span>'
            f'<span class="standings-range">{escape(range_text)}</span></span></div>'
            f'<div class="standings-metric standings-current">{escape(current_text)}</div>'
            f'<div class="standings-metric standings-change {change_class}">{escape(change_text)}</div>'
            f'<div class="standings-metric standings-champion">{escape(format_percent(team.get("champion_probability")))}</div>'
            f'<div class="standings-metric standings-top3">{escape(format_percent(team.get("top3_probability")))}</div>'
            f'<div class="standings-metric standings-bottom3">{escape(format_percent(team.get("bottom3_probability")))}</div>'
            f'<div class="standings-points">{escape(points_text)}</div></div>'
        )
        mobile_classes = ["standings-mobile-card"]
        if predicted_rank <= 3:
            mobile_classes.append("standings-mobile-card--top3")
        if team_is_my_team:
            mobile_classes.append("standings-mobile-card--my-team")
        mobile_rows.append(
            f'<div class="{" ".join(mobile_classes)}">'
            f'<div class="standings-mobile-main">'
            f'<div class="standings-mobile-rank"><span class="standings-mobile-rank-label">予測順位</span>{predicted_rank}</div>'
            f'<div class="standings-mobile-team">{logo}'
            f'<span class="standings-mobile-team-name">{escape(name)}</span></div>'
            f'<div class="standings-mobile-points"><span class="standings-mobile-points-label">期待勝点</span>{escape(points_text)}</div>'
            f'</div>'
            f'<div class="standings-mobile-context">'
            f'<span class="standings-mobile-chip">{escape(current_label)}</span>'
            f'<span class="standings-mobile-chip {change_class}">変動 {escape(change_text)}</span>'
            f'<span class="standings-mobile-chip">{escape(range_text or "想定 -")}</span>'
            f'</div>'
            f'<div class="standings-mobile-probs">'
            f'<div class="standings-mobile-prob"><span class="standings-mobile-prob-label">優勝</span>{escape(format_percent(team.get("champion_probability")))}</div>'
            f'<div class="standings-mobile-prob"><span class="standings-mobile-prob-label">Top 3</span>{escape(format_percent(team.get("top3_probability")))}</div>'
            f'<div class="standings-mobile-prob"><span class="standings-mobile-prob-label">下位3</span>{escape(format_percent(team.get("bottom3_probability")))}</div>'
            f'</div></div>'
        )

    st.markdown(
        '<div class="standings-table standings-table--desktop"><div class="standings-header">'
        '<div>予測</div><div>クラブ</div><div>現在</div><div>変動</div>'
        '<div>期待勝点</div><div>優勝</div><div>Top 3</div><div>下位3</div></div>'
        + "".join(rows)
        + '</div><div class="standings-mobile">'
        + "".join(mobile_rows)
        + "</div>",
        unsafe_allow_html=True,
    )


def _standings_snapshot_label(forecast: dict[str, Any]) -> str:
    generated = format_datetime_jp(forecast.get("generated_at"))
    data_as_of = forecast.get("data_as_of") if isinstance(forecast.get("data_as_of"), dict) else {}
    return f"{generated}（実績：{data_as_of.get('label') or '-'}）"


def _format_rank_change(value: Any) -> tuple[str, str]:
    change = safe_int(value)
    if change is None:
        return "-", ""
    if change > 0:
        return f"↑{change}", "standings-change-up"
    if change < 0:
        return f"↓{abs(change)}", "standings-change-down"
    return "→", ""


def filter_past_matches(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sections = sorted({int(m.get("matchweek") or m.get("section")) for m in matches if _is_int_like(m.get("matchweek") or m.get("section"))})
    teams = sorted({display_team(team) for m in matches for team in [m.get("home_team"), m.get("away_team")] if team})
    result_options = ["すべての判定", "勝敗的中", "勝敗外れ", "スコア的中", "スコア外れ"]

    st.markdown('<div class="section-title">絞り込み</div>', unsafe_allow_html=True)
    team_options = ["すべてのチーム", *teams]
    if not st.session_state.get("_past_team_filter_initialized"):
        my_team_name = display_team(st.session_state.get("my_team_code"))
        st.session_state.past_team_filter = my_team_name if my_team_name in team_options else "すべてのチーム"
        st.session_state._past_team_filter_initialized = True
    elif st.session_state.get("past_team_filter") not in team_options:
        st.session_state.past_team_filter = "すべてのチーム"
    team = st.selectbox("チーム", ["すべてのチーム", *teams], key="past_team_filter")
    section = st.selectbox("試合が行われた節", ["すべての節", *sections], key="past_section_filter")
    judgment = st.selectbox("予測結果に対する判定", result_options, key="past_judgment_filter")

    filtered: list[dict[str, Any]] = []
    for match in matches:
        evaluation = evaluate_prediction(match.get("predicted_score"), match.get("actual_score"))
        match_section = match.get("matchweek") or match.get("section")
        names = {display_team(match.get("home_team")), display_team(match.get("away_team"))}
        if section != "すべての節" and safe_int(match_section) != int(section):
            continue
        if team != "すべてのチーム" and team not in names:
            continue
        if judgment != "すべての判定" and judgment not in {evaluation["result_label"], evaluation["score_label"]}:
            continue
        filtered.append(match)
    return filtered


def render_past_summary(matches: list[dict[str, Any]]) -> None:
    evaluations = [evaluate_prediction(m.get("predicted_score"), m.get("actual_score")) for m in matches]
    total = len(evaluations)
    result_hits = sum(1 for item in evaluations if item["result_hit"])
    score_hits = sum(1 for item in evaluations if item["score_hit"])
    recent = sorted(matches, key=past_match_sort_key, reverse=True)[:5]
    recent_evaluations = [evaluate_prediction(m.get("predicted_score"), m.get("actual_score")) for m in recent]
    recent_total = len(recent_evaluations)
    recent_result_hits = sum(1 for item in recent_evaluations if item["result_hit"])
    recent_score_hits = sum(1 for item in recent_evaluations if item["score_hit"])

    st.markdown(
        f"""
        <div class="summary-card">
          <div class="summary-grid">
            <div class="summary-item">
              <div class="summary-label">評価対象</div>
              <div class="summary-value">{total}試合</div>
            </div>
            <div class="summary-item">
              <div class="summary-label">勝敗的中率</div>
              <div class="summary-value">{format_accuracy(result_hits, total)}</div>
            </div>
            <div class="summary-item">
              <div class="summary-label">スコア完全的中率</div>
              <div class="summary-value">{format_accuracy(score_hits, total)}</div>
            </div>
            <div class="summary-item">
              <div class="summary-label">直近5試合</div>
              <div class="summary-value">勝敗 {recent_result_hits}/{recent_total}・スコア {recent_score_hits}/{recent_total}</div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_past_card(match: dict[str, Any]) -> None:
    evaluation = evaluate_prediction(match.get("predicted_score"), match.get("actual_score"))
    result_class = "result-badge-correct" if evaluation["result_hit"] else "result-badge-wrong"
    score_class = "result-badge-correct" if evaluation["score_hit"] else "result-badge-wrong"
    home = display_team(match.get("home_team"))
    away = display_team(match.get("away_team"))
    matchup = team_matchup_html(match.get("home_team"), match.get("away_team"), home, away)

    st.markdown(
        f"""
        <div class="match-card">
          <div class="small">{escape(format_match_meta(match))}</div>
          {matchup}
          <span class="label {result_class}">{evaluation["result_label"]}</span>
          <span class="label {score_class}">{evaluation["score_label"]}</span>
          <div class="score-row">
            <div>予測スコア：<strong class="score">{format_score(match.get("predicted_score"))}</strong></div>
            <div>実際のスコア：<strong class="score">{format_score(match.get("actual_score"))}</strong></div>
          </div>
          <div class="small">予測の勝敗方向：{outcome_label(evaluation["predicted_outcome"])}</div>
          <div class="small">実際の勝敗方向：{outcome_label(evaluation["actual_outcome"])}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def past_match_sort_key(match: dict[str, Any]) -> tuple[str, str, str]:
    raw_date = match.get("date") or match.get("match_date") or ""
    raw_kickoff = match.get("kickoff") or match.get("kickoff_time") or ""
    try:
        parsed = datetime.fromisoformat(str(raw_date))
        date_key = parsed.date().isoformat()
    except ValueError:
        date_key = str(raw_date)
    return date_key, str(raw_kickoff), str(match.get("match_id") or "")


def format_match_meta(match: dict[str, Any]) -> str:
    date = format_date(match.get("date") or match.get("match_date"))
    kickoff = match.get("kickoff")
    venue = match.get("venue")
    return format_optional_parts(date, kickoff, venue)


def build_detail_href(match_id: str) -> str:
    return "?" + urlencode(
        {
            "view": "detail",
            "match_id": match_id,
            "upcoming_team": current_future_team_filter(),
            "upcoming_section": str(current_future_section_filter()),
        }
    )


def update_future_filter_query_params(team: Any, section: Any) -> None:
    if st.session_state.view == "detail":
        return
    set_query_params_if_changed(
        {
            "view": "list",
            "upcoming_team": str(team),
            "upcoming_section": str(section),
        }
    )


def current_future_team_filter() -> str:
    return str(st.session_state.get("future_team_filter") or query_value("upcoming_team") or "すべてのチーム")


def current_future_section_filter() -> str:
    return str(st.session_state.get("future_section_filter") or query_value("upcoming_section") or "すべての節")


def set_query_params_if_changed(params: dict[str, Any]) -> None:
    cleaned = {key: str(value) for key, value in params.items() if value is not None}
    current = {key: query_value(key) for key in cleaned}
    if current == cleaned and set(st.query_params.keys()) == set(cleaned.keys()):
        return
    st.query_params.clear()
    for key, value in cleaned.items():
        st.query_params[key] = value


def query_value(key: str) -> str | None:
    value = st.query_params.get(key)
    if isinstance(value, list):
        return str(value[0]) if value else None
    if value is None:
        return None
    return str(value)


def match_section(match: dict[str, Any]) -> Any:
    return match.get("matchweek") or match.get("section")


def resolve_feature_count(data: dict[str, Any]) -> int | None:
    for match in safe_matches(data):
        model_info = match.get("model_info")
        if isinstance(model_info, dict) and _is_int_like(model_info.get("feature_count")):
            return int(model_info["feature_count"])
    return None


def find_match(matches: list[dict[str, Any]], match_id: str | None) -> dict[str, Any] | None:
    for match in matches:
        if str(match.get("match_id") or id(match)) == str(match_id):
            return match
    return None


def safe_matches(data: dict[str, Any]) -> list[dict[str, Any]]:
    matches = data.get("matches")
    if not isinstance(matches, list):
        return []
    return [match for match in matches if isinstance(match, dict)]


def display_team(value: Any) -> str:
    if value is None or value == "":
        return "-"
    return to_display_name(str(value))


def is_my_team(value: Any) -> bool:
    current = st.session_state.get("my_team_code")
    if not current or value in (None, ""):
        return False
    return to_dataset_code(str(value)) == str(current)


def safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def estimate_scorer_expected_goals(
    scorer: dict[str, Any],
    total_weight: float,
    team_expected_goals: float | None,
) -> float | None:
    if team_expected_goals is None or team_expected_goals < 0 or total_weight <= 0:
        return None
    scorer_weight = max(safe_float(scorer.get("scorer_score")) or 0.0, 0.0)
    if scorer_weight <= 0:
        return None
    return team_expected_goals * scorer_weight / total_weight


def _probability_value(probabilities: dict | None, key: str) -> float:
    if not isinstance(probabilities, dict):
        return 0.0
    value = safe_float(probabilities.get(key))
    return value if value is not None else 0.0


def _is_int_like(value: Any) -> bool:
    try:
        int(value)
    except (TypeError, ValueError):
        return False
    return True


if __name__ == "__main__":
    main()
