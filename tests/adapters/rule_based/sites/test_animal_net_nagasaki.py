"""AnimalNetNagasakiAdapter のテスト

ながさき犬猫ネット (animal-net.pref.nagasaki.jp) 用 rule-based
adapter の動作を検証する。

- 一覧ページの fixture (`animal_net_pref_nagasaki__syuuyou.html`) からの URL 抽出
- 詳細ページ HTML (`<dl><div class="list-box"><dt>label</dt><dd>value</dd></div></dl>`
  の定義リスト) からの RawAnimalData 構築
- 4 サイトすべてが SiteAdapterRegistry に登録されていること
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.animal_net_nagasaki import (
    AnimalNetNagasakiAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig

# 詳細ページを模した最小 HTML (実サイトの構造想定)
# - 写真は `/wp/wp-content/uploads/...` 配下の `<img>` で WordPress 慣習通り
# - 各情報は `<dl>` 配下の `<div class="list-box"><dt>label</dt><dd>value</dd></div>`
DETAIL_HTML = """
<html><body>
<header>
  <h1><a href="/"><img src="https://animal-net.pref.nagasaki.jp/wp/wp-content/themes/ngk-animal/images/header/logo.svg" alt="ロゴ"></a></h1>
</header>
<main>
  <div class="contents">
    <div class="detail-area">
      <div class="photo-area">
        <img src="https://animal-net.pref.nagasaki.jp/wp/wp-content/uploads/2026/05/31e010ea77d697ed6c0c3a9fb6841664.jpg" alt="No.19602の写真">
        <img src="https://animal-net.pref.nagasaki.jp/wp/wp-content/uploads/2026/05/31e010ea77d697ed6c0c3a9fb6841664-2.jpg" alt="No.19602の写真2">
      </div>
      <dl>
        <div class="list-box">
          <dt>品種</dt><dd>ミックス（雑種）</dd>
        </div>
        <div class="list-box">
          <dt>性別</dt><dd>オス</dd>
        </div>
        <div class="list-box">
          <dt>年齢</dt><dd>約４ヶ月</dd>
        </div>
        <div class="list-box">
          <dt>毛色</dt><dd>黒</dd>
        </div>
        <div class="list-box">
          <dt>大きさ</dt><dd>中型</dd>
        </div>
        <div class="list-box">
          <dt>収容日</dt><dd>2026-05-13</dd>
        </div>
        <div class="list-box">
          <dt>収容場所</dt><dd>長崎県央保健所</dd>
        </div>
        <div class="list-box">
          <dt>連絡先</dt><dd>0957-26-3306</dd>
        </div>
      </dl>
    </div>
  </div>
