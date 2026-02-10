"""
notification-manager ドメインモデル定義

このモジュールはnotification-managerのドメイン層のデータモデルを定義します:
- UserEntity: LINEユーザーエンティティ
- NotificationPreferenceInput: 通知条件入力
- NotificationPreferenceEntity: 通知条件エンティティ
- MatchResult: マッチング結果
- NotificationMessage: 通知メッセージ
- SendResult: 送信結果

Requirements: 1.1, 1.3, 3.1-3.5, 4.1, 4.2
"""

from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class UserEntity(BaseModel):
    """
    LINEユーザーエンティティ

    Requirement 1.1: ユーザー識別子を生成し、初期登録状態を作成する
    """

    id: int = Field(..., description="ユーザーID")
    line_user_id_encrypted: str = Field(..., description="暗号化されたLINEユーザーID")
    is_active: bool = Field(default=True, description="アクティブ状態")

    model_config = ConfigDict(from_attributes=True)


class NotificationPreferenceInput(BaseModel):
    """
    通知条件入力

    Requirement 1.3: 条件項目（種別、都道府県等）の設定
    すべてのフィールドがオプショナルで、NULLは「すべて許可」を意味する
    """

    species: Optional[str] = Field(
        default=None, description="動物種別 ('犬', '猫', None=両方)"
    )
    prefectures: Optional[List[str]] = Field(
        default=None, description="都道府県リスト（複数選択可）"
    )
    age_min_months: Optional[int] = Field(
        default=None, ge=0, description="年齢下限（月単位）"
    )
    age_max_months: Optional[int] = Field(
        default=None, ge=0, description="年齢上限（月単位）"
    )
    size: Optional[str] = Field(
        default=None, description="サイズ ('小型', '中型', '大型', None=すべて)"
    )
    sex: Optional[str] = Field(
        default=None, description="性別 ('男の子', '女の子', None=不問)"
    )

    @field_validator("species")
    @classmethod
    def validate_species(cls, v: Optional[str]) -> Optional[str]:
        """動物種別のバリデーション"""
        if v is not None and v not in ["犬", "猫"]:
            raise ValueError(f"無効な動物種別: {v}。'犬', '猫' のいずれかである必要があります")
        return v

    @field_validator("sex")
    @classmethod
    def validate_sex(cls, v: Optional[str]) -> Optional[str]:
        """性別のバリデーション"""
        if v is not None and v not in ["男の子", "女の子"]:
            raise ValueError(
                f"無効な性別: {v}。'男の子', '女の子' のいずれかである必要があります"
            )
        return v

    @field_validator("size")
    @classmethod
    def validate_size(cls, v: Optional[str]) -> Optional[str]:
        """サイズのバリデーション"""
        if v is not None and v not in ["小型", "中型", "大型"]:
            raise ValueError(
                f"無効なサイズ: {v}。'小型', '中型', '大型' のいずれかである必要があります"
            )
        return v


class NotificationPreferenceEntity(BaseModel):
    """
    通知条件エンティティ

    Requirement 1.3, 1.4: 通知条件の永続化
    """

    id: int = Field(..., description="通知条件ID")
    user_id: int = Field(..., description="ユーザーID")
    species: Optional[str] = Field(default=None, description="動物種別")
    prefectures: Optional[List[str]] = Field(default=None, description="都道府県リスト")
    age_min_months: Optional[int] = Field(default=None, description="年齢下限（月単位）")
    age_max_months: Optional[int] = Field(default=None, description="年齢上限（月単位）")
    size: Optional[str] = Field(default=None, description="サイズ")
    sex: Optional[str] = Field(default=None, description="性別")
    notifications_enabled: bool = Field(default=True, description="通知有効フラグ")

    model_config = ConfigDict(from_attributes=True)


class MatchResult(BaseModel):
    """
    マッチング結果

    Requirement 3.3: マッチング結果のデータ構造
    """

    user_id: int = Field(..., description="ユーザーID")
    line_user_id_encrypted: str = Field(..., description="暗号化されたLINEユーザーID")
    preference_id: int = Field(..., description="通知条件ID")
    match_score: float = Field(
        ..., ge=0.0, le=1.0, description="マッチスコア (1.0 = 完全マッチ)"
    )


class NotificationMessage(BaseModel):
    """
    通知メッセージ

    Requirement 4.2: 通知メッセージに含める情報
    """

    species: str = Field(..., description="動物種別")
    sex: str = Field(..., description="性別")
    age_months: Optional[int] = Field(default=None, description="推定年齢（月単位）")
    size: Optional[str] = Field(default=None, description="サイズ")
    location: str = Field(..., description="収容地域（都道府県・市区町村）")
    source_url: str = Field(..., description="元ページURL")
    category: str = Field(..., description="カテゴリ ('adoption', 'lost')")

    def format_message(self) -> str:
        """
        通知メッセージをフォーマット

        Returns:
            str: 人間が読みやすいフォーマットのメッセージ
        """
        category_label = "譲渡対象" if self.category == "adoption" else "迷子"

        lines = [
            f"🐾 新着{category_label}動物のお知らせ",
            "",
            f"種別: {self.species}",
            f"性別: {self.sex}",
        ]

        if self.age_months is not None:
            if self.age_months < 12:
                age_str = f"{self.age_months}ヶ月"
            else:
                years = self.age_months // 12
                months = self.age_months % 12
                if months > 0:
                    age_str = f"約{years}歳{months}ヶ月"
                else:
                    age_str = f"約{years}歳"
            lines.append(f"年齢: {age_str}")

        if self.size:
            lines.append(f"サイズ: {self.size}")

        lines.extend([
            f"収容場所: {self.location}",
            "",
            f"詳細はこちら: {self.source_url}",
        ])

        return "\n".join(lines)


class SendResult(BaseModel):
    """
    送信結果

    Requirement 4.3, 4.4: 送信結果の記録
    """

    success: bool = Field(..., description="送信成功フラグ")
    error_code: Optional[str] = Field(default=None, description="エラーコード")
    retry_after: Optional[int] = Field(
        default=None, description="リトライ待機時間（秒）- レート制限時"
    )


class NotificationResult(BaseModel):
    """
    通知処理結果

    Requirement 8.1-8.5: 処理結果のサマリー
    """

    total_animals: int = Field(..., description="処理した動物数")
    total_matches: int = Field(..., description="マッチしたユーザー数")
    sent_count: int = Field(..., description="送信成功数")
    skipped_count: int = Field(..., description="スキップ数（重複による）")
    failed_count: int = Field(..., description="送信失敗数")
    processing_time_seconds: float = Field(..., description="処理時間（秒）")
