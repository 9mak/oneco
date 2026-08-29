"""image_url_audit.py のテスト (T102)

HTTP 取得を除く純粋ロジック (URL 正規化・ローテーション対象判定・
ページ内画像抽出・突き合わせ・リンク切れ判定・レポート集計) を検証する。
実 HTTP fetch を伴う関数 (fetch_page / check_image_url / main) は
full_publication_audit.py / site_count_audit.py と同じ方針でユニットテスト対象外
とし、ローカル dry-run で動作確認する。
"""

from __future__ import annotations

import sys
from pathlib import Path

from bs4 import BeautifulSoup

# scripts/ をパスに通して image_url_audit を import (test_publication_audit.py と同パターン)
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import image_url_audit as iua  # noqa: E402


class TestNormalizeImageUrl:
    def test_strips_query_string(self):
        assert iua.normalize_image_url("https://a.jp/x.jpg?ver=2") == "https://a.jp/x.jpg"

    def test_strips_fragment(self):
        assert iua.normalize_image_url("https://a.jp/x.jpg#foo") == "https://a.jp/x.jpg"

    def test_no_change_when_clean(self):
        assert iua.normalize_image_url("https://a.jp/x.jpg") == "https://a.jp/x.jpg"

    def test_lowercases_host_only(self):
        # ホスト名は大文字小文字を区別しないが、パスは区別する (一般的な URL 仕様)
        assert iua.normalize_image_url("https://A.JP/X.jpg") == "https://a.jp/X.jpg"

    def test_raw_and_percent_encoded_japanese_filename_match(self):
        """大分県サイトの実例 (2026-08-29 dry-run で発覚): HTML の生の日本語ファイル名
        (タマ①.jpg) と API 格納値の percent-encoded 表記が同一画像を指すのに
        文字列比較では不一致になっていた偽陽性を防ぐ回帰テスト。"""
        raw = "https://oita-aigo.com/wp/wp-content/uploads/2026/08/タマ①.jpg"
        encoded = (
            "https://oita-aigo.com/wp/wp-content/uploads/2026/08/%E3%82%BF%E3%83%9E%E2%91%A0.jpg"
        )
        assert iua.normalize_image_url(raw) == iua.normalize_image_url(encoded)


class TestShardSelection:
    def test_shard_for_today_is_deterministic(self):
        import datetime

        d = datetime.date(2026, 8, 29)
        assert iua.shard_for_today(7, today=d) == iua.shard_for_today(7, today=d)

    def test_shard_for_today_cycles_within_range(self):
        import datetime

        for offset in range(14):
            d = datetime.date(2026, 8, 29) + datetime.timedelta(days=offset)
            shard = iua.shard_for_today(7, today=d)
            assert 0 <= shard < 7

    def test_consecutive_days_cover_all_shards_once_per_cycle(self):
        import datetime

        base = datetime.date(2026, 8, 29)
        shards = {iua.shard_for_today(7, today=base + datetime.timedelta(days=i)) for i in range(7)}
        assert shards == set(range(7))

    def test_in_shard_matches_modulo(self):
        assert iua.in_shard(animal_id=14, shard=0, total_shards=7) is True
        assert iua.in_shard(animal_id=15, shard=0, total_shards=7) is False
        assert iua.in_shard(animal_id=15, shard=1, total_shards=7) is True

    def test_in_shard_single_shard_covers_all(self):
        assert iua.in_shard(animal_id=123, shard=0, total_shards=1) is True


class TestExtractPageImageUrls:
    def test_extracts_img_src_absolute(self):
        html = '<html><body><img src="/images/a.jpg"></body></html>'
        soup = BeautifulSoup(html, "html.parser")
        urls = iua.extract_page_image_urls(soup, "https://a.jp/detail/1")
        assert "https://a.jp/images/a.jpg" in urls

    def test_extracts_anchor_href_to_image(self):
        html = '<html><body><a href="/full/a.jpg">拡大</a></body></html>'
        soup = BeautifulSoup(html, "html.parser")
        urls = iua.extract_page_image_urls(soup, "https://a.jp/detail/1")
        assert "https://a.jp/full/a.jpg" in urls

    def test_ignores_data_uri(self):
        html = '<html><body><img src="data:image/png;base64,AAA"></body></html>'
        soup = BeautifulSoup(html, "html.parser")
        urls = iua.extract_page_image_urls(soup, "https://a.jp/detail/1")
        assert not any(u.startswith("data:") for u in urls)

    def test_ignores_non_image_anchor(self):
        html = '<html><body><a href="/detail/2">次の子</a></body></html>'
        soup = BeautifulSoup(html, "html.parser")
        urls = iua.extract_page_image_urls(soup, "https://a.jp/detail/1")
        assert "https://a.jp/detail/2" not in urls


