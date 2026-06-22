"""SNS 投稿履歴の YAML 永続化

design.md 5.2 step 5: 投稿結果 (動物 ID, 投稿時刻, プラットフォーム, URL, 成否) を記録。
重複投稿防止のため candidate_selector が posted_urls を参照する。

ストレージは YAML ファイル (SiteBaselineTracker と同じ思想)。DB スキーマ変更を
避けてリリース速度を確保する。本格運用で件数が増えたら DB テーブルに移行。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


class PostLog:
    """投稿履歴を YAML で永続化する。

    URL を主キーとし、再記録は上書き (= 重複投稿防止のための観点では「投稿済み」
    という事実だけが必要)。
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
            logger.warning("PostLog: failed to load %s (%s); treating as empty", self._path, exc)
            return
        if not isinstance(raw, dict):
            return
        posts = raw.get("posts")
        if not isinstance(posts, list):
            return
        for entry in posts:
            if not isinstance(entry, dict):
                continue
            url = entry.get("url")
            if isinstance(url, str) and url:
                self._records[url] = entry

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"posts": list(self._records.values())}
        self._path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False))

    def posted_urls(self) -> set[str]:
        return set(self._records.keys())

    def record(
        self,
        *,
        url: str,
        platform: str,
        text: str,
        dry_run: bool,
    ) -> None:
        if not url:
            raise ValueError("url must be non-empty")
        if not platform:
            raise ValueError("platform must be non-empty")
        self._records[url] = {
            "url": url,
            "platform": platform,
            "text": text,
            "dry_run": dry_run,
        }
        self._save()
