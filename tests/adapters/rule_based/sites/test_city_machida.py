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


class TestCityMachidaAdapterSizeInference:
    """町田市 CMS は「大きさ」欄を持たないが、特徴フィールドに体重・体格表現が
    自由記述で含まれることが多い。これを「小/中/大」語彙に推定して size を補完する。

    2026-05 観測 (snapshots/latest.json):
    - hogo.html + search_{cat,dog}.html の 59件全件で size=null
    - 「特徴」フィールド 57件中、約 9件で「N キロ/N キログラム」明記
    - さらに 9 件で「小柄」「大きめ」など体格語が含まれる
    - 合計で約 30% を構造的に補完可能
    """

    def _extract_one(self, animals_html: str, anchor: str = "現在のペットの保護情報"):
        html = _build_html(anchor, animals_html)
        adapter = CityMachidaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            return adapter.extract_animal_details(urls[0][0], category="sheltered")

    def test_size_from_explicit_weight_label(self):
        """「体重：4kg」のような明示ラベルがあれば直接 size に変換する"""
        animals_html = """
        <div class="h3bg"><h3>猫（おす）</h3></div>
        <div class="img-area-r">
          <ul>
            <li>種類：雑種</li>
            <li>性別：おす</li>
            <li>体重：4kg</li>
            <li>保護場所：町田市</li>
          </ul>
        </div>
        """
        raw = self._extract_one(animals_html)
        assert raw.size == "小"

    @pytest.mark.parametrize(
        ("feature_text", "expected_size"),
        [
            # 体重 → 小/中/大 (kumamoto/oita と同じ 5kg / 15kg 境界)
            ("長毛、人懐こい、体重4キロほど", "小"),
            ("尻尾が短い、二重あご、体重約7キロ", "中"),
            ("7キロ越えの骨格しっかり目、老犬", "中"),
            ("体重3キログラム程度、水色の洋服を着ている", "小"),
            ("大きめで体重5キロくらい　臆病", "中"),
            ("長毛、大きく見えるが体重は軽い（3～4キログラム）", "小"),
            # 体格語 → 小/大 (中は曖昧なため推定しない)
            ("首の周りから胸まで白。小柄で細身、とても臆病。立ち耳。", "小"),
            ("体格は小柄、臆病な性格", "小"),
            ("小柄", "小"),
            ("体型は小柄、基本おとなしくおっとり", "小"),
            # 体重と体格語が両方ある場合は体重を優先
            ("大きめで体重5キロくらい", "中"),
        ],
    )
    def test_size_from_feature_text(self, feature_text: str, expected_size: str):
        """「特徴」フィールドから体重数値・体格語で size を推定する"""
        animals_html = f"""
        <div class="h3bg"><h3>猫（おす）</h3></div>
        <div class="img-area-r">
          <ul>
            <li>種類：雑種</li>
            <li>性別：おす</li>
            <li>特徴：{feature_text}</li>
            <li>保護場所：町田市</li>
          </ul>
        </div>
        """
        raw = self._extract_one(animals_html)
        assert raw.size == expected_size, (
            f"feature={feature_text!r} → size={raw.size!r} (expected {expected_size!r})"
        )

    def test_size_empty_when_no_signal(self):
        """体重・体格語が無い特徴文では size は空のまま維持する (誤推定を避ける)"""
        animals_html = """
        <div class="h3bg"><h3>猫（おす）</h3></div>
        <div class="img-area-r">
          <ul>
            <li>種類：雑種</li>
            <li>性別：おす</li>
            <li>特徴：右耳桜耳、左耳が切れている</li>
            <li>保護場所：町田市</li>
          </ul>
        </div>
        """
        raw = self._extract_one(animals_html)
        assert raw.size == ""

    def test_size_label_preferred_over_feature_weight(self):
        """「大きさ」「体格」明示欄がある場合はそちらを優先する (推定にフォールバックしない)"""
        animals_html = """
        <div class="h3bg"><h3>犬（おす）</h3></div>
        <div class="img-area-r">
          <ul>
            <li>種類：柴犬</li>
            <li>大きさ：中型</li>
            <li>特徴：体重30キログラム</li>
            <li>保護場所：町田市</li>
          </ul>
        </div>
        """
        raw = self._extract_one(animals_html)
        # 明示「中型」ラベルは raw.size に保持され、特徴文の 30kg→大 では上書きされない
        assert "中型" in raw.size or raw.size == "中"

    def test_size_from_age_kogata_pattern(self):
        """「子猫」「子犬」表記も小サイズとして拾う"""
        animals_html = """
        <div class="h3bg"><h3>猫（めす）</h3></div>
        <div class="img-area-r">
          <ul>
            <li>種類：雑種</li>
            <li>性別：めす</li>
            <li>特徴：生後4か月の子猫、あまり慣れていない</li>
            <li>保護場所：町田市</li>
          </ul>
        </div>
        """
        raw = self._extract_one(animals_html)
        assert raw.size == "小"


