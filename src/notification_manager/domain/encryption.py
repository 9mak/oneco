"""
notification-manager 暗号化ユーティリティ

このモジュールはLINEユーザーIDの暗号化/復号機能を提供します。
Fernet（AES-128 + HMAC）による対称鍵暗号化を使用。

Requirement 7.1: LINE ユーザーIDを暗号化してデータベースに保存する
"""

import os
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken


class EncryptionError(Exception):
    """暗号化/復号に関するエラー"""

    pass


class EncryptionService:
    """
    Fernet暗号化サービス

    AES-128-CBC + HMAC-SHA256 による暗号化/復号を提供。
    暗号化結果にはタイムスタンプが含まれ、改ざん検知が可能。
    """

    def __init__(self, key: str):
        """
        EncryptionService を初期化

        Args:
            key: Fernet暗号化キー（Base64エンコード済み）

        Raises:
            EncryptionError: キーが無効な場合
        """
        try:
            self._fernet = Fernet(key.encode() if isinstance(key, str) else key)
        except Exception as e:
            raise EncryptionError(f"無効な暗号化キー: {e}") from e

    def encrypt(self, plaintext: str) -> str:
        """
        平文を暗号化

        Args:
            plaintext: 暗号化する平文

        Returns:
            str: 暗号化された文字列（Base64エンコード）

        Raises:
            EncryptionError: 暗号化に失敗した場合
        """
        try:
            encrypted_bytes = self._fernet.encrypt(plaintext.encode("utf-8"))
            return encrypted_bytes.decode("utf-8")
        except Exception as e:
            raise EncryptionError(f"暗号化に失敗: {e}") from e

    def decrypt(self, ciphertext: str) -> str:
        """
        暗号文を復号

        Args:
            ciphertext: 復号する暗号文（Base64エンコード）

        Returns:
            str: 復号された平文

        Raises:
            EncryptionError: 復号に失敗した場合（キー不一致、改ざん検知など）
        """
        try:
            decrypted_bytes = self._fernet.decrypt(ciphertext.encode("utf-8"))
            return decrypted_bytes.decode("utf-8")
        except InvalidToken as e:
            raise EncryptionError(
                "復号に失敗: 無効なトークン（キー不一致または改ざん検知）"
            ) from e
        except Exception as e:
            raise EncryptionError(f"復号に失敗: {e}") from e

    @classmethod
    def from_env(cls, env_var: str = "ENCRYPTION_KEY") -> "EncryptionService":
        """
        環境変数から暗号化サービスを初期化

        Args:
            env_var: 暗号化キーを格納する環境変数名

        Returns:
            EncryptionService: 初期化された暗号化サービス

        Raises:
            EncryptionError: 環境変数が未設定または無効な場合
        """
        key = os.environ.get(env_var)
        if not key:
            raise EncryptionError(
                f"環境変数 {env_var} が設定されていません。"
                "generate_encryption_key() で生成したキーを設定してください。"
            )
        return cls(key)


def generate_encryption_key() -> str:
    """
    新しいFernet暗号化キーを生成

    Returns:
        str: Base64エンコードされたFernet暗号化キー

    Note:
        生成されたキーは安全に保管し、環境変数として設定してください。
        本番環境では AWS Secrets Manager などのシークレット管理サービスを推奨。
    """
    return Fernet.generate_key().decode("utf-8")
