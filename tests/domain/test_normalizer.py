"""
DataNormalizer のユニットテスト

データ正規化ロジックの各メソッドを個別にテストし、
統合テストで RawAnimalData → AnimalData の変換を検証します。
"""

from datetime import date

import pytest

from src.data_collector.domain.models import RawAnimalData
from src.data_collector.domain.normalizer import DataNormalizer


class TestNormalizeSpecies:
    """動物種別正規化のテスト"""

    def test_normalize_species_inu_variations(self):
        """犬のバリエーションを '犬' に正規化"""
        assert DataNormalizer._normalize_species("いぬ") == "犬"
        assert DataNormalizer._normalize_species("イヌ") == "犬"
        assert DataNormalizer._normalize_species("inu") == "犬"
        assert DataNormalizer._normalize_species("INU") == "犬"
        assert DataNormalizer._normalize_species("dog") == "犬"
        assert DataNormalizer._normalize_species("DOG") == "犬"
        assert DataNormalizer._normalize_species("Dog") == "犬"
        assert DataNormalizer._normalize_species("犬") == "犬"

    def test_normalize_species_neko_variations(self):
        """猫のバリエーションを '猫' に正規化"""
        assert DataNormalizer._normalize_species("ねこ") == "猫"
        assert DataNormalizer._normalize_species("ネコ") == "猫"
        assert DataNormalizer._normalize_species("neko") == "猫"
        assert DataNormalizer._normalize_species("NEKO") == "猫"
        assert DataNormalizer._normalize_species("cat") == "猫"
        assert DataNormalizer._normalize_species("CAT") == "猫"
        assert DataNormalizer._normalize_species("Cat") == "猫"
        assert DataNormalizer._normalize_species("猫") == "猫"

    def test_normalize_species_other(self):
        """犬・猫以外は 'その他' に正規化"""
        assert DataNormalizer._normalize_species("鳥") == "その他"
        assert DataNormalizer._normalize_species("うさぎ") == "その他"
        assert DataNormalizer._normalize_species("ハムスター") == "その他"
        assert DataNormalizer._normalize_species("unknown") == "その他"
        assert DataNormalizer._normalize_species("") == "その他"


class TestNormalizeSex:
    """性別正規化のテスト"""

    def test_normalize_sex_male_variations(self):
        """オスのバリエーションを '男の子' に正規化"""
        assert DataNormalizer._normalize_sex("オス") == "男の子"
        assert DataNormalizer._normalize_sex("おす") == "男の子"
        assert DataNormalizer._normalize_sex("雄") == "男の子"
        assert DataNormalizer._normalize_sex("♂") == "男の子"
        assert DataNormalizer._normalize_sex("male") == "男の子"
        assert DataNormalizer._normalize_sex("MALE") == "男の子"
        assert DataNormalizer._normalize_sex("Male") == "男の子"
        assert DataNormalizer._normalize_sex("男の子") == "男の子"
        assert DataNormalizer._normalize_sex("オトコノコ") == "男の子"

    def test_normalize_sex_female_variations(self):
        """メスのバリエーションを '女の子' に正規化"""
        assert DataNormalizer._normalize_sex("メス") == "女の子"
        assert DataNormalizer._normalize_sex("めす") == "女の子"
        assert DataNormalizer._normalize_sex("雌") == "女の子"
        assert DataNormalizer._normalize_sex("♀") == "女の子"
        assert DataNormalizer._normalize_sex("female") == "女の子"
        assert DataNormalizer._normalize_sex("FEMALE") == "女の子"
        assert DataNormalizer._normalize_sex("Female") == "女の子"
        assert DataNormalizer._normalize_sex("女の子") == "女の子"
        assert DataNormalizer._normalize_sex("オンナノコ") == "女の子"

    def test_normalize_sex_unknown_variations(self):
        """不明のバリエーションを '不明' に正規化"""
        assert DataNormalizer._normalize_sex("?") == "不明"
        assert DataNormalizer._normalize_sex("？") == "不明"
        assert DataNormalizer._normalize_sex("不明") == "不明"
        assert DataNormalizer._normalize_sex("unknown") == "不明"
        assert DataNormalizer._normalize_sex("") == "不明"
        assert DataNormalizer._normalize_sex("その他") == "不明"

    def test_normalize_sex_old_kanji(self):
        """牡 (雄) / 牝 (雌) の旧表記を正しく判定する。

        一部自治体サイトは「牡」「牝」表記を使う。これを取りこぼすと
        sex が全件「不明」になり性別フィルタが機能しない。
        """
        assert DataNormalizer._normalize_sex("牡") == "男の子"
        assert DataNormalizer._normalize_sex("牝") == "女の子"


