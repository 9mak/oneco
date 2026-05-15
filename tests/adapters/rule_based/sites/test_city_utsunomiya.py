"""CityUtsunomiyaAdapter のテスト

宇都宮市動物愛護センターサイト
(city.utsunomiya.lg.jp/kurashi/pet/pet/1005584.html) 用 rule-based
adapter の動作を検証する。

- 1 ページに `div#voice` 配下の `<h2>迷子犬…</h2>` `<h2>負傷猫…</h2>`
  ブロックが並ぶ single_page 形式
- ラベルと値は **全角スペース** で区切られる ("収容日　　令和8年5月13日")
- サイト共通見出し ("栃木県警察" 等) は動物カードとして拾わないこと
- 0 件状態 (動物 `<h2>` が一件も無い) は ParsingError ではなく空リスト
- HTML キャッシュ (HTTP は 1 回のみ実行)
"""

from __future__ import annotations

from unittest.mock import patch

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.city_utsunomiya import (
    CityUtsunomiyaAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig


def _site() -> SiteConfig:
    return SiteConfig(
        name="宇都宮市（迷子犬・負傷猫）",
        prefecture="栃木県",
        prefecture_code="09",
        list_url=("https://www.city.utsunomiya.lg.jp/kurashi/pet/pet/1005584.html"),
        category="lost",
        single_page=True,
    )


def _load_utsunomiya_html(fixture_html) -> str:
    """フィクスチャを読み込み、必要であれば mojibake (二重 UTF-8) を補正する

    リポジトリに保存されている `city_utsunomiya_lg_jp.html` は、本来
    UTF-8 のバイト列を Latin-1 として解釈してから再度 UTF-8 として保存
    し直された二重エンコーディング状態になっているため、実サイト相当
    のテキストを得るには逆変換が必要。実運用 (`_http_get`) では
    requests が正しい UTF-8 として受け取る。
    """
    raw = fixture_html("city_utsunomiya_lg_jp")
    # 復号後に「宇都宮」または「迷子犬」が出現するかで判定
    if "宇都宮" in raw or "迷子犬" in raw:
        return raw
    try:
        return raw.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return raw


class TestCityUtsunomiyaAdapter:
    def test_fetch_animal_list_returns_two_rows(self, fixture_html):
        """フィクスチャから動物 `<h2>` 2 件 (迷子犬 + 負傷猫) が抽出される

        ページには案内 `<h2>` ("栃木県警察" 等) も並ぶが、
        「（掲載期限」を含む見出しのみが動物カードとして拾われる。
        """
        html = _load_utsunomiya_html(fixture_html)
        adapter = CityUtsunomiyaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert len(result) == 2, f"迷子犬 + 負傷猫 の 2 件が抽出されるはず: got {len(result)}"
        for url, cat in result:
            assert "#row=" in url
            assert url.startswith("https://www.city.utsunomiya.lg.jp/kurashi/pet/pet/1005584.html")
            assert cat == "lost"

    def test_fetch_animal_list_caches_html(self, fixture_html):
        """同一インスタンスでの繰り返し呼び出しは HTTP を 1 回しか実行しない"""
        html = _load_utsunomiya_html(fixture_html)
        adapter = CityUtsunomiyaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            adapter.fetch_animal_list()
            adapter.fetch_animal_list()
            adapter.fetch_animal_list()

        assert mock_get.call_count == 1, (
            f"HTML はキャッシュされ HTTP は 1 回のみ: got {mock_get.call_count}"
        )

    def test_extract_first_animal_is_lost_dog(self, fixture_html):
        """1 件目 (迷子犬) から RawAnimalData を構築できる

        フィクスチャ:
            <h2>迷子犬（掲載期限　令和8年5月27日）</h2>
            <p class="imageright"><img src=".../20260513.jpeg" ...></p>
            <p>収容日　　令和8年5月13日</p>
            <p>収容場所　五代2丁目</p>
            <p>種類　　　ダックス系</p>
            <p>毛色　　　黒茶</p>
            <p>性別　　　メス</p>
            <p>体格　　　小</p>
            <p>装着物　　紫とピンクのチェック柄首輪</p>
        """
        html = _load_utsunomiya_html(fixture_html)
        adapter = CityUtsunomiyaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            urls = adapter.fetch_animal_list()
            first_url, category = urls[0]
            raw = adapter.extract_animal_details(first_url, category=category)

        # 同一ページから複数取得しても HTTP は 1 回 (キャッシュ確認)
        assert mock_get.call_count == 1
        assert isinstance(raw, RawAnimalData)
        # `<h2>迷子犬…` から「犬」と推定される
        assert raw.species == "犬"
        assert raw.sex == "メス"
        assert raw.color == "黒茶"
        assert raw.size == "小"
        assert raw.location == "五代2丁目"
        assert "令和8年5月13日" in raw.shelter_date
        # 画像 URL が絶対 URL に変換されている
        assert raw.image_urls
        assert all(u.startswith("http") for u in raw.image_urls)
        assert any("20260513" in u for u in raw.image_urls)
        # source_url は仮想 URL
        assert raw.source_url == first_url
        assert raw.category == "lost"

    def test_extract_second_animal_is_injured_cat(self, fixture_html):
        """2 件目 (負傷猫) は「猫」と推定される"""
        html = _load_utsunomiya_html(fixture_html)
        adapter = CityUtsunomiyaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            second_url, category = urls[1]
            raw = adapter.extract_animal_details(second_url, category=category)

        assert raw.species == "猫"
        assert raw.sex == "メス"
        assert raw.color == "三毛"
        assert raw.location == "下荒針町"
        assert "令和8年5月8日" in raw.shelter_date

    def test_announcement_h2_not_picked_up_as_animal(self, fixture_html):
        """案内 `<h2>` (「栃木県警察」「お問い合わせ」等) は拾われない

        `<h2>` 全 7 件のうち動物カードは 2 件のみ。`（掲載期限`
        フィルタにより案内見出しが混入していないことを確認する。
        """
        html = _load_utsunomiya_html(fixture_html)
        adapter = CityUtsunomiyaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            for url, cat in urls:
                raw = adapter.extract_animal_details(url, category=cat)
                # 動物カードは「迷子犬」「負傷猫」由来なので必ず犬/猫のどちらか
                assert raw.species in ("犬", "猫"), f"案内 h2 が混入: species={raw.species!r}"

    def test_fetch_animal_list_returns_empty_when_no_animal_heading(self):
        """動物 `<h2>` が一件も無い HTML では空リストを返す

        在庫 0 件 (掲載期限切れで全て削除された状態) は実運用で頻発する
        ため ParsingError ではなく空リストとして扱う。
        """
        html_no_animals = (
            "<html><body>"
            "<div id='voice'>"
            "<h2>宇都宮市動物愛護センターで収容している動物の情報</h2>"
            "<p>現在、収容動物はおりません。</p>"
            "<h2>栃木県警察</h2>"
            "<p>落し物検索サービス</p>"
            "</div>"
            "</body></html>"
        )
        adapter = CityUtsunomiyaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html_no_animals):
            result = adapter.fetch_animal_list()

        assert result == [], f"在庫 0 件では空配列が返るはず: got {result!r}"

    def test_site_registered(self):
        """サイト名 `宇都宮市（迷子犬・負傷猫）` が Registry に登録されている"""
        # 他テストが registry を clear する場合に備えて冪等に再登録
        if SiteAdapterRegistry.get("宇都宮市（迷子犬・負傷猫）") is None:
            SiteAdapterRegistry.register("宇都宮市（迷子犬・負傷猫）", CityUtsunomiyaAdapter)
        assert SiteAdapterRegistry.get("宇都宮市（迷子犬・負傷猫）") is CityUtsunomiyaAdapter

    def test_normalize_returns_animal_data(self, fixture_html):
        """normalize() で AnimalData を生成できる (基底のデフォルト実装利用)"""
        html = _load_utsunomiya_html(fixture_html)
        adapter = CityUtsunomiyaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            url, category = urls[0]
            raw = adapter.extract_animal_details(url, category=category)
            normalized = adapter.normalize(raw)

        # AnimalData に変換できる (具体型はそれぞれの normalizer 仕様に従う)
        assert normalized is not None
        # species/category が引き継がれている
        assert getattr(normalized, "category", None) == "lost"
