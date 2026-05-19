"""ベストエフォートの robots.txt 遵守チェッカー。

各サイトの収集処理前に呼び出すと、disallow なパスをスキップできる。
ネットワーク失敗や robots.txt 未配置は許可扱い（best-effort）。
"""

import logging
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests

DEFAULT_USER_AGENT = "oneco-collector/1.0 (+https://github.com/9mak/oneco)"
DEFAULT_TIMEOUT_SEC = 10


class RobotsChecker:
    """robots.txt をドメインごとに 1 回だけ取得して allow/deny を判定する。

    インスタンス単位でキャッシュするので、同一実行内で複数サイトを処理する
    収集ジョブから使うことを想定している。
    """

    def __init__(
        self,
        user_agent: str = DEFAULT_USER_AGENT,
        timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    ) -> None:
        self.user_agent = user_agent
        self.timeout_sec = timeout_sec
        self._parsers: dict[str, RobotFileParser | None] = {}
        self.logger = logging.getLogger(__name__)

    def is_allowed(self, url: str) -> bool:
        """URL の取得が robots.txt 上 allow か。

        判定不能（非 http URL / fetch 失敗 / robots.txt 未配置）はすべて
        True（許可）を返す。strict モードが必要な場合は呼び出し側で
        別途検証する。
        """
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return True

        origin = f"{parsed.scheme}://{parsed.netloc}"
        parser = self._get_parser(origin)
        if parser is None:
            return True
        return parser.can_fetch(self.user_agent, url)

    def _get_parser(self, origin: str) -> RobotFileParser | None:
        if origin in self._parsers:
            return self._parsers[origin]

        parser = self._fetch_parser(origin)
        self._parsers[origin] = parser
        return parser

    def _fetch_parser(self, origin: str) -> RobotFileParser | None:
        robots_url = f"{origin}/robots.txt"
        try:
            res = requests.get(
                robots_url,
                timeout=self.timeout_sec,
                headers={"User-Agent": self.user_agent},
            )
        except Exception as e:
            self.logger.warning(f"robots.txt fetch failed for {origin}: {e!s}")
            return None

        if res.status_code == 404:
            return None
        if res.status_code >= 400:
            self.logger.warning(f"robots.txt returned {res.status_code} for {origin}")
            return None

        parser = RobotFileParser()
        parser.parse(res.text.splitlines())
        return parser
