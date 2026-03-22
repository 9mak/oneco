"""
データモデル (AnimalData, RawAnimalData) のユニットテスト
"""
import pytest
from datetime import date, datetime
from pydantic import ValidationError, HttpUrl

from src.data_collector.domain.models import RawAnimalData, AnimalData, AnimalStatus


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
            source_url="https://example-kochi.jp/animals/123",
            category="adoption"
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
        assert raw_data.category == "adoption"

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
            source_url="https://example.com",
            category="adoption"
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
            source_url="https://example.com/123",
            category="lost"
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
            source_url="https://example-kochi.jp/animals/123",
            category="adoption"
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
            location="高知県",
            source_url="https://example.com/1",
            category="adoption"
        )
        assert animal_dog.species == "犬"

        # 猫
        animal_cat = AnimalData(
            species="猫",
            shelter_date=date(2026, 1, 5),
            location="高知県",
            source_url="https://example.com/2",
            category="adoption"
        )
        assert animal_cat.species == "猫"

        # その他
        animal_other = AnimalData(
            species="その他",
            shelter_date=date(2026, 1, 5),
            location="高知県",
            source_url="https://example.com/3",
            category="adoption"
        )
        assert animal_other.species == "その他"

    def test_species_validation_invalid_values(self):
        """species フィールドの3値制約テスト (無効な値)"""
        with pytest.raises(ValidationError) as exc_info:
            AnimalData(
                species="鳥",  # "犬", "猫", "その他" 以外は無効
                shelter_date=date(2026, 1, 5),
                location="高知県",
                source_url="https://example.com/1",
            category="adoption"
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
            location="高知県",
            source_url="https://example.com/1",
            category="adoption"
        )
        assert animal_male.sex == "男の子"

        # 女の子
        animal_female = AnimalData(
            species="猫",
            sex="女の子",
            shelter_date=date(2026, 1, 5),
            location="高知県",
            source_url="https://example.com/2",
            category="adoption"
        )
        assert animal_female.sex == "女の子"

        # 不明
        animal_unknown = AnimalData(
            species="その他",
            sex="不明",
            shelter_date=date(2026, 1, 5),
            location="高知県",
            source_url="https://example.com/3",
            category="adoption"
        )
        assert animal_unknown.sex == "不明"

    def test_sex_validation_invalid_values(self):
        """sex フィールドの3値制約テスト (無効な値)"""
        with pytest.raises(ValidationError) as exc_info:
            AnimalData(
                species="犬",
                sex="オス",  # "男の子", "女の子", "不明" 以外は無効
                shelter_date=date(2026, 1, 5),
                location="高知県",
                source_url="https://example.com/1",
            category="adoption"
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
                location="高知県",
                source_url="https://example.com/1",
            category="adoption"
            )

        error = exc_info.value.errors()[0]
        assert "age_months" in error["loc"]

    def test_age_months_none_is_valid(self):
        """age_months に None を設定可能"""
        animal = AnimalData(
            species="犬",
            age_months=None,
            shelter_date=date(2026, 1, 5),
            location="高知県",
            source_url="https://example.com/1",
            category="adoption"
        )
        assert animal.age_months is None

    def test_required_fields_missing(self):
        """必須フィールド欠損時の ValidationError スロー確認"""
        # species が欠損
        with pytest.raises(ValidationError) as exc_info:
            AnimalData(
                shelter_date=date(2026, 1, 5),
                location="高知県",
                source_url="https://example.com/1",
            category="adoption"
            )
        assert any("species" in str(err["loc"]) for err in exc_info.value.errors())

        # shelter_date が欠損
        with pytest.raises(ValidationError) as exc_info:
            AnimalData(
                species="犬",
                location="高知県",
                source_url="https://example.com/1",
            category="adoption"
            )
        assert any("shelter_date" in str(err["loc"]) for err in exc_info.value.errors())

        # location が欠損
        with pytest.raises(ValidationError) as exc_info:
            AnimalData(
                species="犬",
                shelter_date=date(2026, 1, 5),
                source_url="https://example.com/1",
            category="adoption"
            )
        assert any("location" in str(err["loc"]) for err in exc_info.value.errors())

        # source_url が欠損
        with pytest.raises(ValidationError) as exc_info:
            AnimalData(
                species="犬",
                shelter_date=date(2026, 1, 5),
                location="高知県"
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
            source_url="https://example.com/123",
            category="adoption"
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
            location="高知県",  # location は必須フィールド
            source_url="https://example.com/1",
            category="adoption"
        )

        # sex のデフォルトは "不明"
        assert animal.sex == "不明"

        # age_months のデフォルトは None
        assert animal.age_months is None

        # color, size, phone のデフォルトは None
        assert animal.color is None
        assert animal.size is None
        assert animal.phone is None

        # image_urls のデフォルトは空リスト
        assert animal.image_urls == []

    def test_location_is_required(self):
        """location フィールドが必須であることを確認"""
        with pytest.raises(ValidationError) as exc_info:
            AnimalData(
                species="犬",
                shelter_date=date(2026, 1, 5),
                source_url="https://example.com/1",
            category="adoption"
                # location を意図的に省略
            )

        error = exc_info.value.errors()[0]
        assert "location" in error["loc"]


