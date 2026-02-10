"""
API スキーマ定義

FastAPI リクエスト/レスポンスのPydanticスキーマを定義します。
既存のAnimalDataとの変換ロジックをサポートします。
"""

from pydantic import BaseModel, ConfigDict, field_validator
from typing import List, Generic, TypeVar, Optional
from datetime import date, datetime
from enum import Enum


T = TypeVar('T')


class AnimalStatusEnum(str, Enum):
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
    age_months: Optional[int] = None
    color: Optional[str] = None
    size: Optional[str] = None
    shelter_date: date
    location: str
    phone: Optional[str] = None
    image_urls: List[str]
    source_url: str
    category: str
    # 拡張フィールド（オプション）
    status: Optional[str] = None
    status_changed_at: Optional[datetime] = None
    outcome_date: Optional[date] = None
    local_image_paths: Optional[List[str]] = None

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

    items: List[T]
    meta: PaginationMeta


class StatusUpdateRequest(BaseModel):
    """
    ステータス更新リクエスト
    """

    status: AnimalStatusEnum
    outcome_date: Optional[date] = None


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
    age_months: Optional[int] = None
    color: Optional[str] = None
    size: Optional[str] = None
    shelter_date: date
    location: str
    phone: Optional[str] = None
    image_urls: List[str]
    source_url: str
    category: str
    status: str
    status_changed_at: Optional[datetime] = None
    outcome_date: Optional[date] = None
    local_image_paths: Optional[List[str]] = None
    archived_at: datetime

    model_config = ConfigDict(from_attributes=True)
