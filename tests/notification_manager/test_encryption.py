"""
notification-manager 暗号化ユーティリティのテスト

Task 2.2: Fernet暗号化/復号ユーティリティのテスト
"""

import os
from unittest.mock import patch

import pytest

from src.notification_manager.domain.encryption import (
    EncryptionError,
    EncryptionService,
    generate_encryption_key,
)


class TestEncryptionService:
    """暗号化サービスのテスト"""

    @pytest.fixture
    def encryption_key(self):
        """テスト用の暗号化キーを生成"""
        return generate_encryption_key()

    @pytest.fixture
    def encryption_service(self, encryption_key):
        """テスト用の暗号化サービス"""
        return EncryptionService(encryption_key)

    def test_encrypt_and_decrypt(self, encryption_service):
        """暗号化して復号できる"""
        original = "U1234567890abcdef"
        encrypted = encryption_service.encrypt(original)
        decrypted = encryption_service.decrypt(encrypted)
        assert decrypted == original

    def test_encrypted_differs_from_original(self, encryption_service):
        """暗号化された値は元の値と異なる"""
        original = "U1234567890abcdef"
        encrypted = encryption_service.encrypt(original)
        assert encrypted != original

    def test_encrypted_is_base64_safe(self, encryption_service):
        """暗号化された値はBase64エンコードされている"""
        original = "U1234567890abcdef"
        encrypted = encryption_service.encrypt(original)
        # Fernet はBase64エンコードを使用
        assert isinstance(encrypted, str)
        # 暗号化結果はURLセーフなBase64
        assert all(c.isalnum() or c in "-_=" for c in encrypted)

    def test_same_plaintext_produces_different_ciphertexts(self, encryption_service):
        """同じ平文でも暗号化結果は毎回異なる（IV/nonceの使用）"""
        original = "U1234567890abcdef"
        encrypted1 = encryption_service.encrypt(original)
        encrypted2 = encryption_service.encrypt(original)
        assert encrypted1 != encrypted2

    def test_decrypt_with_wrong_key_fails(self, encryption_key):
        """異なるキーでは復号できない"""
        service1 = EncryptionService(encryption_key)
        different_key = generate_encryption_key()
        service2 = EncryptionService(different_key)

        original = "U1234567890abcdef"
        encrypted = service1.encrypt(original)

        with pytest.raises(EncryptionError):
            service2.decrypt(encrypted)

    def test_decrypt_invalid_ciphertext_fails(self, encryption_service):
        """不正な暗号文では復号できない"""
        with pytest.raises(EncryptionError):
            encryption_service.decrypt("invalid_ciphertext")

    def test_encrypt_empty_string(self, encryption_service):
        """空文字列も暗号化できる"""
        encrypted = encryption_service.encrypt("")
        decrypted = encryption_service.decrypt(encrypted)
        assert decrypted == ""

    def test_encrypt_unicode(self, encryption_service):
        """日本語文字列も暗号化できる"""
        original = "日本語テスト文字列"
        encrypted = encryption_service.encrypt(original)
        decrypted = encryption_service.decrypt(encrypted)
        assert decrypted == original


class TestEncryptionServiceFromEnv:
    """環境変数からの暗号化サービス初期化のテスト"""

    def test_from_env_variable(self):
        """環境変数から暗号化サービスを初期化できる"""
        test_key = generate_encryption_key()
        with patch.dict(os.environ, {"ENCRYPTION_KEY": test_key}):
            service = EncryptionService.from_env()
            original = "test_value"
            encrypted = service.encrypt(original)
            decrypted = service.decrypt(encrypted)
            assert decrypted == original

    def test_from_env_variable_missing(self):
        """環境変数が未設定の場合はエラー"""
        with patch.dict(os.environ, {}, clear=True):
            # ENCRYPTION_KEY が存在しないことを確認
            if "ENCRYPTION_KEY" in os.environ:
                del os.environ["ENCRYPTION_KEY"]
            with pytest.raises(EncryptionError):
                EncryptionService.from_env()

    def test_from_env_variable_invalid(self):
        """環境変数の値が不正な場合はエラー"""
        with patch.dict(os.environ, {"ENCRYPTION_KEY": "invalid_key"}):
            with pytest.raises(EncryptionError):
                EncryptionService.from_env()


class TestGenerateEncryptionKey:
    """暗号化キー生成のテスト"""

    def test_generate_key_is_valid(self):
        """生成されたキーは有効なFernetキー"""
        key = generate_encryption_key()
        # 有効なキーで暗号化サービスを初期化できる
        service = EncryptionService(key)
        encrypted = service.encrypt("test")
        decrypted = service.decrypt(encrypted)
        assert decrypted == "test"

    def test_generate_key_is_unique(self):
        """生成されたキーは毎回異なる"""
        key1 = generate_encryption_key()
        key2 = generate_encryption_key()
        assert key1 != key2
