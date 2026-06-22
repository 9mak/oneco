"""PostLog: 投稿履歴の YAML 永続化 TDD

重複投稿防止のため URL → 投稿時刻を永続化する。
SiteBaselineTracker と同じく YAML ファイル方式 (run 跨ぎで保持)。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from syndication_service.sns_publisher.post_log import PostLog


class TestPostLog:
    def test_empty_when_no_file(self, tmp_path: Path):
        log = PostLog(path=tmp_path / "sns_posts.yaml")
        assert log.posted_urls() == set()

    def test_record_and_recall(self, tmp_path: Path):
        log = PostLog(path=tmp_path / "sns_posts.yaml")
        log.record(
            url="https://example.jp/a/1",
            platform="threads",
            text="hi",
            dry_run=True,
        )
        assert log.posted_urls() == {"https://example.jp/a/1"}

    def test_persists_to_disk(self, tmp_path: Path):
        path = tmp_path / "sns_posts.yaml"
        a = PostLog(path=path)
        a.record(url="https://example.jp/a/1", platform="threads", text="hi", dry_run=True)
        b = PostLog(path=path)
        assert "https://example.jp/a/1" in b.posted_urls()

    def test_multiple_records(self, tmp_path: Path):
        log = PostLog(path=tmp_path / "sns_posts.yaml")
        log.record(url="https://example.jp/a/1", platform="threads", text="x", dry_run=True)
        log.record(url="https://example.jp/a/2", platform="threads", text="y", dry_run=False)
        assert log.posted_urls() == {"https://example.jp/a/1", "https://example.jp/a/2"}

    def test_dedup_same_url(self, tmp_path: Path):
        """同じ URL の再記録は最新で上書き、posted_urls の数は変わらない"""
        log = PostLog(path=tmp_path / "sns_posts.yaml")
        log.record(url="https://example.jp/a/1", platform="threads", text="old", dry_run=True)
        log.record(url="https://example.jp/a/1", platform="threads", text="new", dry_run=False)
        assert log.posted_urls() == {"https://example.jp/a/1"}

    def test_corrupt_yaml_treated_as_empty(self, tmp_path: Path):
        """壊れた YAML は黙って空扱い (collection を止めない)"""
        path = tmp_path / "sns_posts.yaml"
        path.write_text("not a valid: yaml: [")
        log = PostLog(path=path)
        assert log.posted_urls() == set()

    def test_invalid_record_args_raises(self, tmp_path: Path):
        log = PostLog(path=tmp_path / "sns_posts.yaml")
        with pytest.raises(ValueError):
            log.record(url="", platform="threads", text="x", dry_run=True)
