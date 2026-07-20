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
    get_confidence_label,
    get_match_insight_label,
    get_score_outcome,
    get_strongest_outcome,
    outcome_label,
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
    load_latest_predictions,
    load_past_prediction_results,
)
from app.utils.team_logos import team_matchup_html  # noqa: E402
from src.data.team_master import to_display_name  # noqa: E402


st.set_page_config(
    page_title="Jリーグ試合予想AI｜スコア予測・勝敗予想",
    page_icon="⚽",
    layout="centered",
    initial_sidebar_state="collapsed",
)


def main() -> None:
    inject_css()
    latest = load_latest_predictions()
    all_unplayed = load_all_unplayed_predictions()
    past = load_past_prediction_results()

    initialize_state()
    render_header(latest, past, all_unplayed)

    tab = "これからの試合"
    if st.session_state.view != "detail":
        tab = st.radio(
            "表示切替",
            ["これからの試合", "過去の予測結果"],
            horizontal=True,
            label_visibility="collapsed",
        )

    if tab == "これからの試合":
        if st.session_state.view != "detail":
            render_prediction_logic_summary(latest)
        render_future_matches(latest, all_unplayed)
    else:
        render_past_predictions(past)


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
        @media (max-width: 640px) {
            .block-container { padding-left: 1rem; padding-right: 1rem; }
            .score { font-size: 1.45rem; }
            .app-header { padding: 18px 16px; }
            .app-title { font-size: 1.55rem; }
            .header-meta, .summary-grid { grid-template-columns: 1fr; }
            .score-row { align-items: flex-start; flex-direction: column; }
            .prob-line { text-align: left; }
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
    team = st.selectbox(
        "チーム",
        team_options,
        index=option_index(team_options, query_value("upcoming_team"), default=0),
        key="future_team_filter",
    )
    section = st.selectbox(
        "試合が行われる節",
        section_options,
        index=option_index(section_options, query_value("upcoming_section"), default=0),
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
    confidence = get_confidence_label(strongest.get("value"), probabilities)
    insight = get_match_insight_label(probabilities)
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
    insight = get_match_insight_label(probabilities)
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
    confidence = get_confidence_label(strongest.get("value"), match.get("result_probabilities"))
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


def render_past_predictions(data: dict[str, Any]) -> None:
    st.markdown('<div class="section-title">過去の予測結果</div>', unsafe_allow_html=True)
    matches = safe_matches(data)
    if not matches:
        st.info("まだ評価対象の過去予測結果がありません。試合結果が反映されると、ここに的中率が表示されます。")
        return

    st.caption("判定の見方：「勝敗」は勝ち・引き分け・負けの方向性で判定し、「スコア」は点数まで完全一致したかで判定します。")
    filtered = filter_past_matches(matches)
    render_past_summary(filtered)
    if not filtered:
        st.info("条件に一致する過去予測はありません。")
        return
    for match in filtered:
        render_past_card(match)


def filter_past_matches(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sections = sorted({int(m.get("matchweek") or m.get("section")) for m in matches if _is_int_like(m.get("matchweek") or m.get("section"))})
    teams = sorted({display_team(team) for m in matches for team in [m.get("home_team"), m.get("away_team")] if team})
    result_options = ["すべての判定", "勝敗的中", "勝敗外れ", "スコア的中", "スコア外れ"]

    st.markdown('<div class="section-title">絞り込み</div>', unsafe_allow_html=True)
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


def option_index(options: list[Any], selected: Any, default: int = 0) -> int:
    if selected is None:
        return default
    selected_text = str(selected)
    for index, option in enumerate(options):
        if str(option) == selected_text:
            return index
    return default


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