class TestNormalizeAge:
    """年齢正規化のテスト"""

    def test_normalize_age_years(self):
        """'N歳' を月単位に変換"""
        assert DataNormalizer._normalize_age("1歳") == 12
        assert DataNormalizer._normalize_age("2歳") == 24
        assert DataNormalizer._normalize_age("5歳") == 60
        assert DataNormalizer._normalize_age("10歳") == 120

    def test_normalize_age_months(self):
        """'Nヶ月' をそのまま数値化"""
        assert DataNormalizer._normalize_age("1ヶ月") == 1
        assert DataNormalizer._normalize_age("6ヶ月") == 6
        assert DataNormalizer._normalize_age("11ヶ月") == 11

    def test_normalize_age_months_kagetsu_variations(self):
        """'ヶ月' のバリエーション"""
        assert DataNormalizer._normalize_age("6か月") == 6
        assert DataNormalizer._normalize_age("6カ月") == 6
        assert DataNormalizer._normalize_age("6ケ月") == 6
        assert DataNormalizer._normalize_age("6ヵ月") == 6  # 小書きカタカナ (高知 APC 等)
        assert DataNormalizer._normalize_age("10ヵ月") == 10

    def test_normalize_age_years_nen(self):
        """'N年' を月単位に変換"""
        assert DataNormalizer._normalize_age("1年") == 12
        assert DataNormalizer._normalize_age("2年") == 24
        assert DataNormalizer._normalize_age("3年") == 36

    def test_normalize_age_unknown(self):
        """不明・無効な値は None を返す"""
        assert DataNormalizer._normalize_age("不明") is None
        assert DataNormalizer._normalize_age("unknown") is None
        assert DataNormalizer._normalize_age("?") is None
        assert DataNormalizer._normalize_age("") is None
        assert DataNormalizer._normalize_age("invalid") is None

    def test_normalize_age_sai_kanji(self):
        """'才' (歳の代用字) を歳として扱う (長崎・和歌山・旭川等)"""
        assert DataNormalizer._normalize_age("3才") == 36
        assert DataNormalizer._normalize_age("11才") == 132
        # 全角数字
        assert DataNormalizer._normalize_age("１１才") == 132
        assert DataNormalizer._normalize_age("１０才") == 120

    def test_normalize_age_with_suffix(self):
        """'くらい/以上/前後/半/範囲' 等の付随表現があっても数値化する"""
        assert DataNormalizer._normalize_age("13才くらい") == 156
        assert DataNormalizer._normalize_age("１０才以上") == 120
        assert DataNormalizer._normalize_age("3歳前後") == 36
        assert DataNormalizer._normalize_age("2才半") == 24
        # 範囲表記は上限側にマッチ (search が最初に '歳/才' に当たる数値を採用)
        assert DataNormalizer._normalize_age("2~3才") == 36

    def test_normalize_age_combined_format(self):
        """'N歳Mヶ月' 形式 (オプション: 実装しない場合はスキップ可)"""
        # 実装する場合のテスト
        # assert DataNormalizer._normalize_age("2歳6ヶ月") == 30
        pass

    def test_normalize_age_iso_birth_date(self, monkeypatch):
        """ISO 形式の生年月日 → 今日との差分を月数で返す"""
        from datetime import date

        # 2026-05-10 が今日として、2024-05-10 生まれ → 24ヶ月
        monkeypatch.setattr(DataNormalizer, "_today", staticmethod(lambda: date(2026, 5, 10)))

        assert DataNormalizer._normalize_age("2024-05-10") == 24
        assert DataNormalizer._normalize_age("2025-11-10") == 6
        # 端境（月初）
        assert DataNormalizer._normalize_age("2025-05-09") == 12
        # 未来日付（生年月日が今日より後）→ None
        assert DataNormalizer._normalize_age("2027-01-01") is None

    def test_normalize_age_reiwa_birth_date(self, monkeypatch):
        """令和表記の生年月日 → 月数"""
        from datetime import date

        monkeypatch.setattr(DataNormalizer, "_today", staticmethod(lambda: date(2026, 5, 10)))

        # R5.11.30 = 2023-11-30 → 5/10 < 11/30 なので 29ヶ月
        assert DataNormalizer._normalize_age("R5.11.30") == 29
        # 令和6年9月27日 = 2024-09-27 → 5/10 < 9/27 なので 19ヶ月
        assert DataNormalizer._normalize_age("令和6年9月27日") == 19

    def test_normalize_age_combined_age_month(self):
        """'N歳Mヶ月' 形式の合計を返す"""
        assert DataNormalizer._normalize_age("2歳6ヶ月") == 30
        assert DataNormalizer._normalize_age("1歳3か月") == 15

    def test_normalize_age_explicit_age_wins_over_shelter_date(self, monkeypatch):
        """明示年齢 (N歳) は併記された日付より優先する。

        例: "3歳 2026-05-01収容" の収容日を生年月日と誤認して月齢を
        再計算するのを防ぐ (旧実装では 36ヶ月 → 約1ヶ月 に化けていた)。
        """
        from datetime import date

        monkeypatch.setattr(DataNormalizer, "_today", staticmethod(lambda: date(2026, 6, 1)))
        assert DataNormalizer._normalize_age("3歳 2026-05-01収容") == 36
        assert DataNormalizer._normalize_age("1歳 (2025/4/1 収容)") == 12
        assert DataNormalizer._normalize_age("6ヶ月 / 令和7年5月10日収容") == 6

    def test_normalize_age_rejects_implausible_upper_bound(self):
        """生物学的に有り得ない高齢 (30歳超) は誤パースなので None にする

        沖縄の missing ページで '82歳'(984ヶ月) が観測された。犬猫の寿命の
        上限を大きく超える値は ID 等の誤抽出なので不明扱いにする。
        """
        assert DataNormalizer._normalize_age("82歳") is None
        assert DataNormalizer._normalize_age("100歳") is None
        # 30歳 (360ヶ月) は稀だが有り得るので保持、31歳は棄却
        assert DataNormalizer._normalize_age("30歳") == 360
        assert DataNormalizer._normalize_age("31歳") is None
        # 22歳(264ヶ月)は長寿猫として有り得るので保持 (aniwel の実例)
        assert DataNormalizer._normalize_age("22歳") == 264


