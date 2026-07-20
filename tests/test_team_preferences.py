from app.streamlit_app import collect_available_team_codes
from app.utils.team_preferences import normalize_storage_action


def test_normalize_storage_action_accepts_supported_commands() -> None:
    assert normalize_storage_action({"action": "set", "value": "kasm"}) == ("set", "kasm")
    assert normalize_storage_action({"action": "clear"}) == ("clear", None)
    assert normalize_storage_action({"action": "set", "value": ""}) == ("read", None)
    assert normalize_storage_action({"action": "unknown", "value": "kasm"}) == ("read", None)


def test_collect_available_team_codes_prefers_current_fixtures() -> None:
    teams = collect_available_team_codes(
        latest={},
        all_unplayed={
            "matches": [
                {"home_team": "鹿島アントラーズ", "away_team": "uraw"},
                {"home_team": "FC東京", "away_team": "tbd"},
            ]
        },
        past={"matches": [{"home_team": "横浜FC", "away_team": "湘南ベルマーレ"}]},
        standings_forecasts=[],
    )

    assert set(teams) == {"kasm", "uraw", "FCtk"}
    assert "y-fc" not in teams
    assert "tbd" not in teams


def test_collect_available_team_codes_uses_standings_as_last_fallback() -> None:
    teams = collect_available_team_codes(
        latest={},
        all_unplayed={},
        past={},
        standings_forecasts=[
            {
                "teams": [
                    {"team": "kobe", "team_name": "ヴィッセル神戸"},
                    {"team_name": "サンフレッチェ広島"},
                ]
            }
        ],
    )

    assert set(teams) == {"kobe", "hiro"}