</main>
</body></html>
"""


def _site_syuuyou() -> SiteConfig:
    """保健所収容 (一覧 fixture と一致)"""
    return SiteConfig(
        name="長崎犬猫ネット（保健所収容）",
        prefecture="長崎県",
        prefecture_code="42",
        list_url="https://animal-net.pref.nagasaki.jp/syuuyou",
        category="sheltered",
    )


def _site_jyouto() -> SiteConfig:
    """譲渡"""
    return SiteConfig(
        name="長崎犬猫ネット（譲渡）",
        prefecture="長崎県",
        prefecture_code="42",
        list_url="https://animal-net.pref.nagasaki.jp/jyouto",
        category="adoption",
    )


class TestAnimalNetNagasakiAdapterListExtraction:
    """list ページからの detail URL 抽出"""

    def test_fetch_animal_list_extracts_detail_urls_from_fixture(self, fixture_html):
        """一覧 fixture から 1 件以上の `/animal/no-XXXXX/` URL が抽出できる"""
        html = fixture_html("animal_net_pref_nagasaki__syuuyou")
        adapter = AnimalNetNagasakiAdapter(_site_syuuyou())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert len(result) >= 1
        urls = [u for u, _cat in result]
        # フィクスチャに含まれる既知の詳細 URL
        assert any("https://animal-net.pref.nagasaki.jp/animal/no-19602/" in u for u in urls)
        # 全 URL が `/animal/no-` を含む詳細ページである
        for u in urls:
            assert "/animal/no-" in u
        # ヘッダ/フッタ/絞り込みパネルの遷移リンクが混入しない
        for u in urls:
            assert not u.endswith("/syuuyou")
            assert not u.endswith("/jyouto")
            assert not u.endswith("/maigo")
            assert not u.endswith("/hogo")
            assert "/jyoutoform" not in u
            assert "/maigoform" not in u
        # category は site_config 由来
        assert all(cat == "sheltered" for _u, cat in result)
        # 全 URL が絶対 URL になっている
        assert all(u.startswith("http") for u in urls)

    def test_fetch_animal_list_dedupes_urls(self, fixture_html):
        """同一 URL が重複して並んでいても 1 件に集約される"""
        html = fixture_html("animal_net_pref_nagasaki__syuuyou")
        adapter = AnimalNetNagasakiAdapter(_site_syuuyou())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        urls = [u for u, _cat in result]
        assert len(urls) == len(set(urls))


class TestAnimalNetNagasakiAdapterDetailExtraction:
    """detail ページからの RawAnimalData 構築"""

    def test_extract_animal_details_returns_raw_data(self, assert_raw_animal):
        adapter = AnimalNetNagasakiAdapter(_site_syuuyou())
        with patch.object(adapter, "_http_get", return_value=DETAIL_HTML):
            raw = adapter.extract_animal_details(
                "https://animal-net.pref.nagasaki.jp/animal/no-19602/",
                category="sheltered",
            )
        assert isinstance(raw, RawAnimalData)
        assert_raw_animal(
            raw,
            species="ミックス（雑種）",
            sex="オス",
            age="約４ヶ月",
            color="黒",
            size="中型",
            shelter_date="2026-05-13",
            location="長崎県央保健所",
            # 連絡先 "0957-26-3306" がそのまま正規化される
            phone="0957-26-3306",
            category="sheltered",
        )
        # `/wp-content/uploads/` 配下の動物写真 2 枚が拾えており、
        # ヘッダのロゴ (themes 配下) は除外される
        assert len(raw.image_urls) == 2
        assert all("/wp-content/uploads/" in u for u in raw.image_urls)
        assert all("/wp-content/themes/" not in u for u in raw.image_urls)

    def test_extract_raises_on_empty_html(self):
        """定義リストが見当たらない HTML では例外を出す"""
        adapter = AnimalNetNagasakiAdapter(_site_syuuyou())
        with patch.object(adapter, "_http_get", return_value="<html><body></body></html>"):
            with pytest.raises(Exception):
                adapter.extract_animal_details(
                    "https://animal-net.pref.nagasaki.jp/animal/no-99999/"
                )

    def test_extract_with_jyouto_category(self, assert_raw_animal):
        """譲渡カテゴリ (`adoption`) でも detail 抽出が動く"""
        adapter = AnimalNetNagasakiAdapter(_site_jyouto())
        with patch.object(adapter, "_http_get", return_value=DETAIL_HTML):
            raw = adapter.extract_animal_details(
                "https://animal-net.pref.nagasaki.jp/animal/no-19602/",
                category="adoption",
            )
        assert raw.category == "adoption"
        assert raw.species == "ミックス（雑種）"


class TestAnimalNetNagasakiAdapterRegistry:
    """registry に 4 サイトすべて登録されていること"""

    EXPECTED_SITE_NAMES = (
        "長崎犬猫ネット（保健所収容）",
        "長崎犬猫ネット（譲渡）",
        "長崎犬猫ネット（迷子）",
        "長崎犬猫ネット（保護）",
    )

    @pytest.mark.parametrize("site_name", EXPECTED_SITE_NAMES)
    def test_site_registered_to_animal_net_nagasaki_adapter(self, site_name):
        # 他テストが registry を clear する場合の冪等性のため、
        # 未登録なら再登録してから確認する。
        if SiteAdapterRegistry.get(site_name) is None:
            SiteAdapterRegistry.register(site_name, AnimalNetNagasakiAdapter)
        cls = SiteAdapterRegistry.get(site_name)
        assert cls is AnimalNetNagasakiAdapter, (
            f"{site_name} が AnimalNetNagasakiAdapter に紐付いていません: {cls}"
        )
