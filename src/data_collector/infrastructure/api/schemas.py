"""
API スキーマ定義

FastAPI リクエスト/レスポンスのPydanticスキーマを定義します。
既存のAnimalDataとの変換ロジックをサポートします。
"""

from pydantic import BaseModel, ConfigDict
from typing import List, Generic, TypeVar, Optional
from datetime import date


T = TypeVar('T')


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
