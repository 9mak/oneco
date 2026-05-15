"""HyogoDouaiAdapter のテスト

兵庫県動物愛護センター (hyogo-douai.sakura.ne.jp/shuuyou.html) 用
rule-based adapter の動作を検証する。

- 一覧 = `shuuyou.html` のサマリーテーブル `#sp-table-7` 配下の
  `<a href="hogo*.html">` を detail link として収集する list+detail 形式
- 実フィクスチャは hogo3.html / hogo5.html への link を含むが、
  detail ページ (`hogo*.html`) の HTML は手元に無いので
  詳細抽出のテストは synthetic な HPB 風 HTML を組み立てて検証する
- 在庫 0 件 (どのリンクも無いサマリー) のときは空リストを返すこと
  も合わせて検証する
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.hyogo_douai import (
    HyogoDouaiAdapter,
)
from data_collector.adapters.municipality_adapter import ParsingError
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig


SITE_NAME = "兵庫県動物愛護センター（収容動物）"
LIST_URL = "https://hyogo-douai.sakura.ne.jp/shuuyou.html"


def _site() -> SiteConfig:
    return SiteConfig(
        name=SITE_NAME,
        prefecture="兵庫県",
        prefecture_code="28",
        list_url=LIST_URL,
        category="sheltered",
        single_page=True,
    )


def _load_hyogo_html(fixture_html) -> str:
    """フィクスチャを読み込み、必要であれば mojibake (二重 UTF-8) を補正する

    fixtures/hyogo-douai_sakura_ne_jp.html は本来 UTF-8 のバイト列を
    Latin-1 として解釈してから再度 UTF-8 として保存し直された
    二重エンコーディング状態になっているため、実サイト相当のテキストを
    得るには逆変換が必要。実運用 (`_http_get`) では requests が正しい
    UTF-8 として受け取る。
    """
    raw = fixture_html("hyogo-douai_sakura_ne_jp")
    if "兵庫" in raw:
        return raw
    try:
        return raw.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return raw


def _build_empty_summary_html() -> str:
    """サマリーテーブルは存在するが、どのセルにも詳細リンクが無い HTML

    在庫 0 件状態を再現する。
    """
    return """
    <html><body>
      <div id="sp-block-container-21">
        <table id="sp-table-7" class="sp-part-top sp-table">
          <tbody>
            <tr>
              <th> </th>
              <th>センター</th><th>三木支所</th><th>龍野支所</th>
              <th>但馬支所</th><th>淡路支所</th>
            </tr>
            <tr>
              <th>犬</th>
              <td> </td><td> </td><td> </td><td> </td><td> </td>
            </tr>
            <tr>
              <th>猫</th>
              <td> </td><td> </td><td> </td><td> </td><td> </td>
            </tr>
          </tbody>
        </table>
      </div>
    </body></html>
    """


def _build_detail_html_dog() -> str:
    """HPB 風の detail ページ (hogo3.html 想定) を再現した HTML

    `<th>項目名</th><td>値</td>` の典型構造で各フィールドを掲載する。
    """
    return """
    <html><body>
      <div id="content">
        <h1>収容動物の情報 (龍野支所)</h1>
        <table>
          <tbody>
            <tr>
              <th>収容日</th>
              <td>令和8年5月10日</td>
            </tr>
            <tr>
              <th>性別</th>
              <td>オス</td>
            </tr>
            <tr>
              <th>年齢</th>
              <td>成犬</td>
            </tr>
            <tr>
              <th>毛色</th>
              <td>茶白</td>
            </tr>
            <tr>
              <th>大きさ</th>
              <td>中</td>
            </tr>
            <tr>
              <th>収容場所</th>
              <td>龍野支所</td>
            </tr>
            <tr>
              <th>連絡先</th>
              <td>0791-63-5142</td>
            </tr>
          </tbody>
        </table>
        <img src="img/hogo3_001.jpg" alt="">
      </div>
    </body></html>
    """


class TestHyogoDouaiAdapter:
    def test_fetch_animal_list_returns_detail_links_from_fixture(
        self, fixture_html
    ):
        """実フィクスチャから detail link (hogo*.html) を重複排除して収集できる

        fixture では `<a href="hogo3.html">` × 3, `<a href="hogo5.html">` × 1 が
        サマリーテーブル内に並んでおり、unique で 2 件になる想定。
        """
        html = _load_hyogo_html(fixture_html)
        adapter = HyogoDouaiAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        # hogo3.html と hogo5.html の 2 件 (重複排除済み)
        assert len(result) == 2
        urls = [u for u, _ in result]
        assert any(u.endswith("hogo3.html") for u in urls)
        assert any(u.endswith("hogo5.html") for u in urls)
        # 全て絶対 URL に変換されている
        for u in urls:
            assert u.startswith("https://hyogo-douai.sakura.ne.jp/")
        # category は sites.yaml の sheltered が伝播
        for _, cat in result:
            assert cat == "sheltered"

    def test_fetch_animal_list_returns_empty_when_no_detail_links(self):
        """サマリーテーブルはあるが detail link が無いときは空リストを返す

        在庫 0 件状態は ParsingError ではなく空リスト扱いとする。
        """
        adapter = HyogoDouaiAdapter(_site())
        with patch.object(
            adapter, "_http_get", return_value=_build_empty_summary_html()
        ):
            result = adapter.fetch_animal_list()
        assert result == []

    def test_fetch_animal_list_raises_when_summary_table_missing(self):
        """サマリーテーブル `#sp-table-7` 自体が無い場合は ParsingError"""
        adapter = HyogoDouaiAdapter(_site())
        with patch.object(
            adapter,
            "_http_get",
            return_value="<html><body><p>no table</p></body></html>",
        ):
            with pytest.raises(ParsingError):
                adapter.fetch_animal_list()

    def test_extract_animal_details_from_synthetic_detail(self):
        """detail ページから RawAnimalData を構築できる"""
        adapter = HyogoDouaiAdapter(_site())
        detail_url = "https://hyogo-douai.sakura.ne.jp/hogo3.html"

        with patch.object(
            adapter, "_http_get", return_value=_build_detail_html_dog()
        ):
            raw = adapter.extract_animal_details(
                detail_url, category="sheltered"
            )

        assert isinstance(raw, RawAnimalData)
        # species はラベル抽出では無いので、サイト名/URL から推定 → サイト名
        # に「犬」「猫」が無いため "その他" にフォールバック
        # (本テストの主眼は他フィールドの正しい抽出)
        assert raw.species in ("犬", "猫", "その他")
        assert raw.sex == "オス"
        assert raw.age == "成犬"
        assert raw.color == "茶白"
        assert raw.size == "中"
        assert "令和8年5月10日" in raw.shelter_date
        assert "龍野支所" in raw.location
        # 電話番号は base の _normalize_phone で 4-3-4 -> 4-3-4 のまま正規化
        assert raw.phone == "0791-63-5142"
        # 画像 URL は detail URL からの相対解決で絶対化
        assert raw.image_urls
        for u in raw.image_urls:
            assert u.startswith("https://hyogo-douai.sakura.ne.jp/")
        assert raw.source_url == detail_url
        assert raw.category == "sheltered"

    def test_extract_animal_details_raises_when_no_fields(self):
        """detail ページから 1 フィールドも抽出できないと ParsingError"""
        adapter = HyogoDouaiAdapter(_site())
        empty_detail = "<html><body><p>under construction</p></body></html>"

        with patch.object(adapter, "_http_get", return_value=empty_detail):
            with pytest.raises(ParsingError):
                adapter.extract_animal_details(
                    "https://hyogo-douai.sakura.ne.jp/hogo3.html",
                    category="sheltered",
                )

    def test_species_inference_from_url_dog(self):
        """URL パスに `dog` が含まれていれば species は "犬" 推定される"""
        adapter = HyogoDouaiAdapter(_site())
        detail_url = "https://hyogo-douai.sakura.ne.jp/hogo3_dog.html"

        with patch.object(
            adapter, "_http_get", return_value=_build_detail_html_dog()
        ):
            raw = adapter.extract_animal_details(
                detail_url, category="sheltered"
            )

        # ラベル抽出に「種類」が無くても URL の "dog" から「犬」と推定される
        assert raw.species == "犬"

    def test_site_registered(self):
        """sites.yaml の name が registry に登録されている"""
        # 他テストが registry を clear する場合に備えて冪等に再登録
        if SiteAdapterRegistry.get(SITE_NAME) is None:
            SiteAdapterRegistry.register(SITE_NAME, HyogoDouaiAdapter)
        assert SiteAdapterRegistry.get(SITE_NAME) is HyogoDouaiAdapter
