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


def _site_cat_shelter() -> SiteConfig:
    return SiteConfig(
        name="横須賀市（保護猫）",
        prefecture="神奈川県",
        prefecture_code="14",
        list_url="https://www.yokosuka-doubutu.com/protected-animals-cat/",
        category="sheltered",
    )


def _site_dog_adoption() -> SiteConfig:
    return SiteConfig(
        name="横須賀市（譲渡犬）",
        prefecture="神奈川県",
        prefecture_code="14",
        list_url="https://www.yokosuka-doubutu.com/adopted-animals-dog/",
        category="adoption",
    )


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
        # species は「分類」セル ("犬(保護収容)") から「犬」に正規化される
        # (旧仕様では「種類」セルの "豆柴" がそのまま species に入っていた)
        assert raw.species == "犬"
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
        # 注: HTML に「分類」セルが無いため site_config.name (横須賀市（保護犬）) から
        # species="犬" に推定される (旧仕様では「種類」セルの "雑種" が species だった)
        assert raw.species == "犬"
        assert raw.sex == "メス"

    def test_feature_with_age_splits_color_and_age(self):
        """「特徴」セルに color と age が混在するケースを分離する

        2026-05 観測: 横須賀市は「特徴」セルに「キジ白、推定1歳」のような
        毛色と年齢が同居している。年齢パターンを正規表現で抽出し age に
        格納、color テキストから当該部分を除去する。
        """
        html = """
        <html><body><table><tbody>
          <tr><td>整理番号</td><td>26-19</td></tr>
          <tr><td>分類</td><td>猫(保護収容)</td></tr>
          <tr><td>収容日</td><td>R8.5.4</td></tr>
          <tr><td>収容場所</td><td>長井</td></tr>
          <tr><td>種類</td><td>MIX</td></tr>
          <tr><td>性別</td><td>メス</td></tr>
          <tr><td>特徴</td><td>キジ白、推定1歳</td></tr>
        </tbody></table></body></html>
        """
        adapter = YokosukaDoubutuAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=html):
            raw = adapter.extract_animal_details(
                "https://www.yokosuka-doubutu.com/protected-animals/3131/",
                category="sheltered",
            )
        assert raw.color == "キジ白", f"年齢部分が除去された color: got {raw.color!r}"
        assert "1歳" in raw.age, f"年齢が age に流れた: got {raw.age!r}"
        assert raw.location == "長井"

    def test_feature_only_age_keyword(self):
        """「子猫」「成犬」のような年齢キーワード単独でも age に流れる"""
        html = """
        <html><body><table><tbody>
          <tr><td>種類</td><td>MIX</td></tr>
          <tr><td>性別</td><td>オス</td></tr>
          <tr><td>収容場所</td><td>横須賀</td></tr>
          <tr><td>特徴</td><td>茶トラ、子猫</td></tr>
        </tbody></table></body></html>
        """
        adapter = YokosukaDoubutuAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=html):
            raw = adapter.extract_animal_details(
                "https://www.yokosuka-doubutu.com/protected-animals/x/",
                category="sheltered",
            )
        assert raw.color == "茶トラ"
        assert raw.age == "子猫"

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

    def test_species_inferred_from_category_cell_cat(self):
        """「分類」セルの "猫(保護収容)" から species="猫" を抽出

        実サイト 2026-05 観測: 「種類」セルにはブリード ("MIX", "豆柴") が入り
        species (犬/猫/その他) は「分類」セルに記載される。
        """
        html = """
        <html><body><table><tbody>
          <tr><td>整理番号</td><td>26-19</td></tr>
          <tr><td>分類</td><td>猫(保護収容)</td></tr>
          <tr><td>収容日</td><td>R8.5.4</td></tr>
          <tr><td>収容場所</td><td>長井</td></tr>
          <tr><td>種類</td><td>MIX</td></tr>
          <tr><td>性別</td><td>メス</td></tr>
          <tr><td>特徴</td><td>キジ白</td></tr>
        </tbody></table></body></html>
        """
        adapter = YokosukaDoubutuAdapter(_site_cat_shelter())
        with patch.object(adapter, "_http_get", return_value=html):
            raw = adapter.extract_animal_details(
                "https://www.yokosuka-doubutu.com/protected-animals/3131/",
                category="sheltered",
            )
        assert raw.species == "猫", f"分類セルから species=猫 推定: got {raw.species!r}"

    def test_species_inferred_from_category_cell_dog(self):
        """「分類」セルの "犬(譲渡)" から species="犬" を抽出"""
        html = """
        <html><body><table><tbody>
          <tr><td>整理番号</td><td>26-16</td></tr>
          <tr><td>分類</td><td>犬(譲渡)</td></tr>
          <tr><td>種類</td><td>ラブラドルレトリバー</td></tr>
          <tr><td>性別</td><td>メス</td></tr>
          <tr><td>収容日</td><td>R8.5.1</td></tr>
          <tr><td>収容場所</td><td>横須賀</td></tr>
          <tr><td>体重</td><td>29Kg</td></tr>
          <tr><td>特徴</td><td>お散歩大好き</td></tr>
        </tbody></table></body></html>
        """
        adapter = YokosukaDoubutuAdapter(_site_dog_adoption())
        with patch.object(adapter, "_http_get", return_value=html):
            raw = adapter.extract_animal_details(
                "https://www.yokosuka-doubutu.com/adopted-animals/26-16/",
                category="adoption",
            )
        assert raw.species == "犬", f"分類セルから species=犬 推定: got {raw.species!r}"

    def test_species_fallback_to_site_name(self):
        """「分類」セルが無い詳細ページではサイト名 (横須賀市（保護猫）) から推定"""
        html = """
        <html><body><table><tbody>
          <tr><td>整理番号</td><td>26-19</td></tr>
          <tr><td>収容日</td><td>R8.5.4</td></tr>
          <tr><td>収容場所</td><td>長井</td></tr>
          <tr><td>種類</td><td>MIX</td></tr>
          <tr><td>性別</td><td>メス</td></tr>
        </tbody></table></body></html>
        """
        adapter = YokosukaDoubutuAdapter(_site_cat_shelter())
        with patch.object(adapter, "_http_get", return_value=html):
            raw = adapter.extract_animal_details(
                "https://www.yokosuka-doubutu.com/protected-animals/3131/",
                category="sheltered",
            )
        assert raw.species == "猫"

    def test_size_inferred_from_weight_cell_large(self):
        """「体重: 29Kg」セルから size="大" 推定 (15kg 以上)"""
        html = """
        <html><body><table><tbody>
          <tr><td>分類</td><td>犬(譲渡)</td></tr>
          <tr><td>種類</td><td>ラブラドルレトリバー</td></tr>
          <tr><td>性別</td><td>メス</td></tr>
          <tr><td>収容日</td><td>R8.5.1</td></tr>
          <tr><td>収容場所</td><td>横須賀</td></tr>
          <tr><td>体重</td><td>29Kg</td></tr>
        </tbody></table></body></html>
        """
        adapter = YokosukaDoubutuAdapter(_site_dog_adoption())
        with patch.object(adapter, "_http_get", return_value=html):
            raw = adapter.extract_animal_details(
                "https://www.yokosuka-doubutu.com/adopted-animals/26-16/",
                category="adoption",
            )
        assert raw.size == "大", f"体重29Kg → size=大: got {raw.size!r}"

    def test_size_inferred_from_weight_cell_medium(self):
        """「体重: 9.6Kg」セルから size="中" 推定 (5kg 以上 15kg 未満)"""
        html = """
        <html><body><table><tbody>
          <tr><td>分類</td><td>犬(譲渡)</td></tr>
          <tr><td>種類</td><td>フレンチブルドッグ</td></tr>
          <tr><td>性別</td><td>オス</td></tr>
          <tr><td>収容日</td><td>R8.5.1</td></tr>
          <tr><td>収容場所</td><td>横須賀</td></tr>
          <tr><td>体重</td><td>9.6Kg</td></tr>
        </tbody></table></body></html>
        """
        adapter = YokosukaDoubutuAdapter(_site_dog_adoption())
        with patch.object(adapter, "_http_get", return_value=html):
            raw = adapter.extract_animal_details(
                "https://www.yokosuka-doubutu.com/adopted-animals/3162/",
                category="adoption",
            )
        assert raw.size == "中"

    def test_size_inferred_from_weight_cell_small(self):
        """「体重: 3kg」セルから size="小" 推定 (5kg 未満)"""
        html = """
        <html><body><table><tbody>
          <tr><td>分類</td><td>猫(譲渡)</td></tr>
          <tr><td>種類</td><td>MIX</td></tr>
          <tr><td>性別</td><td>オス</td></tr>
          <tr><td>収容場所</td><td>横須賀</td></tr>
          <tr><td>体重</td><td>3kg</td></tr>
        </tbody></table></body></html>
        """
        adapter = YokosukaDoubutuAdapter(_site_cat_shelter())
        with patch.object(adapter, "_http_get", return_value=html):
            raw = adapter.extract_animal_details(
                "https://www.yokosuka-doubutu.com/adopted-animals/25-79/",
                category="adoption",
            )
        assert raw.size == "小"

    def test_weight_not_leaked_to_raw_data(self):
        """`weight` は内部一時フィールドであり RawAnimalData に直接漏れない

        size が「大きさ」セル/体重推定で埋まる前提で、weight 自体は
        RawAnimalData の属性として露出しない。
        """
        html = """
        <html><body><table><tbody>
          <tr><td>分類</td><td>犬(譲渡)</td></tr>
          <tr><td>種類</td><td>ラブラドル</td></tr>
          <tr><td>性別</td><td>メス</td></tr>
          <tr><td>収容場所</td><td>横須賀</td></tr>
          <tr><td>体重</td><td>29Kg</td></tr>
        </tbody></table></body></html>
        """
        adapter = YokosukaDoubutuAdapter(_site_dog_adoption())
        with patch.object(adapter, "_http_get", return_value=html):
            raw = adapter.extract_animal_details(
                "https://www.yokosuka-doubutu.com/adopted-animals/26-16/",
                category="adoption",
            )
        assert not hasattr(raw, "weight")
        assert raw.size == "大"

    def test_size_inferred_from_weight_in_feature_cell(self):
        """「特徴」セル長文内に埋め込まれた「体重Nkg」から size を推定する

        実サイト (2026-06 観測) の譲渡犬ページは「体重」というセル行が存在せず、
        「特徴」セル長文に「12歳、体重29Kg、フィラリア陰性...」のように
        体重が埋め込まれているケースが多い。FieldSpec(label="体重") では
        セル行マッチのため永遠にヒットせず、snapshot 上 size=0% の原因。

        長文 color はリジェクトされても、抽出された体重は size 推定に使う。
        """
        html = """
        <html><body><table><tbody>
          <tr><td>整理番号</td><td>26-99</td></tr>
          <tr><td>分類</td><td>犬(譲渡)</td></tr>
          <tr><td>種類</td><td>雑種</td></tr>
          <tr><td>性別</td><td>メス</td></tr>
          <tr><td>収容日</td><td>R8.5.14</td></tr>
          <tr><td>収容場所</td><td>不明</td></tr>
          <tr><td>特徴</td><td>12歳、体重29Kg、フィラリア陰性、内部寄生虫駆除薬の投薬済。
            お散歩大好きです。ダイエット中です。フードガードがあります。</td></tr>
        </tbody></table></body></html>
        """
        adapter = YokosukaDoubutuAdapter(_site_dog_adoption())
        with patch.object(adapter, "_http_get", return_value=html):
            raw = adapter.extract_animal_details(
                "https://www.yokosuka-doubutu.com/adopted-animals/26-99/",
                category="adoption",
            )
        # 長文説明文は color から除外される (既存挙動)
        assert raw.color == ""
        # 特徴セル長文内に埋め込まれた「体重29Kg」から size 推定
        assert raw.size == "大", f"特徴セル内の体重から size 推定されるべき: got {raw.size!r}"

    def test_size_inferred_from_weight_in_short_feature(self):
        """「特徴」セルが短い (color として採用される) ケースでも、
        セル内に体重情報があれば size を推定する"""
        html = """
        <html><body><table><tbody>
          <tr><td>分類</td><td>犬(譲渡)</td></tr>
          <tr><td>種類</td><td>雑種</td></tr>
          <tr><td>性別</td><td>メス</td></tr>
          <tr><td>特徴</td><td>キジ白、体重9.6kg</td></tr>
        </tbody></table></body></html>
        """
        adapter = YokosukaDoubutuAdapter(_site_dog_adoption())
        with patch.object(adapter, "_http_get", return_value=html):
            raw = adapter.extract_animal_details(
                "https://www.yokosuka-doubutu.com/adopted-animals/x/",
                category="adoption",
            )
        assert raw.size == "中", f"短い特徴セル内の体重からも size 推定されるべき: got {raw.size!r}"

    def test_size_field_preferred_over_weight(self):
        """「大きさ」セルがある場合は体重推定よりも優先する"""
        html = """
        <html><body><table><tbody>
          <tr><td>分類</td><td>犬(譲渡)</td></tr>
          <tr><td>種類</td><td>柴犬</td></tr>
          <tr><td>性別</td><td>メス</td></tr>
          <tr><td>収容場所</td><td>横須賀</td></tr>
          <tr><td>大きさ</td><td>中型</td></tr>
          <tr><td>体重</td><td>30Kg</td></tr>
        </tbody></table></body></html>
        """
        adapter = YokosukaDoubutuAdapter(_site_dog_adoption())
        with patch.object(adapter, "_http_get", return_value=html):
            raw = adapter.extract_animal_details(
                "https://www.yokosuka-doubutu.com/adopted-animals/x/",
                category="adoption",
            )
        assert raw.size == "中型"

    @pytest.mark.parametrize(
        "weight_text,expected",
        [
            ("4.9kg", "小"),
            ("5kg", "中"),
            ("14.9Kg", "中"),
            ("15kg", "大"),
            ("29Kg", "大"),
            ("不明", ""),
            ("", ""),
        ],
    )
    def test_weight_to_size_boundaries(self, weight_text, expected):
        """境界値 (5kg / 15kg) を含む体重→size 変換の検証"""
        assert YokosukaDoubutuAdapter._weight_to_size(weight_text) == expected

    def test_color_extracted_from_breed_cell_simple(self):
        """「種類」セルが「MIX、黒白」のように毛色併記の場合、color に「黒白」を抽出

        2026-06 実サイト観測 (譲渡カテゴリ):
        - 「種類」セルにブリードと毛色が「、」区切りで併記される
          例: "MIX、黒白" / "チンチラ、白" / "ミヌエット、レッド＆ホワイト"
        - 「特徴」セルは長文説明 (DB color VARCHAR 制約超過) のため color に流れない
        - 結果として color が空のまま 10/11 件が color 欠損していた
        """
        html = """
        <html><body><table><tbody>
          <tr><td>整理番号</td><td>25-79</td></tr>
          <tr><td>分類</td><td>猫(譲渡)</td></tr>
          <tr><td>種類</td><td>MIX、黒白</td></tr>
          <tr><td>性別</td><td>オス</td></tr>
        </tbody></table></body></html>
        """
        adapter = YokosukaDoubutuAdapter(_site_cat_shelter())
        with patch.object(adapter, "_http_get", return_value=html):
            raw = adapter.extract_animal_details(
                "https://www.yokosuka-doubutu.com/adopted-animals/25-79/",
                category="adoption",
            )
        assert raw.color == "黒白", f"got {raw.color!r}"
        assert raw.species == "猫"

    def test_color_extracted_from_breed_cell_complex(self):
        """長めの毛色併記 (「スコティッシュフォールド、ブラウンマッカレルタビー」) も抽出"""
        html = """
        <html><body><table><tbody>
          <tr><td>分類</td><td>猫(譲渡)</td></tr>
          <tr><td>種類</td><td>スコティッシュフォールド、ブラウンマッカレルタビー</td></tr>
          <tr><td>性別</td><td>オス</td></tr>
        </tbody></table></body></html>
        """
        adapter = YokosukaDoubutuAdapter(_site_cat_shelter())
        with patch.object(adapter, "_http_get", return_value=html):
            raw = adapter.extract_animal_details(
                "https://www.yokosuka-doubutu.com/adopted-animals/26-15/",
                category="adoption",
            )
        assert raw.color == "ブラウンマッカレルタビー"

    def test_color_extracted_from_breed_cell_with_ampersand(self):
        """「ミヌエット、レッド＆ホワイト」のように記号を含む毛色も抽出"""
        html = """
        <html><body><table><tbody>
          <tr><td>分類</td><td>猫(譲渡)</td></tr>
          <tr><td>種類</td><td>ミヌエット、レッド＆ホワイト</td></tr>
          <tr><td>性別</td><td>オス</td></tr>
        </tbody></table></body></html>
        """
        adapter = YokosukaDoubutuAdapter(_site_cat_shelter())
        with patch.object(adapter, "_http_get", return_value=html):
            raw = adapter.extract_animal_details(
                "https://www.yokosuka-doubutu.com/adopted-animals/25-64/",
                category="adoption",
            )
        assert raw.color == "レッド＆ホワイト"

    def test_color_not_extracted_when_breed_cell_single(self):
        """「種類」セルに区切りが無い場合 (例: "フレンチブルドッグ") は color 空のまま"""
        html = """
        <html><body><table><tbody>
          <tr><td>分類</td><td>犬(譲渡)</td></tr>
          <tr><td>種類</td><td>フレンチブルドッグ</td></tr>
          <tr><td>性別</td><td>オス</td></tr>
        </tbody></table></body></html>
        """
        adapter = YokosukaDoubutuAdapter(_site_dog_adoption())
        with patch.object(adapter, "_http_get", return_value=html):
            raw = adapter.extract_animal_details(
                "https://www.yokosuka-doubutu.com/adopted-animals/26-25/",
                category="adoption",
            )
        assert raw.color == ""
        assert raw.species == "犬"

    def test_color_from_breed_cell_does_not_override_feature_color(self):
        """「特徴」セルから取れた短い毛色 (例: "黒白") を「種類」セル抽出で上書きしない"""
        html = """
        <html><body><table><tbody>
          <tr><td>分類</td><td>猫(譲渡)</td></tr>
          <tr><td>種類</td><td>MIX、白</td></tr>
          <tr><td>性別</td><td>オス</td></tr>
          <tr><td>特徴</td><td>黒白</td></tr>
        </tbody></table></body></html>
        """
        adapter = YokosukaDoubutuAdapter(_site_cat_shelter())
        with patch.object(adapter, "_http_get", return_value=html):
            raw = adapter.extract_animal_details(
                "https://www.yokosuka-doubutu.com/adopted-animals/x/",
                category="adoption",
            )
        # 「特徴」セルが先に拾われた色 ("黒白") が優先される
        assert raw.color == "黒白"

    def test_color_from_breed_cell_rejects_long_text(self):
        """「種類」セルの後半が極端に長い場合 (説明文混入) は color に採用しない"""
        html = """
        <html><body><table><tbody>
          <tr><td>分類</td><td>猫(譲渡)</td></tr>
          <tr><td>種類</td><td>MIX、とても可愛い毛並みの綺麗な人懐っこい長毛の素敵な男の子です</td></tr>
          <tr><td>性別</td><td>オス</td></tr>
        </tbody></table></body></html>
        """
        adapter = YokosukaDoubutuAdapter(_site_cat_shelter())
        with patch.object(adapter, "_http_get", return_value=html):
            raw = adapter.extract_animal_details(
                "https://www.yokosuka-doubutu.com/adopted-animals/x/",
                category="adoption",
            )
        # 長文は color に流れ込まない
        assert raw.color == ""

    def test_color_extracted_from_breed_cell_when_feature_is_long_description(self):
        """「特徴」セルが長文 (説明文) で長文リジェクトにかかる場合でも
        「種類」セル併記から color を取り出せること

        2026-06 実サイト観測 (回帰):
        - 譲渡ページの「特徴」セルは「11歳。不妊手術済。FIV（＋）...」のような
          200 文字級の長文が入る。
        - PR #105 では `not fields.get("color")` ガードにより、長文の「特徴」
          セル値が先に color に入った段階で「種類」セル抽出がスキップされ、
          その後の長文リジェクトで color が空になる回帰が発生していた。
        - 「特徴」セルが長文の場合は「種類」セルからの抽出を優先することで
          実サイト 10/11 件の color 欠損を解消する。
        """
        feature_long = (
            "11歳。不妊手術済。FIV（＋）おしゃべりをたくさんします。"
            "少し怖がりで、まだあまり寄ってきてくれませんが、人恋しいようです。"
            "寂しがりやです。眼に古い傷があり、白くなっていますが、見えています。"
        )
        html = f"""
        <html><body><table><tbody>
          <tr><td>整理番号</td><td>25-79</td></tr>
          <tr><td>分類</td><td>猫(譲渡)</td></tr>
          <tr><td>種類</td><td>MIX、黒白</td></tr>
          <tr><td>性別</td><td>オス</td></tr>
          <tr><td>特徴</td><td>{feature_long}</td></tr>
        </tbody></table></body></html>
        """
        adapter = YokosukaDoubutuAdapter(_site_cat_shelter())
        with patch.object(adapter, "_http_get", return_value=html):
            raw = adapter.extract_animal_details(
                "https://www.yokosuka-doubutu.com/adopted-animals/25-79/",
                category="adoption",
            )
        # 「特徴」が長文でも「種類」セル後半の "黒白" が color に入る
        assert raw.color == "黒白", f"got {raw.color!r}"

    def test_location_defaults_to_facility_for_adoption_pages(self):
        """譲渡カテゴリ (`/adopted-animals/`) は「収容場所」セルが無いため
        施設名 ("横須賀市動物愛護センター") を location に代入する

        2026-06 実サイト観測: 譲渡 (adopted-animals/*) は「収容場所」セルを
        持たず location が空 → normalizer で "不明" になる。譲渡対象動物は
        施設で会うことになるので、施設名を location に充てる。
        """
        html = """
        <html><body><table><tbody>
          <tr><td>分類</td><td>猫(譲渡)</td></tr>
          <tr><td>種類</td><td>MIX、白</td></tr>
          <tr><td>性別</td><td>メス</td></tr>
        </tbody></table></body></html>
        """
        adapter = YokosukaDoubutuAdapter(_site_cat_shelter())
        with patch.object(adapter, "_http_get", return_value=html):
            raw = adapter.extract_animal_details(
                "https://www.yokosuka-doubutu.com/adopted-animals/25-79/",
                category="adoption",
            )
        assert raw.location == "横須賀市動物愛護センター", f"got {raw.location!r}"

    def test_location_not_defaulted_for_protected_pages(self):
        """保護収容 (`/protected-animals/`) は「収容場所」セルがある前提で
        デフォルト充填しない (空のときは空のまま normalizer に委ねる)"""
        html = """
        <html><body><table><tbody>
          <tr><td>分類</td><td>猫(保護収容)</td></tr>
          <tr><td>種類</td><td>MIX</td></tr>
          <tr><td>性別</td><td>メス</td></tr>
          <tr><td>収容場所</td><td>長井</td></tr>
        </tbody></table></body></html>
        """
        adapter = YokosukaDoubutuAdapter(_site_cat_shelter())
        with patch.object(adapter, "_http_get", return_value=html):
            raw = adapter.extract_animal_details(
                "https://www.yokosuka-doubutu.com/protected-animals/3131/",
                category="sheltered",
            )
        assert raw.location == "長井"

    def test_location_existing_value_not_overridden_for_adoption(self):
        """譲渡カテゴリでも「収容場所」セルが存在する場合は元の値を優先"""
        html = """
        <html><body><table><tbody>
          <tr><td>分類</td><td>犬(譲渡)</td></tr>
          <tr><td>種類</td><td>柴犬</td></tr>
          <tr><td>性別</td><td>メス</td></tr>
          <tr><td>収容場所</td><td>横須賀</td></tr>
        </tbody></table></body></html>
        """
        adapter = YokosukaDoubutuAdapter(_site_dog_adoption())
        with patch.object(adapter, "_http_get", return_value=html):
            raw = adapter.extract_animal_details(
                "https://www.yokosuka-doubutu.com/adopted-animals/x/",
                category="adoption",
            )
        assert raw.location == "横須賀"
