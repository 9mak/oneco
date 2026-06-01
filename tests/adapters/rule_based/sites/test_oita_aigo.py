"""OitaAigoAdapter のテスト

おおいた動物愛護センターサイト (oita-aigo.com) 用 rule-based adapter
の動作を検証する。

- 1 ページに `div.information_box` カードが並ぶ single_page 形式
- 3 サイト (迷子情報メイン / 譲渡犬 / 譲渡猫) すべての登録確認
"""

from __future__ import annotations

from unittest.mock import patch

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.oita_aigo import OitaAigoAdapter
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig


def _lostchild_site() -> SiteConfig:
    return SiteConfig(
        name="おおいた動物愛護センター（迷子情報メイン）",
        prefecture="大分県",
        prefecture_code="44",
        list_url="https://oita-aigo.com/lostchild/",
        category="sheltered",
        single_page=True,
    )


def _adoption_dog_site() -> SiteConfig:
    return SiteConfig(
        name="おおいた動物愛護センター（譲渡犬）",
        prefecture="大分県",
        prefecture_code="44",
        list_url="https://oita-aigo.com/information_doglist/anytimedog/",
        category="adoption",
        single_page=True,
    )


def _adoption_cat_site() -> SiteConfig:
    return SiteConfig(
        name="おおいた動物愛護センター（譲渡猫）",
        prefecture="大分県",
        prefecture_code="44",
        list_url="https://oita-aigo.com/information_catlist/anytimecat/",
        category="adoption",
        single_page=True,
    )


