"""PostLog: 投稿履歴の YAML 永続化 TDD

重複投稿防止のため URL → 投稿時刻を永続化する。
SiteBaselineTracker と同じく YAML ファイル方式 (run 跨ぎで保持)。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from syndication_service.sns_publisher.post_log import (
    PostLog,
    identity_keys_from_fields,
    identity_of,
)


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


class TestIdentityPersistence:
    """identity の永続化と照合キー生成 (T058)"""

    def test_record_with_identity_roundtrips(self, tmp_path: Path):
        path = tmp_path / "posts.yaml"
        log = PostLog(path=path)
        log.record(
            url="https://example.jp/animals/1",
            platform="threads",
            text="t",
            dry_run=True,
            identity={
                "species": "猫",
                "sex": "女の子",
                "color": "三毛",
                "shelter_date": "2026-06-26",
                "image_path": "www.pref.yamanashi.jp/images/126663/33833no2.jpg",
            },
        )
        reloaded = PostLog(path=path)
        keys = reloaded.posted_identity_keys()
        assert "img:www.pref.yamanashi.jp/images/126663/33833no2.jpg" in keys
        # プロフィール (種別/性別/毛色/収容日) は記録のみで照合キーにしない
        # (shelter_date 日次上書きバグの影響下で本番22%が衝突するため)
        assert not any(k.startswith("prof:") for k in keys)

    def test_record_without_identity_is_backward_compatible(self, tmp_path: Path):
        path = tmp_path / "posts.yaml"
        log = PostLog(path=path)
        log.record(url="https://example.jp/animals/2", platform="threads", text="t", dry_run=True)
        reloaded = PostLog(path=path)
        assert reloaded.posted_identity_keys() == set()
        assert "https://example.jp/animals/2" in reloaded.posted_urls()

    def test_placeholder_image_yields_no_key(self, tmp_path: Path):
        path = tmp_path / "posts.yaml"
        log = PostLog(path=path)
        log.record(
            url="https://example.jp/animals/3",
            platform="threads",
            text="t",
            dry_run=True,
            identity={
                "species": "猫",
                "sex": "男の子",
                "color": "黒",
                "shelter_date": "2026-07-01",
                # placeholder 画像 → img キーは作らない
                "image_path": "www.pref.yamanashi.jp/images/noimage01.jpg",
            },
        )
        assert PostLog(path=path).posted_identity_keys() == set()


class TestIdentityHelpers:
    def test_identity_of_uses_host_and_path(self):
        from datetime import date

        from data_collector.domain.models import AnimalData

        animal = AnimalData(
            species="猫",
            sex="女の子",
            color="三毛",
            shelter_date=date(2026, 6, 26),
            location="山梨県",
            source_url="https://example.jp/animals/1",
            category="adoption",
            image_urls=["https://Example.jp/uploads/photo/33833no2.jpg?ver=2"],
        )
        identity = identity_of(animal)
        # クエリは落とし、ホスト+パスを小文字で保持
        assert identity["image_path"] == "example.jp/uploads/photo/33833no2.jpg"
        assert identity["shelter_date"] == "2026-06-26"
        keys = identity_keys_from_fields(identity)
        assert keys == {"img:example.jp/uploads/photo/33833no2.jpg"}

    def test_same_basename_different_path_do_not_collide(self):
        """沖縄型の回帰: 別個体が同名ファイル (large_image.jpg) を持っても
        パスが違えばキーは衝突しない (PR #281 reviewer Critical 対応)"""
        a = identity_keys_from_fields(
            {"image_path": "www.aniwel-pref.okinawa/files/animal/image/1111/large_image.jpg"}
        )
        b = identity_keys_from_fields(
            {"image_path": "www.aniwel-pref.okinawa/files/animal/image/2222/large_image.jpg"}
        )
        assert a and b
        assert a.isdisjoint(b)

    def test_yamanashi_renewal_same_image_url_matches(self):
        """山梨型の回帰: source_url 形式が変わっても画像フル URL は不変
        (実測: /images/126663/33833no2.jpg がリニューアル前後でバイト一致)"""
        before = identity_keys_from_fields(
            {"image_path": "www.pref.yamanashi.jp/images/126663/33833no2.jpg"}
        )
        after = identity_keys_from_fields(
            {"image_path": "www.pref.yamanashi.jp/images/126663/33833no2.jpg"}
        )
        assert before == after != set()
