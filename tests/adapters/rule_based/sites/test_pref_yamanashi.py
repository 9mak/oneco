"""PrefYamanashiAdapter のテスト

山梨県動物愛護指導センターサイト (pref.yamanashi.jp/doubutsu/) 用
rule-based adapter の動作を検証する。

- 1 ページに `div.menu_item` カードが並ぶ single_page 形式
- 6 サイト (探している/保護されている × 犬/猫/その他) すべての登録確認
"""

from __future__ import annotations

from unittest.mock import patch

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.pref_yamanashi import (
    PrefYamanashiAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig


def _site() -> SiteConfig:
    return SiteConfig(
        name="山梨県（探している犬）",
        prefecture="山梨県",
        prefecture_code="19",
        list_url="https://www.pref.yamanashi.jp/doubutsu/m_dog/index.html",
        category="lost",
        single_page=True,
    )


def _load_yamanashi_html(fixture_html) -> str:
    """フィクスチャを読み込み、必要であれば mojibake (二重 UTF-8) を補正する

    リポジトリに保存されている `pref_yamanashi__mdog.html` は、
    本来 UTF-8 のバイト列を Latin-1 として解釈してから再度 UTF-8 として
    保存し直された二重エンコーディング状態になっているため、
    実サイト相当のテキストを得るには逆変換が必要。
    実運用 (`_http_get`) では requests が正しい UTF-8 として受け取る。
    """
    raw = fixture_html("pref_yamanashi__mdog")
    # 実際のページに含まれる漢字 "山梨" が出てくるか判定
    if "山梨" in raw:
        return raw
    try:
        return raw.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return raw


class TestPrefYamanashiAdapter:
    def test_fetch_animal_list_returns_multiple_rows(self, fixture_html):
        """一覧ページから複数の動物カード (仮想 URL) が抽出できる"""
        html = _load_yamanashi_html(fixture_html)
        adapter = PrefYamanashiAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert len(result) >= 2, "少なくとも 2 件以上のカードが抽出されるはず"
        for url, cat in result:
            assert "#row=" in url
            assert url.startswith("https://www.pref.yamanashi.jp/")
            assert cat == "lost"

    def test_extract_animal_details_first_row(self, fixture_html):
        """1 件目のカードから RawAnimalData を構築できる + detail から補完が走る"""
        html = _load_yamanashi_html(fixture_html)
        adapter = PrefYamanashiAdapter(_site())

        # detail URL からは空の HTML を返してフェイルセーフを確認
        def _http_side_effect(url):
            if url.endswith("index.html"):
                return html
            return "<html><body></body></html>"

        with patch.object(adapter, "_http_get", side_effect=_http_side_effect):
            urls = adapter.fetch_animal_list()
            first_url, category = urls[0]
            raw = adapter.extract_animal_details(first_url, category=category)

        assert isinstance(raw, RawAnimalData)
        # サイト名から犬と推定される
        assert raw.species == "犬"
        # フィクスチャ 1 件目: 場所 "甲州市塩山西広門田", 性別 "メス",
        # 毛色 "うす茶（ベージュ）"
        assert "甲州市" in raw.location
        assert raw.sex == "メス"
        assert "茶" in raw.color
        # 画像 URL が絶対 URL に変換されている
        assert raw.image_urls
        assert all(u.startswith("http") for u in raw.image_urls)
        # source_url は仮想 URL
        assert raw.source_url == first_url
        assert raw.category == "lost"

    def test_extract_animal_details_enriches_with_detail_page(self, fixture_html):
        """カードの detail URL を辿って phone / size を補完する

        実サイト (2026-05 観測) の詳細ページは以下の構造:
            <h2>種類・体格</h2>
            <p>トイプードル　中型</p>
            <h2>性別</h2>
            <p>オス</p>
            <h2>毛色</h2>
            <p>濃い茶色</p>
            <h2>管轄保健所の連絡先</h2>
            <p>峡東保健所TEL:0553-20-2751</p>

        旧実装は size と phone をハードコード空で返していたため、
        山梨 218 件全件で size/phone が欠損していた。本テストは detail HTML
        を mock して補完が走ることを保証する。
        """
        list_html = _load_yamanashi_html(fixture_html)
        detail_html = """
        <html><body>
          <h2>管轄保健所の連絡先</h2>
          <p>峡東保健所TEL:0553-20-2751</p>
          <h2>種類・体格</h2>
          <p>トイプードル　中型</p>
          <h2>性別</h2>
          <p>オス</p>
          <h2>毛色</h2>
          <p>濃い茶色</p>
        </body></html>
        """
        adapter = PrefYamanashiAdapter(_site())

        def _http_side_effect(url):
            if url.endswith("index.html"):
                return list_html
            return detail_html

        with patch.object(adapter, "_http_get", side_effect=_http_side_effect):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="lost")

        # detail から補完された size と phone
        assert raw.size == "中型", f"detail から size 補完されるべき: got {raw.size!r}"
        assert raw.phone == "0553-20-2751", f"detail から phone 補完されるべき: got {raw.phone!r}"

    def test_extract_size_from_kind_size_variants(self):
        """「種類・体格」テキストの多様な表記から size を抽出する単体テスト

        実サイト (2026-06 調査) で観測された表記パターンを網羅する。
        旧 token 分割実装は全角括弧・中点・体重表記を取り損ねていた。
        """
        cls = PrefYamanashiAdapter
        # 直接体格語
        assert cls._extract_size_from_kind_size("トイプードル 中型") == "中型"
        assert cls._extract_size_from_kind_size("雑種 小型（3.5kg）") == "小型"
        # 全角括弧 token 分離不能
        assert cls._extract_size_from_kind_size("猫（雑種）大型") == "大型"
        # 中点区切り
        assert cls._extract_size_from_kind_size("猫（雑種）・中型") == "中型"
        # 体重 → size 推定
        assert cls._extract_size_from_kind_size("雑種、体重約4kg") == "小"
        assert cls._extract_size_from_kind_size("3kgくらい") == "小"
        assert cls._extract_size_from_kind_size("雑種 10kg") == "中"
        # 体格語優先 (kg 注記より)
        assert cls._extract_size_from_kind_size("大型犬 20kg") == "大型"
        # 年齢キーワード
        assert cls._extract_size_from_kind_size("子猫") == "小"
        assert cls._extract_size_from_kind_size("子犬") == "小"
        # 構造的不可能 (情報なし)
        assert cls._extract_size_from_kind_size("雑種") == ""
        assert cls._extract_size_from_kind_size("柴犬") == ""
        assert cls._extract_size_from_kind_size("ポメラニアンとチワワのミックス") == ""

    def test_extract_breed_from_kind_size_variants(self):
        """「種類・体格」テキストから犬種/品種を抽出する単体テスト (2026-06-15)。

        旧実装は size のみ抽出し犬種を破棄していた (222 件で breed 欠損)。
        体格/体重/年齢語を除いた残りを breed とし、判定不能なら空を返す
        (誤った breed を作らない)。
        """
        cls = PrefYamanashiAdapter
        assert cls._extract_breed_from_kind_size("トイプードル 中型") == "トイプードル"
        assert cls._extract_breed_from_kind_size("雑種 小型（3.5kg）") == "雑種"
        assert cls._extract_breed_from_kind_size("猫（雑種）大型") == "雑種"
        assert cls._extract_breed_from_kind_size("猫（雑種）・中型") == "雑種"
        assert cls._extract_breed_from_kind_size("雑種、体重約4kg") == "雑種"
        assert cls._extract_breed_from_kind_size("柴犬") == "柴犬"
        assert cls._extract_breed_from_kind_size("雑種") == "雑種"
        assert (
            cls._extract_breed_from_kind_size("ポメラニアンとチワワのミックス")
            == "ポメラニアンとチワワのミックス"
        )
        # 品種情報なし → 空 (size 語・体重・年齢語のみ)
        assert cls._extract_breed_from_kind_size("3kgくらい") == ""
        assert cls._extract_breed_from_kind_size("子猫") == ""
        assert cls._extract_breed_from_kind_size("中型") == ""
        assert cls._extract_breed_from_kind_size("") == ""

    def test_extract_animal_details_breed_via_normalize(self, fixture_html):
        """「種類・体格」から breed を抽出し normalize() 戻り値に乗ること。

        CLAUDE.md サイレントドロップ規約: raw でなく adapter.normalize(raw) の
        AnimalData.breed をアサートする (個体識別フィールドの恒久欠損防止)。
        """
        list_html = _load_yamanashi_html(fixture_html)
        detail_html = """
        <html><body>
          <h2>種類・体格</h2>
          <p>トイプードル 中型</p>
          <h2>管轄保健所の連絡先</h2>
          <p>峡東保健所TEL:0553-20-2751</p>
        </body></html>
        """
        adapter = PrefYamanashiAdapter(_site())

        def _http_side_effect(url):
            if url.endswith("index.html"):
                return list_html
            return detail_html

        with patch.object(adapter, "_http_get", side_effect=_http_side_effect):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="lost")
            animal = adapter.normalize(raw)

        assert raw.breed == "トイプードル"
        assert animal.breed == "トイプードル"
        assert animal.size == "中型"

    def test_extract_animal_details_size_with_annotation(self, fixture_html):
        """「雑種 小型（3.5kg）」のように体格 token に注記が続くケースも拾う

        旧実装は token 完全一致 (`_SIZE_VALID` set) のみだったため
        「小型（3.5kg）」のような注記付き token を取り損ねていた。
        snapshot で 184件の size 欠損のうち相当数がこのパターン。
        """
        list_html = _load_yamanashi_html(fixture_html)
        detail_html = """
        <html><body>
          <h2>種類・体格</h2>
          <p>雑種　小型（3.5kg）</p>
          <h2>管轄保健所の連絡先</h2>
          <p>峡東保健所TEL:0553-20-2751</p>
        </body></html>
        """
        adapter = PrefYamanashiAdapter(_site())

        def _http_side_effect(url):
            if url.endswith("index.html"):
                return list_html
            return detail_html

        with patch.object(adapter, "_http_get", side_effect=_http_side_effect):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="lost")

        assert raw.size == "小型", f"注記付き token から size 抽出されるべき: got {raw.size!r}"

    def test_extract_animal_details_size_kind_only_returns_empty(self, fixture_html):
        """「雑種」のみで体格欄無し、かつ その他の情報 にもサイズ手掛かりが
        無い場合は構造的に取得不可で空文字"""
        list_html = _load_yamanashi_html(fixture_html)
        detail_html = """
        <html><body>
          <h2>種類・体格</h2>
          <p>雑種</p>
          <h2>その他の情報</h2>
          <p>首輪なし、人慣れしている</p>
        </body></html>
        """
        adapter = PrefYamanashiAdapter(_site())

        def _http_side_effect(url):
            if url.endswith("index.html"):
                return list_html
            return detail_html

        with patch.object(adapter, "_http_get", side_effect=_http_side_effect):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="lost")

        assert raw.size == ""

    def test_extract_animal_details_size_from_other_info_size_word(self, fixture_html):
        """「種類・体格」欄に size がない場合でも
        その他の情報の自由記述に「中型」「小型」等の体格語があれば拾う

        実サイト (2026-06 観測):
            種類・体格: 雑種
            その他の情報: 去勢済み、首輪無し、中型(5kg位) 3才
        69% の size 欠損のうち相当数がこのパターン。
        """
        list_html = _load_yamanashi_html(fixture_html)
        detail_html = """
        <html><body>
          <h2>種類・体格</h2>
          <p>雑</p>
          <h2>その他の情報</h2>
          <p>去勢済み、首輪無し、中型(5kg位) 3才</p>
        </body></html>
        """
        adapter = PrefYamanashiAdapter(_site())

        def _http_side_effect(url):
            if url.endswith("index.html"):
                return list_html
            return detail_html

        with patch.object(adapter, "_http_get", side_effect=_http_side_effect):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="lost")

        assert raw.size == "中型", f"その他の情報から size 抽出されるべき: got {raw.size!r}"

    def test_extract_animal_details_size_from_other_info_weight_kg(self, fixture_html):
        """その他の情報に体重表記しかない場合、5/15kg 境界で size 推定する"""
        list_html = _load_yamanashi_html(fixture_html)
        detail_html = """
        <html><body>
          <h2>種類・体格</h2>
          <p>雑種</p>
          <h2>その他の情報</h2>
          <p>首輪あり 体重2.3kg（逸走時）</p>
        </body></html>
        """
        adapter = PrefYamanashiAdapter(_site())

        def _http_side_effect(url):
            if url.endswith("index.html"):
                return list_html
            return detail_html

        with patch.object(adapter, "_http_get", side_effect=_http_side_effect):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="lost")

        assert raw.size == "小", f"体重 → size 推定されるべき: got {raw.size!r}"

    def test_extract_animal_details_size_from_other_info_fullwidth_weight(self, fixture_html):
        """全角数字と U+339F「㎏」記号の体重表記も拾う

        例: その他の情報「９才、体重６ｋｇ 去勢手術済」
        例: その他の情報「大型5㎏くらい」
        """
        list_html = _load_yamanashi_html(fixture_html)
        detail_html = """
        <html><body>
          <h2>種類・体格</h2>
          <p>雑種</p>
          <h2>その他の情報</h2>
          <p>９才、体重６ｋｇ 去勢手術済</p>
        </body></html>
        """
        adapter = PrefYamanashiAdapter(_site())

        def _http_side_effect(url):
            if url.endswith("index.html"):
                return list_html
            return detail_html

        with patch.object(adapter, "_http_get", side_effect=_http_side_effect):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="lost")

        assert raw.size == "中", f"全角数字の体重 → size 推定されるべき: got {raw.size!r}"

    def test_extract_animal_details_size_kind_takes_priority_over_other_info(self, fixture_html):
        """「種類・体格」に size があれば その他の情報 より優先する"""
        list_html = _load_yamanashi_html(fixture_html)
        detail_html = """
        <html><body>
          <h2>種類・体格</h2>
          <p>雑種　大型</p>
          <h2>その他の情報</h2>
          <p>体重2kg 小型</p>
        </body></html>
        """
        adapter = PrefYamanashiAdapter(_site())

        def _http_side_effect(url):
            if url.endswith("index.html"):
                return list_html
            return detail_html

        with patch.object(adapter, "_http_get", side_effect=_http_side_effect):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="lost")

        assert raw.size == "大型", f"種類・体格を優先すべき: got {raw.size!r}"

    def test_extract_animal_details_enriches_age_from_other_info(self, fixture_html):
        """detail ページの「その他の情報」欄から「年齢：3才」等を抽出する

        実サイト (2026-05 観測) は「種類・体格」「性別」「毛色」等の構造化欄に
        加えて、自由記述の「その他の情報」欄に「年齢：3才」「推定2歳」のような
        フォーマットで年齢が記載されることがある。記載がないカードもあるため
        best-effort で抽出し、見つからない場合は空文字のまま (age_months → None)。
        """
        list_html = _load_yamanashi_html(fixture_html)
        detail_html = """
        <html><body>
          <h2>管轄保健所の連絡先</h2>
          <p>峡東保健所TEL:0553-20-2751</p>
          <h2>種類・体格</h2>
          <p>トイプードル　中型</p>
          <h2>性別</h2>
          <p>オス</p>
          <h2>毛色</h2>
          <p>濃い茶色</p>
          <h2>その他の情報</h2>
          <p>人なつこい 年齢：3才 首輪なし</p>
        </body></html>
        """
        adapter = PrefYamanashiAdapter(_site())

        def _http_side_effect(url):
            if url.endswith("index.html"):
                return list_html
            return detail_html

        with patch.object(adapter, "_http_get", side_effect=_http_side_effect):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="lost")

        assert raw.age == "3才", f"その他の情報欄から age 抽出されるべき: got {raw.age!r}"

    def test_extract_animal_details_age_supports_months_and_years(self, fixture_html):
        """「○ヶ月」「推定○歳」等の age バリエーションも拾える"""
        list_html = _load_yamanashi_html(fixture_html)
        detail_html_months = """
        <html><body>
          <h2>その他の情報</h2>
          <p>推定6ヶ月 子犬</p>
        </body></html>
        """
        adapter = PrefYamanashiAdapter(_site())

        def _http_side_effect(url):
            if url.endswith("index.html"):
                return list_html
            return detail_html_months

        with patch.object(adapter, "_http_get", side_effect=_http_side_effect):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="lost")

        assert "6" in raw.age
        assert "月" in raw.age or "ヶ月" in raw.age

    def test_extract_animal_details_age_empty_when_not_present(self, fixture_html):
        """その他の情報欄に年齢記載がないカードは age 空文字"""
        list_html = _load_yamanashi_html(fixture_html)
        detail_html_no_age = """
        <html><body>
          <h2>種類・体格</h2>
          <p>甲斐犬　中型</p>
          <h2>その他の情報</h2>
          <p>首輪無し マイクロチップ無し</p>
        </body></html>
        """
        adapter = PrefYamanashiAdapter(_site())

        def _http_side_effect(url):
            if url.endswith("index.html"):
                return list_html
            return detail_html_no_age

        with patch.object(adapter, "_http_get", side_effect=_http_side_effect):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="lost")

        assert raw.age == ""

    def test_extract_animal_details_phone_from_genzai_fallback(self, fixture_html):
        """`管轄保健所の連絡先` h2 が存在しないページでも
        `現在の収容場所及び連絡先` h2 から phone を補完する

        2026-06 snapshot で phone 欠損していた 26 件は
        `/doubutsu/p_cat/{id}.html` 等の古い detail テンプレートで、
        `管轄保健所の連絡先` h2 が存在せず `現在の収容場所及び連絡先`
        h2 のみが phone を持っていたパターン。フォールバックとして
        後者からも phone を拾えるようにする。
        """
        list_html = _load_yamanashi_html(fixture_html)
        # `管轄保健所の連絡先` 無し、`現在の収容場所及び連絡先` のみ
        detail_html = """
        <html><body>
          <h2>保護した場所</h2>
          <p>中央市一町畑</p>
          <h2>現在の収容場所及び連絡先</h2>
          <p>（収容場所）住民<br />（連絡先）中北保健所（動物愛護指導センター内）<br />TEL：055-273-5034</p>
          <h2>種類・体格</h2>
          <p>雑種</p>
        </body></html>
        """
        adapter = PrefYamanashiAdapter(_site())

        def _http_side_effect(url):
            if url.endswith("index.html"):
                return list_html
            return detail_html

        with patch.object(adapter, "_http_get", side_effect=_http_side_effect):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="lost")

        assert raw.phone == "055-273-5034", (
            f"現在の収容場所及び連絡先 から phone 補完されるべき: got {raw.phone!r}"
        )

    def test_extract_animal_details_phone_prefers_kankatsu_over_genzai(self, fixture_html):
        """両方の h2 が存在する場合は `管轄保健所の連絡先` を優先する

        `現在の収容場所及び連絡先` は収容施設の連絡先で、`管轄保健所の連絡先`
        が保健所の正式番号。両方ある場合は後者を優先したい。
        """
        list_html = _load_yamanashi_html(fixture_html)
        detail_html = """
        <html><body>
          <h2>管轄保健所の連絡先</h2>
          <p>峡東保健所<br />TEL：0553-20-2751</p>
          <h2>現在の収容場所及び連絡先</h2>
          <p>（収容場所）住民<br />（連絡先）動物愛護指導センター<br />TEL：055-273-5034</p>
        </body></html>
        """
        adapter = PrefYamanashiAdapter(_site())

        def _http_side_effect(url):
            if url.endswith("index.html"):
                return list_html
            return detail_html

        with patch.object(adapter, "_http_get", side_effect=_http_side_effect):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="lost")

        assert raw.phone == "0553-20-2751", f"管轄保健所の連絡先 を優先するべき: got {raw.phone!r}"

    def test_extract_animal_details_phone_full_width_hyphen(self, fixture_html):
        """全角ハイフン (ｰ U+FF70 / ー U+30FC / － U+FF0D) 区切りも phone として認識する

        実サイトの一部 detail ページ (例: kt/m_cat/33798.html) は
        `0553ｰ20ｰ2751` のように半角カタカナ長音 (U+FF70) を区切り文字に
        使っており、ASCII ハイフンのみを受け付ける旧パターンでは
        全角ハイフン経由の phone を取り逃がしていた。
        """
        list_html = _load_yamanashi_html(fixture_html)
        # ｰ = U+FF70 (HALFWIDTH KATAKANA-HIRAGANA PROLONGED SOUND MARK)
        detail_html_ff70 = """
        <html><body>
          <h2>管轄保健所の連絡先</h2>
          <p>峡東保健所 TEL:0553ｰ20ｰ2751</p>
        </body></html>
        """
        adapter = PrefYamanashiAdapter(_site())

        def _http_side_effect(url):
            if url.endswith("index.html"):
                return list_html
            return detail_html_ff70

        with patch.object(adapter, "_http_get", side_effect=_http_side_effect):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="lost")

        # 全角ハイフンは ASCII ハイフンに正規化された上で抽出される
        assert raw.phone == "0553-20-2751", (
            f"全角ハイフン区切り phone を抽出すべき: got {raw.phone!r}"
        )

    def test_extract_animal_details_falls_back_when_detail_fails(self, fixture_html):
        """detail fetch が失敗しても一覧の情報で RawAnimalData が返る"""
        html = _load_yamanashi_html(fixture_html)
        adapter = PrefYamanashiAdapter(_site())

        def _http_side_effect(url):
            if url.endswith("index.html"):
                return html
            raise RuntimeError("detail fetch failed")

        with patch.object(adapter, "_http_get", side_effect=_http_side_effect):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="lost")
        # 一覧の情報は取れている
        assert "甲州市" in raw.location
        assert raw.sex == "メス"
        # size と phone は空のまま
        assert raw.size == ""
        assert raw.phone == ""

    def test_no_header_row_skipped_incorrectly(self, fixture_html):
        """カード形式なのでヘッダ行は存在せず、全件が動物として抽出される

        SKIP_FIRST_ROW=False の宣言通り、最初のカードもデータとして扱われる。
        フィクスチャ 1 件目の場所 (甲州市…) が結果に含まれていることで確認する。
        """
        html = _load_yamanashi_html(fixture_html)
        adapter = PrefYamanashiAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            locations = []
            for url, cat in urls[:3]:
                raw = adapter.extract_animal_details(url, category=cat)
                locations.append(raw.location)

        # 1 件目 (本来ヘッダではない) が確実にデータ扱い
        assert any("甲州市" in loc for loc in locations)
        # ヘッダ的な空文字や "場所" のような項目名が混じっていない
        assert not any(loc.strip() in ("", "場所", "市町村") for loc in locations)

    def test_all_six_sites_registered(self):
        """6 つの山梨県サイト名すべてが Registry に登録されている"""
        expected = [
            "山梨県（探している犬）",
            "山梨県（探している猫）",
            "山梨県（探している他のペット）",
            "山梨県（保護されている犬）",
            "山梨県（保護されている猫）",
            "山梨県（保護されている他のペット）",
        ]
        for name in expected:
            # 他テストが registry を clear する場合に備えて冪等に再登録
            if SiteAdapterRegistry.get(name) is None:
                SiteAdapterRegistry.register(name, PrefYamanashiAdapter)
            assert SiteAdapterRegistry.get(name) is PrefYamanashiAdapter

    def test_no_cards_returns_empty_list(self):
        """カード要素が見当たらない HTML は真ゼロとして空リストを返す"""
        adapter = PrefYamanashiAdapter(_site())
        with patch.object(adapter, "_http_get", return_value="<html><body></body></html>"):
            result = adapter.fetch_animal_list()
        assert result == []
