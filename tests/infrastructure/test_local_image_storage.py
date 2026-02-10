"""LocalImageStorage のユニットテスト"""

import pytest
from pathlib import Path

from src.data_collector.infrastructure.image_storage import LocalImageStorage


class TestLocalImageStorage:
    """LocalImageStorage のテストケース"""

    @pytest.fixture
    def storage(self, tmp_path: Path) -> LocalImageStorage:
        """LocalImageStorage インスタンスを作成（一時ディレクトリ使用）"""
        return LocalImageStorage(base_path=tmp_path / "images")

    @pytest.fixture
    def sample_image_content(self) -> bytes:
        """サンプル画像データを作成（最小限のJPEGヘッダー）"""
        # JPEG マジックバイト + 最小限のデータ
        return b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x00" * 100

    @pytest.fixture
    def sample_hash(self) -> str:
        """サンプルSHA-256ハッシュを作成"""
        return "a1b2c3d4e5f6789012345678901234567890123456789012345678901234abcd"

    # === save() のテスト ===

    def test_save_creates_file(
        self, storage: LocalImageStorage, sample_image_content: bytes, sample_hash: str
    ):
        """save() がファイルを作成することを確認"""
        local_path = storage.save(sample_hash, sample_image_content, "jpg")

        full_path = storage.base_path / local_path
        assert full_path.exists()
        assert full_path.is_file()

    def test_save_creates_hash_based_directory_structure(
        self, storage: LocalImageStorage, sample_image_content: bytes, sample_hash: str
    ):
        """save() がハッシュベースのディレクトリ構造を作成することを確認

        ディレクトリ構造: {base_path}/{hash[:2]}/{hash[2:4]}/{hash}.{ext}
        """
        local_path = storage.save(sample_hash, sample_image_content, "jpg")

        path = Path(local_path)
        # ディレクトリ構造の検証
        assert path.parent.name == sample_hash[2:4]  # 2番目のディレクトリ
        assert path.parent.parent.name == sample_hash[:2]  # 1番目のディレクトリ
        # ファイル名の検証
        assert path.name == f"{sample_hash}.jpg"

    def test_save_writes_correct_content(
        self, storage: LocalImageStorage, sample_image_content: bytes, sample_hash: str
    ):
        """save() が正しいコンテンツを書き込むことを確認"""
        local_path = storage.save(sample_hash, sample_image_content, "jpg")

        full_path = storage.base_path / local_path
        with open(full_path, "rb") as f:
            saved_content = f.read()

        assert saved_content == sample_image_content

    def test_save_returns_relative_path(
        self, storage: LocalImageStorage, sample_image_content: bytes, sample_hash: str
    ):
        """save() が相対パスを返すことを確認"""
        local_path = storage.save(sample_hash, sample_image_content, "jpg")

        # base_path からの相対パス形式であること
        expected_path = f"{sample_hash[:2]}/{sample_hash[2:4]}/{sample_hash}.jpg"
        assert local_path == expected_path

    def test_save_handles_different_extensions(
        self, storage: LocalImageStorage, sample_image_content: bytes, sample_hash: str
    ):
        """save() が異なる拡張子を正しく処理することを確認"""
        for ext in ["jpg", "png", "gif", "webp"]:
            # 異なるハッシュを使用
            hash_with_ext = sample_hash[:-4] + ext[:4]
            local_path = storage.save(hash_with_ext, sample_image_content, ext)

            assert local_path.endswith(f".{ext}")
            assert Path(storage.base_path / local_path).exists()

    def test_save_overwrites_existing_file(
        self, storage: LocalImageStorage, sample_hash: str
    ):
        """save() が既存ファイルを上書きすることを確認"""
        content1 = b"first content"
        content2 = b"second content"

        storage.save(sample_hash, content1, "jpg")
        local_path = storage.save(sample_hash, content2, "jpg")

        with open(storage.base_path / local_path, "rb") as f:
            saved_content = f.read()

        assert saved_content == content2

    # === exists() のテスト ===

    def test_exists_returns_none_for_nonexistent_hash(
        self, storage: LocalImageStorage, sample_hash: str
    ):
        """exists() が存在しないハッシュに対して None を返すことを確認"""
        result = storage.exists(sample_hash)

        assert result is None

    def test_exists_returns_path_for_existing_hash(
        self, storage: LocalImageStorage, sample_image_content: bytes, sample_hash: str
    ):
        """exists() が存在するハッシュに対してパスを返すことを確認"""
        saved_path = storage.save(sample_hash, sample_image_content, "jpg")

        result = storage.exists(sample_hash)

        assert result == saved_path

    def test_exists_finds_different_extensions(
        self, storage: LocalImageStorage, sample_image_content: bytes, sample_hash: str
    ):
        """exists() が異なる拡張子のファイルを見つけることを確認"""
        storage.save(sample_hash, sample_image_content, "png")

        result = storage.exists(sample_hash)

        assert result is not None
        assert result.endswith(".png")

    # === delete() のテスト ===

    def test_delete_removes_file(
        self, storage: LocalImageStorage, sample_image_content: bytes, sample_hash: str
    ):
        """delete() がファイルを削除することを確認"""
        local_path = storage.save(sample_hash, sample_image_content, "jpg")

        result = storage.delete(local_path)

        assert result is True
        assert not Path(storage.base_path / local_path).exists()

    def test_delete_returns_false_for_nonexistent_file(
        self, storage: LocalImageStorage
    ):
        """delete() が存在しないファイルに対して False を返すことを確認"""
        result = storage.delete("nonexistent/path/file.jpg")

        assert result is False

    # === move() のテスト ===

    def test_move_moves_file_to_archive(
        self, storage: LocalImageStorage, sample_image_content: bytes, sample_hash: str
    ):
        """move() がファイルをアーカイブに移動することを確認"""
        source_path = storage.save(sample_hash, sample_image_content, "jpg")

        new_path = storage.move(source_path, "archive")

        # 元のファイルは存在しない
        assert not Path(storage.base_path / source_path).exists()
        # 新しいファイルが存在する
        assert Path(storage.base_path / new_path).exists()

    def test_move_preserves_content(
        self, storage: LocalImageStorage, sample_image_content: bytes, sample_hash: str
    ):
        """move() がコンテンツを保持することを確認"""
        source_path = storage.save(sample_hash, sample_image_content, "jpg")

        new_path = storage.move(source_path, "archive")

        with open(storage.base_path / new_path, "rb") as f:
            moved_content = f.read()

        assert moved_content == sample_image_content

    def test_move_creates_archive_directory_structure(
        self, storage: LocalImageStorage, sample_image_content: bytes, sample_hash: str
    ):
        """move() がアーカイブディレクトリ構造を作成することを確認"""
        source_path = storage.save(sample_hash, sample_image_content, "jpg")

        new_path = storage.move(source_path, "archive")

        path = Path(new_path)
        # アーカイブプレフィックスが含まれていることを確認
        assert "archive" in new_path

    # === get_usage_bytes() のテスト ===

    def test_get_usage_bytes_returns_zero_for_empty_storage(
        self, storage: LocalImageStorage
    ):
        """get_usage_bytes() が空のストレージに対して 0 を返すことを確認"""
        usage = storage.get_usage_bytes()

        assert usage == 0

    def test_get_usage_bytes_returns_correct_size(
        self, storage: LocalImageStorage, sample_image_content: bytes, sample_hash: str
    ):
        """get_usage_bytes() が正しいサイズを返すことを確認"""
        storage.save(sample_hash, sample_image_content, "jpg")

        usage = storage.get_usage_bytes()

        assert usage == len(sample_image_content)

    def test_get_usage_bytes_sums_multiple_files(
        self, storage: LocalImageStorage
    ):
        """get_usage_bytes() が複数ファイルのサイズを合計することを確認"""
        content1 = b"a" * 100
        content2 = b"b" * 200
        hash1 = "hash1" + "0" * 59
        hash2 = "hash2" + "0" * 59

        storage.save(hash1, content1, "jpg")
        storage.save(hash2, content2, "png")

        usage = storage.get_usage_bytes()

        assert usage == 300

    # === 初期化のテスト ===

    def test_init_creates_base_directory(self, tmp_path: Path):
        """初期化時にベースディレクトリが作成されることを確認"""
        base_path = tmp_path / "new_images"
        assert not base_path.exists()

        LocalImageStorage(base_path=base_path)

        assert base_path.exists()
        assert base_path.is_dir()
