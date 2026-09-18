"""アニウェル北海道（猫の里親募集） aniwel.jp のテスト

2026-09 のサイトリニューアル (WordPress → baserCMS) で旧一覧 `/cats/` が 404 になり、
9/2 以降の収集が止まったまま古い 10 頭が公開され続けていた (T417)。新サイトは
一覧 `/afa/` (ページ送りあり) → 個別ページ `/afa/view/<名前>` の構成なので、
spec 駆動の GenericAdapter (config/site_specs/aniwel.yaml) で読む。

フィクスチャは 2026-09-17 に実サイトから取得した HTML。
"""

from __future__ import annotations

import re
from datetime import date
from unittest.mock import patch

from data_collector.adapters.rule_based import sites  # noqa: F401  registry 登録用
from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.domain.normalizer import DataNormalizer
from data_collector.llm.config import SiteConfig, SiteConfigLoader

_SITE_NAME = "アニウェル北海道（猫の里親募集）"
_LIST_URL = "https://aniwel.jp/afa/"

# import 時点 (コレクション時) で取っておく。test_registry.py などが実行時に registry を clear するため
AniwelAdapter = SiteAdapterRegistry.get(_SITE_NAME)


def _site() -> SiteConfig:
    return SiteConfig(
        name=_SITE_NAME,
        prefecture="北海道",
        prefecture_code="01",
        list_url=_LIST_URL,
        category="adoption",
        phone="0157-57-3612",
    )


def _pages(fixture_html) -> dict[str, str]:
    return {
        _LIST_URL: fixture_html("aniwel_afa__page1"),
        "https://aniwel.jp/afa/index?page=2": fixture_html("aniwel_afa__page2"),
        "https://aniwel.jp/afa/index?page=3": fixture_html("aniwel_afa__page3"),
    }


class TestAniwelList:
    def test_follows_pagination_and_returns_detail_pages(self, fixture_html):
        adapter = AniwelAdapter(_site())
        pages = _pages(fixture_html)

        with patch.object(adapter, "_http_get", side_effect=pages.__getitem__):
            result = adapter.fetch_animal_list()

        slugs = ["momo", "shiro", "satsuki", "tom", "luck", "nazuna", "tama", "shinkuro"]
        slugs += ["magari", "sasuke"]
        assert result == [(f"https://aniwel.jp/afa/view/{s}", "adoption") for s in slugs]
        assert adapter.list_truncated is False

    def test_page_without_cards_is_empty_not_error(self, fixture_html):
        """募集中の子がいない月も正常な 0 件として扱う (prune の安全弁は 0 件では働かない)"""
        adapter = AniwelAdapter(_site())
        empty = fixture_html("aniwel_afa__page3").replace("list-parts inview", "gone")

        with patch.object(adapter, "_http_get", return_value=empty):
            assert adapter.fetch_animal_list() == []


class TestAniwelDetail:
    def test_extracts_fields_and_normalizes(self, fixture_html):
        adapter = AniwelAdapter(_site())
        url = "https://aniwel.jp/afa/view/momo"

        with patch.object(adapter, "_http_get", return_value=fixture_html("aniwel_afa__view_momo")):
            raw = adapter.extract_animal_details(url, "adoption")

        assert raw.species == "猫"
        assert raw.name == "もも"
        assert raw.sex == "メス"
        assert raw.age == "2021-9-3"
        assert raw.location == "アニウェル北海道（北見市）"
        assert raw.description.startswith("しろちゃんのお母さんです。")
        assert raw.source_url == url
        assert raw.image_urls == [
            "https://aniwel.jp/files/bc_custom_content/3/custom_entries/2026/09/00000013_photo_thumb.jpg",
            "https://aniwel.jp/design/images/afa_photo/momo01.jpg",
            "https://aniwel.jp/design/images/afa_photo/momo02.jpg",
            "https://aniwel.jp/design/images/afa_photo/momo03.jpg",
            "https://aniwel.jp/design/images/afa_photo/momo04.jpg",
            "https://aniwel.jp/design/images/afa_photo/momo5.jpg",
        ]

        with patch.object(DataNormalizer, "_today", staticmethod(lambda: date(2026, 9, 17))):
            animal = adapter.normalize(raw)

        assert animal.species == "猫"
        # スライド写真は /design/ 配下のため全サイト共通のジャンク画像判定で落ち、アイキャッチだけが残る
        assert [str(u) for u in animal.image_urls] == [raw.image_urls[0]]
        assert animal.sex == "女の子"
        assert animal.age_months == 60
        assert animal.name == "もも"
        assert animal.phone == "0157-57-3612"
        assert animal.location == "アニウェル北海道（北見市）"
        assert str(animal.source_url) == url

    def test_image_urls_do_not_change_with_cache_busting_query(self, fixture_html):
        """アイキャッチ画像には取得ごとに変わる数字のクエリが付く。付いたままだと毎日画像が変わったことになる"""
        adapter = AniwelAdapter(_site())
        html = fixture_html("aniwel_afa__view_momo")
        other_query = re.sub(r"photo_thumb\.jpg\?\d+", "photo_thumb.jpg?7", html)
        assert other_query != html

        urls = []
        for page in (html, other_query):
            with patch.object(adapter, "_http_get", return_value=page):
                urls.append(
                    adapter.extract_animal_details("https://aniwel.jp/afa/view/momo").image_urls
                )

        assert urls[0] == urls[1]

    def test_age_takes_first_birth_date_when_two_are_entered(self, fixture_html):
        """シンクロは年齢欄に生年月日が 2 つ入っている (span 要素)。先頭を採る"""
        adapter = AniwelAdapter(_site())

        with patch.object(
            adapter, "_http_get", return_value=fixture_html("aniwel_afa__view_shinkuro")
        ):
            raw = adapter.extract_animal_details("https://aniwel.jp/afa/view/shinkuro")

        assert raw.age == "2016-12-1"
        assert raw.sex == "オス"
        assert raw.name == "シンクロ"


class TestAniwelSiteConfig:
    def test_sites_yaml_points_at_renewed_list_with_contact_phone(self):
        """一覧はリニューアル後の /afa/。電話はサイト下部の「TEL：0157-57-3612(10:00～16:00)」"""
        from pathlib import Path

        sites_yaml = Path(__file__).resolve().parents[4] / "src/data_collector/config/sites.yaml"
        site = next(s for s in SiteConfigLoader.load(sites_yaml).sites if s.name == _SITE_NAME)

        assert site.list_url == _LIST_URL
        assert site.phone == "0157-57-3612"
        assert site.single_page is False

    def test_registered_from_spec_not_bespoke_module(self):
        import importlib.util

        assert AniwelAdapter is not None
        # GenericAdapter が type() で生成するクラスは Generic<サイト名>Adapter という名前になる
        assert AniwelAdapter.__name__.startswith("Generic")
        # 同名の個別 adapter が残っていると registry では個別側が勝ち、spec が使われない
        assert importlib.util.find_spec("data_collector.adapters.rule_based.sites.aniwel") is None
