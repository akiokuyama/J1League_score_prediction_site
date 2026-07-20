"""HTML helpers for displaying 2026-27 J1 team emblems."""

from __future__ import annotations

from html import escape
from typing import Any

from src.data.team_master import to_dataset_code


# Grid positions in J.LEAGUE.jp's official 2026-27 80px emblem sprite.
# Source: https://www.jleague.jp/img/common/2026_27/team_emb_l.webp
TEAM_EMBLEM_CELLS: dict[str, tuple[int, int]] = {
    "kasm": (7, 0),
    "mito": (8, 0),
    "uraw": (2, 1),
    "chib": (4, 1),
    "kasw": (5, 1),
    "FCtk": (6, 1),
    "fctk": (6, 1),
    "tk-v": (7, 1),
    "mcd": (8, 1),
    "ka-f": (9, 1),
    "y-fm": (0, 2),
    "shim": (0, 3),
    "nago": (3, 3),
    "kyot": (6, 3),
    "g-os": (7, 3),
    "c-os": (8, 3),
    "kobe": (0, 4),
    "okay": (3, 4),
    "hiro": (4, 4),
    "fuku": (1, 5),
    "ngsk": (4, 5),
}

EMBLEM_DISPLAY_SIZE = 40


def team_logo_html(team: Any, display_name: str) -> str:
    """Return an accessible emblem span, with a fallback for unknown teams."""

    raw_team = "" if team is None else str(team)
    code = to_dataset_code(raw_team)
    label = escape(f"{display_name} ロゴ", quote=True)
    cell = TEAM_EMBLEM_CELLS.get(code)
    if cell is None:
        return f'<span class="team-logo team-logo--fallback" role="img" aria-label="{label}">⚽</span>'

    column, row = cell
    x = -(column * EMBLEM_DISPLAY_SIZE)
    y = -(row * EMBLEM_DISPLAY_SIZE)
    return (
        f'<span class="team-logo" role="img" aria-label="{label}" '
        f'style="background-position: {x}px {y}px;"></span>'
    )


def team_matchup_html(
    home_team: Any,
    away_team: Any,
    home_name: str,
    away_name: str,
) -> str:
    """Build the shared home-versus-away display used by prediction cards."""

    home_logo = team_logo_html(home_team, home_name)
    away_logo = team_logo_html(away_team, away_name)
    return (
        '<div class="teams team-matchup">'
        '<div class="team-identity team-identity--home">'
        '<span class="team-copy">'
        f'<span class="team-name">{escape(home_name)}</span>'
        '<span class="team-side-label">HOME</span>'
        "</span>"
        f"{home_logo}"
        "</div>"
        '<span class="versus">VS</span>'
        '<div class="team-identity team-identity--away">'
        f"{away_logo}"
        '<span class="team-copy">'
        f'<span class="team-name">{escape(away_name)}</span>'
        '<span class="team-side-label">AWAY</span>'
        "</span>"
        "</div>"
        "</div>"
    )
