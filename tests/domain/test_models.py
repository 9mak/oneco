"""
データモデル (AnimalData, RawAnimalData) のユニットテスト
"""
import pytest
from datetime import date
from pydantic import ValidationError, HttpUrl

from src.data_collector.domain.models import RawAnimalData, AnimalData


class TestRawAnimalData:
    """RawAnimalData モデルのテスト"""

    def test_raw_animal_data_instantiation(self):
        """全フィールドを持つ RawAnimalData の生成"""
        raw_data = RawAnimalData(
            species="いぬ",
            sex="オス",
            age="2歳",
            color="茶色",
            size="中型",
            shelter_date="令和8年1月5日",
            location="高知県動物愛護センター",
            phone="0881234567",
            image_urls=["https://example.com/image1.jpg", "https://example.com/image2.jpg"],
            source_url="https://example-kochi.jp/animals/123"
        )

        assert raw_data.species == "いぬ"
        assert raw_data.sex == "オス"
        assert raw_data.age == "2歳"
        assert raw_data.color == "茶色"
        assert raw_data.size == "中型"
        assert raw_data.shelter_date == "令和8年1月5日"
        assert raw_data.location == "高知県動物愛護センター"
        assert raw_data.phone == "0881234567"
        assert len(raw_data.image_urls) == 2
        assert raw_data.source_url == "https://example-kochi.jp/animals/123"

    def test_raw_animal_data_all_fields_are_strings(self):
        """全フィールドが文字列型を受け入れる"""
        raw_data = RawAnimalData(
            species="dog",
            sex="male",
            age="unknown",
            color="brown",
            size="medium",
            shelter_date="2026-01-05",
            location="Kochi",
            phone="088-123-4567",
            image_urls=["url1", "url2"],
            source_url="https://example.com"
        )

        # すべてのフィールドが文字列型であることを確認
        assert isinstance(raw_data.species, str)
        assert isinstance(raw_data.sex, str)
        assert isinstance(raw_data.age, str)
        assert isinstance(raw_data.color, str)
        assert isinstance(raw_data.size, str)
        assert isinstance(raw_data.shelter_date, str)
        assert isinstance(raw_data.location, str)
        assert isinstance(raw_data.phone, str)

    def test_raw_animal_data_serialization(self):
        """Pydantic シリアライゼーションの動作確認"""
        raw_data = RawAnimalData(
            species="猫",
            sex="メス",
            age="6ヶ月",
            color="白",
            size="小型",
            shelter_date="2026/01/05",
            location="センター",
            phone="088-111-2222",
            image_urls=["https://example.com/cat.jpg"],
            source_url="https://example.com/123"
        )

        # model_dump
        data_dict = raw_data.model_dump()
        assert data_dict["species"] == "猫"
        assert data_dict["sex"] == "メス"

        # model_dump_json
        json_str = raw_data.model_dump_json()
        assert "猫" in json_str
        assert "メス" in json_str


