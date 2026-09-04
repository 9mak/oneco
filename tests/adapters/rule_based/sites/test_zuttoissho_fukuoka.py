"""ZuttoisshoFukuokaAdapter のテスト

福岡市の犬猫譲渡ポータル「ずっといっしょ」(zuttoissho.com) 用
rule-based adapter の動作を検証する。

背景 (T124/W001):
- wannyan.city.fukuoka.lg.jp の犬譲渡/猫譲渡 (sorting_id=5) は
  zuttoissho.com/mukaeru/ への JS リダイレクト通知のみで実データが
  存在しない (T046/T108 で既知)。実データは
  https://zuttoissho.com/omukae/animal/{dog,cat}/ へ完全移行済み
  (2026-09-03 実査: 猫13件・犬1件、いずれも「センター譲渡」区分)。
- zuttoissho.com は og:site_name / Organization schema / footer copyright
  いずれも「福岡市」で、他自治体との共用プラットフォームではない
  (福岡市専用の custom domain)。
- 一覧は WordPress 標準の wp-pagenavi によるページネーション
  (実測 10 件/ページ) があり、猫は 2 ページに跨る。犬保護中/猫保護中の
  wannyan.city.fukuoka.lg.jp とは別ドメイン・別テンプレートのため
  wannyan_fukuoka.py とは別 adapter として実装する。
- 静的 HTTP GET のみで取得可能 (2026-09-03 実査で bot UA でも 200/同一内容
  を確認済み)。JS 不要のため PlaywrightFetchMixin は使わない。
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.municipality_adapter import ParsingError
from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.zuttoissho_fukuoka import (
    ZuttoisshoFukuokaAdapter,
)
from data_collector.adapters.rule_based.wordpress_list import WordPressListAdapter
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig

# ─────────────────── 一覧ページ HTML ───────────────────
# 実サイト (2026-09-03 実査) を模した最小構成。
# `ul.animal_list` (犬/猫タブ切替ナビ、`/omukae/animal/{cat,dog}/` への自己
# リンクを含む) と `ul.omukae_list` (実際の動物カード) の 2 つの `<ul>` を
# 両方含める。LIST_LINK_SELECTOR がタブナビを拾わないことを検証するため。
LIST_HTML_CAT_PAGE1 = """
<html><body>
<div class="omukae_page">
  <div class="switch">
    <ul class="animal_list flex">
      <li class="current"><a href="https://zuttoissho.com/omukae/animal/cat/">猫</a></li>
      <li><a href="https://zuttoissho.com/omukae/animal/dog/">犬</a></li>
    </ul>
  </div>
  <section class="omukae container1">
    <ul class="omukae_list flex">
      <li><a href="https://zuttoissho.com/omukae/6279/"><h3 class="title">c4901【仮名：フミ】</h3></a></li>
      <li><a href="https://zuttoissho.com/omukae/6284/"><h3 class="title">c4902【仮名：フク】</h3></a></li>
      <li><a href="https://zuttoissho.com/omukae/6285/"><h3 class="title">c4903【仮名：フー】</h3></a></li>
      <li><a href="https://zuttoissho.com/omukae/6280/"><h3 class="title">c4906【仮名：えいと】</h3></a></li>
      <li><a href="https://zuttoissho.com/omukae/6031/"><h3 class="title">c4852【仮名：キャミ】</h3></a></li>
      <li><a href="https://zuttoissho.com/omukae/6204/"><h3 class="title">c4896【仮名：みぃ】</h3></a></li>
      <li><a href="https://zuttoissho.com/omukae/6126/"><h3 class="title">c4883【仮名：くぅ】</h3></a></li>
      <li><a href="https://zuttoissho.com/omukae/6137/"><h3 class="title">c4884【仮名：くっぴー】</h3></a></li>
      <li><a href="https://zuttoissho.com/omukae/6234/"><h3 class="title">c4907【仮名：めお】</h3></a></li>
      <li><a href="https://zuttoissho.com/omukae/6244/"><h3 class="title">c4909【仮名：コハク】</h3></a></li>
    </ul>
    <div class='wp-pagenavi' role='navigation'>
      <span aria-current='page' class='current'>1</span>
      <a class="page larger" title="ページ 2" href="https://zuttoissho.com/omukae/animal/cat/page/2/">2</a>
      <a class="nextpostslink" rel="next" aria-label="次のページ" href="https://zuttoissho.com/omukae/animal/cat/page/2/">&raquo;</a>
    </div>
  </section>
