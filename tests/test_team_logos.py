from app.utils.team_logos import TEAM_EMBLEM_CELLS, team_logo_html, team_matchup_html


def test_all_2026_27_j1_teams_have_emblem_positions() -> None:
    expected_codes = {
        "kasm",
        "mito",
        "uraw",
        "chib",
        "kasw",
        "FCtk",
        "tk-v",
        "mcd",
        "ka-f",
        "y-fm",
        "shim",
        "nago",
        "kyot",
        "g-os",
        "c-os",
        "kobe",
        "okay",
        "hiro",
        "fuku",
        "ngsk",
    }

    assert expected_codes <= TEAM_EMBLEM_CELLS.keys()


def test_team_logo_uses_sprite_position_and_accessible_label() -> None:
    logo = team_logo_html("kasm", "鹿島アントラーズ")

    assert 'aria-label="鹿島アントラーズ ロゴ"' in logo
    assert "background-position: -280px 0px" in logo
    assert "team-logo--fallback" not in logo


def test_unknown_team_uses_safe_fallback() -> None:
    logo = team_logo_html("unknown", '<script>alert("x")</script>')

    assert "team-logo--fallback" in logo
    assert "⚽" in logo
    assert "<script>" not in logo


def test_matchup_html_contains_both_teams_and_logos() -> None:
    matchup = team_matchup_html("kasm", "uraw", "鹿島アントラーズ", "浦和レッズ")

    assert "鹿島アントラーズ" in matchup
    assert "浦和レッズ" in matchup
    assert matchup.count('class="team-logo"') == 2
    assert "HOME" in matchup
    assert "AWAY" in matchup
