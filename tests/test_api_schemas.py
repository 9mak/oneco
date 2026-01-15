"""
API スキーマのテスト

AnimalPublic, PaginationMeta, PaginatedResponse の Pydantic スキーマが
要件通りに実装されているかを検証します。
"""

import pytest
from datetime import date
from pydantic import ValidationError
from src.data_collector.infrastructure.api.schemas import (
    AnimalPublic,
    PaginationMeta,
    PaginatedResponse,
)
from src.data_collector.infrastructure.database.models import Animal


def test_animal_public_schema_from_dict():
    """AnimalPublicスキーマが辞書から正しく作成されるか"""
    data = {
        "id": 1,
        "species": "犬",
        "sex": "男の子",
        "age_months": 24,
        "color": "茶色",
        "size": "中型",
        "shelter_date": date(2026, 1, 5),
        "location": "高知県動物愛護センター",
        "phone": "088-123-4567",
        "image_urls": ["https://example.com/img1.jpg"],
        "source_url": "https://example.com/animal/1",
    }

    animal = AnimalPublic(**data)

    assert animal.id == 1
    assert animal.species == "犬"
    assert animal.sex == "男の子"
    assert animal.age_months == 24
    assert animal.color == "茶色"
    assert animal.size == "中型"
    assert animal.shelter_date == date(2026, 1, 5)
    assert animal.location == "高知県動物愛護センター"
    assert animal.phone == "088-123-4567"
    assert animal.image_urls == ["https://example.com/img1.jpg"]
    assert animal.source_url == "https://example.com/animal/1"


def test_animal_public_schema_from_orm():
    """AnimalPublicスキーマがSQLAlchemyモデルから変換できるか"""
    orm_animal = Animal(
        id=1,
        species="猫",
        sex="女の子",
        age_months=12,
        color="白",
        size="小型",
        shelter_date=date(2026, 1, 6),
        location="高知県",
        phone="088-999-8888",
        image_urls=["https://example.com/img2.jpg"],
        source_url="https://example.com/animal/2",
    )

    animal = AnimalPublic.model_validate(orm_animal)

    assert animal.id == 1
    assert animal.species == "猫"
    assert animal.sex == "女の子"
    assert animal.age_months == 12
    assert animal.source_url == "https://example.com/animal/2"


def test_animal_public_schema_optional_fields():
    """AnimalPublicスキーマがオプションフィールドを正しく扱うか"""
    data = {
        "id": 1,
        "species": "犬",
        "sex": "男の子",
        "shelter_date": date(2026, 1, 5),
        "location": "高知県",
        "image_urls": [],
        "source_url": "https://example.com/animal/1",
    }

    animal = AnimalPublic(**data)

    assert animal.age_months is None
    assert animal.color is None
    assert animal.size is None
    assert animal.phone is None


def test_animal_public_schema_missing_required_fields():
    """AnimalPublicスキーマが必須フィールド欠損時にエラーを出すか"""
    data = {
        "id": 1,
        "species": "犬",
        # shelter_date が欠損
        "location": "高知県",
        "source_url": "https://example.com/animal/1",
    }

    with pytest.raises(ValidationError) as exc_info:
        AnimalPublic(**data)

    errors = exc_info.value.errors()
    assert any(error["loc"][0] == "shelter_date" for error in errors)


def test_pagination_meta_schema():
    """PaginationMetaスキーマが正しく作成されるか"""
    meta = PaginationMeta(
        total_count=150,
        limit=50,
        offset=0,
        current_page=1,
        total_pages=3,
        has_next=True,
    )

    assert meta.total_count == 150
    assert meta.limit == 50
    assert meta.offset == 0
    assert meta.current_page == 1
    assert meta.total_pages == 3
    assert meta.has_next is True


def test_pagination_meta_calculates_current_page():
    """PaginationMetaがcurrent_pageを正しく計算するか"""
    # offset=0, limit=50 → page 1
    meta = PaginationMeta(
        total_count=150,
        limit=50,
        offset=0,
        current_page=1,
        total_pages=3,
        has_next=True,
    )
    assert meta.current_page == 1

    # offset=50, limit=50 → page 2
    meta = PaginationMeta(
        total_count=150,
        limit=50,
        offset=50,
        current_page=2,
        total_pages=3,
        has_next=True,
    )
    assert meta.current_page == 2


def test_pagination_meta_has_next_logic():
    """PaginationMetaがhas_nextを正しく計算するか"""
    # offset=0, limit=50, total=150 → has_next=True
    meta = PaginationMeta(
        total_count=150,
        limit=50,
        offset=0,
        current_page=1,
        total_pages=3,
        has_next=True,
    )
    assert meta.has_next is True

    # offset=100, limit=50, total=150 → has_next=False (最終ページ)
    meta = PaginationMeta(
        total_count=150,
        limit=50,
        offset=100,
        current_page=3,
        total_pages=3,
        has_next=False,
    )
    assert meta.has_next is False


def test_paginated_response_schema():
    """PaginatedResponseスキーマが正しく作成されるか"""
    animals = [
        AnimalPublic(
            id=1,
            species="犬",
            sex="男の子",
            age_months=24,
            color="茶色",
            size="中型",
            shelter_date=date(2026, 1, 5),
            location="高知県",
            phone="088-123-4567",
            image_urls=["https://example.com/img1.jpg"],
            source_url="https://example.com/animal/1",
        )
    ]

    meta = PaginationMeta(
        total_count=150,
        limit=50,
        offset=0,
        current_page=1,
        total_pages=3,
        has_next=True,
    )

    response = PaginatedResponse[AnimalPublic](items=animals, meta=meta)

    assert len(response.items) == 1
    assert response.items[0].id == 1
    assert response.meta.total_count == 150


def test_paginated_response_empty_items():
    """PaginatedResponseスキーマが空のitemsを正しく扱うか"""
    meta = PaginationMeta(
        total_count=0,
        limit=50,
        offset=0,
        current_page=1,
        total_pages=0,
        has_next=False,
    )

    response = PaginatedResponse[AnimalPublic](items=[], meta=meta)

    assert len(response.items) == 0
    assert response.meta.total_count == 0


def test_animal_public_serialization_to_json():
    """AnimalPublicスキーマがJSON形式に正しくシリアライズされるか"""
    animal = AnimalPublic(
        id=1,
        species="犬",
        sex="男の子",
        age_months=24,
        color="茶色",
        size="中型",
        shelter_date=date(2026, 1, 5),
        location="高知県",
        phone="088-123-4567",
        image_urls=["https://example.com/img1.jpg"],
        source_url="https://example.com/animal/1",
    )

    json_data = animal.model_dump()

    assert json_data["id"] == 1
    assert json_data["species"] == "犬"
    assert json_data["shelter_date"] == date(2026, 1, 5)
    assert isinstance(json_data["image_urls"], list)


def test_animal_public_date_serialization():
    """AnimalPublicスキーマがISO 8601形式で日付をシリアライズするか"""
    animal = AnimalPublic(
        id=1,
        species="犬",
        sex="男の子",
        shelter_date=date(2026, 1, 5),
        location="高知県",
        image_urls=[],
        source_url="https://example.com/animal/1",
    )

    # model_dump(mode="json") で ISO 8601 形式になることを確認
    json_data = animal.model_dump(mode="json")

    # Pydantic v2 では date は文字列として出力される
    assert json_data["shelter_date"] == "2026-01-05"
