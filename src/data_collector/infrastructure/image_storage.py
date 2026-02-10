"""
画像ストレージ基盤

ローカルファイルシステムへの画像永続化機能を提供します。
ハッシュベースのディレクトリ構造により、効率的な重複検出とファイル管理を実現します。
"""

from pathlib import Path
from typing import Optional, Protocol
import shutil


class ImageStorageProtocol(Protocol):
    """
    画像ストレージプロトコル

    将来的なS3移行を考慮した抽象インターフェース。
    """

    def save(self, hash: str, content: bytes, extension: str) -> str:
        """画像を保存し、パスを返す"""
        ...

    def move(self, source_path: str, dest_prefix: str) -> str:
        """画像を移動し、新パスを返す"""
        ...

    def delete(self, path: str) -> bool:
        """画像を削除"""
        ...

    def exists(self, hash: str) -> Optional[str]:
        """ハッシュが存在するかチェック"""
        ...

    def get_usage_bytes(self) -> int:
        """使用量を取得"""
        ...


class LocalImageStorage:
    """
    ローカルファイルシステムストレージ

    ハッシュベースのディレクトリ構造でファイルを管理します。
    パス構造: {base_path}/{hash[:2]}/{hash[2:4]}/{hash}.{ext}
    """

    # サポートする画像形式
    SUPPORTED_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp"}

    def __init__(self, base_path: Path):
        """
        LocalImageStorage を初期化

        Args:
            base_path: ベースディレクトリパス
        """
        self.base_path = base_path
        # ベースディレクトリを作成
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _build_path(self, hash: str, extension: str) -> Path:
        """
        ハッシュからファイルパスを構築

        Args:
            hash: SHA-256 ハッシュ値
            extension: ファイル拡張子

        Returns:
            Path: 完全なファイルパス
        """
        # ディレクトリ構造: {hash[:2]}/{hash[2:4]}/{hash}.{ext}
        dir1 = hash[:2]
        dir2 = hash[2:4]
        filename = f"{hash}.{extension}"
        return self.base_path / dir1 / dir2 / filename

    def _get_relative_path(self, hash: str, extension: str) -> str:
        """
        相対パスを取得

        Args:
            hash: SHA-256 ハッシュ値
            extension: ファイル拡張子

        Returns:
            str: ベースパスからの相対パス
        """
        dir1 = hash[:2]
        dir2 = hash[2:4]
        return f"{dir1}/{dir2}/{hash}.{extension}"

    def save(self, hash: str, content: bytes, extension: str) -> str:
        """
        画像を保存

        ハッシュベースのディレクトリ構造でファイルを保存します。

        Args:
            hash: SHA-256 ハッシュ値
            content: 画像バイナリデータ
            extension: ファイル拡張子

        Returns:
            str: 保存されたファイルの相対パス
        """
        full_path = self._build_path(hash, extension)

        # ディレクトリを作成
        full_path.parent.mkdir(parents=True, exist_ok=True)

        # ファイルを書き込み
        with open(full_path, "wb") as f:
            f.write(content)

        return self._get_relative_path(hash, extension)

    def exists(self, hash: str) -> Optional[str]:
        """
        ハッシュが存在するかチェック

        サポートされる全ての拡張子でファイルの存在を確認します。

        Args:
            hash: SHA-256 ハッシュ値

        Returns:
            Optional[str]: 存在する場合はパス、存在しない場合は None
        """
        for ext in self.SUPPORTED_EXTENSIONS:
            full_path = self._build_path(hash, ext)
            if full_path.exists():
                return self._get_relative_path(hash, ext)
        return None

    def delete(self, path: str) -> bool:
        """
        画像を削除

        Args:
            path: 削除するファイルの相対パス

        Returns:
            bool: 削除成功した場合は True、失敗した場合は False
        """
        full_path = self.base_path / path
        if full_path.exists():
            full_path.unlink()
            return True
        return False

    def move(self, source_path: str, dest_prefix: str) -> str:
        """
        画像を移動

        アーカイブなど別のディレクトリにファイルを移動します。

        Args:
            source_path: 移動元の相対パス
            dest_prefix: 移動先のプレフィックス（例: "archive"）

        Returns:
            str: 移動先の相対パス
        """
        source_full = self.base_path / source_path
        dest_relative = f"{dest_prefix}/{source_path}"
        dest_full = self.base_path / dest_relative

        # 移動先ディレクトリを作成
        dest_full.parent.mkdir(parents=True, exist_ok=True)

        # ファイルを移動
        shutil.move(str(source_full), str(dest_full))

        return dest_relative

    def get_usage_bytes(self) -> int:
        """
        ストレージ使用量を取得

        ベースディレクトリ配下の全ファイルサイズを合計します。

        Returns:
            int: 使用量（バイト）
        """
        total = 0
        if self.base_path.exists():
            for file_path in self.base_path.rglob("*"):
                if file_path.is_file():
                    total += file_path.stat().st_size
        return total
