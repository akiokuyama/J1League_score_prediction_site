from __future__ import annotations

import json
from pathlib import Path

from PIL import Image


PWA_ROOT = Path("docs/app")


def test_pwa_manifest_and_icons_are_complete() -> None:
    manifest = json.loads((PWA_ROOT / "manifest.webmanifest").read_text(encoding="utf-8"))

    assert manifest["name"] == "J1試合予想AI"
    assert manifest["start_url"] == "./"
    assert manifest["scope"] == "./"
    assert manifest["display"] == "standalone"
    assert {icon["purpose"] for icon in manifest["icons"]} == {"any", "maskable"}

    expected_sizes = {
        "icons/icon-192.png": (192, 192),
        "icons/icon-512.png": (512, 512),
        "icons/icon-maskable-512.png": (512, 512),
    }
    for relative_path, expected_size in expected_sizes.items():
        path = PWA_ROOT / relative_path
        assert path.exists()
        with Image.open(path) as image:
            assert image.size == expected_size
            assert image.format == "PNG"


def test_pwa_shell_registers_required_mobile_capabilities() -> None:
    html = (PWA_ROOT / "index.html").read_text(encoding="utf-8")
    javascript = (PWA_ROOT / "app.js").read_text(encoding="utf-8")
    service_worker = (PWA_ROOT / "service-worker.js").read_text(encoding="utf-8")
    stylesheet = (PWA_ROOT / "styles.css").read_text(encoding="utf-8")

    assert 'rel="manifest"' in html
    assert 'name="apple-mobile-web-app-capable"' in html
    assert 'class="bottom-nav"' in html
    assert "serviceWorker.register" in javascript
    assert "j1_prediction_my_team_v1" in javascript
    assert "j1_prediction_theme_v1" in javascript
    assert 'input[name="theme"]' in javascript
    assert 'applyTheme(state.theme, { persist: false })' in javascript
    assert "document.documentElement.dataset.theme = theme" in html
    assert "all_unplayed_predictions.json" in javascript
    assert "PAST_RESULTS_BASE" in javascript
    assert 'const PAST_RESULTS_BASE = "./data/past_prediction_results"' in javascript
    assert "pastIndex: `${PAST_RESULTS_BASE}/index.json`" in javascript
    assert "表示するシーズン" in javascript
    assert "今シーズンの試合結果はまだありません" in javascript
    assert 'const STANDINGS_FORECAST_BASE = `${REPOSITORY_DATA_BASE}/standings_forecast`' in javascript
    assert "standings: `${STANDINGS_FORECAST_BASE}/latest.json`" in javascript
    assert "standingsIndex: `${STANDINGS_FORECAST_BASE}/index.json`" in javascript
    assert "loadStandingsForecasts" in javascript
    assert "表示する順位予測の日時" in javascript
    assert "formatForecastDateTime" in javascript
    assert "./manifest.webmanifest" in service_worker
    assert 'href="./styles.css?v=4"' in html
    assert 'src="./app.js?v=6"' in html
    assert 'APP_CACHE = "j1-prediction-app-v8"' in service_worker
    assert '"./app.js?v=6"' in service_worker
    assert '"./styles.css?v=4"' in service_worker
    assert "raw.githubusercontent.com" in service_worker
    assert "./data/past_prediction_results/index.json" in service_worker
    assert "./data/past_prediction_results/2026_27_j1.json" in service_worker
    assert "./data/past_prediction_results/2026_special.json" in service_worker
    assert 'url.pathname.includes("/app/data/past_prediction_results/")' in service_worker
    assert "[hidden]" in stylesheet
    assert "display: none !important;" in stylesheet
    assert ':root[data-theme="dark"]' in stylesheet
    assert ':root[data-theme="light"]' in stylesheet
    assert ".theme-options" in stylesheet
    assert 'state.teamFilter === "all" || !state.myTeam' not in javascript
    assert 'teamFilter: initialMyTeam ? "my-team" : "all"' in javascript


def test_landing_page_links_to_pwa() -> None:
    html = Path("docs/index.html").read_text(encoding="utf-8")

    assert 'href="./app/"' in html
    assert "2026/27 明治安田J1リーグ対応" in html


def test_past_results_are_split_by_season_with_partial_archive_note() -> None:
    index = json.loads((Path("outputs/past_prediction_results") / "index.json").read_text(encoding="utf-8"))
    seasons = {season["key"]: season for season in index["seasons"]}
    current = json.loads(
        (Path("outputs/past_prediction_results") / seasons["2026_27_j1"]["data_file"]).read_text(encoding="utf-8")
    )
    special = json.loads(
        (Path("outputs/past_prediction_results") / seasons["2026_special"]["data_file"]).read_text(encoding="utf-8")
    )

    assert index["default_season"] == "2026_27_j1"
    assert current["season"] == "2026_27"
    assert current["matches"] == []
    assert len(special["matches"]) == 49
    assert seasons["2026_special"]["coverage"]["start_date"] == "2026-05-10"
    assert seasons["2026_special"]["coverage"]["end_date"] == "2026-06-06"
    assert "第16節" in seasons["2026_special"]["coverage"]["note"]
    assert "大会全体の結果ではありません" in seasons["2026_special"]["coverage"]["note"]
    assert (
        Path("docs/app/data/past_prediction_results/index.json").read_text(encoding="utf-8")
        == Path("outputs/past_prediction_results/index.json").read_text(encoding="utf-8")
    )
    for filename in ["2026_27_j1.json", "2026_special.json"]:
        assert (
            Path("docs/app/data/past_prediction_results", filename).read_text(encoding="utf-8")
            == Path("outputs/past_prediction_results", filename).read_text(encoding="utf-8")
        )
