"""SapcaAdapter (sapca.jp / 滋賀県動物保護管理協会) のテスト

- list ページのフィクスチャから detail URL を重複なく抽出できる
- detail ページ想定の in-line HTML から RawAnimalData を構築できる
- registry にサイト名が登録されている
"""

from __future__ import annotations

from unittest.mock import patch

from data_collector.adapters.rule_based import sites  # noqa: F401  registry 登録用
from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig

# T405: 専用モジュールを spec 駆動の GenericAdapter へ移行したため、
# registry 経由でクラスを引く (spec: config/site_specs/sapca.yaml)。
SapcaAdapter = SiteAdapterRegistry.get("滋賀県動物保護管理センター（迷い犬猫）")
assert SapcaAdapter is not None


def _site() -> SiteConfig:
    return SiteConfig(
        name="滋賀県動物保護管理センター（迷い犬猫）",
        prefecture="滋賀県",
        prefecture_code="25",
        list_url="https://www.sapca.jp/lost",
        list_link_pattern="a[href*='/lost/'][href$='.html']",
        category="sheltered",
    )


# 想定 detail ページ HTML (WordPress + table 構造)
DETAIL_HTML = """
<html><body>
  <article>
    <h1>迷い犬</h1>
    <img src="https://www.sapca.jp/wp-content/uploads/2026/05/IMG_5503-e1778740295727.jpg">
    <table>
      <tr><th>種類</th><td>犬</td></tr>
      <tr><th>性別</th><td>オス</td></tr>
      <tr><th>年齢</th><td>不明</td></tr>
      <tr><th>毛色</th><td>茶白</td></tr>
      <tr><th>体格</th><td>中型</td></tr>
      <tr><th>保護日</th><td>2026-05-01</td></tr>
      <tr><th>保護場所</th><td>湖南市</td></tr>
      <tr><th>連絡先</th><td>0748-75-1911</td></tr>
    </table>
    <img src="https://www.sapca.jp/wp-content/themes/sapca/img/common/banner_donation.jpg">
  </article>
</body></html>
"""


class TestSapcaAdapterListExtraction:
    """list ページからの detail URL 抽出"""

    def test_fetch_animal_list_excludes_sumi_cards_from_fixture(self, fixture_html):
        """フィクスチャの2件は両方 `li.sumi`「飼い主さんのところへ戻りました」なので0件になる (T134)

        以前はこの2件を抽出することを期待値にしていたが、実データを読み直すと
        どちらも既に飼い主のもとへ戻った個体で、募集中として公開してはいけない
        ものだった。詳細ページは 200 のまま残るため prune では落ちない。
        """
        adapter = SapcaAdapter(_site())
        html = fixture_html("sapca_jp")
        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()
        assert result == []

    def test_fetch_animal_list_extracts_available_cards(self):
        """`sumi` が付いていないカードは従来どおり抽出する"""
        html = """
        <html><body><ul class="list">
          <li class="sumi lost-sumi"><a href="https://www.sapca.jp/lost/21056.html">
            飼い主さんのところへ 戻りました</a></li>
          <li><a href="https://www.sapca.jp/lost/21730.html">迷い犬 湖南市</a></li>
        </ul></body></html>
        """
        adapter = SapcaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        urls = [u for u, _cat in result]
        assert urls == ["https://www.sapca.jp/lost/21730.html"]
        # `/lost` 自体 (一覧ページ) や mailto などは混入しない
        for u in urls:
            assert u.endswith(".html")
            assert "/lost/" in u
        # category は site_config 由来
        assert all(cat == "sheltered" for _u, cat in result)

    def test_fetch_animal_list_deduplicates(self, fixture_html):
        """同一 detail URL が複数回現れても重複除去される"""
        adapter = SapcaAdapter(_site())
        html = fixture_html("sapca_jp")
        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()
        urls = [u for u, _cat in result]
        assert len(urls) == len(set(urls))


