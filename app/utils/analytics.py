"""Consent-aware GA4 integration for the Streamlit application."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import streamlit as st


MEASUREMENT_ID = "G-D757SHS30N"
CONSENT_STORAGE_KEY = "j1_analytics_consent_v1"
LINKED_DOMAINS = [
    "akiokuyama.github.io",
    "j1league-score-prediction.streamlit.app",
]

_ANALYTICS_BRIDGE_JS = r"""
export default function(component) {
    const { data, parentElement, setStateValue } = component;
    const measurementId = data.measurement_id;
    const storageKey = data.storage_key;
    const linkedDomains = Array.isArray(data.linked_domains) ? data.linked_domains : [];
    const events = Array.isArray(data.events) ? data.events : [];
    let storageError = null;

    window.__j1AnalyticsBridge = window.__j1AnalyticsBridge || {
        consentInitialized: false,
        tagRequested: false,
        configured: false,
        sentEventKeys: new Set(),
    };
    const bridge = window.__j1AnalyticsBridge;

    window.dataLayer = window.dataLayer || [];
    window.gtag = window.gtag || function() {
        window.dataLayer.push(arguments);
    };

    if (!bridge.consentInitialized) {
        bridge.consentInitialized = true;
        window.gtag("consent", "default", {
            ad_storage: "denied",
            ad_user_data: "denied",
            ad_personalization: "denied",
            analytics_storage: "denied",
            wait_for_update: 500,
        });
    }

    function readConsent() {
        try {
            const value = window.localStorage.getItem(storageKey);
            return value === "granted" || value === "denied" ? value : null;
        } catch (exception) {
            storageError = exception instanceof Error ? exception.message : String(exception);
            return null;
        }
    }

    function writeConsent(value) {
        try {
            window.localStorage.setItem(storageKey, value);
        } catch (exception) {
            storageError = exception instanceof Error ? exception.message : String(exception);
        }
    }

    function ensureTag() {
        if (!bridge.tagRequested) {
            bridge.tagRequested = true;
            const script = document.createElement("script");
            script.async = true;
            script.src = `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(measurementId)}`;
            script.dataset.j1AnalyticsTag = measurementId;
            document.head.appendChild(script);
        }
        if (!bridge.configured) {
            bridge.configured = true;
            const debugMode = ["localhost", "127.0.0.1"].includes(window.location.hostname);
            window.gtag("js", new Date());
            window.gtag("set", "linker", { domains: linkedDomains });
            window.gtag("config", measurementId, { debug_mode: debugMode });
        }
    }

    let consent = readConsent();
    if (data.consent_action === "granted" || data.consent_action === "denied") {
        consent = data.consent_action;
        writeConsent(consent);
    }

    if (consent === "granted" || consent === "denied") {
        window.gtag("consent", "update", {
            ad_storage: "denied",
            ad_user_data: "denied",
            ad_personalization: "denied",
            analytics_storage: consent,
        });
    }

    if (consent === "granted") {
        ensureTag();
        for (const event of events) {
            const eventKey = String(event.key || "");
            if (!event.name || !eventKey || bridge.sentEventKeys.has(eventKey)) continue;
            window.gtag("event", event.name, event.parameters || {});
            bridge.sentEventKeys.add(eventKey);
        }
    }

    const snapshot = {
        loaded: true,
        consent: consent,
        storage_error: storageError,
        sent_event_count: bridge.sentEventKeys.size,
    };
    const serialized = JSON.stringify(snapshot);
    if (parentElement.dataset.analyticsSnapshot !== serialized) {
        parentElement.dataset.analyticsSnapshot = serialized;
        setStateValue("snapshot", snapshot);
    }
}
"""

_analytics_bridge = st.components.v2.component(
    "j1_ga4_analytics_bridge",
    js=_ANALYTICS_BRIDGE_JS,
    isolate_styles=False,
)


@dataclass(frozen=True)
class AnalyticsSnapshot:
    """State returned by the browser-side analytics bridge."""

    loaded: bool
    consent: Literal["granted", "denied"] | None = None
    storage_error: str | None = None
    sent_event_count: int = 0


def sync_analytics(
    *,
    component_key: str,
    consent_action: Literal["read", "granted", "denied"] = "read",
    events: list[dict[str, Any]] | None = None,
) -> AnalyticsSnapshot:
    """Synchronize consent and send a batch of deduplicated GA4 events."""

    result = _analytics_bridge(
        key=component_key,
        data={
            "measurement_id": MEASUREMENT_ID,
            "storage_key": CONSENT_STORAGE_KEY,
            "linked_domains": LINKED_DOMAINS,
            "consent_action": consent_action,
            "events": events or [],
        },
        default={
            "snapshot": {
                "loaded": False,
                "consent": None,
                "storage_error": None,
                "sent_event_count": 0,
            }
        },
        height=0,
        on_snapshot_change=lambda: None,
    )
    raw = getattr(result, "snapshot", None)
    if not isinstance(raw, dict):
        return AnalyticsSnapshot(loaded=False)
    consent = raw.get("consent")
    return AnalyticsSnapshot(
        loaded=bool(raw.get("loaded")),
        consent=consent if consent in {"granted", "denied"} else None,
        storage_error=str(raw["storage_error"]) if raw.get("storage_error") else None,
        sent_event_count=int(raw.get("sent_event_count") or 0),
    )


def queue_analytics_event(
    event_name: str,
    parameters: dict[str, str | int | float | bool] | None = None,
) -> None:
    """Queue one event for the next browser-bridge flush."""

    counter = int(st.session_state.get("_analytics_event_counter") or 0) + 1
    st.session_state._analytics_event_counter = counter
    sanitized = {
        str(key): value[:100] if isinstance(value, str) else value
        for key, value in (parameters or {}).items()
        if isinstance(value, (str, int, float, bool))
    }
    queue = st.session_state.setdefault("_analytics_event_queue", [])
    queue.append(
        {
            "name": event_name,
            "parameters": {"app_surface": "streamlit", **sanitized},
            "key": f"streamlit:{counter}:{event_name}",
        }
    )


def flush_analytics_events() -> AnalyticsSnapshot:
    """Send queued events and remove them from Streamlit session state."""

    events = st.session_state.pop("_analytics_event_queue", [])
    return sync_analytics(
        component_key="analytics_event_bridge",
        events=events if isinstance(events, list) else [],
    )


def track_state_change(
    state_key: str,
    value: Any,
    event_name: str,
    parameters: dict[str, str | int | float | bool] | None = None,
) -> None:
    """Queue an event only when an already-initialized widget value changes."""

    previous_key = f"_analytics_previous_{state_key}"
    if previous_key in st.session_state and st.session_state[previous_key] != value:
        queue_analytics_event(event_name, parameters)
    st.session_state[previous_key] = value