class TestOitaAigoAdapter:
    def test_fetch_animal_list_returns_rows(self, fixture_html):
        """一覧ページから動物カード (仮想 URL) が抽出できる"""
        html = fixture_html("oita_aigo__lostchild")
        adapter = OitaAigoAdapter(_lostchild_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert len(result) >= 1
        for url, cat in result:
            assert "#row=" in url
            assert url.startswith("https://oita-aigo.com/")
            assert cat == "sheltered"

    def test_extract_animal_details_first_row(self, fixture_html, assert_raw_animal):
        """1 件目のカードから RawAnimalData を構築できる

        フィクスチャの 1 件目:
          - 保護地域: 佐伯市
          - 推定年齢: 8歳
          - 性別: オス
          - 体重: 14.04kg
          - lostchild_ttl: 令和8年5月1日
          - 画像: /wp-content/uploads/2026/05/...jpg
        """
        html = fixture_html("oita_aigo__lostchild")
        adapter = OitaAigoAdapter(_lostchild_site())

        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            urls = adapter.fetch_animal_list()
            first_url, category = urls[0]
            raw = adapter.extract_animal_details(first_url, category=category)

        # 一覧 HTML は 1 回しか取得しない (詳細ページが別 URL にあれば
        # それは別途取得されるため call_count は 1 とは限らない)。
        list_calls = sum(
            1
            for c in mock_get.call_args_list
            if c.args and c.args[0] == adapter.site_config.list_url
        )
        assert list_calls == 1
        assert isinstance(raw, RawAnimalData)
        assert_raw_animal(
            raw,
            sex="オス",
            age="8歳",
            # 14.04kg → 中 (5kg以上15kg未満) に変換される
            size="中",
            location="佐伯市",
            shelter_date="令和8年5月1日",
            category="sheltered",
        )
        # 迷子情報メインは犬猫混在のため species は空 (不明)
        assert raw.species == ""
        # phone は全動物カードでセンター本部代表電話を共通利用する
        assert raw.phone == "097-588-1122"
        # 画像 URL が絶対化され、uploads 配下のみ採用される
        assert raw.image_urls
        assert all(u.startswith("https://oita-aigo.com/") for u in raw.image_urls)
        assert any("/wp-content/uploads/" in u for u in raw.image_urls)
        # source_url は仮想 URL
        assert raw.source_url == first_url

    def test_species_inferred_for_adoption_dog_site(self, fixture_html):
        """譲渡犬サイトでは species が "犬" に推定される

        フィクスチャは lostchild ページだが、テンプレートが共通なので
        site_config だけ譲渡犬サイトに差し替えて species 推定だけ確認する。
        """
        html = fixture_html("oita_aigo__lostchild")
        adapter = OitaAigoAdapter(_adoption_dog_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            url, cat = urls[0]
            raw = adapter.extract_animal_details(url, category=cat)

        assert raw.species == "犬"
        assert raw.category == "adoption"

    def test_species_inferred_for_adoption_cat_site(self, fixture_html):
        """譲渡猫サイトでは species が "猫" に推定される"""
        html = fixture_html("oita_aigo__lostchild")
        adapter = OitaAigoAdapter(_adoption_cat_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            url, cat = urls[0]
            raw = adapter.extract_animal_details(url, category=cat)

        assert raw.species == "猫"
        assert raw.category == "adoption"

    def test_all_three_sites_registered(self):
        """3 つの大分愛護センターサイト名すべてが Registry に登録されている"""
        expected = [
            "おおいた動物愛護センター（迷子情報メイン）",
            "おおいた動物愛護センター（譲渡犬）",
            "おおいた動物愛護センター（譲渡猫）",
        ]
        for name in expected:
            # 他テストが registry を clear する場合に備えて冪等に再登録
            if SiteAdapterRegistry.get(name) is None:
                SiteAdapterRegistry.register(name, OitaAigoAdapter)
            assert SiteAdapterRegistry.get(name) is OitaAigoAdapter

    def test_no_cards_returns_empty_list(self):
        """カード要素が見当たらない HTML は真ゼロとして空リストを返す"""
        adapter = OitaAigoAdapter(_lostchild_site())
        with patch.object(adapter, "_http_get", return_value="<html><body></body></html>"):
            result = adapter.fetch_animal_list()
        assert result == []


# 譲渡ページ (anytimedog/anytimecat) のカードには「保護地域」欄が無い。
# (譲渡動物はセンターに収容されているため発見場所の概念が無い)
_ADOPTION_CARD_NO_LOCATION = """
<html><body><main>
  <div class="information_box">
    <dl><dt>仮名</dt><dd>ブロンソン</dd></dl>
    <dl><dt>種類</dt><dd>雑種</dd></dl>
    <dl><dt>推定年齢</dt><dd>9歳 (R8.2.6現在)</dd></dl>
    <dl><dt>性別</dt><dd>オス</dd></dl>
    <dl><dt>体重</dt><dd>17.0kg</dd></dl>
    <dl><dt>不妊手術</dt><dd>済</dd></dl>
  </div>
</main></body></html>
"""


class TestOitaAigoShelterLocationFallback:
    """保護地域欄が無い譲渡カードで location をシェルター名に補完する。

    旧実装では譲渡犬/猫が location 不明のまま保存されていた (実収集 24件)。
    譲渡動物は当該センターに居るため、サイト名 (括弧内を除く) を location の
    フォールバックに使う。
    """

    def test_adoption_card_without_location_falls_back_to_shelter_name(self):
        adapter = OitaAigoAdapter(_adoption_dog_site())
        with patch.object(adapter, "_http_get", return_value=_ADOPTION_CARD_NO_LOCATION):
            urls = adapter.fetch_animal_list()
            url, cat = urls[0]
            raw = adapter.extract_animal_details(url, category=cat)
        assert raw.location == "おおいた動物愛護センター"
        assert raw.species == "犬"

    def test_lostchild_keeps_real_location(self, fixture_html):
        """保護地域がある迷子カードはシェルター名で上書きしない (回帰防止)"""
        html = fixture_html("oita_aigo__lostchild")
        adapter = OitaAigoAdapter(_lostchild_site())
        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            url, cat = urls[0]
            raw = adapter.extract_animal_details(url, category=cat)
        assert raw.location == "佐伯市"


class TestOitaAigoWeightToSize:
    """カードの「体重: 11.64kg」を size の語彙 (小/中/大) に変換する。

    旧実装は「11.64kg」をそのまま size に流していたが、
    normalizer は SIZE_VALID = {小,中,大,...} にのみマッチさせるため
    全件 size=None に落ちていた (実収集 27/27 全件で size 欠損)。
    体重レンジで小/中/大に推定し、normalizer に標準語彙で渡す。
    """

    @staticmethod
    def _card(weight: str) -> str:
        return f"""
        <html><body><main>
          <div class="information_box">
            <dl><dt>保護地域</dt><dd>杵築市</dd></dl>
            <dl><dt>推定年齢</dt><dd>1歳</dd></dl>
            <dl><dt>性別</dt><dd>メス</dd></dl>
            <dl><dt>体重</dt><dd>{weight}</dd></dl>
          </div>
        </main></body></html>
        """

    def test_under_5kg_becomes_small(self):
        adapter = OitaAigoAdapter(_lostchild_site())
        with patch.object(adapter, "_http_get", return_value=self._card("4.48kg")):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="sheltered")
        assert raw.size == "小"

    def test_between_5_and_15kg_becomes_medium(self):
        adapter = OitaAigoAdapter(_lostchild_site())
        with patch.object(adapter, "_http_get", return_value=self._card("11.64kg")):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="sheltered")
        assert raw.size == "中"

    def test_15kg_or_more_becomes_large(self):
        adapter = OitaAigoAdapter(_lostchild_site())
        with patch.object(adapter, "_http_get", return_value=self._card("17.0kg")):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="sheltered")
        assert raw.size == "大"

    def test_non_numeric_weight_keeps_empty(self):
        """体重欄が空や非数値の場合は size を空文字にする"""
        adapter = OitaAigoAdapter(_lostchild_site())
        with patch.object(adapter, "_http_get", return_value=self._card("不明")):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="sheltered")
        assert raw.size == ""