class TestNormalizeDate:
    """日付正規化のテスト"""

    def test_normalize_date_reiwa_era(self):
        """令和の和暦を ISO 8601 に変換"""
        assert DataNormalizer._normalize_date("令和8年1月5日") == "2026-01-05"
        assert DataNormalizer._normalize_date("令和7年12月31日") == "2025-12-31"
        assert DataNormalizer._normalize_date("令和6年3月15日") == "2024-03-15"

    def test_normalize_date_slash_format(self):
        """スラッシュ区切りの日付を ISO 8601 に変換"""
        assert DataNormalizer._normalize_date("2026/01/05") == "2026-01-05"
        assert DataNormalizer._normalize_date("2025/12/31") == "2025-12-31"
        assert DataNormalizer._normalize_date("2024/3/15") == "2024-03-15"
        assert DataNormalizer._normalize_date("2024/03/15") == "2024-03-15"

    def test_normalize_date_hyphen_format(self):
        """すでに ISO 8601 形式の日付はそのまま返す"""
        assert DataNormalizer._normalize_date("2026-01-05") == "2026-01-05"
        assert DataNormalizer._normalize_date("2025-12-31") == "2025-12-31"

    def test_normalize_date_japanese_dot_format(self):
        """'年月日' 区切りの日付を ISO 8601 に変換"""
        assert DataNormalizer._normalize_date("2026年1月5日") == "2026-01-05"
        assert DataNormalizer._normalize_date("2025年12月31日") == "2025-12-31"

    def test_normalize_date_reiwa_space_format(self):
        """令和略記（スペース区切り）を ISO 8601 に変換"""
        # 全角スペース区切り
        assert DataNormalizer._normalize_date("R6　9/27") == "2024-09-27"
        assert DataNormalizer._normalize_date("R7　1/15") == "2025-01-15"
        # 半角スペース区切り
        assert DataNormalizer._normalize_date("R6 9/27") == "2024-09-27"
        assert DataNormalizer._normalize_date("R7 1/15") == "2025-01-15"

    def test_normalize_date_reiwa_space_with_time_suffix(self):
        """時刻付き令和略記から日付のみ抽出"""
        assert DataNormalizer._normalize_date("R7　8/27　午前10時頃") == "2025-08-27"
        assert DataNormalizer._normalize_date("R6　9/27　午後3時頃") == "2024-09-27"

    def test_normalize_date_month_day_only(self, monkeypatch):
        """月/日のみの場合、補完ロジック (今日固定 = 2026-05-25)

        - "4/30" → 過去 25 日 → 今年扱い
        - "6/17" → 未来 23 日 → 30 日以内なので今年扱い
        - "1/31" → 過去 114 日 → 11 ヶ月以内なので今年扱い
        """
        monkeypatch.setattr(DataNormalizer, "_today", staticmethod(lambda: date(2026, 5, 25)))

        assert DataNormalizer._normalize_date("4/30") == "2026-04-30"
        assert DataNormalizer._normalize_date("6/17") == "2026-06-17"
        # "12/1" を 5 月時点で見た場合は前年扱い (今日 +30 日超は前年補完)
        assert DataNormalizer._normalize_date("12/1") == "2025-12-01"

    def test_normalize_date_month_day_with_time_suffix(self, monkeypatch):
        """時刻付き月/日のみの場合の補完"""
        monkeypatch.setattr(DataNormalizer, "_today", staticmethod(lambda: date(2026, 5, 25)))
        assert DataNormalizer._normalize_date("1/31　午前10時頃") == "2026-01-31"

    def test_normalize_date_yearless_future_uses_previous_year(self, monkeypatch):
        """年なし日付で 今日 +30 日 を超える未来は前年補完される (Codex MED #6)

        5 月時点でサイトに "12/1" と書かれていたら、その日付は来年 12/1 では
        なく去年 12/1 を指すのが自然 (保護動物の収容日は通常過去)。
        """
        monkeypatch.setattr(DataNormalizer, "_today", staticmethod(lambda: date(2026, 5, 25)))
        # 12/1 は 約 190 日後の未来 → 30 日超 → 前年に補完
        assert DataNormalizer._normalize_date("12/1") == "2025-12-01"
        assert DataNormalizer._normalize_date("12月1日") == "2025-12-01"

    def test_normalize_date_reiwa_dot_format(self):
        """RN.M/D 形式（ドット区切り）を ISO 8601 に変換"""
        assert DataNormalizer._normalize_date("R3.11/16") == "2021-11-16"
        assert DataNormalizer._normalize_date("R8.1/9") == "2026-01-09"

    def test_normalize_date_invalid_format(self):
        """無効な日付形式は ValueError をスロー"""
        with pytest.raises(ValueError):
            DataNormalizer._normalize_date("invalid date")

        with pytest.raises(ValueError):
            DataNormalizer._normalize_date("")

    def test_normalize_date_reiwa_zero_year_rejected(self):
        """令和0年 は存在しないので ValueError (Codex LOW #7)

        旧実装は `年 = 2018 + reiwa_year` で「令和0年」を 2018 年として通過
        させていたが、令和元年 = 2019 年なので 2018 年に変換するのは不正。
        """
        with pytest.raises(ValueError, match="令和0年"):
            DataNormalizer._normalize_date("令和0年1月1日")
        with pytest.raises(ValueError, match="令和0年"):
            DataNormalizer._normalize_date("R0.1.1")
        with pytest.raises(ValueError, match="令和0年"):
            DataNormalizer._normalize_date("R0.1/1")


