"""JSON 出力コンポーネント"""

from typing import List
from pathlib import Path
import json
from datetime import datetime

from ..domain.models import AnimalData
from ..domain.diff_detector import DiffResult


class OutputWriter:
    """
    正規化済みデータを animal-repository 向け JSON として出力

    Responsibilities:
    - AnimalData リストを JSON ファイルに書き込み
    - スキーマバリデーション（Pydantic による自動検証）
    - 出力先ディレクトリ管理

    Requirements: 2.7
    """

    OUTPUT_DIR = Path("output")
    OUTPUT_FILE = OUTPUT_DIR / "animals.json"

    def __init__(self):
        """OutputWriter を初期化"""
        pass

    def write_output(self, data: List[AnimalData], diff_result: DiffResult) -> Path:
        """
        正規化済みデータを JSON ファイルに出力

        Args:
            data: 今回収集したデータ
            diff_result: 差分検知結果（メタデータとして含める）

        Returns:
            Path: 出力ファイルパス

        Preconditions: data は空でも可（初回実行時など）
        Postconditions: animals.json が生成される
        """
        # ディレクトリ自動作成
        self.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        # 出力データ構造の構築
        output_data = {
            "collected_at": self._get_current_timestamp(),
            "total_count": len(data),
            "diff": {
                "new_count": len(diff_result.new),
                "updated_count": len(diff_result.updated),
                "deleted_count": len(diff_result.deleted_candidates)
            },
            "animals": [animal.model_dump(mode='json') for animal in data]
        }

        # JSON ファイルに書き込み
        with open(self.OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)

        return self.OUTPUT_FILE

    def _get_current_timestamp(self) -> str:
        """
        現在時刻を ISO 8601 形式で取得

        Returns:
            str: ISO 8601 形式のタイムスタンプ（UTC、Z サフィックス付き）
        """
        return datetime.utcnow().isoformat() + "Z"
