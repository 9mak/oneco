"""ZaidanFukuokaDouaiAdapter のテスト

福岡県動物愛護協会サイト (zaidan-fukuoka-douai.or.jp) 用 rule-based
adapter の動作を検証する。

- 一覧ページの fixture (`zaidan_fukuoka_douai__dog.html`) からの URL 抽出
- 詳細ページ HTML (`<dl><dt>...</dt><dd>...</dd></dl>` の定義リスト) からの
  RawAnimalData 構築
- 8 サイトすべてが SiteAdapterRegistry に登録されていること
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.zaidan_fukuoka_douai import (
    ZaidanFukuokaDouaiAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig

# 詳細ページを模した最小 HTML (実サイトの構造想定)
# - 写真は `<figure>` 配下の `<img>` で `/files/download/Animals/...`
# - 各情報は `<dl><dt>label</dt><dd>value</dd></dl>` の定義リスト
DETAIL_HTML = """
<html><body>
<div class="main">
  <div class="inner">
    <div class="detail-wrap">
      <h2>収容犬詳細</h2>
      <figure class="detail-pht">
        <img src="/files/download/Animals/329e7da2-a4b5-4aad-896e-3a15acc1bfa0/image_01/main/l">
      </figure>
      <figure class="detail-pht">
        <img src="/files/download/Animals/329e7da2-a4b5-4aad-896e-3a15acc1bfa0/image_02/sub/l">
      </figure>
      <div class="animals-data">
        <dl><dt>個体管理ナンバー</dt><dd>D2137</dd></dl>
        <dl><dt>収容日</dt><dd>2026年5月14日</dd></dl>
        <dl><dt>品種</dt><dd>雑種</dd></dl>
        <dl><dt>性別</dt><dd>オス</dd></dl>
        <dl><dt>年齢</dt><dd>推定3歳</dd></dl>
        <dl><dt>毛色</dt><dd>茶白</dd></dl>
        <dl><dt>大きさ</dt><dd>中型</dd></dl>
        <dl><dt>収容先</dt><dd>京築保健福祉環境事務所</dd></dl>
        <dl><dt>連絡先</dt><dd>0930-23-2380</dd></dl>
      </div>
    </div>
  </div>
