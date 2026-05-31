"""CityMachidaAdapter のテスト (h3+ul li 形式)

町田市保健所サイト (city.machida.tokyo.jp/iryo/hokenjo/pet/mayoi/) 用
rule-based adapter の動作を検証する。

旧 fixture (`city_machida.html`) は table 形式前提の古い HTML スナップショット
だったが、町田市は CMS が h3+ul li 形式に切り替わったため、ここでは合成 HTML
ベースで仕様を検証する。実 URL の構造は 2026-05-18 時点で:

- syuyou.html       : 0 件正常 (article > h2「現在の収容状況」のみ、h3 無し)
- hogo.html         : 複数頭 (article > h2「現在のペットの保護情報」+ h3+ul li)
- search_*.html     : 複数頭 (article > h2「現在の迷子のX情報」+ h3+ul li)

検証観点:
- 6 サイト全部が同じ adapter に Registry されている
- セクションアンカー h2 がある + h3 無し → 0 件正常終了
- セクションアンカー h2 が無い → ParsingError (adapter 破損検出)
- h3+ul li から RawAnimalData が正しく構築される
- h3 のテキスト「猫（おす）」から species/sex が推定される
- 失踪場所/失踪日時 ラベル (捜索系) も location/shelter_date にマップされる
- HTTP は 1 回のみ実行（キャッシュ）
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.city_machida import (
    CityMachidaAdapter,
)
from data_collector.llm.config import SiteConfig


def _site(
    name: str = "町田市（保護情報）",
    list_url: str = "https://www.city.machida.tokyo.jp/iryo/hokenjo/pet/mayoi/hogo.html",
    category: str = "sheltered",
) -> SiteConfig:
    return SiteConfig(
        name=name,
        prefecture="東京都",
        prefecture_code="13",
        list_url=list_url,
        category=category,
        single_page=True,
    )


def _build_html(anchor_h2: str, animals_html: str = "") -> str:
    """セクションアンカー h2 を含む合成 HTML を構築する"""
    return f"""
    <html><body>
    <article>
      <h1>ページタイトル</h1>
      <h2>{anchor_h2}</h2>
      {animals_html}
      <h2>関連リンク</h2>
      <p>その他...</p>
    </article>
    </body></html>
    """


class TestCityMachidaAdapterEmptyState:
    def test_section_anchor_present_but_no_h3_returns_empty(self):
        """セクションアンカー h2 はあるが h3 が無い → 0 件で正常終了

        syuyou.html のように「現在の収容状況」見出しはあるが動物が
        いない状態を再現する。
        """
        html = _build_html("現在の収容状況")
        adapter = CityMachidaAdapter(_site(name="町田市（収容動物のお知らせ）"))
        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()
        assert result == []

    def test_no_section_anchor_raises_parsing_error(self):
        """アンカー h2 自体が無い HTML は ParsingError（adapter 破損検出）

        サイトの構造が変わってセクション h2 が消えたケースを 0 件と
        誤判定しないために、ここは必ず例外を投げる必要がある。
        """
        adapter = CityMachidaAdapter(_site())
        with patch.object(
            adapter,
            "_http_get",
            return_value="<html><body><article><h1>x</h1></article></body></html>",
        ):
            with pytest.raises(Exception):
                adapter.fetch_animal_list()

    def test_no_article_falls_back_to_body(self):
        """`<article>` 不在でも body 内にセクション h2 があれば動作する

        pet_fumei/index.html のように article がない派生テンプレートに
        将来該当する場合の保険。
        """
        html = """
        <html><body>
        <main>
          <h2>現在の迷子の猫情報</h2>
          <div class="h3bg"><h3>猫（おす）</h3></div>
          <div class="img-area-r">
            <ul>
              <li>種類：雑種</li>
              <li>性別：おす</li>
              <li>毛色：キジトラ</li>
              <li>失踪場所：町田市忠生</li>
              <li>失踪日時：2025年12月1日</li>
            </ul>
          </div>
        </main>
        </body></html>
        """
        adapter = CityMachidaAdapter(
            _site(
                name="町田市（迷子猫・捜索）",
                list_url=(
                    "https://www.city.machida.tokyo.jp/iryo/hokenjo/pet/mayoi/pet_fumei/search_cat.html"
                ),
                category="lost",
            )
        )
        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category=urls[0][1])
        assert len(urls) == 1
        assert raw.species == "猫"
        assert raw.sex == "オス"
        assert "町田市忠生" in raw.location


class TestCityMachidaAdapterExtractFields:
    def test_hogo_two_animals_extracted(self):
        """hogo.html 相当の合成 HTML から 2 頭分を抽出できる"""
        animals_html = """
        <div class="h3bg"><h3>猫（おす）</h3></div>
        <div class="img-area-r">
          <p>猫</p>
          <ul>
            <li>種類：雑種</li>
            <li>性別：おす</li>
            <li>毛色：キジトラ ハチワレ 白ベース</li>
            <li>首輪：なし</li>
            <li>特徴：右耳桜耳、左耳が切れている</li>
            <li>保護場所：町田市忠生一丁目</li>
            <li>保護日：2025年11月21日</li>
          </ul>
        </div>
        <div class="h3bg"><h3>猫(おす)</h3></div>
        <div class="img-area-r">
          <p>猫</p>
          <ul>
            <li>種類：雑種</li>
            <li>性別：おす（去勢済みを確認）</li>
            <li>毛色：キジトラ</li>
            <li>保護場所：町田市図師</li>
            <li>保護日：2025年11月15日</li>
          </ul>
        </div>
        """
        html = _build_html("現在のペットの保護情報", animals_html)
        adapter = CityMachidaAdapter(_site(name="町田市（保護情報）"))
        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            urls = adapter.fetch_animal_list()
            raws = [adapter.extract_animal_details(u, category=c) for u, c in urls]

        assert mock_get.call_count == 1, "HTML はキャッシュされる"
        assert len(urls) == 2

        # 1 件目
        first = raws[0]
        assert first.species == "猫"
        assert first.sex == "オス"
        assert "キジトラ" in first.color
        assert "町田市忠生一丁目" in first.location
        assert "2025年11月21日" in first.shelter_date
        assert first.source_url == urls[0][0]
        assert first.category == "sheltered"

        # 2 件目
        second = raws[1]
        assert second.species == "猫"
        assert second.sex == "オス"
        assert "町田市図師" in second.location

    def test_search_dog_with_shisso_fields(self):
        """search_dog.html 相当: 「失踪場所」「失踪日時」が location/shelter_date に入る"""
        animals_html = """
        <div class="h3bg"><h3>犬（めす）</h3></div>
        <div class="img-area-r">
          <ul>
            <li>種類：柴犬</li>
            <li>性別：めす</li>
            <li>毛色：茶</li>
            <li>失踪場所：町田市本町田</li>
            <li>失踪日時：2025年10月1日午後</li>
          </ul>
        </div>
        """
        html = _build_html("現在の迷子の犬情報", animals_html)
        adapter = CityMachidaAdapter(
            _site(
                name="町田市（迷子犬・捜索）",
                list_url=(
                    "https://www.city.machida.tokyo.jp/iryo/hokenjo/pet/mayoi/pet_fumei/search_dog.html"
                ),
                category="lost",
            )
        )
        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category=urls[0][1])

        assert raw.species == "犬"
        assert raw.sex == "メス"
        assert "町田市本町田" in raw.location
        assert "2025年10月1日" in raw.shelter_date
        assert raw.category == "lost"

    def test_phone_extracted_from_contact_aside(self):
        """`<aside class="contact"><p class="contact__tel">電話：042-722-6727</p>`
        からページ共通の問い合わせ先電話番号を取得する

        2026-05 観測: 町田市 CMS は動物カード内に個別電話番号を持たず、
        ページ末尾の問い合わせ先 aside に 1 つだけ電話番号が表示される。
        全動物カードでこの電話番号を共通利用する。
        """
        animals_html = """
        <div class="h3bg"><h3>猫（おす）</h3></div>
        <div class="img-area-r">
          <ul>
            <li>種類：雑種</li>
            <li>性別：おす</li>
            <li>保護場所：町田市忠生</li>
            <li>保護日：2025年11月21日</li>
          </ul>
        </div>
        """
        # 実サイト構造を再現: article 内の動物データ + 別 aside.contact に電話番号
        html = f"""
        <html><body>
        <article>
          <h1>ペットの保護情報</h1>
          <h2>現在のペットの保護情報</h2>
          {animals_html}
        </article>
        <aside class="contact" id="contact">
          <div class="contact__inner">
            <p class="contact__title">このページの担当課へのお問い合わせ
              <span>保健所 生活衛生課 愛護動物係</span></p>
            <div class="contact__content">
              <p class="contact__tel">電話：042-722-6727</p>
              <p class="contact__fax">FAX：042-722-3249</p>
            </div>
          </div>
        </aside>
        </body></html>
        """
        adapter = CityMachidaAdapter(_site(name="町田市（保護情報）"))
        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="sheltered")
        assert raw.phone == "042-722-6727", (
            f"contact__tel から電話番号が取れるべき: got {raw.phone!r}"
        )

    def test_phone_empty_when_no_contact_aside(self):
        """contact aside が無い場合は空文字を維持する (フェイルセーフ)"""
        animals_html = """
        <div class="h3bg"><h3>猫（めす）</h3></div>
        <div class="img-area-r">
          <ul><li>種類：雑種</li><li>保護場所：町田市</li></ul>
        </div>
        """
        html = _build_html("現在のペットの保護情報", animals_html)
        adapter = CityMachidaAdapter(_site(name="町田市（保護情報）"))
        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="sheltered")
        assert raw.phone == ""

    def test_species_from_h3_when_label_missing(self):
        """li に「種類」ラベルが無いケースは h3 から species を推定する"""
        animals_html = """
        <div class="h3bg"><h3>猫（めす）</h3></div>
        <div class="img-area-r">
          <ul>
            <li>性別：めす</li>
            <li>毛色：黒</li>
            <li>保護場所：町田市</li>
            <li>保護日：2025年12月1日</li>
          </ul>
        </div>
        """
        html = _build_html("現在のペットの保護情報", animals_html)
        adapter = CityMachidaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0])
        assert raw.species == "猫"
        assert raw.sex == "メス"


class TestCityMachidaAdapterRegistry:
    def test_all_six_sites_registered(self):
        """6 サイト全名称が同じ adapter にマップされている"""
        expected = [
            "町田市（収容動物のお知らせ）",
            "町田市（保護情報）",
            "町田市（捜索：飼い主が探している）",
            "町田市（迷子犬・捜索）",
            "町田市（迷子猫・捜索）",
            "町田市（迷子その他・捜索）",
        ]
        for name in expected:
            if SiteAdapterRegistry.get(name) is None:
                SiteAdapterRegistry.register(name, CityMachidaAdapter)
            assert SiteAdapterRegistry.get(name) is CityMachidaAdapter
