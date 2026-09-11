"""DigestLog: 日次まとめ投稿ログの YAML 永続化 TDD (T160)

同一日付の二重投稿防止のため date -> post_id を永続化する。
"""

from __future__ import annotations

from pathlib import Path

from syndication_service.sns_publisher.post_log import DigestLog


class TestDigestLog:
    def test_not_posted_when_no_file(self, tmp_path: Path):
        log = DigestLog(path=tmp_path / "sns_digest_log.yaml")
        assert log.is_posted("2026-09-10") is False

    def test_record_and_recall(self, tmp_path: Path):
        log = DigestLog(path=tmp_path / "sns_digest_log.yaml")
        log.record(date_str="2026-09-10", post_id="123", posted_at="2026-09-11T00:00:00+00:00")
        assert log.is_posted("2026-09-10") is True
        assert log.is_posted("2026-09-11") is False

    def test_persists_to_disk(self, tmp_path: Path):
        path = tmp_path / "sns_digest_log.yaml"
        a = DigestLog(path=path)
        a.record(date_str="2026-09-10", post_id="123", posted_at="2026-09-11T00:00:00+00:00")
        b = DigestLog(path=path)
        assert b.is_posted("2026-09-10") is True

    def test_multiple_dates(self, tmp_path: Path):
        log = DigestLog(path=tmp_path / "sns_digest_log.yaml")
        log.record(date_str="2026-09-10", post_id="1", posted_at="2026-09-11T00:00:00+00:00")
        log.record(date_str="2026-09-11", post_id="2", posted_at="2026-09-12T00:00:00+00:00")
        assert log.is_posted("2026-09-10") is True
        assert log.is_posted("2026-09-11") is True

    def test_dedup_same_date_overwrites(self, tmp_path: Path):
        """同じ date の再記録は最新で上書きする (件数は増えない)"""
        path = tmp_path / "sns_digest_log.yaml"
        log = DigestLog(path=path)
        log.record(date_str="2026-09-10", post_id="old", posted_at="2026-09-11T00:00:00+00:00")
        log.record(date_str="2026-09-10", post_id="new", posted_at="2026-09-11T01:00:00+00:00")

        import yaml

        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert len(raw["posts"]) == 1
        assert raw["posts"][0]["post_id"] == "new"

    def test_corrupt_yaml_treated_as_empty(self, tmp_path: Path):
        """壊れた YAML は黙って空扱い (collection を止めない)"""
        path = tmp_path / "sns_digest_log.yaml"
        path.write_text("not a valid: yaml: [")
        log = DigestLog(path=path)
        assert log.is_posted("2026-09-10") is False

    def test_record_requires_date(self, tmp_path: Path):
        import pytest

        log = DigestLog(path=tmp_path / "sns_digest_log.yaml")
        with pytest.raises(ValueError):
            log.record(date_str="", post_id="1", posted_at="2026-09-11T00:00:00+00:00")

    def test_record_dry_run_post_id_none(self, tmp_path: Path):
        """dry_run 時は post_id=None を記録できる (ただし publisher は dry_run で record しない契約)"""
        log = DigestLog(path=tmp_path / "sns_digest_log.yaml")
        log.record(date_str="2026-09-10", post_id=None, posted_at="2026-09-11T00:00:00+00:00")
        assert log.is_posted("2026-09-10") is True