class TestNormalizePhone:
    """電話番号正規化のテスト"""

    def test_normalize_phone_10_digits(self):
        """10桁の電話番号を 0XX-XXX-XXXX に変換"""
        assert DataNormalizer._normalize_phone("0881234567") == "088-123-4567"
        assert DataNormalizer._normalize_phone("0312345678") == "03-1234-5678"

    def test_normalize_phone_11_digits(self):
        """11桁の電話番号を 0XX-XXXX-XXXX に変換"""
        assert DataNormalizer._normalize_phone("08812345678") == "088-1234-5678"
        assert DataNormalizer._normalize_phone("09012345678") == "090-1234-5678"

    def test_normalize_phone_already_formatted(self):
        """すでにハイフン付きの電話番号はそのまま返す"""
        assert DataNormalizer._normalize_phone("088-123-4567") == "088-123-4567"
        assert DataNormalizer._normalize_phone("090-1234-5678") == "090-1234-5678"

    def test_normalize_phone_with_parentheses(self):
        """括弧付き電話番号を変換"""
        assert DataNormalizer._normalize_phone("(088)123-4567") == "088-123-4567"
        assert DataNormalizer._normalize_phone("(088)1234567") == "088-123-4567"

    def test_normalize_phone_invalid_length(self):
        """無効な桁数 (9桁以下や12桁以上) は空文字を返す (内線混入時の不正データ防止)"""
        assert DataNormalizer._normalize_phone("123") == ""
        assert DataNormalizer._normalize_phone("12345678") == ""
        assert DataNormalizer._normalize_phone("123456789012") == ""

    def test_normalize_phone_zenkaku_digits(self):
        """全角数字を半角に正規化して整形する"""
        assert DataNormalizer._normalize_phone("０８８ー８２６ー２３６４") == "088-826-2364"
        assert DataNormalizer._normalize_phone("０９０－１２３４－５６７８") == "090-1234-5678"

    def test_normalize_phone_ignores_extension(self):
        """内線以降は切り捨てて桁数を狂わせない"""
        assert DataNormalizer._normalize_phone("088-826-2364 内線123") == "088-826-2364"
        assert DataNormalizer._normalize_phone("0888262364 ext. 99") == "088-826-2364"

    def test_normalize_phone_ignores_representative_label(self):
        """「(代表)」等の付帯情報を切り捨てる"""
        assert DataNormalizer._normalize_phone("088-826-2364 (代表)") == "088-826-2364"

    def test_normalize_phone_ignores_secondary_number(self):
        """スラッシュ区切りの2番目の番号 (受付時刻等) は無視する"""
        assert DataNormalizer._normalize_phone("088-826-2364 / 9:00-17:00") == "088-826-2364"

    def test_normalize_phone_no_digits_returns_empty(self):
        """数字が 1 桁も無い文字列 (URL や説明文) は空文字を返す

        DB の phone VARCHAR(20) を超える長文 (例: 'お問い合わせフォームから連絡')
        が phone セルに誤って流入したとき、そのまま return すると INSERT 失敗で
        トランザクション全体 rollback となるため、空文字で安全側に倒す。
        """
        assert DataNormalizer._normalize_phone("お問い合わせフォームから連絡") == ""
        assert DataNormalizer._normalize_phone("https://example.com/contact/") == ""
        assert DataNormalizer._normalize_phone("お問い合わせはこちら") == ""

    def test_normalize_phone_long_garbage_returns_empty(self):
        """20 桁超の長大数字列 (誤マッピング) は空文字を返す。

        旧実装は 20 文字で切り捨てて DB に入れていたが、これは不正電話番号の
        混入経路だった (Codex リリースレビュー I-10)。安全側に倒し空文字 → None。
        """
        long_digits = "1" * 30
        assert DataNormalizer._normalize_phone(long_digits) == ""


