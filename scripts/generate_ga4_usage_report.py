#!/usr/bin/env python3
"""Generate a repeatable GA4 usage report for the J1 prediction app.

The GA4 property also contains a Qiita data stream. Every query therefore
filters by the J1 app's stream ID so that unrelated traffic is never mixed in.
Authentication uses Google Application Default Credentials (ADC).
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "local" / "analytics"
DEFAULT_PROPERTY_ID = "489676180"
DEFAULT_STREAM_ID = "15315638495"

APP_EVENT_NAMES = (
    "select_app_surface",
    "app_open",
    "view_app_section",
    "view_match_detail",
    "select_team_filter",
    "select_matchweek_filter",
    "select_result_filter",
    "select_past_season",
    "select_standings_snapshot",
    "set_my_team",
    "clear_my_team",
    "theme_changed",
    "install_prompt_available",
    "install_attempt",
    "install_prompt_result",
    "install_instructions_open",
    "app_installed",
    "data_load_error",
)


@dataclass(frozen=True)
class ReportTable:
    title: str
    dimensions: tuple[str, ...]
    metrics: tuple[str, ...]
    rows: tuple[dict[str, str], ...]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="J1試合予測AIのGA4利用状況をMarkdownとJSONに出力します。"
    )
    parser.add_argument(
        "--property-id",
        default=os.getenv("GA4_PROPERTY_ID", DEFAULT_PROPERTY_ID),
        help="GA4 property ID (default: %(default)s)",
    )
    parser.add_argument(
        "--stream-id",
        default=os.getenv("GA4_STREAM_ID", DEFAULT_STREAM_ID),
        help="J1 app data stream ID (default: %(default)s)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=28,
        help="昨日までの集計日数 (default: %(default)s)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="出力先ディレクトリ (default: %(default)s)",
    )
    return parser.parse_args()


def _load_google_analytics_types() -> dict[str, Any]:
    try:
        from google.analytics.data_v1beta import BetaAnalyticsDataClient
        from google.analytics.data_v1beta.types import (
            DateRange,
            Dimension,
            Filter,
            FilterExpression,
            FilterExpressionList,
            Metric,
            OrderBy,
            RunReportRequest,
        )
    except ImportError as exc:  # pragma: no cover - depends on optional SDK
        raise SystemExit(
            "Google Analytics Data API SDKがありません。"
            " `python -m pip install -r requirements-analytics.txt` を実行してください。"
        ) from exc

    return {
        "BetaAnalyticsDataClient": BetaAnalyticsDataClient,
        "DateRange": DateRange,
        "Dimension": Dimension,
        "Filter": Filter,
        "FilterExpression": FilterExpression,
        "FilterExpressionList": FilterExpressionList,
        "Metric": Metric,
        "OrderBy": OrderBy,
        "RunReportRequest": RunReportRequest,
    }


def _stream_filter(types: dict[str, Any], stream_id: str) -> Any:
    Filter = types["Filter"]
    FilterExpression = types["FilterExpression"]
    return FilterExpression(
        filter=Filter(
            field_name="streamId",
            string_filter=Filter.StringFilter(
                match_type=Filter.StringFilter.MatchType.EXACT,
                value=stream_id,
                case_sensitive=False,
            ),
        )
    )


def _event_filter(types: dict[str, Any], event_names: Sequence[str]) -> Any:
    Filter = types["Filter"]
    FilterExpression = types["FilterExpression"]
    return FilterExpression(
        filter=Filter(
            field_name="eventName",
            in_list_filter=Filter.InListFilter(
                values=list(event_names),
                case_sensitive=True,
            ),
        )
    )


def _combined_filter(
    types: dict[str, Any], stream_id: str, event_names: Sequence[str] | None = None
) -> Any:
    expressions = [_stream_filter(types, stream_id)]
    if event_names:
        expressions.append(_event_filter(types, event_names))
    if len(expressions) == 1:
        return expressions[0]
    return types["FilterExpression"](
        and_group=types["FilterExpressionList"](expressions=expressions)
    )


def _response_rows(response: Any, dimensions: Sequence[str], metrics: Sequence[str]) -> tuple[dict[str, str], ...]:
    rows: list[dict[str, str]] = []
    for row in response.rows:
        values: dict[str, str] = {}
        for name, value in zip(dimensions, row.dimension_values):
            values[name] = value.value
        for name, value in zip(metrics, row.metric_values):
            values[name] = value.value
        rows.append(values)
    return tuple(rows)


def _run_table(
    client: Any,
    types: dict[str, Any],
    *,
    property_id: str,
    stream_id: str,
    days: int,
    title: str,
    dimensions: Sequence[str],
    metrics: Sequence[str],
    event_names: Sequence[str] | None = None,
    order_metric: str | None = None,
    limit: int = 100,
) -> ReportTable:
    Dimension = types["Dimension"]
    Metric = types["Metric"]
    DateRange = types["DateRange"]
    OrderBy = types["OrderBy"]
    RunReportRequest = types["RunReportRequest"]

    order_bys = []
    if order_metric:
        order_bys.append(
            OrderBy(
                metric=OrderBy.MetricOrderBy(metric_name=order_metric),
                desc=True,
            )
        )

    request = RunReportRequest(
        property=f"properties/{property_id}",
        dimensions=[Dimension(name=name) for name in dimensions],
        metrics=[Metric(name=name) for name in metrics],
        date_ranges=[DateRange(start_date=f"{days}daysAgo", end_date="yesterday")],
        dimension_filter=_combined_filter(types, stream_id, event_names),
        order_bys=order_bys,
        limit=limit,
    )
    response = client.run_report(request)
    return ReportTable(
        title=title,
        dimensions=tuple(dimensions),
        metrics=tuple(metrics),
        rows=_response_rows(response, dimensions, metrics),
    )


def fetch_reports(property_id: str, stream_id: str, days: int) -> tuple[ReportTable, ...]:
    if days < 1:
        raise ValueError("--days must be at least 1")

    types = _load_google_analytics_types()
    client = types["BetaAnalyticsDataClient"]()

    return (
        _run_table(
            client,
            types,
            property_id=property_id,
            stream_id=stream_id,
            days=days,
            title="概要",
            dimensions=(),
            metrics=(
                "activeUsers",
                "sessions",
                "engagedSessions",
                "screenPageViews",
                "eventCount",
                "averageSessionDuration",
                "bounceRate",
            ),
        ),
        _run_table(
            client,
            types,
            property_id=property_id,
            stream_id=stream_id,
            days=days,
            title="日別推移",
            dimensions=("date",),
            metrics=("activeUsers", "sessions", "screenPageViews", "eventCount"),
            order_metric=None,
            limit=max(days + 5, 100),
        ),
        _run_table(
            client,
            types,
            property_id=property_id,
            stream_id=stream_id,
            days=days,
            title="ページ",
            dimensions=("hostName", "pageTitle"),
            metrics=("screenPageViews", "activeUsers", "eventCount", "bounceRate"),
            order_metric="screenPageViews",
            limit=30,
        ),
        _run_table(
            client,
            types,
            property_id=property_id,
            stream_id=stream_id,
            days=days,
            title="機能利用イベント",
            dimensions=("eventName",),
            metrics=("eventCount", "totalUsers"),
            event_names=APP_EVENT_NAMES,
            order_metric="eventCount",
        ),
        _run_table(
            client,
            types,
            property_id=property_id,
            stream_id=stream_id,
            days=days,
            title="流入元",
            dimensions=("sessionSourceMedium",),
            metrics=("sessions", "activeUsers", "engagedSessions", "engagementRate"),
            order_metric="sessions",
            limit=30,
        ),
        _run_table(
            client,
            types,
            property_id=property_id,
            stream_id=stream_id,
            days=days,
            title="デバイス",
            dimensions=("deviceCategory",),
            metrics=("activeUsers", "sessions", "engagedSessions"),
            order_metric="activeUsers",
        ),
    )


LABELS = {
    "activeUsers": "アクティブユーザー",
    "sessions": "セッション",
    "engagedSessions": "エンゲージメントセッション",
    "screenPageViews": "表示回数",
    "eventCount": "イベント数",
    "totalUsers": "総ユーザー",
    "averageSessionDuration": "平均セッション時間",
    "bounceRate": "直帰率",
    "engagementRate": "エンゲージメント率",
    "date": "日付",
    "hostName": "ホスト名",
    "pageTitle": "ページタイトル",
    "eventName": "イベント名",
    "sessionSourceMedium": "参照元 / メディア",
    "deviceCategory": "デバイス",
}

PERCENT_METRICS = {"bounceRate", "engagementRate"}
DURATION_METRICS = {"averageSessionDuration"}


def _format_value(name: str, value: str) -> str:
    if value in {"", "(not set)"}:
        return value or "-"
    if name == "date" and len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:]}"
    try:
        number = float(value)
    except ValueError:
        return value.replace("|", "\\|")
    if name in PERCENT_METRICS:
        return f"{number * 100:.1f}%"
    if name in DURATION_METRICS:
        return f"{number:.1f}秒"
    if number.is_integer():
        return f"{int(number):,}"
    return f"{number:,.2f}"


def render_markdown(
    *,
    property_id: str,
    stream_id: str,
    days: int,
    generated_on: str,
    tables: Iterable[ReportTable],
) -> str:
    table_list = tuple(tables)
    lines = [
        "# J1試合予測AI GA4利用状況",
        "",
        f"- 生成日: {generated_on}",
        f"- 対象期間: 昨日までの{days}日間",
        f"- GA4プロパティID: `{property_id}`",
        f"- J1アプリのストリームID: `{stream_id}`",
        "- Qiita用ストリームは集計から除外",
        "",
    ]
    feature_table = next((table for table in table_list if table.title == "機能利用イベント"), None)
    if feature_table:
        events = {row.get("eventName", ""): row for row in feature_table.rows}
        app_open_users = float(events.get("app_open", {}).get("totalUsers", "0") or 0)
        app_open_count = float(events.get("app_open", {}).get("eventCount", "0") or 0)
        lines.extend(["## すぐ見る指標", ""])
        if app_open_users:
            lines.extend(
                [
                    f"- 利用者: **{int(app_open_users):,}人**",
                    f"- 起動回数: **{int(app_open_count):,}回**（1人あたり {app_open_count / app_open_users:.2f}回）",
                ]
            )
            for event_name, label in (
                ("view_match_detail", "試合詳細を見た人"),
                ("set_my_team", "マイチームを設定した人"),
                ("app_installed", "PWAをインストールした人"),
            ):
                users = float(events.get(event_name, {}).get("totalUsers", "0") or 0)
                lines.append(
                    f"- {label}: **{int(users):,}人**（利用者の {users / app_open_users * 100:.1f}%）"
                )
        else:
            lines.append("- `app_open` がないため、期間内利用者を算出できません。")
        error_count = float(events.get("data_load_error", {}).get("eventCount", "0") or 0)
        lines.append(f"- データ読込エラー: **{int(error_count):,}件**")
        lines.append("")

    for table in table_list:
        lines.extend([f"## {table.title}", ""])
        columns = (*table.dimensions, *table.metrics)
        if not table.rows:
            lines.extend(["データがありません。", ""])
            continue
        lines.append("| " + " | ".join(LABELS.get(name, name) for name in columns) + " |")
        lines.append("| " + " | ".join("---" for _ in columns) + " |")
        for row in table.rows:
            lines.append(
                "| "
                + " | ".join(_format_value(name, row.get(name, "")) for name in columns)
                + " |"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_outputs(
    *,
    output_dir: Path,
    property_id: str,
    stream_id: str,
    days: int,
    tables: Sequence[ReportTable],
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    generated_on = date.today().isoformat()
    markdown_path = output_dir / "ga4_usage_report_latest.md"
    json_path = output_dir / "ga4_usage_report_latest.json"

    markdown_path.write_text(
        render_markdown(
            property_id=property_id,
            stream_id=stream_id,
            days=days,
            generated_on=generated_on,
            tables=tables,
        ),
        encoding="utf-8",
    )
    payload = {
        "generated_on": generated_on,
        "days": days,
        "property_id": property_id,
        "stream_id": stream_id,
        "tables": [
            {
                "title": table.title,
                "dimensions": table.dimensions,
                "metrics": table.metrics,
                "rows": table.rows,
            }
            for table in tables
        ],
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return markdown_path, json_path


def main() -> int:
    args = parse_args()
    tables = fetch_reports(args.property_id, args.stream_id, args.days)
    markdown_path, json_path = write_outputs(
        output_dir=args.output_dir,
        property_id=args.property_id,
        stream_id=args.stream_id,
        days=args.days,
        tables=tables,
    )
    print(f"Markdown: {markdown_path}")
    print(f"JSON: {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