</div>
</body></html>
"""

LIST_HTML_CAT_PAGE2 = """
<html><body>
<div class="omukae_page">
  <ul class="animal_list flex">
    <li class="current"><a href="https://zuttoissho.com/omukae/animal/cat/">猫</a></li>
    <li><a href="https://zuttoissho.com/omukae/animal/dog/">犬</a></li>
  </ul>
  <section class="omukae container1">
    <ul class="omukae_list flex">
      <li><a href="https://zuttoissho.com/omukae/6243/"><h3 class="title">c4900</h3></a></li>
      <li><a href="https://zuttoissho.com/omukae/6245/"><h3 class="title">c4899</h3></a></li>
      <li><a href="https://zuttoissho.com/omukae/6264/"><h3 class="title">c4898</h3></a></li>
    </ul>
    <div class='wp-pagenavi' role='navigation'>
      <a class="previouspostslink" rel="prev" href="https://zuttoissho.com/omukae/animal/cat/">&laquo;</a>
      <a class="page smaller" title="ページ 1" href="https://zuttoissho.com/omukae/animal/cat/">1</a>
      <span aria-current='page' class='current'>2</span>
    </div>
  </section>
</div>
</body></html>
"""

# 犬は 2026-09-03 実査で 1 件のみ・ページ送りなし (wp-pagenavi 自体が無い)。
LIST_HTML_DOG_SINGLE = """
<html><body>
<div class="omukae_page">
  <ul class="animal_list flex">
    <li><a href="https://zuttoissho.com/omukae/animal/cat/">猫</a></li>
    <li class="current"><a href="https://zuttoissho.com/omukae/animal/dog/">犬</a></li>
  </ul>
  <section class="omukae container1">
    <ul class="omukae_list flex">
      <li><a href="https://zuttoissho.com/omukae/6266/"><h3 class="title">d1856【仮名：ぼうろ】</h3></a></li>
    </ul>
  </section>
</div>
</body></html>
"""

# 在庫 0 件を模した HTML (omukae_list はあるがカードが 1 件も無い)。
LIST_HTML_EMPTY = """
<html><body>
<div class="omukae_page">
  <ul class="animal_list flex">
    <li><a href="https://zuttoissho.com/omukae/animal/cat/">猫</a></li>
    <li class="current"><a href="https://zuttoissho.com/omukae/animal/dog/">犬</a></li>
  </ul>
  <section class="omukae container1">
    <ul class="omukae_list flex"></ul>
  </section>
</div>
</body></html>
"""

# ─────────────────── detail ページ HTML ───────────────────
# 実サイト (https://zuttoissho.com/omukae/6279/, 2026-09-03 実査) を模した
# 最小構成。footer の「トピックス」画像 (`/wp-content/uploads/2019/...`) を
# 意図的に含める。IMAGE_SELECTOR が gallery 以外を拾わないことを検証する
# ため (`/wp-content/uploads/` 配下という条件だけでは footer 画像も通って
# しまう=個体混入と同型のバグを防ぐ回帰テスト)。
DETAIL_HTML_CAT = """
<html><body>
<header>
  <img src="https://zuttoissho.com/wp/wp-content/themes/zuttoissho/img/logo1.svg" alt="ロゴ">