class TestSapcaAdapterDetailExtraction:
    """detail ページからの RawAnimalData 構築"""

    def test_extract_animal_details_returns_raw_data(self, assert_raw_animal):
        adapter = SapcaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=DETAIL_HTML):
            raw = adapter.extract_animal_details(
                "https://www.sapca.jp/lost/21056.html",
                category="sheltered",
            )
        assert isinstance(raw, RawAnimalData)
        assert_raw_animal(
            raw,
            species="犬",
            sex="オス",
            age="不明",
            color="茶白",
            size="中型",
            shelter_date="2026-05-01",
            location="湖南市",
            phone="0748-75-1911",
            source_url="https://www.sapca.jp/lost/21056.html",
            category="sheltered",
        )

        # normalize() 経由でも主要フィールドが期待通りに変換されること
        # (T042/T114: raw のみの確認では normalize 段の退行を検知できない)。
        # 実際に adapter.normalize() を実行して確認した値: sex "オス"→"男の子"、
        # age "不明"→None、shelter_date "2026-05-01"→date(2026, 5, 1)。
        animal_data = adapter.normalize(raw)
        assert animal_data.sex == "男の子"
        assert animal_data.age_months is None
        assert animal_data.size == "中型"
        assert animal_data.shelter_date.isoformat() == "2026-05-01"
        assert animal_data.location == "湖南市"
        assert animal_data.phone == "0748-75-1911"

    def test_extract_filters_template_images_and_keeps_uploads(self):
        adapter = SapcaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=DETAIL_HTML):
            raw = adapter.extract_animal_details("https://www.sapca.jp/lost/21056.html")
        # uploads 配下の写真のみ残り、themes 配下の装飾バナーは弾かれる
        assert len(raw.image_urls) == 1
        assert all("/wp-content/uploads/" in u for u in raw.image_urls)

    def test_extract_animal_details_with_real_labels(self, assert_raw_animal):
        """T131b: 実ページ (2026-09-09確認) は「収容日」「保護した場所」を使う。

        旧実装の label 指定「保護日」「保護場所」は実際の th テキストと
        完全一致・部分一致のどちらもヒットせず shelter_date/location が
        100% 欠損していた (sapca.jp/lost/21810.html で実測)。
        """
        real_html = """
        <html><body>
          <article>
            <h1>迷い犬</h1>
            <table class="dogcat">
              <tr><th>収容日</th><td>９月９日（水）</td></tr>
              <tr><th>保護した場所</th><td>甲賀市土山町北土山</td></tr>
              <tr><th>種類</th><td>雑種</td></tr>
              <tr><th>性別</th><td>メス</td></tr>
              <tr><th>毛色</th><td>茶白</td></tr>
              <tr><th>体格</th><td>中小</td></tr>
              <tr><th>首輪</th><td>なし</td></tr>
              <tr><th>備考</th><td></td></tr>
            </table>
          </article>
        </body></html>
        """
        adapter = SapcaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=real_html):
            raw = adapter.extract_animal_details(
                "https://www.sapca.jp/lost/21810.html",
                category="sheltered",
            )
        assert_raw_animal(
            raw,
            species="雑種",
            sex="メス",
            color="茶白",
            size="中小",
            shelter_date="９月９日（水）",
            location="甲賀市土山町北土山",
            source_url="https://www.sapca.jp/lost/21810.html",
            category="sheltered",
        )

        animal_data = adapter.normalize(raw)
        assert animal_data.location == "甲賀市土山町北土山"


class TestSapcaAdapterRegistry:
    """registry 登録"""

    def test_site_registered(self):
        cls = SiteAdapterRegistry.get("滋賀県動物保護管理センター（迷い犬猫）")
        # 他テストが registry を clear する場合に備えて冪等に再登録
        if cls is None:
            SiteAdapterRegistry.register("滋賀県動物保護管理センター（迷い犬猫）", SapcaAdapter)
            cls = SiteAdapterRegistry.get("滋賀県動物保護管理センター（迷い犬猫）")
        assert cls is SapcaAdapter


class TestSapcaAdapterEmptyList:
    """カードが 1 件もない場合の挙動 (在庫 0 件 = 真ゼロ)"""

    def test_returns_empty_when_no_links(self):
        adapter = SapcaAdapter(_site())
        with patch.object(
            adapter,
            "_http_get",
            return_value="<html><body><ul class='list'></ul></body></html>",
        ):
            result = adapter.fetch_animal_list()
        assert result == []
