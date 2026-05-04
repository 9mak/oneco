"""
API スキーマ定義

FastAPI リクエスト/レスポンスのPydanticスキーマを定義します。
既存のAnimalDataとの変換ロジックをサポートします。
"""

from datetime import date, datetime
from enum import StrEnum
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class AnimalStatusEnum(StrEnum):
    """動物ステータス（API用）"""

    SHELTERED = "sheltered"
    ADOPTED = "adopted"
    RETURNED = "returned"
    DECEASED = "deceased"


class AnimalPublic(BaseModel):
    """
    公開用動物データスキーマ

    SQLAlchemy Animal モデルまたは辞書から作成できます。
    ISO 8601形式の日付シリアライゼーションをサポートします。
    """

    id: int
    species: str
    sex: str
    age_months: int | None = None
    color: str | None = None
    size: str | None = None
    shelter_date: date
    location: str
    prefecture: str | None = None
    phone: str | None = None
    image_urls: list[str]
    source_url: str
    category: str
    # 拡張フィールド（オプション）
    status: str | None = None
    status_changed_at: datetime | None = None
    outcome_date: date | None = None
    local_image_paths: list[str] | None = None

    model_config = ConfigDict(from_attributes=True)


class PaginationMeta(BaseModel):
    """
    ページネーションメタデータ

    ページネーション情報を含むレスポンスメタデータを提供します。
    """

    total_count: int
    limit: int
    offset: int
    current_page: int
    total_pages: int
    has_next: bool


class PaginatedResponse(BaseModel, Generic[T]):
    """
    ページネーション付きレスポンス

    ジェネリック型を使用し、任意のアイテム型をサポートします。
    """

    items: list[T]
    meta: PaginationMeta


class StatusUpdateRequest(BaseModel):
    """
    ステータス更新リクエスト
    """

    status: AnimalStatusEnum
    outcome_date: date | None = None


class StatusUpdateResponse(BaseModel):
    """
    ステータス更新レスポンス
    """

    success: bool
    animal: AnimalPublic


class ArchivedAnimalPublic(BaseModel):
    """
    公開用アーカイブ動物データスキーマ

    アーカイブされた動物データのAPIレスポンススキーマ。
    """

    id: int
    original_id: int
    species: str
    sex: str
    age_months: int | None = None
    color: str | None = None
    size: str | None = None
    shelter_date: date
    location: str
    prefecture: str | None = None
    phone: str | None = None
    image_urls: list[str]
    source_url: str
    category: str
    status: str
    status_changed_at: datetime | None = None
    outcome_date: date | None = None
    local_image_paths: list[str] | None = None
    archived_at: datetime

    model_config = ConfigDict(from_attributes=True)