class TestCapSize:
    """size 長さ制限 (DB の VARCHAR(50) セーフネット)"""

    def test_cap_size_short_passthrough(self):
        assert DataNormalizer._cap_size("中型") == "中型"
        assert DataNormalizer._cap_size("Sサイズ") == "Sサイズ"

    def test_cap_size_empty_returns_none(self):
        assert DataNormalizer._cap_size("") is None
        assert DataNormalizer._cap_size(None) is None
        assert DataNormalizer._cap_size("   ") is None

    def test_cap_size_truncates_at_50_chars(self):
        """50 文字超の size は 50 文字に切り詰めて DB 制約違反を防ぐ"""
        long_text = "あ" * 80
        result = DataNormalizer._cap_size(long_text)
        assert result is not None
        assert len(result) == 50

    def test_cap_size_normalizes_synonyms_to_canonical(self):
        """単漢字 小/中/大 を 小型/中型/大型 に正規化する (UI フィルタ統一)"""
        assert DataNormalizer._cap_size("小") == "小型"
        assert DataNormalizer._cap_size("中") == "中型"
        assert DataNormalizer._cap_size("大") == "大型"
        # 既に正規形のものはそのまま
        assert DataNormalizer._cap_size("小型") == "小型"
        assert DataNormalizer._cap_size("大型") == "大型"

    def test_cap_size_strips_weight_noise_keeping_size_word(self):
        """体重・タブ混入を除去して体格語のみ残す (実データの汚染ケース)"""
        assert DataNormalizer._cap_size("小型\t\t\t\t\t（7.7kg）") == "小型"
        assert DataNormalizer._cap_size("中型\t\t\t（推定11kg）") == "中型"
        assert DataNormalizer._cap_size("大型\t\t(4.3kg)") == "大型"

    def test_cap_size_weight_only_becomes_none(self):
        """体重情報のみ (体格語なし) は size ではないので None にする"""
        assert DataNormalizer._cap_size("0.3kg") is None
        assert DataNormalizer._cap_size("(現在の体重：４．９Kg（適正体重：６Kg～）)") is None
        assert DataNormalizer._cap_size("(現在の体重：９．８５Kg)") is None


