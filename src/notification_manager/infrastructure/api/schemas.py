"""
notification-manager APIスキーマ定義

このモジュールはnotification-managerのAPI層のスキーマを定義します:
- AnimalDataSchema: 動物データスキーマ（Webhook受信用）
- NewAnimalWebhookRequest: 新着動物Webhookリクエスト
- HealthResponse: ヘルスチェックレスポンス

Requirements: 2.1, 2.3, 6.6
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator


class AnimalDataSchema(BaseModel):
    """
    動物データスキーマ（Webhook受信用）

    data-collectorからの新着動物データを受け取る。
    AnimalDataモデルと互換性を持つ。

    Requirement 2.3: 新着動物データのバリデーション
    """

    species: str = Field(..., description="動物種別 ('犬', '猫', 'その他')")
    shelter_date: date = Field(..., description="収容日 (ISO 8601)")
    location: str = Field(..., description="収容場所（最低限都道府県名）")
    source_url: HttpUrl = Field(..., description="元ページURL")
    category: str = Field(..., description="カテゴリ ('adoption', 'lost')")
    sex: str = Field(default="不明", description="性別 ('男の子', '女の子', '不明')")
    age_months: int | None = Field(default=None, description="推定年齢 (月単位)")
    color: str | None = Field(default=None, description="毛色")
    size: str | None = Field(default=None, description="体格")
    phone: str | None = Field(default=None, description="電話番号")
    image_urls: list[HttpUrl] = Field(default_factory=list, description="画像URL一覧")

    @field_validator("species")
    @classmethod
    def validate_species(cls, v: str) -> str:
        """動物種別のバリデーション"""
        if v not in ["犬", "猫", "その他"]:
            raise ValueError(
                f"無効な動物種別: {v}。'犬', '猫', 'その他' のいずれかである必要があります"
            )
        return v

    @field_validator("sex")
    @classmethod
    def validate_sex(cls, v: str) -> str:
        """性別のバリデーション"""
        if v not in ["男の子", "女の子", "不明"]:
            raise ValueError(
                f"無効な性別: {v}。'男の子', '女の子', '不明' のいずれかである必要があります"
            )
        return v

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        """カテゴリのバリデーション"""
        if v not in ["adoption", "lost"]:
            raise ValueError(
                f"無効なカテゴリ: {v}。'adoption', 'lost' のいずれかである必要があります"
            )
        return v


class NewAnimalWebhookRequest(BaseModel):
    """
    data-collectorからの新着動物通知リクエスト

    Requirement 2.1, 2.3: 新着動物データの受信と検証
    """

    animals: list[AnimalDataSchema] = Field(..., description="新着動物データのリスト")
    source: str = Field(..., description="送信元 ('data-collector')")
    timestamp: datetime = Field(..., description="リクエストタイムスタンプ")


class WebhookResponse(BaseModel):
    """
    Webhookレスポンス

    Requirement 2.5: HTTP 202 Acceptedの即時返却
    """

    status: str = Field(default="accepted", description="処理状態")
    message: str = Field(default="Processing started", description="メッセージ")


class HealthResponse(BaseModel):
    """
    ヘルスチェックレスポンス

    Requirement 6.6: サービス状態の確認
    """

    status: Literal["healthy", "degraded", "unhealthy"] = Field(..., description="サービス状態")
    database: bool = Field(..., description="データベース接続状態")
    line_api: bool = Field(..., description="LINE API接続状態")
    timestamp: datetime = Field(default_factory=datetime.now, description="チェック時刻")


class LineWebhookEvent(BaseModel):
    """LINE Webhookイベント"""

    type: str = Field(..., description="イベントタイプ")
    source: dict = Field(..., description="イベントソース")
    timestamp: int = Field(..., description="タイムスタンプ")
    replyToken: str | None = Field(default=None, description="リプライトークン")
    message: dict | None = Field(default=None, description="メッセージ（message eventの場合）")


class LineWebhookRequest(BaseModel):
    """LINE Webhookリクエスト"""

    events: list[LineWebhookEvent] = Field(..., description="イベントリスト")