class TestRawAnimalDataCategory:
    """RawAnimalData の category フィールドのテスト"""

    def test_raw_animal_data_category_field_exists(self):
        """RawAnimalData に category フィールドが存在することを確認"""
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
            category="adoption"
        )

        assert raw_data.category == "adoption"
        assert isinstance(raw_data.category, str)

    def test_raw_animal_data_category_is_required(self):
        """RawAnimalData の category フィールドが必須であることを確認"""
        with pytest.raises(ValidationError) as exc_info:
            RawAnimalData(
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
                # category を意図的に省略
            )

        assert any("category" in str(err["loc"]) for err in exc_info.value.errors())


class TestAnimalDataCategory:
    """AnimalData の category フィールドのテスト"""

    def test_animal_data_category_field_exists(self):
        """AnimalData に category フィールドが存在することを確認"""
        animal = AnimalData(
            species="犬",
            shelter_date=date(2026, 1, 5),
            location="高知県",
            source_url="https://example.com/1",
            category="adoption"
        )

        assert animal.category == "adoption"
        assert isinstance(animal.category, str)

    def test_animal_data_category_is_required(self):
        """AnimalData の category フィールドが必須であることを確認"""
        with pytest.raises(ValidationError) as exc_info:
            AnimalData(
                species="犬",
                shelter_date=date(2026, 1, 5),
                location="高知県",
                source_url="https://example.com/1",
                # category を意図的に省略
            )

        assert any("category" in str(err["loc"]) for err in exc_info.value.errors())

    def test_animal_data_category_validates_adoption(self):
        """AnimalData が 'adoption' カテゴリを受け入れることを確認"""
        animal = AnimalData(
            species="犬",
            shelter_date=date(2026, 1, 5),
            location="高知県",
            source_url="https://example.com/1",
            category="adoption"
        )

        assert animal.category == "adoption"

    def test_animal_data_category_validates_lost(self):
        """AnimalData が 'lost' カテゴリを受け入れることを確認"""
        animal = AnimalData(
            species="猫",
            shelter_date=date(2026, 1, 5),
            location="高知県",
            source_url="https://example.com/2",
            category="lost"
        )

        assert animal.category == "lost"

    def test_animal_data_category_validates_sheltered(self):
        """AnimalData が 'sheltered' カテゴリを受け入れることを確認"""
        animal = AnimalData(
            species="犬",
            shelter_date=date(2026, 1, 5),
            location="高知県",
            source_url="https://example.com/3",
            category="sheltered"
        )

        assert animal.category == "sheltered"

    def test_animal_data_category_rejects_invalid_values(self):
        """AnimalData が無効なカテゴリ値を拒否することを確認"""
        with pytest.raises(ValidationError) as exc_info:
            AnimalData(
                species="犬",
                shelter_date=date(2026, 1, 5),
                location="高知県",
                source_url="https://example.com/1",
                category="invalid"
            )

        error = exc_info.value.errors()[0]
        assert "category" in error["loc"]
        assert "adoption" in str(error["msg"]) or "lost" in str(error["msg"]) or "sheltered" in str(error["msg"])


class TestAnimalStatus:
    """AnimalStatus 列挙型のテスト"""

    def test_animal_status_sheltered_value(self):
        """sheltered ステータスの値が正しいか"""
        assert AnimalStatus.SHELTERED == "sheltered"
        assert AnimalStatus.SHELTERED.value == "sheltered"

    def test_animal_status_adopted_value(self):
        """adopted ステータスの値が正しいか"""
        assert AnimalStatus.ADOPTED == "adopted"
        assert AnimalStatus.ADOPTED.value == "adopted"

    def test_animal_status_returned_value(self):
        """returned ステータスの値が正しいか"""
        assert AnimalStatus.RETURNED == "returned"
        assert AnimalStatus.RETURNED.value == "returned"

    def test_animal_status_deceased_value(self):
        """deceased ステータスの値が正しいか"""
        assert AnimalStatus.DECEASED == "deceased"
        assert AnimalStatus.DECEASED.value == "deceased"

    def test_animal_status_is_string_enum(self):
        """AnimalStatus が str と Enum の両方の性質を持つか"""
        # 文字列として比較可能
        assert AnimalStatus.SHELTERED == "sheltered"
        # Enum としてイテレーション可能
        statuses = list(AnimalStatus)
        assert len(statuses) == 4