class TestAnimalData:
    """AnimalData モデルのテスト"""

    def test_animal_data_with_valid_data(self):
        """有効なデータで AnimalData を生成"""
        animal = AnimalData(
            species="犬",
            sex="男の子",
            age_months=24,
            color="茶色",
            size="中型",
            shelter_date=date(2026, 1, 5),
            location="高知県動物愛護センター",
            phone="088-123-4567",
            image_urls=["https://example.com/image1.jpg"],
            source_url="https://example-kochi.jp/animals/123"
        )

        assert animal.species == "犬"
        assert animal.sex == "男の子"
        assert animal.age_months == 24
        assert animal.color == "茶色"
        assert animal.size == "中型"
        assert animal.shelter_date == date(2026, 1, 5)
        assert animal.location == "高知県動物愛護センター"
        assert animal.phone == "088-123-4567"
        assert len(animal.image_urls) == 1
        assert str(animal.source_url) == "https://example-kochi.jp/animals/123"

    def test_species_validation_valid_values(self):
        """species フィールドの3値制約テスト (有効な値)"""
        # 犬
        animal_dog = AnimalData(
            species="犬",
            shelter_date=date(2026, 1, 5),
            source_url="https://example.com/1"
        )
        assert animal_dog.species == "犬"

        # 猫
        animal_cat = AnimalData(
            species="猫",
            shelter_date=date(2026, 1, 5),
            source_url="https://example.com/2"
        )
        assert animal_cat.species == "猫"

        # その他
        animal_other = AnimalData(
            species="その他",
            shelter_date=date(2026, 1, 5),
            source_url="https://example.com/3"
        )
        assert animal_other.species == "その他"

    def test_species_validation_invalid_values(self):
        """species フィールドの3値制約テスト (無効な値)"""
        with pytest.raises(ValidationError) as exc_info:
            AnimalData(
                species="鳥",  # "犬", "猫", "その他" 以外は無効
                shelter_date=date(2026, 1, 5),
                source_url="https://example.com/1"
            )

        error = exc_info.value.errors()[0]
        assert "species" in error["loc"]
        assert "犬" in str(error["msg"]) or "猫" in str(error["msg"]) or "その他" in str(error["msg"])

    def test_sex_validation_valid_values(self):
        """sex フィールドの3値制約テスト (有効な値)"""
        # 男の子
        animal_male = AnimalData(
            species="犬",
            sex="男の子",
            shelter_date=date(2026, 1, 5),
            source_url="https://example.com/1"
        )
        assert animal_male.sex == "男の子"

        # 女の子
        animal_female = AnimalData(
            species="猫",
            sex="女の子",
            shelter_date=date(2026, 1, 5),
            source_url="https://example.com/2"
        )
        assert animal_female.sex == "女の子"

        # 不明
        animal_unknown = AnimalData(
            species="その他",
            sex="不明",
            shelter_date=date(2026, 1, 5),
            source_url="https://example.com/3"
        )
        assert animal_unknown.sex == "不明"

    def test_sex_validation_invalid_values(self):
        """sex フィールドの3値制約テスト (無効な値)"""
        with pytest.raises(ValidationError) as exc_info:
            AnimalData(
                species="犬",
                sex="オス",  # "男の子", "女の子", "不明" 以外は無効
                shelter_date=date(2026, 1, 5),
                source_url="https://example.com/1"
            )

        error = exc_info.value.errors()[0]
        assert "sex" in error["loc"]

    def test_age_months_negative_value_rejection(self):
        """age_months の負値チェックテスト"""
        with pytest.raises(ValidationError) as exc_info:
            AnimalData(
                species="犬",
                age_months=-5,  # 負値は無効
                shelter_date=date(2026, 1, 5),
                source_url="https://example.com/1"
            )

        error = exc_info.value.errors()[0]
        assert "age_months" in error["loc"]

    def test_age_months_none_is_valid(self):
        """age_months に None を設定可能"""
        animal = AnimalData(
            species="犬",
            age_months=None,
            shelter_date=date(2026, 1, 5),
            source_url="https://example.com/1"
        )
        assert animal.age_months is None

    def test_required_fields_missing(self):
        """必須フィールド欠損時の ValidationError スロー確認"""
        # species が欠損
        with pytest.raises(ValidationError) as exc_info:
            AnimalData(
                shelter_date=date(2026, 1, 5),
                source_url="https://example.com/1"
            )
        assert any("species" in str(err["loc"]) for err in exc_info.value.errors())

        # shelter_date が欠損
        with pytest.raises(ValidationError) as exc_info:
            AnimalData(
                species="犬",
                source_url="https://example.com/1"
            )
        assert any("shelter_date" in str(err["loc"]) for err in exc_info.value.errors())

        # source_url が欠損
        with pytest.raises(ValidationError) as exc_info:
            AnimalData(
                species="犬",
                shelter_date=date(2026, 1, 5)
            )
        assert any("source_url" in str(err["loc"]) for err in exc_info.value.errors())

    def test_json_serialization_deserialization(self):
        """JSON シリアライゼーション・デシリアライゼーションの正確性確認"""
        animal = AnimalData(
            species="犬",
            sex="男の子",
            age_months=24,
            color="茶色",
            shelter_date=date(2026, 1, 5),
            location="高知県",
            phone="088-123-4567",
            image_urls=["https://example.com/image.jpg"],
            source_url="https://example.com/123"
        )

        # シリアライゼーション
        json_data = animal.model_dump_json()
        assert "犬" in json_data
        assert "男の子" in json_data

        # デシリアライゼーション
        animal_dict = animal.model_dump()
        recreated_animal = AnimalData(**animal_dict)

        assert recreated_animal.species == animal.species
        assert recreated_animal.sex == animal.sex
        assert recreated_animal.age_months == animal.age_months
        assert recreated_animal.shelter_date == animal.shelter_date

    def test_default_values(self):
        """デフォルト値のテスト"""
        animal = AnimalData(
            species="犬",
            shelter_date=date(2026, 1, 5),
            source_url="https://example.com/1"
        )

        # sex のデフォルトは "不明"
        assert animal.sex == "不明"

        # age_months のデフォルトは None
        assert animal.age_months is None

        # color, size, location, phone のデフォルトは None
        assert animal.color is None
        assert animal.size is None
        assert animal.location is None
        assert animal.phone is None

        # image_urls のデフォルトは空リスト
        assert animal.image_urls == []