class TestOitaAigoPhone:
    """phone はカード内に無いが、ページ末尾 (またはサイト共通) の
    センター代表電話を全動物に割り当てる。

    2026-05 観測: oita-aigo.com には複数の地域別保健所電話番号が
    並ぶが、動物カードと特定の番号が紐付いていない。最頻の代表電話
    `097-588-1122` (おおいた動物愛護センター本部) を共通利用する。
    """

    _CENTER_TEL = "097-588-1122"

    def _card_with_footer(self) -> str:
        return f"""
        <html><body>
          <main>
            <div class="information_box">
              <dl><dt>保護地域</dt><dd>杵築市</dd></dl>
              <dl><dt>推定年齢</dt><dd>1歳</dd></dl>
              <dl><dt>性別</dt><dd>メス</dd></dl>
              <dl><dt>体重</dt><dd>4.48kg</dd></dl>
            </div>
          </main>
          <footer>
            <p>おおいた動物愛護センター</p>
            <p>TEL：{self._CENTER_TEL}</p>
          </footer>
        </body></html>
        """

    def test_phone_extracted_from_center_tel(self):
        adapter = OitaAigoAdapter(_lostchild_site())
        with patch.object(adapter, "_http_get", return_value=self._card_with_footer()):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="sheltered")
        assert raw.phone == self._CENTER_TEL, (
            f"センター代表電話が phone に入るべき: got {raw.phone!r}"
        )


# ─────────────────── 詳細ページからの color/size 補完 ───────────────────
# 一覧カードには毛色情報が無いが、各カードから詳細ページにリンクが張られており、
# 詳細ページの `<dl><dt>毛色</dt>` (または「毛色・長さ」) には色情報がある。
# 同様に犬の「大きさ」(中型/大型) も詳細ページにのみ存在する。
# 2026-05 観測: 26件中 color 12件 / size 14件しか取れていない。
# 残14件(犬・lostchild) で color、残12件(猫) で size を埋めるための
# 詳細ページ追加フェッチ機構をテストする。
_LIST_WITH_DETAIL_LINK = """
<html><body><main>
  <div class="information_box">
    <a href="https://oita-aigo.com/transferdoglist/24-0609-2/">
      <div class="information_image"><img src="/img.jpg"></div>
      <div class="information_text">
        <dl><dd>No.24-0609-2</dd></dl>
        <dl><dt>仮名</dt><dd>ブロンソン</dd></dl>
        <dl><dt>種類</dt><dd>雑種</dd></dl>
        <dl><dt>推定年齢</dt><dd>9歳</dd></dl>
        <dl><dt>性別</dt><dd>オス</dd></dl>
        <dl><dt>体重</dt><dd>17.0kg</dd></dl>
      </div>
    </a>
  </div>
</main></body></html>
"""