class TestImageFoundOnPage:
    def test_found_exact_match(self):
        page_images = {"https://a.jp/x.jpg"}
        assert iua.image_found_on_page("https://a.jp/x.jpg", page_images) is True

    def test_found_ignoring_query_string(self):
        page_images = {"https://a.jp/x.jpg?ver=3"}
        assert iua.image_found_on_page("https://a.jp/x.jpg", page_images) is True

    def test_not_found(self):
        page_images = {"https://a.jp/other.jpg"}
        assert iua.image_found_on_page("https://a.jp/x.jpg", page_images) is False


class TestClassifyImageStatus:
    def test_200_ok(self):
        assert iua.classify_image_status(200, "image/jpeg") == "ok"

    def test_404_is_broken(self):
        assert iua.classify_image_status(404, "text/html") == "broken"

    def test_410_is_broken(self):
        assert iua.classify_image_status(410, None) == "broken"

    def test_500_is_transient_error_not_broken(self):
        assert iua.classify_image_status(500, None) == "error"

    def test_none_status_is_error(self):
        assert iua.classify_image_status(None, None) == "error"

    def test_200_non_image_content_type_is_ok_by_status(self):
        # content-type の厳密判定は誤検知しやすいため status のみで判定する
        assert iua.classify_image_status(200, "text/html") == "ok"


class TestAuditAnimalImages:
    def _animal(self, **overrides):
        base = {
            "id": 1,
            "source_url": "https://a.jp/detail/1",
            "image_urls": ["https://a.jp/images/a.jpg"],
        }
        base.update(overrides)
        return base

    def test_all_images_found_no_flags(self):
        animal = self._animal()
        page_images = {"https://a.jp/images/a.jpg"}
        image_statuses = {"https://a.jp/images/a.jpg": "ok"}
        result = iua.audit_animal_images(
            animal, page_status="ok", page_images=page_images, image_statuses=image_statuses
        )
        assert result["flags"] == []

    def test_image_not_found_flag(self):
        animal = self._animal()
        page_images = {"https://a.jp/images/other.jpg"}
        image_statuses = {"https://a.jp/images/a.jpg": "ok"}
        result = iua.audit_animal_images(
            animal, page_status="ok", page_images=page_images, image_statuses=image_statuses
        )
        assert "image_not_found_on_page" in result["flags"]

    def test_page_fetch_error_flag_when_page_not_ok(self):
        animal = self._animal()
        image_statuses = {"https://a.jp/images/a.jpg": "ok"}
        result = iua.audit_animal_images(
            animal, page_status="error", page_images=None, image_statuses=image_statuses
        )
        assert result["flags"] == ["page_fetch_error"]

    def test_broken_link_flag(self):
        animal = self._animal()
        page_images = {"https://a.jp/images/a.jpg"}
        image_statuses = {"https://a.jp/images/a.jpg": "broken"}
        result = iua.audit_animal_images(
            animal, page_status="ok", page_images=page_images, image_statuses=image_statuses
        )
        assert "image_broken_link" in result["flags"]

    def test_image_fetch_error_flag(self):
        animal = self._animal()
        page_images = {"https://a.jp/images/a.jpg"}
        image_statuses = {"https://a.jp/images/a.jpg": "error"}
        result = iua.audit_animal_images(
            animal, page_status="ok", page_images=page_images, image_statuses=image_statuses
        )
        assert "image_fetch_error" in result["flags"]

    def test_multiple_flags_combine(self):
        animal = self._animal(image_urls=["https://a.jp/images/a.jpg", "https://a.jp/b.jpg"])
        page_images = {"https://a.jp/images/a.jpg"}
        image_statuses = {
            "https://a.jp/images/a.jpg": "ok",
            "https://a.jp/b.jpg": "broken",
        }
        result = iua.audit_animal_images(
            animal, page_status="ok", page_images=page_images, image_statuses=image_statuses
        )
        assert "image_not_found_on_page" in result["flags"]
        assert "image_broken_link" in result["flags"]


class TestPageUrlCacheKey:
    def test_strips_fragment_for_cache_key(self):
        assert iua.page_cache_key("https://a.jp/list.html#row=3") == "https://a.jp/list.html"

    def test_no_fragment_unchanged(self):
        assert iua.page_cache_key("https://a.jp/detail/1") == "https://a.jp/detail/1"
