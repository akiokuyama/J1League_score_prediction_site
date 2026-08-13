import pandas as pd

from src.config import get_competition
from src.data.scrape_matches import (
    REGULAR_J1_DATA_SITE_URL,
    _filter_profile_matches,
    _merge_with_existing,
    _parse_data_site_tables,
    _parse_matchlist_sections,
    _parse_next_schedule,
)


def test_regular_j1_data_site_targets_2026_27_results() -> None:
    assert "competition_years=2026" in REGULAR_J1_DATA_SITE_URL
    assert "competition_frame_ids=1" in REGULAR_J1_DATA_SITE_URL


def test_parse_data_site_table_includes_regular_and_playoff_matches() -> None:
    html = """
    <table>
      <thead>
        <tr>
          <th>シーズン</th><th>大会</th><th>節</th><th>試合日</th><th>K/O時刻</th>
          <th>ホーム</th><th>スコア</th><th>アウェイ</th><th>スタジアム</th><th>入場者数</th><th>インターネット中継・TV放送</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>2026特別</td><td>明治安田Ｊ１百年構想 EASTグループ</td><td>第１節第１日</td><td>26/02/06(金)</td><td>19:03</td>
          <td>横浜FM</td><td>2-3</td><td>町田</td><td>日産ス</td><td>30529</td><td>ＤＡＺＮ</td>
        </tr>
        <tr>
          <td>2026特別</td><td>明治安田Ｊ１百年構想 プレーオフラウンド</td><td>第１戦第１日</td><td>26/05/30(土)</td><td>14:00</td>
          <td>名古屋</td><td></td><td>未定</td><td>パロ瑞穂</td><td></td><td>ＤＡＺＮ</td>
        </tr>
      </tbody>
    </table>
    """

    df = _parse_data_site_tables(html, "https://example.test")

    assert len(df) == 2
    regular = df.iloc[0]
    assert regular["section"] == 1
    assert regular["match_date"] == "2026-02-06"
    assert regular["home_team"] == "y-fm"
    assert regular["away_team"] == "mcd"
    assert regular["home_score"] == 2
    assert regular["away_score"] == 3
    assert regular["status"] == "finished"

    playoff = df.iloc[1]
    assert playoff["section"] == 101
    assert playoff["section_label"] == "第１戦第１日"
    assert playoff["home_team"] == "nago"
    assert playoff["away_team"] == "tbd"
    assert playoff["status"] == "postponed_or_tbd"


def test_regular_j1_parser_excludes_completed_special_competition() -> None:
    html = """
    <section class="matchlistWrap">
      <div class="timeStamp"><h4>2026年6月1日</h4></div>
      <div class="leagAccTit"><h5>明治安田Ｊ１百年構想リーグ 第10節</h5></div>
      <table class="matchTable"><tbody><tr><td class="match"><td class="clubName">横浜FM</td><td class="point"></td><td class="clubName">町田</td></td><td class="stadium">19:00 日産ス</td></tr></tbody></table>
    </section>
    <section class="matchlistWrap">
      <div class="timeStamp"><h4>2026年8月7日</h4></div>
      <div class="leagAccTit"><h5>明治安田Ｊ１リーグ 第1節</h5></div>
      <table class="matchTable"><tbody><tr><td class="match"><td class="clubName">横浜FM</td><td class="point"></td><td class="clubName">鹿島</td></td><td class="stadium">19:00 日産ス</td></tr></tbody></table>
    </section>
    """

    profile = get_competition("2026_27_j1")
    df = _filter_profile_matches(_parse_matchlist_sections(html, profile), profile)

    assert len(df) == 1
    assert df.iloc[0]["season"] == "2026_27"
    assert df.iloc[0]["category"] == "j1"
    assert df.iloc[0]["match_date"] == "2026-08-07"
    assert df.iloc[0]["competition"] == "明治安田J1リーグ"


def test_regular_j1_data_site_parser_reads_finished_result() -> None:
    html = """
    <table>
      <thead><tr>
        <th>シーズン</th><th>大会</th><th>節</th><th>試合日</th><th>K/O時刻</th>
        <th>ホーム</th><th>スコア</th><th>アウェイ</th><th>スタジアム</th><th>入場者数</th><th>インターネット中継・TV放送</th>
      </tr></thead>
      <tbody><tr>
        <td>2026/27</td><td>Ｊ１</td><td>第１節第１日</td><td>26/08/07(金)</td><td>19:26</td>
        <td>横浜FM</td><td>3-4</td><td>鹿島</td><td>MUFG国立</td><td>63960</td><td>ＤＡＺＮ</td>
      </tr></tbody>
    </table>
    """
    profile = get_competition("2026_27_j1")
    df = _filter_profile_matches(
        _parse_data_site_tables(html, REGULAR_J1_DATA_SITE_URL, profile), profile
    )

    assert len(df) == 1
    assert df.iloc[0]["home_score"] == 3
    assert df.iloc[0]["away_score"] == 4
    assert df.iloc[0]["status"] == "finished"


def test_next_schedule_parser_merges_partial_refresh_with_full_schedule() -> None:
    html = """
    <div class="p-game-schedule__group">
      <h3>2026/8/7 (金) 第1節</h3>
      <a class="m-schedule__link" href="/match/j1/2026/080701/">
        <span class="m-schedule__team-name" data-media="pc">横浜Ｆ・マリノス</span>
        <p class="m-schedule__time-text">19:25</p>
        <span class="m-schedule__team-name" data-media="pc">鹿島アントラーズ</span>
        <p class="m-schedule__info-stadium" data-media="pc">ＭＵＦＧスタジアム</p>
      </a>
    </div>
    """
    profile = get_competition("2026_27_j1")
    fresh = _parse_next_schedule(html, profile)
    existing = fresh.copy()
    existing.loc[0, "kickoff_time"] = "未定"
    second = existing.copy()
    second.loc[0, "match_date"] = "2026-08-08"
    second.loc[0, "home_team"] = "kasw"
    second.loc[0, "away_team"] = "mito"
    existing = pd.concat([existing, second], ignore_index=True)

    merged = _merge_with_existing(fresh, existing)

    assert len(merged) == 2
    assert merged.loc[merged["home_team"] == "y-fm", "kickoff_time"].iloc[0] == "19:25"
    assert merged.loc[merged["home_team"] == "kasw", "away_team"].iloc[0] == "mito"
