"""
robots.txt 遵守チェッカー

サイト設定（sites.yaml）の各 list_url に対し、サーバーの robots.txt を
取得して当該URLがクローラーに対して disallow されていないかを判定する。

このモジュールは I/O とロジックを分離し、ロジック部分（is_allowed_by_robots）
はオフラインでユニットテスト可能。CLI 部分は実 HTTP を叩く。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

DEFAULT_USER_AGENT = "OnecoCollector"


@dataclass(frozen=True)
class RobotCheckResult:
    """robots.txt 判定結果"""

    url: str
    allowed: bool
    reason: str  # 人間可読な根拠
    robots_url: str


def _build_parser(robots_txt: str, robots_url: str) -> RobotFileParser:
    parser = RobotFileParser()
    parser.set_url(robots_url)
    parser.parse(robots_txt.splitlines())
    return parser


def is_allowed_by_robots(
    target_url: str,
    robots_txt: str,
    user_agent: str = DEFAULT_USER_AGENT,
) -> RobotCheckResult:
    """
    robots.txt の本文を渡して、target_url への user_agent のアクセスが
    許可されているかを判定する。

    robots.txt が空 or 取得失敗のケース（呼び出し側で空文字を渡せ）では
    RFC 9309 に従い「許可」とみなす。
    """
    parsed = urlparse(target_url)
    if not parsed.netloc:
        return RobotCheckResult(
            url=target_url,
            allowed=False,
            reason="invalid URL (no netloc)",
            robots_url="",
        )

    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

    if not robots_txt.strip():
        return RobotCheckResult(
            url=target_url,
            allowed=True,
            reason="robots.txt empty/unavailable → permissive (RFC 9309)",
            robots_url=robots_url,
        )

    parser = _build_parser(robots_txt, robots_url)
    allowed = parser.can_fetch(user_agent, target_url)
    return RobotCheckResult(
        url=target_url,
        allowed=allowed,
        reason="allowed" if allowed else "disallowed by robots.txt",
        robots_url=robots_url,
    )


def summarize(results: Iterable[RobotCheckResult]) -> dict[str, int]:
    """件数サマリー（CLI レポート用）"""
    summary = {"total": 0, "allowed": 0, "disallowed": 0}
    for r in results:
        summary["total"] += 1
        if r.allowed:
            summary["allowed"] += 1
        else:
            summary["disallowed"] += 1
    return summary