class TestAnimalDataExtended:
    """AnimalData 拡張フィールドのテスト"""

    def test_animal_data_status_field_optional(self):
        """status フィールドがオプショナルでデフォルトが None であることを確認"""
        animal = AnimalData(
            species="犬",
            shelter_date=date(2026, 1, 5),
            location="高知県",
            source_url="https://example.com/1",
            category="adoption"
        )

        # status はデフォルトで None（後方互換性）
        assert animal.status is None

    def test_animal_data_status_field_accepts_enum(self):
        """status フィールドが AnimalStatus 列挙型を受け入れることを確認"""
        animal = AnimalData(
            species="犬",
            shelter_date=date(2026, 1, 5),
            location="高知県",
            source_url="https://example.com/1",
            category="adoption",
            status=AnimalStatus.SHELTERED
        )

        assert animal.status == AnimalStatus.SHELTERED

    def test_animal_data_status_field_accepts_string(self):
        """status フィールドが文字列も受け入れることを確認"""
        animal = AnimalData(
            species="犬",
            shelter_date=date(2026, 1, 5),
            location="高知県",
            source_url="https://example.com/1",
            category="adoption",
            status="adopted"
        )

        assert animal.status == AnimalStatus.ADOPTED

    def test_animal_data_status_changed_at_optional(self):
        """status_changed_at フィールドがオプショナルであることを確認"""
        animal = AnimalData(
            species="犬",
            shelter_date=date(2026, 1, 5),
            location="高知県",
            source_url="https://example.com/1",
            category="adoption"
        )

        assert animal.status_changed_at is None

    def test_animal_data_status_changed_at_accepts_datetime(self):
        """status_changed_at フィールドが datetime を受け入れることを確認"""
        now = datetime(2026, 1, 27, 15, 30, 0)
        animal = AnimalData(
            species="犬",
            shelter_date=date(2026, 1, 5),
            location="高知県",
            source_url="https://example.com/1",
            category="adoption",
            status=AnimalStatus.ADOPTED,
            status_changed_at=now
        )

        assert animal.status_changed_at == now

    def test_animal_data_outcome_date_optional(self):
        """outcome_date フィールドがオプショナルであることを確認"""
        animal = AnimalData(
            species="犬",
            shelter_date=date(2026, 1, 5),
            location="高知県",
            source_url="https://example.com/1",
            category="adoption"
        )

        assert animal.outcome_date is None

    def test_animal_data_outcome_date_accepts_date(self):
        """outcome_date フィールドが date を受け入れることを確認"""
        animal = AnimalData(
            species="犬",
            shelter_date=date(2026, 1, 5),
            location="高知県",
            source_url="https://example.com/1",
            category="adoption",
            status=AnimalStatus.ADOPTED,
            outcome_date=date(2026, 1, 20)
        )

        assert animal.outcome_date == date(2026, 1, 20)

    def test_animal_data_local_image_paths_optional(self):
        """local_image_paths フィールドがオプショナルであることを確認"""
        animal = AnimalData(
            species="犬",
            shelter_date=date(2026, 1, 5),
            location="高知県",
            source_url="https://example.com/1",
            category="adoption"
        )

        assert animal.local_image_paths is None

    def test_animal_data_local_image_paths_accepts_list(self):
        """local_image_paths フィールドが文字列リストを受け入れることを確認"""
        paths = ["/images/ab/cd/abcd1234.jpg", "/images/ef/gh/efgh5678.jpg"]
        animal = AnimalData(
            species="犬",
            shelter_date=date(2026, 1, 5),
            location="高知県",
            source_url="https://example.com/1",
            category="adoption",
            local_image_paths=paths
        )

        assert animal.local_image_paths == paths
        assert len(animal.local_image_paths) == 2

    def test_animal_data_backward_compatibility(self):
        """新フィールドが全てオプショナルで後方互換性が保たれていることを確認"""
        # 既存のコードと同じ引数で作成可能
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
            source_url="https://example-kochi.jp/animals/123",
            category="adoption"
        )

        # 既存フィールドは正常に動作
        assert animal.species == "犬"
        assert animal.sex == "男の子"
        assert animal.category == "adoption"

        # 新規フィールドは None
        assert animal.status is None
        assert animal.status_changed_at is None
        assert animal.outcome_date is None
        assert animal.local_image_paths is None

    def test_animal_data_full_extended_fields(self):
        """全ての拡張フィールドを持つ AnimalData を作成"""
        now = datetime(2026, 1, 27, 15, 30, 0)
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
            source_url="https://example-kochi.jp/animals/123",
            category="adoption",
            status=AnimalStatus.ADOPTED,
            status_changed_at=now,
            outcome_date=date(2026, 1, 20),
            local_image_paths=["/images/ab/cd/test.jpg"]
        )

        assert animal.status == AnimalStatus.ADOPTED
        assert animal.status_changed_at == now
        assert animal.outcome_date == date(2026, 1, 20)
        assert animal.local_image_paths == ["/images/ab/cd/test.jpg"]
