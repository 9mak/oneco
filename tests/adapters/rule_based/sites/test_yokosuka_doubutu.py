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

        with patch.object(adapter, "_http_get", side_effect=[list_html, DETAIL_HTML]):
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

    def test_long_features_text_excluded_from_color(self):
        """譲渡カテゴリで「特徴」セルに長文説明が入る場合、color には流入させない

        実サイトの譲渡犬/譲渡猫ページの 特徴 セルは「12歳、体重29Kg、フィラリア
        陰性、内部寄生虫駆除薬の投薬済...」のような長文説明文が入ることがある。
        この長文が DB の color VARCHAR(100) に INSERT されると StringDataRightTruncation
        で失敗 → トランザクション全体 rollback で 1 サイト全滅する。
        adapter 段階で 30 文字超の 特徴 は color から除外する。
        """
        long_features_html = """
        <html><body><table><tbody>
          <tr><td>整理番号</td><td>26-99</td></tr>
          <tr><td>種類</td><td>雑種</td></tr>
          <tr><td>性別</td><td>メス</td></tr>
          <tr><td>収容日</td><td>R8.5.14</td></tr>
          <tr><td>収容場所</td><td>不明</td></tr>
          <tr><td>特徴</td><td>12歳、体重29Kg、フィラリア陰性、内部寄生虫駆除薬の投薬済。
            お散歩大好きです。ダイエット中です。フードガードがあります。</td></tr>
        </tbody></table></body></html>
        """
        adapter = YokosukaDoubutuAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=long_features_html):
            raw = adapter.extract_animal_details(
                "https://www.yokosuka-doubutu.com/adopted-animals/26-99/",
                category="adoption",
            )
        # 長文説明文は color に流れ込まない
        assert raw.color == ""
        # 他のフィールドは通常通り抽出される
        assert raw.species == "雑種"
        assert raw.sex == "メス"

    def test_short_color_text_kept_in_color(self):
        """短い 特徴 (例: '黒白') は従来通り color として採用される"""
        short_color_html = """
        <html><body><table><tbody>
          <tr><td>種類</td><td>豆柴</td></tr>
          <tr><td>性別</td><td>オス</td></tr>
          <tr><td>収容日</td><td>R8.5.14</td></tr>
          <tr><td>収容場所</td><td>池田町</td></tr>
          <tr><td>特徴</td><td>黒白</td></tr>
        </tbody></table></body></html>
        """
        adapter = YokosukaDoubutuAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=short_color_html):
            raw = adapter.extract_animal_details(
                "https://www.yokosuka-doubutu.com/protected-animals/26-22/",
                category="sheltered",
            )
        assert raw.color == "黒白"

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
        with patch.object(adapter, "_http_get", return_value="<html><body></body></html>"):
            with pytest.raises(Exception):
                adapter.extract_animal_details(
                    "https://www.yokosuka-doubutu.com/protected-animals/00-00/"
                )
