"""HamaAikyouAdapter のテスト

浜松市動物愛護教育センター（はぴまるの丘 / hama-aikyou.jp）用 rule-based
adapter の動作を検証する。

- `<h2>中央区/浜名区/天竜区</h2>` の各区セクション配下の `<table>` を動物
  データ表として抽出する single_page サイト
- 実フィクスチャは 0 件状態（各区とも「現在、X区で保護された犬はいません。」
  告知のみ）なので、データを伴うテストは synthetic な HTML を組み立てて検証する
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.hama_aikyou import (
    HamaAikyouAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig

_LIST_URL = "https://www.hama-aikyou.jp/hogoinu/index.html"
_SITE_NAME = "浜松市はぴまるの丘（保護犬）"


def _site(
    name: str = _SITE_NAME,
    list_url: str = _LIST_URL,
) -> SiteConfig:
    return SiteConfig(
        name=name,
        prefecture="静岡県",
        prefecture_code="22",
        list_url=list_url,
        category="lost",
        single_page=True,
    )


def _load_hama_html(fixture_html) -> str:
    """フィクスチャを読み込み、必要であれば mojibake (二重 UTF-8) を補正する

    リポジトリに保存されている `hama_aikyou_jp.html` は本来 UTF-8 のバイト列を
    Latin-1 として解釈してから再度 UTF-8 として保存し直された二重エンコー
    ディング状態のため、実サイト相当のテキストを得るには逆変換が必要。
    実運用 (`_http_get`) では requests が正しい UTF-8 として受け取るため、
    adapter 側の `_load_rows` は mojibake 検出が不要な状態で入ってくる。
    """
    raw = fixture_html("hama_aikyou_jp")
    if "浜松" in raw or "中央区" in raw:
        return raw
    try:
        return raw.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return raw


def _animal_table(rows_html: str) -> str:
    """中央区等の区セクション内に置く動物データテーブルを生成する"""
    return f"""
    <table>
      <thead>
        <tr>
          <th>問合せ番号</th>
          <th>犬種</th>
          <th>性別</th>
          <th>毛色</th>
          <th>保護日</th>
          <th>保護場所</th>
        </tr>
      </thead>
      <tbody>
        {rows_html}
      </tbody>
    </table>
    """


def _build_html(
    chuo_section: str = ('<span class="color-01">現在、中央区で保護された犬はいません。</span>'),
    hamana_section: str = ('<span class="color-01">現在、浜名区で保護された犬はいません。</span>'),
    tenryu_section: str = ('<span class="color-01">現在、天竜区で保護された犬はいません。</span>'),
) -> str:
    """3 区セクションと「引き取るには」セクションを含む HTML を生成する"""
    return f"""
    <html><body>
      <main id="main">
        <h1>保護犬情報</h1>
        <h2 id="f750f0eb">中央区</h2>
        {chuo_section}
        <h2 id="7f13b4d3">浜名区</h2>
        {hamana_section}
        <h2 id="77c9144d">天竜区</h2>
        {tenryu_section}
        <h2 id="3a2fa2ef">保護されている犬を引き取るには</h2>
        <p>１．電話で連絡してください</p>
        <table>
          <tr><td>受付窓口</td><td>動物愛護教育センター</td></tr>
          <tr><td>受付時間</td><td>午前8時30分～午後5時15分</td></tr>
        </table>
        <table>
          <tr><td>提出する書類</td><td>抑留犬返還願</td></tr>
          <tr><td>持ち物</td><td>犬を繋留するロープ等</td></tr>
        </table>
      </main>
    </body></html>
    """


class TestHamaAikyouAdapter:
    def test_fetch_animal_list_returns_empty_for_real_fixture(self, fixture_html):
        """実フィクスチャ（3区とも在庫 0 件）では空リストを返す"""
        html = _load_hama_html(fixture_html)
        adapter = HamaAikyouAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert result == []

    def test_fetch_animal_list_returns_empty_for_all_empty_synthetic(self):
        """3 区とも告知のみの synthetic HTML でも空リストを返す"""
        html = _build_html()
        adapter = HamaAikyouAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert result == []

    def test_fetch_animal_list_returns_rows_when_one_region_has_data(self):
        """1 区にデータ行があるとき、その分だけ仮想 URL リストを返す"""
        rows = (
            "<tr><td>123</td><td>雑種</td><td>オス</td><td>茶</td>"
            "<td>令和8年5月10日</td><td>中央区A町</td></tr>"
        )
        html = _build_html(chuo_section=_animal_table(rows))
        adapter = HamaAikyouAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert len(result) == 1
        url, cat = result[0]
        assert url == f"{_LIST_URL}#row=0"
        assert cat == "lost"

    def test_fetch_animal_list_aggregates_rows_across_regions(self):
        """複数区にまたがるデータ行を全て集約する"""
        chuo_rows = (
            "<tr><td>1</td><td>雑種</td><td>オス</td><td>黒</td>"
            "<td>令和8年5月1日</td><td>中央区B町</td></tr>"
        )
        hamana_rows = (
            "<tr><td>2</td><td>柴犬</td><td>メス</td><td>茶</td>"
            "<td>令和8年5月2日</td><td>浜名区C町</td></tr>"
            "<tr><td>3</td><td>雑種</td><td>オス</td><td>白</td>"
            "<td>令和8年5月3日</td><td>浜名区D町</td></tr>"
        )
        html = _build_html(
            chuo_section=_animal_table(chuo_rows),
            hamana_section=_animal_table(hamana_rows),
        )
        adapter = HamaAikyouAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert len(result) == 3
        for i, (url, cat) in enumerate(result):
            assert url == f"{_LIST_URL}#row={i}"
            assert cat == "lost"

    def test_extract_animal_details_first_row(self):
        """1 行目から RawAnimalData を構築できる（区名が location に補完される）"""
        rows = (
            "<tr><td>1</td><td>雑種</td><td>オス</td><td>茶白</td>"
            "<td>令和8年5月10日</td><td>○○町</td></tr>"
        )
        html = _build_html(chuo_section=_animal_table(rows))
        adapter = HamaAikyouAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            urls = adapter.fetch_animal_list()
            first_url, category = urls[0]
            raw = adapter.extract_animal_details(first_url, category=category)

        # 同一ページからの複数取得でも HTTP は 1 回だけ
        assert mock_get.call_count == 1
        assert isinstance(raw, RawAnimalData)
        assert raw.species == "犬"
        assert raw.sex == "オス"
        assert raw.color == "茶白"
        assert "令和8年5月10日" in raw.shelter_date
        assert "中央区" in raw.location
        assert "○○町" in raw.location
        assert raw.source_url == first_url
        assert raw.category == "lost"

    def test_species_inference_for_cat(self):
        """行テキストに「猫」が含まれるとき species は「猫」になる

        本サイトは「保護犬」だが、テキスト上の優先度は犬 > 猫 (両方含まれる
        場合は犬を返す) の素直な規則。猫単独表記なら猫を返す。
        """
        rows = (
            "<tr><td>1</td><td>猫科混血</td><td>メス</td><td>三毛</td>"
            "<td>令和8年5月12日</td><td>中央区</td></tr>"
        )
        # 「保護犬」サイト名の影響を避けるためサイト名から犬を消す
        site = _site(name="浜松市はぴまるの丘")
        html = _build_html(chuo_section=_animal_table(rows))
        adapter = HamaAikyouAdapter(site)

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="lost")

        assert raw.species == "猫"

    def test_default_species_is_dog_for_protect_dog_site(self):
        """テキストに犬猫いずれも無くてもサイト名（保護犬）から「犬」を返す"""
        rows = (
            "<tr><td>1</td><td>不明</td><td>オス</td><td>白</td>"
            "<td>令和8年5月12日</td><td>中央区</td></tr>"
        )
        html = _build_html(chuo_section=_animal_table(rows))
        adapter = HamaAikyouAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="lost")

        assert raw.species == "犬"

    def test_ignores_tables_under_non_animal_headings(self):
        """『保護されている犬を引き取るには』配下のテーブルは抽出されない"""
        # 全区とも告知のみだが、引き取り手続きセクションには 2 つの
        # 運用説明テーブルがある（_build_html 既定の状態）
        html = _build_html()
        adapter = HamaAikyouAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert result == []

    def test_extract_caches_html_across_calls(self):
        """同一 adapter インスタンスでは _http_get は 1 回だけ呼ばれる"""
        rows = (
            "<tr><td>1</td><td>雑種</td><td>オス</td><td>黒</td>"
            "<td>令和8年5月1日</td><td>A町</td></tr>"
            "<tr><td>2</td><td>柴犬</td><td>メス</td><td>白</td>"
            "<td>令和8年5月2日</td><td>B町</td></tr>"
        )
        html = _build_html(chuo_section=_animal_table(rows))
        adapter = HamaAikyouAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            urls = adapter.fetch_animal_list()
            for u, c in urls:
                adapter.extract_animal_details(u, category=c)

        assert mock_get.call_count == 1

    def test_multiple_rows_indexed_correctly_with_region_attribution(self):
        """複数区の行が index 順で正しく抽出され、location に区名が付く"""
        chuo_rows = (
            "<tr><td>1</td><td>雑種</td><td>オス</td><td>黒</td>"
            "<td>令和8年5月1日</td><td>A町</td></tr>"
        )
        tenryu_rows = (
            "<tr><td>2</td><td>柴犬</td><td>メス</td><td>白</td>"
            "<td>令和8年5月2日</td><td>B町</td></tr>"
        )
        html = _build_html(
            chuo_section=_animal_table(chuo_rows),
            tenryu_section=_animal_table(tenryu_rows),
        )
        adapter = HamaAikyouAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            assert len(urls) == 2
            raw0 = adapter.extract_animal_details(urls[0][0], category="lost")
            raw1 = adapter.extract_animal_details(urls[1][0], category="lost")

        assert "中央区" in raw0.location
        assert "A町" in raw0.location
        assert "天竜区" in raw1.location
        assert "B町" in raw1.location

    def test_image_urls_resolved_to_absolute(self):
        """行内 img の src が絶対 URL として解決される"""
        rows = (
            "<tr><td>1</td><td>雑種</td><td>オス</td><td>黒</td>"
            "<td>令和8年5月1日</td>"
            '<td><img src="/media/dog001.jpg" alt="">A町</td></tr>'
        )
        html = _build_html(chuo_section=_animal_table(rows))
        adapter = HamaAikyouAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="lost")

        assert raw.image_urls
        for u in raw.image_urls:
            assert u.startswith("https://www.hama-aikyou.jp/")

    def test_raises_parsing_error_when_no_section_headings(self):
        """区見出しすら無く empty-state も無い場合は例外を出す"""
        html = "<html><body><main><h2>無関係</h2></main></body></html>"
        adapter = HamaAikyouAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            with pytest.raises(Exception):
                adapter.fetch_animal_list()

    def test_site_registered(self):
        """サイト名が Registry に登録されている"""
        if SiteAdapterRegistry.get(_SITE_NAME) is None:
            SiteAdapterRegistry.register(_SITE_NAME, HamaAikyouAdapter)
        assert SiteAdapterRegistry.get(_SITE_NAME) is HamaAikyouAdapter
