from __future__ import annotations

from pathlib import Path

from app.utils.analytics import CONSENT_STORAGE_KEY, LINKED_DOMAINS, MEASUREMENT_ID


def test_static_analytics_uses_same_measurement_and_cross_domain_configuration() -> None:
    javascript = Path("docs/analytics.js").read_text(encoding="utf-8")

    assert MEASUREMENT_ID == "G-D757SHS30N"
    assert CONSENT_STORAGE_KEY == "j1_analytics_consent_v1"
    assert '"G-D757SHS30N"' in javascript
    for domain in LINKED_DOMAINS:
        assert domain in javascript
    assert 'window.gtag("set", "linker"' in javascript


def test_analytics_defaults_to_denied_and_requires_explicit_consent() -> None:
    static_javascript = Path("docs/analytics.js").read_text(encoding="utf-8")
    streamlit_python = Path("app/utils/analytics.py").read_text(encoding="utf-8")

    for source in (static_javascript, streamlit_python):
        assert 'ad_storage: "denied"' in source
        assert 'ad_user_data: "denied"' in source
        assert 'ad_personalization: "denied"' in source
        assert 'analytics_storage: "denied"' in source
    assert 'readConsent() !== "granted"' in static_javascript
    assert 'if (consent === "granted")' in streamlit_python


def test_pwa_and_streamlit_register_required_product_events() -> None:
    pwa_javascript = Path("docs/app/app.js").read_text(encoding="utf-8")
    streamlit_python = Path("app/streamlit_app.py").read_text(encoding="utf-8")
    combined = pwa_javascript + streamlit_python

    required_events = {
        "app_open",
        "view_app_section",
        "view_match_detail",
        "select_team_filter",
        "select_matchweek_filter",
        "select_past_season",
        "select_standings_snapshot",
        "set_my_team",
        "clear_my_team",
    }
    for event_name in required_events:
        assert event_name in combined
    for event_name in {
        "install_attempt",
        "install_prompt_result",
        "app_installed",
        "theme_changed",
        "data_load_error",
    }:
        assert event_name in pwa_javascript


def test_streamlit_analytics_deduplicates_browser_events() -> None:
    source = Path("app/utils/analytics.py").read_text(encoding="utf-8")

    assert "sentEventKeys: new Set()" in source
    assert "bridge.sentEventKeys.has(eventKey)" in source
    assert "bridge.sentEventKeys.add(eventKey)" in source
    assert "st.session_state._analytics_event_counter" in source
