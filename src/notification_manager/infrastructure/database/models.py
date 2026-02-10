"""
notification-manager データベースモデル定義

このモジュールはnotification-managerのデータベーススキーマを定義します。
- User: LINEユーザー情報（暗号化されたuser_id）
- NotificationPreference: ユーザー通知条件
- NotificationHistory: 通知送信履歴

Requirements: 1.1, 1.3, 1.4, 5.1, 5.2, 5.3, 7.1
"""

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    JSON,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, relationship


class NotificationBase(DeclarativeBase):
    """notification-manager 用の SQLAlchemy 宣言的ベースクラス"""

    pass


class User(NotificationBase):
    """
    LINEユーザーテーブル

    保護動物通知を受け取るLINEユーザーの情報を管理します。
    LINE user_id はプライバシー保護のため暗号化して保存します。

    Requirements: 1.1, 7.1
    """

    __tablename__ = "notification_users"

    # Primary Key
    id: int = Column(Integer, primary_key=True, autoincrement=True)

    # 暗号化されたLINEユーザーID（Fernet暗号化、255文字まで）
    line_user_id_encrypted: str = Column(
        String(255), nullable=False, unique=True, index=True
    )

    # アクティブフラグ（ブロック/削除時にFalseに設定）
    is_active: bool = Column(Boolean, nullable=False, default=True)

    # タイムスタンプ
    created_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # リレーション
    preference = relationship(
        "NotificationPreference",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    notification_history = relationship(
        "NotificationHistory",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    # アクティブユーザー検索用の部分インデックス
    __table_args__ = (
        Index(
            "idx_notification_users_active",
            "is_active",
            postgresql_where=(is_active == True),
        ),
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, is_active={self.is_active})>"


class NotificationPreference(NotificationBase):
    """
    通知条件テーブル

    ユーザーが設定した通知条件を管理します。
    各条件項目がNULLの場合は「すべて許可」を意味します。

    Requirements: 1.3, 1.4
    """

    __tablename__ = "notification_preferences"

    # Primary Key
    id: int = Column(Integer, primary_key=True, autoincrement=True)

    # 外部キー（ユーザー）
    user_id: int = Column(
        Integer,
        ForeignKey("notification_users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # 1ユーザーにつき1つの条件
    )

    # 条件項目（NULLは「すべて許可」）
    species: Optional[str] = Column(String(20), nullable=True)  # '犬', '猫', NULL=両方
    prefectures: Optional[List[str]] = Column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=True,
    )  # ["高知県", "愛媛県"]
    age_min_months: Optional[int] = Column(Integer, nullable=True)
    age_max_months: Optional[int] = Column(Integer, nullable=True)
    size: Optional[str] = Column(String(20), nullable=True)  # '小型', '中型', '大型'
    sex: Optional[str] = Column(String(20), nullable=True)  # '男の子', '女の子'

    # 通知有効フラグ
    notifications_enabled: bool = Column(Boolean, nullable=False, default=True)

    # タイムスタンプ
    created_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # リレーション
    user = relationship("User", back_populates="preference")

    # アクティブな通知条件検索用の部分インデックス
    __table_args__ = (
        Index(
            "idx_notification_preferences_active",
            "notifications_enabled",
            postgresql_where=(notifications_enabled == True),
        ),
    )

    def __repr__(self) -> str:
        return f"<NotificationPreference(id={self.id}, user_id={self.user_id}, species={self.species})>"


class NotificationHistory(NotificationBase):
    """
    通知履歴テーブル

    通知送信履歴を管理し、重複通知を防止します。
    (user_id, animal_source_url) の組み合わせにユニーク制約を設定。

    Requirements: 5.1, 5.2, 5.3
    """

    __tablename__ = "notification_history"

    # Primary Key
    id: int = Column(Integer, primary_key=True, autoincrement=True)

    # 外部キー（ユーザー）
    user_id: int = Column(
        Integer,
        ForeignKey("notification_users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # 動物ソースURL（重複通知防止のキー）
    animal_source_url: str = Column(Text, nullable=False)

    # 送信ステータス: 'sent', 'failed', 'skipped'
    status: str = Column(String(20), nullable=False)

    # 通知日時
    notified_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # リレーション
    user = relationship("User", back_populates="notification_history")

    # インデックス
    __table_args__ = (
        # 重複通知防止のユニーク制約
        Index(
            "idx_notification_history_user_url",
            "user_id",
            "animal_source_url",
            unique=True,
        ),
        # 履歴検索用の日付インデックス
        Index("idx_notification_history_notified_at", "notified_at"),
    )

    def __repr__(self) -> str:
        return f"<NotificationHistory(id={self.id}, user_id={self.user_id}, status={self.status})>"
