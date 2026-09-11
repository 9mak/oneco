"""SNS 日次まとめ投稿ログの YAML 永続化 (T160)

個体単位の投稿履歴 (旧 data/sns_posts.yaml) は日次まとめ化に伴い不要になった。
「投稿済み日付」だけを記録し、同一日付の二重投稿を防ぐ。

ストレージは YAML ファイル (旧実装と同じ思想)。既定パスは
data/sns_digest_log.yaml だが、環境変数 SNS_DIGEST_LOG_PATH で差し替え可能
(oneco-state 側の永続パスへ向けるため)。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

DEFAULT_DIGEST_LOG_PATH = Path("data/sns_digest_log.yaml")


class DigestLog:
    """日次まとめの投稿履歴を YAML で永続化する。

    date (YYYY-MM-DD 文字列) を主キーとし、同じ date の再記録は上書きする
    (= 「投稿済み」という事実だけが必要)。
    """

    def __init__(self, *, path: Path) -> None:
        self._path = path
        self._records: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = yaml.safe_load(self._path.read_text(encoding="utf-8"))
        except Exception as exc:  # YAML 破損は黙って空扱い (collection を止めない)
            logger.warning("DigestLog: failed to load %s (%s); treating as empty", self._path, exc)
            return
        if not isinstance(raw, dict):
            return
        posts = raw.get("posts")
        if not isinstance(posts, list):
            return
        for entry in posts:
            if not isinstance(entry, dict):
                continue
            entry_date = entry.get("date")
            if isinstance(entry_date, str) and entry_date:
                self._records[entry_date] = entry

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"posts": list(self._records.values())}
        self._path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False))

    def is_posted(self, date_str: str) -> bool:
        """指定日付 (YYYY-MM-DD) が投稿済みか。"""
        return date_str in self._records

    def record(
        self,
        *,
        date_str: str,
        post_id: str | None,
        posted_at: str,
    ) -> None:
        """投稿記録を残す。

        Args:
            date_str: 対象日付 (YYYY-MM-DD, JST)
            post_id: Threads の投稿 ID (dry_run 時は None)
            posted_at: 記録時刻 (ISO 8601 文字列)
        """
        if not date_str:
            raise ValueError("date_str must be non-empty")
        entry: dict[str, Any] = {
            "date": date_str,
            "post_id": post_id,
            "posted_at": posted_at,
        }
        self._records[date_str] = entry
        self._save()