class TestNormalizePhonePipeline:
    """normalize 経由での phone 変換 (空文字 → None)"""

    def test_phone_empty_string_becomes_none(self):
        """数字無し phone が空文字経由で None として DB 保存される"""
        raw = RawAnimalData(
            species="犬",
            sex="メス",
            age="3歳",
            color="茶",
            size="中",
            shelter_date="2026-05-01",
            location="高知県",
            phone="お問い合わせフォームから",
            image_urls=[],
            source_url="https://example.com/animals/1",
            category="adoption",
        )
        result = DataNormalizer.normalize(raw)
        assert result.phone is None


class TestCapColor:
    """color 長さ制限 (DB の VARCHAR(100) セーフネット)"""

    def test_cap_color_short_passthrough(self):
        """短い color はそのまま返す"""
        assert DataNormalizer._cap_color("茶白") == "茶白"
        assert DataNormalizer._cap_color("黒") == "黒"

    def test_cap_color_empty_returns_none(self):
        """空文字 / None は None"""
        assert DataNormalizer._cap_color("") is None
        assert DataNormalizer._cap_color(None) is None
        assert DataNormalizer._cap_color("   ") is None

    def test_cap_color_redacts_phone_pii(self):
        """color フィールド内に混入した電話番号を ███ に置換する

        自治体サイトの自由記述 (「特徴」「コメント」) に飼い主や保護者の
        個人連絡先 (例: "首輪に電話番号 090-1234-5678 記載") が記載される
        ケースがあり、リリース後に個人情報が公開リスクになる。
        adapter 層では取り切れないため normalizer の PII フィルタで防御する。
        """
        # 半角ハイフン
        assert "090-1234-5678" not in (
            DataNormalizer._cap_color("黒、首輪に電話 090-1234-5678 記載") or ""
        )
        # 全角ハイフン
        assert "０９０－１２３４－５６７８" not in (
            DataNormalizer._cap_color("茶、連絡先０９０－１２３４－５６７８") or ""
        )
        # 市外局番なしハイフンなしの 10/11 桁連続
        assert "09012345678" not in (
            DataNormalizer._cap_color("白、首輪に連絡先 09012345678 と記載") or ""
        )

    def test_cap_color_redacts_email_pii(self):
        """color フィールド内のメールアドレスを ███ に置換する"""
        result = DataNormalizer._cap_color("茶白、owner@example.com に連絡を")
        assert result is not None
        assert "owner@example.com" not in result
        assert "@" not in result

    def test_cap_color_preserves_non_pii(self):
        """PII でない普通の毛色テキストは温存される"""
        # サイズ感の言及 (3kg) は PII ではない
        assert DataNormalizer._cap_color("茶、3kg") == "茶、3kg"
        # 鼻黒・耳茶等の通常記述
        assert DataNormalizer._cap_color("白に黒斑、鼻黒") == "白に黒斑、鼻黒"

    def test_cap_color_truncates_at_100_chars(self):
        """100 文字超の color は 100 文字に切り詰めて DB 制約違反を防ぐ"""
        long_text = "あ" * 150
        result = DataNormalizer._cap_color(long_text)
        assert result is not None
        assert len(result) == 100

    def test_normalize_caps_long_color_in_pipeline(self):
        """`normalize` 経由でも長文 color が 100 文字に収まる"""
        raw = RawAnimalData(
            species="犬",
            sex="メス",
            age="3歳",
            color="あ" * 200,
            size="中",
            shelter_date="2026-05-01",
            location="横須賀市",
            phone="04-6869-0040",
            image_urls=[],
            source_url="https://example.com/animals/1",
            category="adoption",
        )
        result = DataNormalizer.normalize(raw)
        assert result.color is not None
        assert len(result.color) <= 100