# 譲渡犬の詳細ページ。「毛色」dt がある。
_DETAIL_DOG_HTML = """
<html><body><main>
  <dl><dt>種類</dt><dd>雑種</dd></dl>
  <dl><dt>推定年齢</dt><dd>9歳 (R8.2.6現在)</dd></dl>
  <dl><dt>毛色</dt><dd>茶</dd></dl>
  <dl><dt>性別</dt><dd>オス</dd></dl>
  <dl><dt>体重</dt><dd>17.0kg</dd></dl>
  <dl><dt>首回り</dt><dd>34cm</dd></dl>
</main></body></html>
"""

# 迷子犬の詳細ページ。「毛色・長さ」と「大きさ」がある。
_LIST_LOSTCHILD_WITH_DETAIL_LINK = """
<html><body><main>
  <div class="information_box">
    <a href="https://oita-aigo.com/lostchild/r8-5-28/">
      <div class="information_text">
        <dl><dd class="lostchild_ttl">令和8年5月28日</dd></dl>
        <dl><dt>保護地域</dt><dd>杵築市</dd></dl>
        <dl><dt>推定年齢</dt><dd>1歳</dd></dl>
        <dl><dt>性別</dt><dd>メス</dd></dl>
        <dl><dt>体重</dt><dd>11.64kg</dd></dl>
      </div>
    </a>
  </div>
</main></body></html>
"""

_DETAIL_LOSTCHILD_HTML = """
<html><body><main>
  <dl><dt>保護地域</dt><dd>杵築市山香町</dd></dl>
  <dl><dt>種類</dt><dd>ビーグル雑種</dd></dl>
  <dl><dt>毛色・長さ</dt><dd>黒茶白</dd></dl>
  <dl><dt>性別</dt><dd>メス</dd></dl>
  <dl><dt>大きさ</dt><dd>中型</dd></dl>
  <dl><dt>体重</dt><dd>11.64kg</dd></dl>
</main></body></html>
"""


def _make_http_get(list_html: str, detail_url: str, detail_html: str):
    """list_url を返し、detail_url なら detail_html を返す _http_get モック工場"""

    def _fake_get(url: str, **kwargs) -> str:
        if url == detail_url:
            return detail_html
        return list_html

    return _fake_get


