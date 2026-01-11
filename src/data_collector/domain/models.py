"""
データモデル定義

このモジュールは data-collector のドメイン層のデータモデルを定義します:
- RawAnimalData: 自治体サイトから抽出した正規化前の生データ
- AnimalData: 統一スキーマに正規化された保護動物データ
"""

from typing import List, Optional
from datetime import date
from pydantic import BaseModel, Field, field_validator, HttpUrl


class RawAnimalData(BaseModel):
    """
    自治体サイトから抽出した正規化前の生データ

    全フィールドが文字列型で、後続の正規化処理 (DataNormalizer) に渡すための
    型安全性を確保します。
    """

    species: str = Field(..., description="動物種別 (正規化前)")
    sex: str = Field(..., description="性別 (正規化前)")
    age: str = Field(..., description="年齢 (正規化前)")
    color: str = Field(..., description="毛色")
    size: str = Field(..., description="体格")
    shelter_date: str = Field(..., description="収容日 (正規化前)")
    location: str = Field(..., description="収容場所")
    phone: str = Field(..., description="電話番号 (正規化前)")
    image_urls: List[str] = Field(..., description="画像URL一覧")
    source_url: str = Field(..., description="元ページURL")


class AnimalData(BaseModel):
    """
    統一された保護動物データモデル

    Pydantic による型安全性とバリデーションを提供し、animal-repository への
    出力スキーマとして機能します。
    """

    # 必須フィールド
    species: str = Field(..., description="動物種別 ('犬', '猫', 'その他')")
    shelter_date: date = Field(..., description="収容日 (ISO 8601)")
    source_url: HttpUrl = Field(..., description="元ページURL")

    # 準必須フィールド (不明値許容)
    sex: str = Field(default="不明", description="性別 ('男の子', '女の子', '不明')")
    age_months: Optional[int] = Field(default=None, description="推定年齢 (月単位)")
    color: Optional[str] = Field(default=None, description="毛色")
    size: Optional[str] = Field(default=None, description="体格")
    location: Optional[str] = Field(default=None, description="収容場所")
    phone: Optional[str] = Field(default=None, description="電話番号 (ハイフン含む)")
    image_urls: List[HttpUrl] = Field(default_factory=list, description="画像URL一覧")

    @field_validator("species")
    @classmethod
    def validate_species(cls, v: str) -> str:
        """
        動物種別の3値制約バリデーション

        Args:
            v: 動物種別の値

        Returns:
            str: バリデーション済みの動物種別

        Raises:
            ValueError: '犬', '猫', 'その他' 以外の値が渡された場合
        """
        if v not in ["犬", "猫", "その他"]:
            raise ValueError(
                f"無効な動物種別: {v}。'犬', '猫', 'その他' のいずれかである必要があります"
            )
        return v

    @field_validator("sex")
    @classmethod
    def validate_sex(cls, v: str) -> str:
        """
        性別の3値制約バリデーション

        Args:
            v: 性別の値

        Returns:
            str: バリデーション済みの性別

        Raises:
            ValueError: '男の子', '女の子', '不明' 以外の値が渡された場合
        """
        if v not in ["男の子", "女の子", "不明"]:
            raise ValueError(
                f"無効な性別: {v}。'男の子', '女の子', '不明' のいずれかである必要があります"
            )
        return v

    @field_validator("age_months")
    @classmethod
    def validate_age_months(cls, v: Optional[int]) -> Optional[int]:
        """
        年齢の負値チェックバリデーション

        Args:
            v: 年齢 (月単位)

        Returns:
            Optional[int]: バリデーション済みの年齢

        Raises:
            ValueError: 負の値が渡された場合
        """
        if v is not None and v < 0:
            raise ValueError(f"年齢は負の値にできません: {v}")
        return v

    class Config:
        """Pydantic 設定"""
        json_schema_extra = {
            "example": {
                "species": "犬",
                "sex": "男の子",
                "age_months": 24,
                "color": "茶色",
                "size": "中型",
                "shelter_date": "2026-01-05",
                "location": "高知県動物愛護センター",
                "phone": "088-123-4567",
                "image_urls": ["https://example.com/image1.jpg"],
                "source_url": "https://example-kochi.jp/animals/123"
            }
        }