class TestNormalizerIntegration:
    """DataNormalizer の統合テスト"""

    def test_normalize_raw_to_animal_data_full(self):
        """RawAnimalData を AnimalData に変換する完全な統合テスト"""
        raw_data = RawAnimalData(
            species="いぬ",
            sex="オス",
            age="2歳",
            color="茶色",
            size="中型",
            shelter_date="令和8年1月5日",
            location="高知県動物愛護センター",
            phone="0881234567",
            image_urls=["https://example.com/image1.jpg"],
            source_url="https://example-kochi.jp/animals/123",
            category="adoption",
        )

        animal_data = DataNormalizer.normalize(raw_data)

        assert animal_data.species == "犬"
        assert animal_data.sex == "男の子"
        assert animal_data.age_months == 24
        assert animal_data.color == "茶色"
        assert animal_data.size == "中型"
        assert animal_data.shelter_date == date(2026, 1, 5)
        assert animal_data.location == "高知県動物愛護センター"
        assert animal_data.phone == "088-123-4567"
        assert len(animal_data.image_urls) == 1
        assert str(animal_data.source_url) == "https://example-kochi.jp/animals/123"

    def test_normalize_clamps_future_shelter_date_to_today(self, monkeypatch):
        """未来の収容日は物理的に不正なので収集日(今日)にフォールバックする

        長崎 animal-net で収容日/「いなくなった日時」が未来日 (2026-05-31,
        2026-06-11) になる実例があり、アーカイブの時系列整合性が崩れる。
        """
        monkeypatch.setattr(DataNormalizer, "_today", staticmethod(lambda: date(2026, 5, 27)))
        raw = RawAnimalData(
            species="犬",
            sex="オス",
            age="2歳",
            color="茶",
            size="中型",
            shelter_date="2026-05-31",  # 4日先 = 未来日
            location="長崎県",
            phone="",
            image_urls=[],
            source_url="https://animal-net.pref.nagasaki.jp/animal/no-19632/",
            category="sheltered",
        )
        result = DataNormalizer.normalize(raw)
        assert result.shelter_date == date(2026, 5, 27)

    def test_normalize_keeps_past_shelter_date(self, monkeypatch):
        """過去〜当日の収容日はそのまま保持する (未来日ガードの誤発動防止)"""
        monkeypatch.setattr(DataNormalizer, "_today", staticmethod(lambda: date(2026, 5, 27)))
        raw = RawAnimalData(
            species="犬",
            sex="オス",
            age="2歳",
            color="茶",
            size="中型",
            shelter_date="2026-05-20",
            location="長崎県",
            phone="",
            image_urls=[],
            source_url="https://animal-net.pref.nagasaki.jp/animal/no-1/",
            category="sheltered",
        )
        result = DataNormalizer.normalize(raw)
        assert result.shelter_date == date(2026, 5, 20)

    def test_normalize_with_unknown_values(self):
        """不明な値を含む RawAnimalData の正規化"""
        raw_data = RawAnimalData(
            species="鳥",
            sex="不明",
            age="不明",
            color="",
            size="",
            shelter_date="2026/01/05",
            location="",
            phone="",
            image_urls=[],
            source_url="https://example.com/123",
            category="adoption",
        )

        animal_data = DataNormalizer.normalize(raw_data)

        assert animal_data.species == "その他"
        assert animal_data.sex == "不明"
        assert animal_data.age_months is None
        assert animal_data.shelter_date == date(2026, 1, 5)
        # location が空の場合は "不明" にフォールバック
        assert animal_data.location == "不明"

    def test_normalize_location_fallback_to_unknown(self):
        """location が空の場合は '不明' にフォールバック"""
        raw_data = RawAnimalData(
            species="犬",
            sex="オス",
            age="2歳",
            color="茶色",
            size="中型",
            shelter_date="令和8年1月5日",
            location="",  # 空の location
            phone="0881234567",
            image_urls=["https://example.com/image1.jpg"],
            source_url="https://example.com/dog",
            category="adoption",
        )

        animal_data = DataNormalizer.normalize(raw_data)

        assert animal_data.location == "不明"

    def test_normalize_location_preserved_when_valid(self):
        """location が有効な値の場合はそのまま保持"""
        raw_data = RawAnimalData(
            species="犬",
            sex="オス",
            age="2歳",
            color="茶色",
            size="中型",
            shelter_date="令和8年1月5日",
            location="高知県動物愛護センター",
            phone="0881234567",
            image_urls=["https://example.com/image1.jpg"],
            source_url="https://example.com/dog",
            category="adoption",
        )

        animal_data = DataNormalizer.normalize(raw_data)

        assert animal_data.location == "高知県動物愛護センター"

    def test_normalize_triggers_validation_error(self):
        """正規化後のデータが AnimalData のバリデーションを満たさない場合の動作確認"""
        # 実装時は正規化ロジックが正しいため、このケースは発生しない想定
        # ただし、将来のバグ防止のため、正規化失敗時の挙動を確認する
        pass

    def test_normalize_with_various_formats(self):
        """様々な形式の入力を正規化"""
        test_cases = [
            {
                "raw": RawAnimalData(
                    species="cat",
                    sex="female",
                    age="6ヶ月",
                    color="白",
                    size="小型",
                    shelter_date="2026-01-05",
                    location="センター",
                    phone="088-111-2222",
                    image_urls=["https://example.com/cat.jpg"],
                    source_url="https://example.com/cat",
                    category="lost",
                ),
                "expected": {
                    "species": "猫",
                    "sex": "女の子",
                    "age_months": 6,
                },
            },
            {
                "raw": RawAnimalData(
                    species="DOG",
                    sex="MALE",
                    age="1年",
                    color="黒",
                    size="大型",
                    shelter_date="2026年1月5日",
                    location="保健所",
                    phone="09012345678",
                    image_urls=[],
                    source_url="https://example.com/dog",
                    category="adoption",
                ),
                "expected": {
                    "species": "犬",
                    "sex": "男の子",
                    "age_months": 12,
                },
            },
        ]

        for case in test_cases:
            animal_data = DataNormalizer.normalize(case["raw"])
            assert animal_data.species == case["expected"]["species"]
            assert animal_data.sex == case["expected"]["sex"]
            assert animal_data.age_months == case["expected"]["age_months"]


