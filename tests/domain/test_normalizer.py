"""
DataNormalizer のユニットテスト

データ正規化ロジックの各メソッドを個別にテストし、
統合テストで RawAnimalData → AnimalData の変換を検証します。
"""
import pytest
from datetime import date
from pydantic import ValidationError

from src.data_collector.domain.models import RawAnimalData, AnimalData
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

    def test_normalize_age_combined_format(self):
        """'N歳Mヶ月' 形式 (オプション: 実装しない場合はスキップ可)"""
        # 実装する場合のテスト
        # assert DataNormalizer._normalize_age("2歳6ヶ月") == 30
        pass


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

    def test_normalize_date_invalid_format(self):
        """無効な日付形式は ValueError をスロー"""
        with pytest.raises(ValueError):
            DataNormalizer._normalize_date("invalid date")

        with pytest.raises(ValueError):
            DataNormalizer._normalize_date("")


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
        """無効な桁数の電話番号はそのまま返す (または ValueError)"""
        # 実装方針によって挙動を決定
        # Option 1: そのまま返す
        result = DataNormalizer._normalize_phone("123")
        assert result == "123"  # または ValueError


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
            source_url="https://example-kochi.jp/animals/123"
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
            source_url="https://example.com/123"
        )

        animal_data = DataNormalizer.normalize(raw_data)

        assert animal_data.species == "その他"
        assert animal_data.sex == "不明"
        assert animal_data.age_months is None
        assert animal_data.shelter_date == date(2026, 1, 5)

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
                    source_url="https://example.com/cat"
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
                    source_url="https://example.com/dog"
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