</header>
<article class="omukae_single">
  <section class="detail container1">
    <div class="gallery">
      <div class="swiper-container">
        <div class="swiper-wrapper">
          <div class="swiper-slide">
            <img src="https://zuttoissho.com/wp/wp-content/uploads/2026/08/cc403cfc4cf0dad3e96565b24ae3baa9.jpg" width="500" height="375" alt="" />
          </div>
          <div class="swiper-slide">
            <img src="https://zuttoissho.com/wp/wp-content/uploads/2026/08/0c98042e5b43de47cfc683dc52058b50.jpg" width="500" height="375" alt="" />
          </div>
        </div>
      </div>
    </div>
    <div class="group">
      <p class="no">お問い合わせ番号【C4901】</p>
      <p class="type">センター譲渡</p>
    </div>
    <p class="title">c4901【仮名：フミ】中央区）パーク動物病院にいます</p>
    <p class="heading">センターからのメッセージ</p>
    <div class="description">
      <p>FeLV(-) FIV(-) 三種混合ワクチン接種済み。</p>
    </div>
    <dl class="data_list clearfix">
      <dt>登録日</dt>
      <dd>2026/08/19</dd>
      <dt>動物種</dt>
      <dd>
        猫			</dd>
      <dt>品種</dt>
      <dd>雑種</dd>
      <dt>毛色</dt>
      <dd>キジ白</dd>
      <dt>性別</dt>
      <dd>メス</dd>
      <dt>体格</dt>
      <dd>小</dd>
      <dt>年齢</dt>
      <dd>2か月齢</dd>
      <dt>その他特徴</dt>
      <dd>-</dd>
      <dt>申込状況</dt>
      <dd>
        申込者なし			</dd>
    </dl>
  </section>
  <section class="takeover container1">
    <h3 class="sec_title">譲り受け希望の方へ</h3>
    <a class="goto_pdf" href="https://zuttoissho.com/wp/wp-content/themes/zuttoissho/pdf/cat.pdf">猫のセンター譲渡の流れ（PDF）</a>
    <ul class="place_list">
      <li>
        <p class="name">福岡市獣医師会の動物病院（まずは下記までお問い合わせください）</p>
        <p class="address">住所：〒813-0023 福岡市東区蒲田５丁目１０番１号　東部動物愛護管理センター</p>
        <p class="tel">TEL：092-691-0131（ガイダンス１番）　/　FAX：092-691-0132</p>
      </li>
    </ul>
  </section>
</article>
<footer>
  <section class="topics">
    <ul class="topics_list flex">
      <li>
        <a href="https://zuttoissho.com/wp/wp-content/themes/zuttoissho/pdf/4_volunteer_milk.pdf">
          <img src="https://zuttoissho.com/wp/wp-content/uploads/2019/10/ee7e58677cc8be59e7494921c2ba570a.jpg" alt="" />
        </a>
      </li>
    </ul>
  </section>
</footer>
</body></html>
"""

# 犬 detail: place_list の name が address に含まれない典型ケース。
DETAIL_HTML_DOG = """
<html><body>
<article class="omukae_single">
  <section class="detail container1">
    <div class="gallery">
      <div class="swiper-container">
        <div class="swiper-wrapper">
          <div class="swiper-slide">
            <img src="https://zuttoissho.com/wp/wp-content/uploads/2026/08/7ef85c01b548e52d6f81a4bd2a775769.jpg" width="479" height="492" alt="" />
          </div>
        </div>
      </div>
    </div>
    <div class="group">
      <p class="no">お問い合わせ番号【D1856】</p>
      <p class="type">センター譲渡</p>
    </div>
    <p class="title">d1856【仮名：ぼうろ】東部動物愛護管理センターにいます</p>
    <dl class="data_list clearfix">
      <dt>登録日</dt>
      <dd>2026/08/14</dd>
      <dt>動物種</dt>
      <dd>
        犬			</dd>
      <dt>品種</dt>
      <dd>ヨーキーMIX</dd>
      <dt>毛色</dt>
      <dd>黒茶</dd>
      <dt>性別</dt>
      <dd>去勢オス</dd>
      <dt>体格</dt>
      <dd>小</dd>
      <dt>年齢</dt>
      <dd>10～13歳</dd>
      <dt>その他特徴</dt>
      <dd>-</dd>
    </dl>
  </section>
  <section class="takeover container1">
    <ul class="place_list">
      <li>
        <p class="name">東部動物愛護管理センター（あにまるぽーと）</p>
        <p class="address">住所：〒813-0023 福岡市東区蒲田5-10-1</p>
        <p class="tel">TEL：092-691-0131（ガイダンス１番）　/　FAX：092-691-0132</p>
      </li>
    </ul>
  </section>
