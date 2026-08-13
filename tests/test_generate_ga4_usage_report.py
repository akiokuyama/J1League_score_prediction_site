from scripts.generate_ga4_usage_report import ReportTable, _format_value, render_markdown


def test_format_value() -> None:
    assert _format_value("bounceRate", "0.273") == "27.3%"
    assert _format_value("averageSessionDuration", "42.125") == "42.1秒"
    assert _format_value("eventCount", "1234") == "1,234"
    assert _format_value("date", "20260807") == "2026-08-07"


def test_render_markdown_records_stream_scope() -> None:
    table = ReportTable(
        title="機能利用イベント",
        dimensions=("eventName",),
        metrics=("eventCount", "totalUsers"),
        rows=(
            {"eventName": "app_open", "eventCount": "38", "totalUsers": "8"},
        ),
    )

    output = render_markdown(
        property_id="489676180",
        stream_id="15315638495",
        days=28,
        generated_on="2026-08-08",
        tables=(table,),
    )

    assert "Qiita用ストリームは集計から除外" in output
    assert "利用者: **8人**" in output
    assert "1人あたり 4.75回" in output
    assert "| app_open | 38 | 8 |" in output
    assert "`15315638495`" in output
