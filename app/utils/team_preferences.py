"""Browser-backed preference storage for the Streamlit app."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import streamlit as st


STORAGE_KEY = "j1_prediction_my_team_v1"

_PREFERENCE_STORAGE_JS = r"""
export default function(component) {
    const { data, parentElement, setStateValue } = component;
    const storageKey = data.storage_key;
    let value = null;
    let error = null;

    try {
        if (data.action === "set" && data.value) {
            window.localStorage.setItem(storageKey, String(data.value));
        } else if (data.action === "clear") {
            window.localStorage.removeItem(storageKey);
        }
        value = window.localStorage.getItem(storageKey);
    } catch (exception) {
        error = exception instanceof Error ? exception.message : String(exception);
    }

    const snapshot = {
        loaded: true,
        value: value,
        error: error,
    };
    const serialized = JSON.stringify(snapshot);
    if (parentElement.dataset.myTeamSnapshot !== serialized) {
        parentElement.dataset.myTeamSnapshot = serialized;
        setStateValue("snapshot", snapshot);
    }
}
"""

_preference_storage = st.components.v2.component(
    "my_team_preference_storage",
    js=_PREFERENCE_STORAGE_JS,
    isolate_styles=False,
)


@dataclass(frozen=True)
class TeamPreferenceSnapshot:
    """Result returned by the browser preference component."""

    loaded: bool
    value: str | None = None
    error: str | None = None


def sync_team_preference(
    *,
    action: Literal["read", "set", "clear"] = "read",
    value: str | None = None,
) -> TeamPreferenceSnapshot:
    """Read or update the saved team code in browser localStorage."""

    result = _preference_storage(
        key="my_team_preference_storage",
        data={
            "storage_key": STORAGE_KEY,
            "action": action,
            "value": value,
        },
        default={"snapshot": {"loaded": False, "value": None, "error": None}},
        height=0,
        on_snapshot_change=lambda: None,
    )
    raw = getattr(result, "snapshot", None)
    if not isinstance(raw, dict):
        return TeamPreferenceSnapshot(loaded=False)

    stored_value = raw.get("value")
    error = raw.get("error")
    return TeamPreferenceSnapshot(
        loaded=bool(raw.get("loaded")),
        value=str(stored_value) if stored_value not in (None, "") else None,
        error=str(error) if error not in (None, "") else None,
    )


def normalize_storage_action(value: Any) -> tuple[Literal["read", "set", "clear"], str | None]:
    """Normalize a pending storage command kept in session state."""

    if not isinstance(value, dict):
        return "read", None
    action = value.get("action")
    team_code = value.get("value")
    if action == "set" and team_code not in (None, ""):
        return "set", str(team_code)
    if action == "clear":
        return "clear", None
    return "read", None