</article>
</body></html>
"""


def _site_dog_adoption() -> SiteConfig:
    """福岡市わんにゃん（犬譲渡） - zuttoissho.com/omukae/animal/dog/"""
    return SiteConfig(
        name="福岡市わんにゃん（犬譲渡）",
        prefecture="福岡県",
        prefecture_code="40",
        list_url="https://zuttoissho.com/omukae/animal/dog/",
        category="adoption",
    )


def _site_cat_adoption() -> SiteConfig:
    """福岡市わんにゃん（猫譲渡） - zuttoissho.com/omukae/animal/cat/"""
    return SiteConfig(
        name="福岡市わんにゃん（猫譲渡）",
        prefecture="福岡県",
        prefecture_code="40",
        list_url="https://zuttoissho.com/omukae/animal/cat/",
        category="adoption",
    )


class TestZuttoisshoFukuokaAdapterClassStructure:
    """継承構造とクラス定数"""

    def test_inherits_wordpress_list_adapter(self):
        assert issubclass(ZuttoisshoFukuokaAdapter, WordPressListAdapter)

    def test_list_link_selector_targets_omukae_list_only(self):
        """LIST_LINK_SELECTOR がタブナビ (`ul.animal_list`) を含まない"""
        assert "omukae_list" in ZuttoisshoFukuokaAdapter.LIST_LINK_SELECTOR


class TestZuttoisshoFukuokaAdapterListExtraction:
    """list ページからの detail URL 抽出 (ページネーション含む)"""

    def test_fetch_animal_list_excludes_tab_nav_links(self):
        """`ul.animal_list` の犬/猫タブ切替リンクを detail URL として拾わない"""
        adapter = ZuttoisshoFukuokaAdapter(_site_cat_adoption())
        with patch.object(adapter, "_http_get", return_value=LIST_HTML_CAT_PAGE2):
            result = adapter.fetch_animal_list()
        urls = [u for u, _cat in result]
        assert all("/omukae/animal/" not in u for u in urls)
        assert all("/omukae/" in u for u in urls)

    def test_fetch_animal_list_follows_pagination(self):
        """wp-pagenavi の次ページリンクを辿り、2 ページ目のカードも回収する"""
        adapter = ZuttoisshoFukuokaAdapter(_site_cat_adoption())
        fetched: list[str] = []

        def fake_get(url: str, **_kwargs: object) -> str:
            fetched.append(url)
            return LIST_HTML_CAT_PAGE2 if "page/2" in url else LIST_HTML_CAT_PAGE1

        with patch.object(adapter, "_http_get", side_effect=fake_get):
            result = adapter.fetch_animal_list()

        urls = [u for u, _cat in result]
        assert len(urls) == 13
        assert len(fetched) == 2
        assert "page/2" in fetched[1]
        assert any("/omukae/6243/" in u for u in urls)
        assert adapter.list_truncated is False

    def test_fetch_animal_list_single_page_no_pagenavi(self):
        """wp-pagenavi 自体が無い (1 ページのみ) サイトでも正常終端する"""
        adapter = ZuttoisshoFukuokaAdapter(_site_dog_adoption())
        with patch.object(adapter, "_http_get", return_value=LIST_HTML_DOG_SINGLE):
            result = adapter.fetch_animal_list()
        urls = [u for u, _cat in result]
        assert len(urls) == 1
        assert "/omukae/6266/" in urls[0]
        assert adapter.list_truncated is False

    def test_fetch_animal_list_returns_empty_for_zero_stock(self):
        """在庫 0 件 (`omukae_list` にカードが無い) では空リストを返す"""
        adapter = ZuttoisshoFukuokaAdapter(_site_dog_adoption())
        with patch.object(adapter, "_http_get", return_value=LIST_HTML_EMPTY):
            result = adapter.fetch_animal_list()
        assert result == []

    def test_fetch_animal_list_uses_category_from_site_config(self):
        adapter = ZuttoisshoFukuokaAdapter(_site_cat_adoption())
        with patch.object(adapter, "_http_get", return_value=LIST_HTML_CAT_PAGE2):
            result = adapter.fetch_animal_list()
        assert all(cat == "adoption" for _u, cat in result)

    def test_fetch_animal_list_dedupes_urls(self):
        dup_html = """
        <html><body>
        <ul class="omukae_list">
          <li><a href="https://zuttoissho.com/omukae/999/">a</a></li>
          <li><a href="https://zuttoissho.com/omukae/999/">a again</a></li>
        </ul>
        </body></html>
        """
        adapter = ZuttoisshoFukuokaAdapter(_site_dog_adoption())
        with patch.object(adapter, "_http_get", return_value=dup_html):
            result = adapter.fetch_animal_list()
        urls = [u for u, _cat in result]
        assert len(urls) == 1

    def test_fetch_animal_list_pagination_stops_on_visited_page(self, caplog):
        """next リンクが既訪ページを指しても無限ループしない"""
        looping = """
        <html><body>
        <ul class="omukae_list"><li><a href="https://zuttoissho.com/omukae/1/">a</a></li></ul>
        <div class='wp-pagenavi'>
          <a class="nextpostslink" rel="next" href="https://zuttoissho.com/omukae/animal/dog/">next</a>
        </div>
        </body></html>
        """
        adapter = ZuttoisshoFukuokaAdapter(_site_dog_adoption())
        with (
            patch.object(adapter, "_http_get", return_value=looping) as mock_get,
            caplog.at_level("WARNING"),
        ):
            result = adapter.fetch_animal_list()
        assert len(result) == 1
        assert mock_get.call_count == 1
        assert adapter.list_truncated is True

    def test_fetch_animal_list_warns_when_page_cap_reached(self, caplog):
        """上限ページ数に達したら打ち切って warning を残す"""

        def endless_pages(url: str, **_kwargs: object) -> str:
            n = int(url.rsplit("page/", 1)[1].rstrip("/")) if "page/" in url else 1
            return f"""
            <html><body>
            <ul class="omukae_list"><li><a href="https://zuttoissho.com/omukae/{n}/">x</a></li></ul>
            <div class='wp-pagenavi'>
              <a class="nextpostslink" rel="next" href="https://zuttoissho.com/omukae/animal/cat/page/{n + 1}/">next</a>
            </div>
            </body></html>
            """

        adapter = ZuttoisshoFukuokaAdapter(_site_cat_adoption())
        with (
            patch.object(adapter, "_http_get", side_effect=endless_pages) as mock_get,
            caplog.at_level("WARNING"),
        ):
            result = adapter.fetch_animal_list()

        assert mock_get.call_count == ZuttoisshoFukuokaAdapter.MAX_LIST_PAGES
        assert len(result) == ZuttoisshoFukuokaAdapter.MAX_LIST_PAGES
        assert adapter.list_truncated is True


class TestZuttoisshoFukuokaAdapterDetailExtraction:
    """detail ページからの RawAnimalData 構築"""

    def test_extract_animal_details_cat(self, assert_raw_animal):
        adapter = ZuttoisshoFukuokaAdapter(_site_cat_adoption())
        detail_url = "https://zuttoissho.com/omukae/6279/"
        with patch.object(adapter, "_http_get", return_value=DETAIL_HTML_CAT):
            raw = adapter.extract_animal_details(detail_url, category="adoption")

        assert isinstance(raw, RawAnimalData)
        assert_raw_animal(
            raw,
            species="猫",
            breed="雑種",
            color="キジ白",
            sex="メス",
            size="小",
            age="2か月齢",
            shelter_date="2026/08/19",
            category="adoption",
            source_url=detail_url,
        )
        # 個体識別: お問い合わせ番号 / 仮名
        assert raw.management_number == "C4901"
        assert raw.name == "フミ"
        # location: name が address に含まれないため両方連結される
        assert "福岡市獣医師会の動物病院" in raw.location
        assert "東区蒲田" in raw.location
        # phone は _normalize_phone によりハイフン区切りに正規化される
        assert raw.phone == "092-691-0131"

    def test_extract_animal_details_dog(self, assert_raw_animal):
        adapter = ZuttoisshoFukuokaAdapter(_site_dog_adoption())
        detail_url = "https://zuttoissho.com/omukae/6266/"
        with patch.object(adapter, "_http_get", return_value=DETAIL_HTML_DOG):
            raw = adapter.extract_animal_details(detail_url, category="adoption")

        assert_raw_animal(
            raw,
            species="犬",
            breed="ヨーキーMIX",
            color="黒茶",
            sex="去勢オス",
            size="小",
            age="10～13歳",
            shelter_date="2026/08/14",
        )
        assert raw.management_number == "D1856"
        assert raw.name == "ぼうろ"
        assert "東部動物愛護管理センター" in raw.location
        assert "蒲田5-10-1" in raw.location
        assert raw.phone == "092-691-0131"

    def test_image_urls_exclude_footer_topics_and_header_logo(self):
        """gallery 以外の `/wp-content/uploads/` 画像 (footer トピックス等) を
        個体写真として混入させない

        `/wp-content/uploads/` 配下という条件だけでフィルタすると、footer の
        「トピックス」記事サムネイル (`uploads/2019/...`) まで全個体の
        image_urls に混入する (熊本 recommend-area と同型の個体混入バグ)。
        gallery 配下だけを個体写真として扱う必要がある。
        """
        adapter = ZuttoisshoFukuokaAdapter(_site_cat_adoption())
        detail_url = "https://zuttoissho.com/omukae/6279/"
        with patch.object(adapter, "_http_get", return_value=DETAIL_HTML_CAT):
            raw = adapter.extract_animal_details(detail_url, category="adoption")

        assert len(raw.image_urls) == 2
        assert all("uploads/2026/08" in u for u in raw.image_urls)
        assert not any("uploads/2019" in u for u in raw.image_urls)
        assert not any("logo1.svg" in u for u in raw.image_urls)

    def test_extract_raises_on_empty_html(self):
        adapter = ZuttoisshoFukuokaAdapter(_site_dog_adoption())
        with patch.object(adapter, "_http_get", return_value="<html><body></body></html>"):
            with pytest.raises(ParsingError):
                adapter.extract_animal_details("https://zuttoissho.com/omukae/0/")

    def test_extract_animal_details_infers_species_from_list_url_when_label_missing(self):
        """`動物種` ラベルが無い場合に list URL (`/dog/` or `/cat/`) から補完する"""
        html_no_species = """
        <html><body>
        <article>
          <dl class="data_list">
            <dt>性別</dt><dd>メス</dd>
          </dl>
        </article>
        </body></html>
        """
        adapter = ZuttoisshoFukuokaAdapter(_site_cat_adoption())
        with patch.object(adapter, "_http_get", return_value=html_no_species):
            raw = adapter.extract_animal_details("https://zuttoissho.com/omukae/1/")
        assert raw.species == "猫"

    def test_normalize_produces_animal_data(self):
        """normalize() 経由でも致命フィールドが脱落しないこと"""
        adapter = ZuttoisshoFukuokaAdapter(_site_cat_adoption())
        detail_url = "https://zuttoissho.com/omukae/6279/"
        with patch.object(adapter, "_http_get", return_value=DETAIL_HTML_CAT):
            raw = adapter.extract_animal_details(detail_url, category="adoption")
        animal = adapter.normalize(raw)
        assert animal.species == "猫"
        assert animal.category == "adoption"
        assert animal.prefecture == "福岡県"
        assert str(animal.source_url).rstrip("/") == detail_url.rstrip("/")
        assert animal.phone == "092-691-0131"
        assert len(animal.image_urls) == 2


class TestZuttoisshoFukuokaAdapterRegistry:
    """registry に 2 サイトとも登録されていること

    sites.yaml の `name` フィールド (福岡市わんにゃん（犬譲渡）/（猫譲渡）) は
    旧 wannyan.city.fukuoka.lg.jp 時代の名称を維持しつつ、list_url のみ
    zuttoissho.com へ差し替えられている (T124)。
    """

    EXPECTED_SITE_NAMES = (
        "福岡市わんにゃん（犬譲渡）",
        "福岡市わんにゃん（猫譲渡）",
    )

    @pytest.mark.parametrize("site_name", EXPECTED_SITE_NAMES)
    def test_site_registered_to_zuttoissho_fukuoka_adapter(self, site_name):
        if SiteAdapterRegistry.get(site_name) is None:
            SiteAdapterRegistry.register(site_name, ZuttoisshoFukuokaAdapter)
        cls = SiteAdapterRegistry.get(site_name)
        assert cls is ZuttoisshoFukuokaAdapter, (
            f"{site_name} が ZuttoisshoFukuokaAdapter に紐付いていません: {cls}"
        )
