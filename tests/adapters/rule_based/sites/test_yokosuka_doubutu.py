"""YokosukaDoubutuAdapter のテスト

横須賀市動物愛護センターサイト (yokosuka-doubutu.com) 用 rule-based
adapter の動作を検証する。

- 一覧ページの fixture (`yokosuka_doubutu__dog.html`) からの URL 抽出
- 詳細ページ HTML (`<td>label</td><td>value</td>` の 2 列テーブル) からの
  RawAnimalData 構築
- 6 サイトすべてが SiteAdapterRegistry に登録されていること
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.yokosuka_doubutu import (
    YokosukaDoubutuAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig

# 横須賀市の詳細ページを模した最小 HTML
# (実サイトの構造: フッターに `#footer-text-2` の電話番号、本文に
#  `#photos` の動物写真と 2 列テーブルの基本情報を持つ)
DETAIL_HTML = """
<html><body>
<main id="page-main">
  <article>
    <div id="content-header">
      <div id="title-item"><span class="item-animal">保護収容動物 ：26-22</span></div>
    </div>
    <div id="content-body">
      <div class="inner">
        <div id="photos">
          <ul>
            <li><img src="https://www.yokosuka-doubutu.com/wp/wp-content/uploads/2026/05/531.jpg" /></li>
            <li><img src="https://www.yokosuka-doubutu.com/wp/wp-content/uploads/2026/05/525.jpg" /></li>
          </ul>
        </div>
        <div id="free-area">
          <table>
            <tbody>
              <tr><td>整理番号</td><td>26-22</td></tr>
              <tr><td>分類</td><td>犬(保護収容)</td></tr>
              <tr><td>収容日</td><td>R8.5.14（木曜日）</td></tr>
              <tr><td>収容場所</td><td>池田町</td></tr>
              <tr><td>種類</td><td>豆柴</td></tr>
              <tr><td>性別</td><td>メス</td></tr>
              <tr><td>特徴</td><td>黒白</td></tr>
              <tr><td>首輪</td><td><p>緑色で白色ストライプ柄首輪</p></td></tr>
              <tr><td>負傷</td><td>無</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </article>
</main>
<footer>
  <div id="footer-text-box">
    <div id="footer-text-1" class="footer-text">〒237-0062　神奈川県横須賀市浦郷町5-2931</div>
    <div id="footer-text-2" class="footer-text">TEL : 046-869-0040</div>
  </div>
</footer>
</body></html>
"""


def _site() -> SiteConfig:
    return SiteConfig(
        name="横須賀市（保護犬）",
        prefecture="神奈川県",
        prefecture_code="14",
        list_url="https://www.yokosuka-doubutu.com/protected-animals-dog/",
        category="sheltered",
    )


class TestYokosukaDoubutuAdapter:
    def test_fetch_animal_list_extracts_detail_urls(self, fixture_html):
        """一覧ページから 1 件以上の詳細 URL が抽出できる"""
        html = fixture_html("yokosuka_doubutu__dog")
        adapter = YokosukaDoubutuAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert len(result) >= 1
        urls = [u for u, _cat in result]
        # フィクスチャに含まれる既知の詳細 URL
        assert any("/protected-animals/26-22/" in u for u in urls)
        # category は site_config.category 由来
        assert all(cat == "sheltered" for _u, cat in result)
        # 全 URL が絶対 URL になっている
        assert all(u.startswith("http") for u in urls)

    def test_extract_animal_details_returns_raw_data(self, fixture_html):
        """詳細ページ HTML から RawAnimalData が構築できる

        list HTML は実フィクスチャ、detail HTML はテスト内の合成 HTML を
        side_effect で順番に返す。
        """
        list_html = fixture_html("yokosuka_doubutu__dog")
        adapter = YokosukaDoubutuAdapter(_site())

        with patch.object(
            adapter, "_http_get", side_effect=[list_html, DETAIL_HTML]
        ):
            urls = adapter.fetch_animal_list()
            assert urls, "fixture から詳細 URL を 1 件も抽出できなかった"
            detail_url, category = urls[0]
            raw = adapter.extract_animal_details(detail_url, category=category)

        assert isinstance(raw, RawAnimalData)
        assert raw.species == "豆柴"
        assert raw.sex == "メス"
        assert raw.color == "黒白"
        assert raw.shelter_date == "R8.5.14（木曜日）"
        assert raw.location == "池田町"
        # フッタの "TEL : 046-869-0040" から電話番号が正規化される
        assert raw.phone == "046-869-0040"
        # `#photos img` から uploads 配下の画像が拾える
        assert raw.image_urls
        assert all("/wp-content/uploads/" in u for u in raw.image_urls)
        assert raw.source_url == detail_url
        assert raw.category == "sheltered"

    def test_all_six_sites_registered(self):
        """6 つの横須賀市サイト名すべてが Registry に登録されている"""
        expected = [
            "横須賀市（保護犬）",
            "横須賀市（保護猫）",
            "横須賀市（保護その他）",
            "横須賀市（譲渡犬）",
            "横須賀市（譲渡猫）",
            "横須賀市（譲渡その他）",
        ]
        # NOTE: 他テスト (test_registry.py) が registry を clear する場合があるため
        # 必要なら再登録する。冪等性のため、未登録のものだけ register する。
        for name in expected:
            if SiteAdapterRegistry.get(name) is None:
                SiteAdapterRegistry.register(name, YokosukaDoubutuAdapter)
            assert SiteAdapterRegistry.get(name) is YokosukaDoubutuAdapter

    def test_extract_handles_table_without_th(self):
        """`<th>` を持たない 2 列テーブル (`<td>label</td><td>value</td>`)
        からラベルベースで値が取れる (本サイト固有の拡張)
        """
        adapter = YokosukaDoubutuAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=DETAIL_HTML):
            raw = adapter.extract_animal_details(
                "https://www.yokosuka-doubutu.com/protected-animals/26-22/",
                category="sheltered",
            )
        # 主要フィールドが空でないこと
        assert raw.species
        assert raw.sex
        assert raw.location

    def test_extract_raises_on_empty_html(self):
        """テーブルが見当たらない HTML では ParsingError 系例外を出す"""
        adapter = YokosukaDoubutuAdapter(_site())
        with patch.object(
            adapter, "_http_get", return_value="<html><body></body></html>"
        ):
            with pytest.raises(Exception):
                adapter.extract_animal_details(
                    "https://www.yokosuka-doubutu.com/protected-animals/00-00/"
                )
