"""GA4 週次レポート自動化 (T071③)。

oneco (GA4 property `properties/541319394`) の直近7日間 (JST, 前日締め) の主要指標を
取得し、前週7日間との比較 (増減) を添えて Markdown レポートを出力し、Discord へ要約を
通知する。

設計判断:
- 認証は Application Default Credentials (ADC) 前提。ローカル ad hoc 実行では
  --access-token-from-env で「事前に取得したアクセストークンを環境変数経由で渡す」
  経路も用意する (呼び出し元の ADC を書き換えたくない場合の代替)。
- 期間は「直近7日 (今日を含まない、JST 前日締め)」対 「その前の7日」。日次バッチではなく
  週次サマリなので曜日変動を均せる7日区切りにする (weekly-count-audit.yml と同じ思想)。
- 対象イベント: page_view, external_link_click, click。動物詳細ページ (/animals/ 配下) の
  screenPageViews は個別に集計する (サイトの中核導線がどれだけ見られているかを追う指標)。
  pagePath 上位10件も併記する。
- Discord 通知はコンパクトに: users / 動物詳細PV / external_link_click の3指標と前週比のみ。
  詳細 (イベント別・上位ページ) は Markdown レポート (workflow artifact) 側に譲る
  (Discord content 2000 文字上限に収めるため、weekly-count-audit と同じ絞り込み思想)。
- GA4 API 呼び出しが失敗した場合はサイレントに exit 0 せず、Discord に失敗を通知した上で
  exit 1 にする (secret-health.yml の「二重ガード」思想を踏襲。無音の欠測を防ぐ)。
- レポートは commit せず workflow artifact 保存のみ (weekly-count-audit.yml と同じ判断:
  週次スナップショットを main 履歴に自動コミットする運用前例を踏襲しない)。
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from data_collector.infrastructure.notification_client import (  # noqa: E402
    NotificationClient,
    NotificationLevel,
)

JST = ZoneInfo("Asia/Tokyo")
GA4_PROPERTY = "properties/541319394"
TRACKED_EVENTS = ("page_view", "external_link_click", "click")
ANIMAL_PATH_PREFIX = "/animals/"
TOP_PAGES_LIMIT = 10


@dataclass
class Period:
    """[start, end] は両端含む日付 (GA4 API の date range 仕様に合わせる)。"""

    start: date
    end: date

    @property
    def label(self) -> str:
        return f"{self.start.isoformat()}〜{self.end.isoformat()}"


def compute_periods(today: date) -> tuple[Period, Period]:
    """today (JST) を基準に「直近7日 (前日締め)」と「その前の7日」を返す。"""
    yesterday = today - timedelta(days=1)
    current = Period(start=yesterday - timedelta(days=6), end=yesterday)
    previous = Period(
        start=current.start - timedelta(days=7), end=current.start - timedelta(days=1)
    )
    return current, previous


def delta_str(current: int, previous: int) -> str:
    """前週比を人間可読な文字列にする (+12 / -3 / ±0)。"""
    diff = current - previous
    if diff > 0:
        return f"+{diff}"
    if diff < 0:
        return str(diff)
    return "±0"


def pct_str(current: int, previous: int) -> str:
    if previous == 0:
        return "n/a" if current == 0 else "+∞%"
    pct = (current - previous) / previous * 100
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.1f}%"


class GA4Client:
    """google-analytics-data BetaAnalyticsDataClient の薄いラッパー。

    テストではこのクラス自体をモックし、実 API を呼ばない。
    """

    def __init__(self, property_id: str, access_token: str | None = None) -> None:
        from google.analytics.data_v1beta import BetaAnalyticsDataClient

        if access_token:
            # --access-token-from-env 経路: 呼び出し元 ADC を使わず、事前取得済みの
            # アクセストークンを直接使う (impersonation 済みトークンをそのまま渡す想定)。
            # google.auth.credentials.Credentials は abstract (refresh 未実装) なので
            # インスタンス化できない。google.oauth2.credentials.Credentials は非 abstract で
            # 固定トークンをそのまま使う用途に対応している (refresh は呼ばれない)。
            from google.oauth2.credentials import Credentials

            credentials = Credentials(token=access_token)
            self._client = BetaAnalyticsDataClient(credentials=credentials)
        else:
            self._client = BetaAnalyticsDataClient()
        self._property_id = property_id

    def run_report(self, **kwargs: Any) -> Any:
        from google.analytics.data_v1beta.types import RunReportRequest

        request = RunReportRequest(property=self._property_id, **kwargs)
        return self._client.run_report(request)


def fetch_metrics(client: GA4Client, period: Period) -> dict[str, Any]:
    """指定期間の主要指標を取得する。

    Returns:
        {
          "total_users": int,
          "events": {event_name: count, ...},
          "animal_page_views": int,
          "top_pages": [(pagePath, views), ...],  # 降順、最大 TOP_PAGES_LIMIT 件
        }
    """
    from google.analytics.data_v1beta.types import (
        DateRange,
        Dimension,
        Filter,
        FilterExpression,
        Metric,
        OrderBy,
    )

    date_range = DateRange(start_date=period.start.isoformat(), end_date=period.end.isoformat())

    users_resp = client.run_report(
        date_ranges=[date_range],
        metrics=[Metric(name="totalUsers")],
    )
    total_users = _first_metric_int(users_resp)

    events_resp = client.run_report(
        date_ranges=[date_range],
        dimensions=[Dimension(name="eventName")],
        metrics=[Metric(name="eventCount")],
    )
    events = dict.fromkeys(TRACKED_EVENTS, 0)
    for row in events_resp.rows:
        name = row.dimension_values[0].value
        if name in events:
            events[name] = int(row.metric_values[0].value)

    animal_resp = client.run_report(
        date_ranges=[date_range],
        dimensions=[Dimension(name="pagePath")],
        metrics=[Metric(name="screenPageViews")],
        dimension_filter=FilterExpression(
            filter=Filter(
                field_name="pagePath",
                string_filter=Filter.StringFilter(
                    match_type=Filter.StringFilter.MatchType.BEGINS_WITH,
                    value=ANIMAL_PATH_PREFIX,
                ),
            )
        ),
    )
    animal_page_views = sum(int(row.metric_values[0].value) for row in animal_resp.rows)

    top_resp = client.run_report(
        date_ranges=[date_range],
        dimensions=[Dimension(name="pagePath")],
        metrics=[Metric(name="screenPageViews")],
        order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="screenPageViews"), desc=True)],
        limit=TOP_PAGES_LIMIT,
    )
    top_pages = [
        (row.dimension_values[0].value, int(row.metric_values[0].value)) for row in top_resp.rows
    ]

    return {
        "total_users": total_users,
        "events": events,
        "animal_page_views": animal_page_views,
        "top_pages": top_pages,
    }


def _first_metric_int(resp: Any) -> int:
    if not resp.rows:
        return 0
    return int(resp.rows[0].metric_values[0].value)


def render_markdown(
    current: Period, previous: Period, cur: dict[str, Any], prev: dict[str, Any]
) -> str:
    lines = [
        "# GA4 週次レポート (oneco)",
        "",
        f"- 対象期間: {current.label} (前週比較: {previous.label})",
        f"- 生成日時 (JST): {datetime.now(JST).isoformat(timespec='seconds')}",
        "",
        "## サマリ",
        "",
        "| 指標 | 今週 | 前週 | 増減 | 増減率 |",
        "|---|---:|---:|---:|---:|",
        (
            f"| ユーザー数 | {cur['total_users']} | {prev['total_users']} | "
            f"{delta_str(cur['total_users'], prev['total_users'])} | "
            f"{pct_str(cur['total_users'], prev['total_users'])} |"
        ),
        (
            f"| 動物詳細ページ閲覧数 (`{ANIMAL_PATH_PREFIX}*`) | {cur['animal_page_views']} | "
            f"{prev['animal_page_views']} | "
            f"{delta_str(cur['animal_page_views'], prev['animal_page_views'])} | "
            f"{pct_str(cur['animal_page_views'], prev['animal_page_views'])} |"
        ),
    ]
    for event_name in TRACKED_EVENTS:
        c = cur["events"].get(event_name, 0)
        p = prev["events"].get(event_name, 0)
        lines.append(
            f"| イベント: `{event_name}` | {c} | {p} | {delta_str(c, p)} | {pct_str(c, p)} |"
        )

    lines += ["", "## 上位ページ (今週, screenPageViews)", "", "| pagePath | views |", "|---|---:|"]
    if cur["top_pages"]:
        for path, views in cur["top_pages"]:
            lines.append(f"| `{path}` | {views} |")
    else:
        lines.append("| (データなし) | - |")

    lines.append("")
    return "\n".join(lines)


def render_discord_message(current: Period, cur: dict[str, Any], prev: dict[str, Any]) -> str:
    users_c, users_p = cur["total_users"], prev["total_users"]
    animal_c, animal_p = cur["animal_page_views"], prev["animal_page_views"]
    ext_c = cur["events"].get("external_link_click", 0)
    ext_p = prev["events"].get("external_link_click", 0)
    return (
        f"[GA4 週次] {current.label}\n"
        f"- ユーザー数: {users_c} ({delta_str(users_c, users_p)}, {pct_str(users_c, users_p)})\n"
        f"- 動物詳細PV: {animal_c} ({delta_str(animal_c, animal_p)}, {pct_str(animal_c, animal_p)})\n"
        f"- external_link_click: {ext_c} ({delta_str(ext_c, ext_p)}, {pct_str(ext_c, ext_p)})"
    )


def notify_discord(message: str, level: NotificationLevel = NotificationLevel.INFO) -> bool:
    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook:
        print("[ga4-weekly] DISCORD_WEBHOOK_URL 未設定のため通知スキップ", file=sys.stderr)
        return False
    client = NotificationClient({"discord_webhook_url": webhook})
    client.send_alert(level, message, {})
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run", action="store_true", help="Discord 通知せず標準出力に表示するのみ"
    )
    parser.add_argument("--out-dir", default=str(ROOT / "reports" / "ga4"))
    parser.add_argument(
        "--access-token-from-env",
        help="このアクセストークン (impersonation 済み等) を環境変数名で指定して認証に使う。未指定時は ADC。",
    )
    args = parser.parse_args()

    access_token: str | None = None
    if args.access_token_from_env:
        access_token = os.environ.get(args.access_token_from_env)
        if not access_token:
            print(f"[ga4-weekly] {args.access_token_from_env} が未設定/空です", file=sys.stderr)
            return 1

    today = datetime.now(JST).date()
    current, previous = compute_periods(today)

    try:
        client = GA4Client(GA4_PROPERTY, access_token=access_token)
        cur = fetch_metrics(client, current)
        prev = fetch_metrics(client, previous)
    except Exception as e:  # GA4 API 障害・認証失敗等
        print(f"[ga4-weekly] GA4 API 呼び出し失敗: {e!r}", file=sys.stderr)
        notify_discord(
            f"[GA4 週次] レポート生成に失敗しました: {type(e).__name__}: {e}",
            level=NotificationLevel.ERROR,
        )
        return 1

    markdown = render_markdown(current, previous, cur, prev)
    discord_message = render_discord_message(current, cur, prev)

    if args.dry_run:
        print(markdown)
        print("---", file=sys.stderr)
        print(discord_message, file=sys.stderr)
        return 0

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = today.strftime("%Y%m%d")
    md_path = out_dir / f"ga4-weekly-{stamp}.md"
    md_path.write_text(markdown, encoding="utf-8")
    print(f"[ga4-weekly] 出力: {md_path}", file=sys.stderr)

    notify_discord(discord_message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