</div>
</body></html>
"""


def _site_protections_dog() -> SiteConfig:
    """保健所収容犬 (一覧 fixture と一致)"""
    return SiteConfig(
        name="福岡県動物愛護協会（保健所収容犬）",
        prefecture="福岡県",
        prefecture_code="40",
        list_url="https://www.zaidan-fukuoka-douai.or.jp/animals/protections/dog",
        category="sheltered",
    )


def _site_centers_dog() -> SiteConfig:
    """センター譲渡犬"""
    return SiteConfig(
        name="福岡県動物愛護協会（センター譲渡犬）",
        prefecture="福岡県",
        prefecture_code="40",
        list_url="https://www.zaidan-fukuoka-douai.or.jp/animals/centers/dog",
        category="adoption",
    )


class TestZaidanFukuokaDouaiAdapterListExtraction:
    """list ページからの detail URL 抽出"""

    def test_fetch_animal_list_extracts_detail_urls_from_fixture(
        self, fixture_html
    ):
        """一覧ページから 1 件以上の詳細 URL が抽出できる"""
        html = fixture_html("zaidan_fukuoka_douai__dog")
        adapter = ZaidanFukuokaDouaiAdapter(_site_protections_dog())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert len(result) >= 1
        urls = [u for u, _cat in result]
        # フィクスチャに含まれる既知の詳細 URL (uuid 形式)
        assert any(
            "/animals/protection-detail/329e7da2-a4b5-4aad-896e-3a15acc1bfa0"
            in u
            for u in urls
        )
        # 全 URL が `-detail/` を含む詳細ページである
        for u in urls:
            assert "-detail/" in u
        # ヘッダ/フッタの一覧遷移リンクは混入しない
        for u in urls:
            assert not u.endswith("/animals/protections/dog")
            assert not u.endswith("/animals/protections/cat")
        # category は site_config 由来
        assert all(cat == "sheltered" for _u, cat in result)
        # 全 URL が絶対 URL になっている
        assert all(u.startswith("http") for u in urls)


class TestZaidanFukuokaDouaiAdapterDetailExtraction:
    """detail ページからの RawAnimalData 構築"""

    def test_extract_animal_details_returns_raw_data(self, assert_raw_animal):
        adapter = ZaidanFukuokaDouaiAdapter(_site_protections_dog())
        with patch.object(adapter, "_http_get", return_value=DETAIL_HTML):
            raw = adapter.extract_animal_details(
                "https://www.zaidan-fukuoka-douai.or.jp/animals/protection-detail/329e7da2-a4b5-4aad-896e-3a15acc1bfa0",
                category="sheltered",
            )
        assert isinstance(raw, RawAnimalData)
        assert_raw_animal(
            raw,
            species="雑種",
            sex="オス",
            age="推定3歳",
            color="茶白",
            size="中型",
            shelter_date="2026年5月14日",
            location="京築保健福祉環境事務所",
            # 連絡先 "0930-23-2380" がそのまま正規化される
            phone="0930-23-2380",
            category="sheltered",
        )
        # `<figure>` 配下の動物写真 2 枚が拾えている
        assert len(raw.image_urls) == 2
        assert all(
            "/files/download/Animals/" in u for u in raw.image_urls
        )
        # 相対 URL が絶対 URL に変換されている
        assert all(
            u.startswith("https://www.zaidan-fukuoka-douai.or.jp/")
            for u in raw.image_urls
        )

    def test_extract_raises_on_empty_html(self):
        """定義リストが見当たらない HTML では例外を出す"""
        adapter = ZaidanFukuokaDouaiAdapter(_site_protections_dog())
        with patch.object(
            adapter, "_http_get", return_value="<html><body></body></html>"
        ):
            with pytest.raises(Exception):
                adapter.extract_animal_details(
                    "https://www.zaidan-fukuoka-douai.or.jp/animals/protection-detail/zzz"
                )


class TestZaidanFukuokaDouaiAdapterRegistry:
    """registry に 8 サイトすべて登録されていること"""

    EXPECTED_SITE_NAMES = (
        "福岡県動物愛護協会（保健所収容犬）",
        "福岡県動物愛護協会（保健所収容猫）",
        "福岡県動物愛護協会（一般保護犬）",
        "福岡県動物愛護協会（一般保護猫）",
        "福岡県動物愛護協会（センター譲渡犬）",
        "福岡県動物愛護協会（センター譲渡猫）",
        "福岡県動物愛護協会（団体譲渡犬）",
        "福岡県動物愛護協会（団体譲渡猫）",
    )

    @pytest.mark.parametrize("site_name", EXPECTED_SITE_NAMES)
    def test_site_registered_to_zaidan_fukuoka_douai_adapter(self, site_name):
        # 他テストが registry を clear する場合の冪等性のため、
        # 未登録なら再登録してから確認する。
        if SiteAdapterRegistry.get(site_name) is None:
            SiteAdapterRegistry.register(site_name, ZaidanFukuokaDouaiAdapter)
        cls = SiteAdapterRegistry.get(site_name)
        assert cls is ZaidanFukuokaDouaiAdapter, (
            f"{site_name} が ZaidanFukuokaDouaiAdapter に紐付いていません: {cls}"
        )


class TestZaidanFukuokaDouaiAdapterCenterCategory:
    """センター譲渡 (`/animals/centers/`) ルートも list 抽出が動くこと"""

    def test_center_detail_link_pattern_matches(self):
        """`/animals/center-detail/{uuid}` 形式の詳細リンクも拾える"""
        # 4 系統 (protection / personal-hogo / center / group) は
        # 接頭辞のみ違うため、`-detail/` を含む `<a>` を一括で拾えるはず。
        html = """
        <html><body>
          <div class="main">
            <div class="inner">
              <div class="thumb-list animals-list">
                <ul>
                  <li>
                    <a href="/animals/center-detail/abc-123">
                      <figure class="list-pht"><img src="/files/download/Animals/abc-123/image_01/title/m"></figure>
                    </a>
                  </li>
                </ul>
              </div>
            </div>
          </div>
        </body></html>
        """
        adapter = ZaidanFukuokaDouaiAdapter(_site_centers_dog())
        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()
        urls = [u for u, _cat in result]
        assert (
            "https://www.zaidan-fukuoka-douai.or.jp/animals/center-detail/abc-123"
            in urls
        )
        assert all(cat == "adoption" for _u, cat in result)