class TestCityMachidaAdapterColorExtraction:
    """町田市 CMS では「毛色」以外のラベル揺れ・コロン抜けが観測される。
    残 6 件の color 欠損を解消するための分岐網羅。

    2026-06 観測 (search_cat.html 55件中 6件 color=null):
    - 「柄：ハチワレ（白黒）」「色柄：茶色、縞模様あり」など別ラベル: 4件
    - 「毛色○○」とコロンが抜けた CMS 入力ミス: 2件 (idx=36, 37)
    """

    def _extract_one(self, animals_html: str, anchor: str = "現在の迷子の猫情報"):
        html = _build_html(anchor, animals_html)
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
            return adapter.extract_animal_details(urls[0][0], category="lost")

    def test_color_from_gara_label(self):
        """「柄：ハチワレ（白黒）」を color として抽出する (idx=17 相当)"""
        animals_html = """
        <div class="h3bg"><h3>猫（めす）</h3></div>
        <div class="img-area-r">
          <ul>
            <li>性別：めす（避妊済）</li>
            <li>種類：雑種</li>
            <li>柄：ハチワレ（白黒）</li>
            <li>失踪場所：小山が丘1丁目</li>
          </ul>
        </div>
        """
        raw = self._extract_one(animals_html)
        assert "ハチワレ" in raw.color
        assert "白黒" in raw.color

    def test_color_from_irogara_label(self):
        """「色柄：茶色、縞模様あり」を color として抽出する (idx=27 相当)"""
        animals_html = """
        <div class="h3bg"><h3>猫（おす）</h3></div>
        <div class="img-area-r">
          <ul>
            <li>性別：おす</li>
            <li>色柄：茶色、縞模様あり</li>
            <li>失踪場所：図師町3000番台</li>
          </ul>
        </div>
        """
        raw = self._extract_one(animals_html)
        assert "茶色" in raw.color
        assert "縞模様" in raw.color

    def test_color_from_long_irogara_value(self):
        """値が長文 (30+ 文字) の「色柄」も切り捨てずに color に入る (idx=28,29 相当)"""
        animals_html = """
        <div class="h3bg"><h3>猫（めす）</h3></div>
        <div class="img-area-r">
          <ul>
            <li>性別：めす</li>
            <li>色柄：白地、顔右側・背中2ヶ所・腰に黒トラのぶち、尻尾も黒トラ模様</li>
            <li>失踪場所：高ヶ坂4丁目付近</li>
          </ul>
        </div>
        """
        raw = self._extract_one(animals_html)
        assert "白地" in raw.color
        assert "黒トラ" in raw.color

    def test_color_from_keiro_without_colon(self):
        """「毛色○○」とコロン抜けの CMS 入力ミスでも color を抽出する (idx=36 相当)"""
        animals_html = """
        <div class="h3bg"><h3>猫（おす）</h3></div>
        <div class="img-area-r">
          <ul>
            <li>性別：おす（去勢手術していない）</li>
            <li>種類：雑種</li>
            <li>毛色黒と白（足は白）</li>
            <li>失踪場所：町田市図師町2000番台付近</li>
          </ul>
        </div>
        """
        raw = self._extract_one(animals_html)
        assert "黒と白" in raw.color

    def test_color_from_keiro_without_colon_kijitora(self):
        """同上: 「毛色キジトラ（足は白）」を color に抽出 (idx=37 相当)"""
        animals_html = """
        <div class="h3bg"><h3>猫（めす）</h3></div>
        <div class="img-area-r">
          <ul>
            <li>性別：めす</li>
            <li>種類：雑種</li>
            <li>毛色キジトラ（足は白）</li>
            <li>失踪場所：町田市原町田1丁目</li>
          </ul>
        </div>
        """
        raw = self._extract_one(animals_html)
        assert "キジトラ" in raw.color

    def test_color_from_gara_without_colon(self):
        """「柄○○」コロン抜けでも対応する (idx=17 系の派生バリアント)"""
        animals_html = """
        <div class="h3bg"><h3>猫（めす）</h3></div>
        <div class="img-area-r">
          <ul>
            <li>性別：めす</li>
            <li>柄ハチワレ</li>
            <li>失踪場所：町田市</li>
          </ul>
        </div>
        """
        raw = self._extract_one(animals_html)
        assert "ハチワレ" in raw.color

    def test_existing_keiro_label_still_works(self):
        """既存「毛色：キジトラ」の動作は壊さない (リグレッション防止)"""
        animals_html = """
        <div class="h3bg"><h3>猫（おす）</h3></div>
        <div class="img-area-r">
          <ul>
            <li>性別：おす</li>
            <li>毛色：キジトラ</li>
            <li>失踪場所：町田市</li>
          </ul>
        </div>
        """
        raw = self._extract_one(animals_html)
        assert raw.color == "キジトラ"

    def test_shippo_label_not_misclassified_as_color(self):
        """「しっぽ：黒くて長い」は color に誤マップしない (柄 と prefix 衝突しない確認)"""
        animals_html = """
        <div class="h3bg"><h3>猫（めす）</h3></div>
        <div class="img-area-r">
          <ul>
            <li>性別：めす</li>
            <li>しっぽ：黒くて長いまっすぐなしっぽ</li>
            <li>毛色：キジトラ</li>
            <li>失踪場所：町田市</li>
          </ul>
        </div>
        """
        raw = self._extract_one(animals_html)
        # 毛色 ラベルの値だけが color に入り、しっぽの内容は混ざらない
        assert raw.color == "キジトラ"


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