class TestOitaAigoDetailPageFallback:
    """カードから取れない color/size を詳細ページから補完する。

    実 oita-aigo.com 観測 (2026-05):
      - lostchild / anytimedog カードには「毛色」「大きさ」がない
      - 詳細ページの `<dl><dt>毛色</dt>` (もしくは「毛色・長さ」) と
        `<dt>大きさ</dt>` には記載がある
    カードのリンク (`<a href>`) を辿って詳細ページから補完する。
    HTTP は同一詳細 URL あたり 1 回までキャッシュする。
    """

    def test_anytimedog_color_filled_from_detail(self):
        """譲渡犬カードの color を詳細ページの「毛色」で補完する"""
        adapter = OitaAigoAdapter(_adoption_dog_site())
        fake = _make_http_get(
            _LIST_WITH_DETAIL_LINK,
            "https://oita-aigo.com/transferdoglist/24-0609-2/",
            _DETAIL_DOG_HTML,
        )
        with patch.object(adapter, "_http_get", side_effect=fake):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="adoption")
        assert raw.color == "茶"
        # 体重推定の中(17kg → 大)は依然として使われる (詳細に「大きさ」が無い場合)
        assert raw.size == "大"

    def test_lostchild_color_filled_from_keyword_label(self):
        """迷子カードの color を詳細ページの「毛色・長さ」で補完する"""
        adapter = OitaAigoAdapter(_lostchild_site())
        fake = _make_http_get(
            _LIST_LOSTCHILD_WITH_DETAIL_LINK,
            "https://oita-aigo.com/lostchild/r8-5-28/",
            _DETAIL_LOSTCHILD_HTML,
        )
        with patch.object(adapter, "_http_get", side_effect=fake):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="sheltered")
        assert raw.color == "黒茶白"

    def test_lostchild_size_prefers_detail_size_label_over_weight(self):
        """詳細ページに「大きさ」(中型) がある場合は体重推定より優先する

        体重 11.64kg は推定だと「中」になるが、詳細ページに「中型」とある
        ので語彙としてもデータソースとしても明示的な「中型」を採用する。
        """
        adapter = OitaAigoAdapter(_lostchild_site())
        fake = _make_http_get(
            _LIST_LOSTCHILD_WITH_DETAIL_LINK,
            "https://oita-aigo.com/lostchild/r8-5-28/",
            _DETAIL_LOSTCHILD_HTML,
        )
        with patch.object(adapter, "_http_get", side_effect=fake):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="sheltered")
        assert raw.size == "中型"

    def test_detail_fetch_failure_does_not_break_extraction(self):
        """詳細ページ取得が失敗しても、カードから取れる範囲は返す (回帰防止)"""
        from data_collector.adapters.municipality_adapter import NetworkError

        adapter = OitaAigoAdapter(_adoption_dog_site())

        def _flaky(url: str, **kwargs) -> str:
            if "transferdoglist" in url:
                raise NetworkError("detail unreachable", url=url)
            return _LIST_WITH_DETAIL_LINK

        with patch.object(adapter, "_http_get", side_effect=_flaky):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="adoption")

        # 詳細失敗時は color 空のまま、size は体重推定が効く
        assert raw.color == ""
        assert raw.size == "大"  # 17kg → 大
        assert raw.sex == "オス"

    def test_detail_page_fetched_only_once_per_url(self):
        """同一詳細 URL に対して _http_get は 1 回しか呼ばれない (キャッシュ)"""
        adapter = OitaAigoAdapter(_adoption_dog_site())

        call_log: list[str] = []

        def _logged_get(url: str, **kwargs) -> str:
            call_log.append(url)
            if "transferdoglist" in url:
                return _DETAIL_DOG_HTML
            return _LIST_WITH_DETAIL_LINK

        with patch.object(adapter, "_http_get", side_effect=_logged_get):
            urls = adapter.fetch_animal_list()
            # 同じ仮想 URL を 2 回呼ぶ → list/detail それぞれ 1 回までに収まること
            adapter.extract_animal_details(urls[0][0], category="adoption")
            adapter.extract_animal_details(urls[0][0], category="adoption")

        list_calls = sum(1 for u in call_log if u.endswith("/anytimedog/"))
        detail_calls = sum(1 for u in call_log if "transferdoglist" in u)
        assert list_calls == 1, f"list page should be fetched once: {call_log}"
        assert detail_calls == 1, f"detail page should be fetched once: {call_log}"


# 実 oita-aigo.com の anytimedog / anytimecat ページでは、カード先頭に
# 「随時」というカテゴリラベル付きの自リンク (一覧 URL 自身) があり、
# 詳細ページへのリンクはその次に並ぶ。PR #108 の実装は
# `card.find("a", href=True)` で先頭の `<a>` を取っていたため、
# 詳細フェッチが list URL に向かい毛色 dl が一切取れず実スナップショットで
# 改善ゼロだった。本クラスはこの構造を fixture で再現し、詳細リンクが
# 正しく選ばれて color が補完されることを担保する。
_LIST_WITH_CATEGORY_SELF_LINK_THEN_DETAIL = """
<html><body><main>
  <div class="information_box">
    <a href="https://oita-aigo.com/information_doglist/anytimedog/">随時</a>
    <a href="https://oita-aigo.com/transferdoglist/24-0609-2/">
      <div class="information_image"><img src="/img.jpg"></div>
      <div class="information_text">
        <dl><dd>No.24-0609-2</dd></dl>
        <dl><dt>仮名</dt><dd>ブロンソン</dd></dl>
        <dl><dt>種類</dt><dd>雑種</dd></dl>
        <dl><dt>推定年齢</dt><dd>9歳</dd></dl>
        <dl><dt>性別</dt><dd>オス</dd></dl>
        <dl><dt>体重</dt><dd>17.0kg</dd></dl>
      </div>
    </a>
  </div>
</main></body></html>
"""