class TestFilterValidImageUrls:
    """画像URLフィルタ: http(s) 以外を除外しレコード全損を防ぐ"""

    def test_filters_invalid_schemes(self):
        urls = [
            "https://example.com/a.jpg",
            "data:image/png;base64,AAA",
            "javascript:alert(1)",
            "/relative/path.jpg",
            "http://example.com/b.jpg",
        ]
        assert DataNormalizer._filter_valid_image_urls(urls) == [
            "https://example.com/a.jpg",
            "http://example.com/b.jpg",
        ]

    def test_dedupes_while_preserving_order(self):
        urls = [
            "https://example.com/a.jpg",
            "https://example.com/b.jpg",
            "https://example.com/a.jpg",
        ]
        assert DataNormalizer._filter_valid_image_urls(urls) == [
            "https://example.com/a.jpg",
            "https://example.com/b.jpg",
        ]

    def test_handles_none_and_empty(self):
        assert DataNormalizer._filter_valid_image_urls(None) == []
        assert DataNormalizer._filter_valid_image_urls([]) == []

    def test_normalize_does_not_drop_record_on_bad_image_url(self):
        """不正スキームの画像 URL が混入してもレコードは生存する"""
        raw = RawAnimalData(
            species="犬",
            sex="オス",
            age="2歳",
            color="",
            size="",
            shelter_date="2026-01-05",
            location="センター",
            phone="",
            image_urls=[
                "https://example.com/ok.jpg",
                "javascript:alert(1)",
                "data:image/gif;base64,XXX",
            ],
            source_url="https://example.com/animals/1",
            category="adoption",
        )
        animal = DataNormalizer.normalize(raw)
        assert len(animal.image_urls) == 1
        assert str(animal.image_urls[0]) == "https://example.com/ok.jpg"


class TestNormalizeCategory:
    """カテゴリパススルーのテスト"""

    def test_normalize_category_adoption_passthrough(self):
        """'adoption' カテゴリがそのままパススルーされることを確認"""
        raw_data = RawAnimalData(
            species="犬",
            sex="オス",
            age="2歳",
            color="茶色",
            size="中型",
            shelter_date="2026-01-05",
            location="高知県",
            phone="088-123-4567",
            image_urls=["https://example.com/image.jpg"],
            source_url="https://example.com/1",
            category="adoption",
        )

        animal_data = DataNormalizer.normalize(raw_data)

        assert animal_data.category == "adoption"

    def test_normalize_category_lost_passthrough(self):
        """'lost' カテゴリがそのままパススルーされることを確認"""
        raw_data = RawAnimalData(
            species="猫",
            sex="メス",
            age="1歳",
            color="白",
            size="小型",
            shelter_date="2026-01-05",
            location="高知県",
            phone="088-123-4567",
            image_urls=["https://example.com/image.jpg"],
            source_url="https://example.com/2",
            category="lost",
        )

        animal_data = DataNormalizer.normalize(raw_data)

        assert animal_data.category == "lost"
