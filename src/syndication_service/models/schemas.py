"""
Syndication Service API Schemas

Pydantic モデルでクエリパラメータとレスポンスを定義。
"""

from datetime import date
from typing import Optional
from pydantic import BaseModel, Field


class FeedQueryParams(BaseModel):
    """通常フィードのクエリパラメータ"""

    species: Optional[str] = Field(None, description="種別フィルタ ('犬', '猫', 'その他')")
    category: Optional[str] = Field(None, description="カテゴリフィルタ ('adoption', 'lost')")
    location: Optional[str] = Field(None, description="地域フィルタ（部分一致）")
    status: Optional[str] = Field(None, description="ステータスフィルタ ('sheltered', 'adopted', 'returned', 'deceased')")
    sex: Optional[str] = Field(None, description="性別フィルタ ('男の子', '女の子', '不明')")
    limit: int = Field(50, ge=1, le=100, description="アイテム数（最大100、デフォルト50）")

    def to_dict(self) -> dict:
        """辞書形式に変換（None 値を除外）"""
        return {k: v for k, v in self.model_dump().items() if v is not None}


class ArchiveFeedQueryParams(BaseModel):
    """アーカイブフィードのクエリパラメータ"""

    species: Optional[str] = Field(None, description="種別フィルタ")
    location: Optional[str] = Field(None, description="地域フィルタ")
    archived_from: Optional[date] = Field(None, description="アーカイブ開始日")
    archived_to: Optional[date] = Field(None, description="アーカイブ終了日")
    limit: int = Field(50, ge=1, le=100, description="アイテム数（最大100、デフォルト50）")

    def to_dict(self) -> dict:
        """辞書形式に変換（None 値を除外）"""
        result = {}
        for k, v in self.model_dump().items():
            if v is not None:
                # date 型は文字列に変換
                if isinstance(v, date):
                    result[k] = v.isoformat()
                else:
                    result[k] = v
        return result