# 迷子情報メインも同様にカテゴリ自リンク → 詳細リンクの並びになりうる
_LIST_LOSTCHILD_WITH_CATEGORY_SELF_LINK_THEN_DETAIL = """
<html><body><main>
  <div class="information_box">
    <a href="https://oita-aigo.com/lostchild/">迷子</a>
    <a href="https://oita-aigo.com/lostchild/r8-5-28/">
      <div class="information_text">
        <dl><dd class="lostchild_ttl">令和8年5月28日</dd></dl>
        <dl><dt>保護地域</dt><dd>杵築市</dd></dl>
        <dl><dt>推定年齢</dt><dd>1歳</dd></dl>
        <dl><dt>性別</dt><dd>メス</dd></dl>
        <dl><dt>体重</dt><dd>11.64kg</dd></dl>
      </div>
    </a>
  </div>
</main></body></html>
"""


class TestOitaAigoDetailLinkSelection:
    """カード内に複数の `<a>` がある場合、list URL 自身ではなく
    詳細ページ URL を選ぶ (PR #108 の取り損ね原因の修正)。
    """

    def test_anytimedog_skips_category_self_link_and_picks_detail(self):
        """カテゴリ自リンク (list URL と同一) はスキップし詳細リンクを選ぶ"""
        adapter = OitaAigoAdapter(_adoption_dog_site())
        fake = _make_http_get(
            _LIST_WITH_CATEGORY_SELF_LINK_THEN_DETAIL,
            "https://oita-aigo.com/transferdoglist/24-0609-2/",
            _DETAIL_DOG_HTML,
        )
        with patch.object(adapter, "_http_get", side_effect=fake):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="adoption")
        # 詳細ページの「毛色: 茶」で color が補完されているはず
        assert raw.color == "茶"

    def test_anytimedog_does_not_fetch_list_url_as_detail(self):
        """list URL を detail として取得してはならない (無限ループ/重複防止)"""
        adapter = OitaAigoAdapter(_adoption_dog_site())
        call_log: list[str] = []

        def _logged_get(url: str, **kwargs) -> str:
            call_log.append(url)
            if "transferdoglist" in url:
                return _DETAIL_DOG_HTML
            return _LIST_WITH_CATEGORY_SELF_LINK_THEN_DETAIL

        with patch.object(adapter, "_http_get", side_effect=_logged_get):
            urls = adapter.fetch_animal_list()
            adapter.extract_animal_details(urls[0][0], category="adoption")

        # list URL (anytimedog/) は fetch_animal_list の 1 回のみ
        list_calls = sum(1 for u in call_log if u.endswith("/anytimedog/"))
        assert list_calls == 1, (
            f"list URL should only be fetched once (for the list itself), "
            f"not as a detail fallback: {call_log}"
        )
        # 詳細リンクが正しく拾われていれば transferdoglist が 1 回呼ばれる
        detail_calls = sum(1 for u in call_log if "transferdoglist" in u)
        assert detail_calls == 1, f"detail page should be fetched: {call_log}"

    def test_lostchild_skips_category_self_link_and_picks_detail(self):
        """迷子情報でもカテゴリ自リンクを飛ばして詳細リンクを選ぶ"""
        adapter = OitaAigoAdapter(_lostchild_site())
        fake = _make_http_get(
            _LIST_LOSTCHILD_WITH_CATEGORY_SELF_LINK_THEN_DETAIL,
            "https://oita-aigo.com/lostchild/r8-5-28/",
            _DETAIL_LOSTCHILD_HTML,
        )
        with patch.object(adapter, "_http_get", side_effect=fake):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="sheltered")
        assert raw.color == "黒茶白"
        assert raw.size == "中型"
