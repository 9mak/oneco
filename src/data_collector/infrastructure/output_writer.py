"""JSON 出力コンポーネント"""

import json
from datetime import datetime
from pathlib import Path

from ..domain.diff_detector import DiffResult
from ..domain.models import AnimalData


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

    def write_output(self, data: list[AnimalData], diff_result: DiffResult) -> Path:
        """
        正規化済みデータを JSON ファイルに出力 (merge モード)

        CollectorService が **サイトごと** に呼び出すため、既存 animals.json を
        読み込み、source_url で dedupe (今回 data を優先) してから書き直す。
        これにより run 内で 209 サイト分のデータが animals.json に累積される。

        diff カウントは「今回サイト分」の累積として加算される。
        run の境界をクリアにするためには、main の collection ループ開始前に
        `OutputWriter.reset()` を呼ぶこと。

        Args:
            data: 今回収集したデータ (このサイト分)
            diff_result: 差分検知結果（このサイト分、累積される）

        Returns:
            Path: 出力ファイルパス
        """
        self.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        # 既存 animals.json を load (壊れていれば空扱い)
        existing_animals: list[dict] = []
        existing_diff = {"new_count": 0, "updated_count": 0, "deleted_count": 0}
        if self.OUTPUT_FILE.exists():
            try:
                with open(self.OUTPUT_FILE, encoding="utf-8") as f:
                    old = json.load(f)
                if isinstance(old, dict):
                    existing_animals = old.get("animals", []) or []
                    existing_diff = old.get("diff", existing_diff) or existing_diff
            except (json.JSONDecodeError, OSError):
                pass

        # 今回 data の source_url を集めて、既存から該当 URL を除外
        new_urls = {str(a.source_url) for a in data}
        merged_animals = [a for a in existing_animals if a.get("source_url") not in new_urls]
        merged_animals.extend(a.model_dump(mode="json") for a in data)

        # diff カウントは累積
        merged_diff = {
            "new_count": existing_diff.get("new_count", 0) + len(diff_result.new),
            "updated_count": existing_diff.get("updated_count", 0) + len(diff_result.updated),
            "deleted_count": existing_diff.get("deleted_count", 0)
            + len(diff_result.deleted_candidates),
        }

        output_data = {
            "collected_at": self._get_current_timestamp(),
            "total_count": len(merged_animals),
            "diff": merged_diff,
            "animals": merged_animals,
        }

        with open(self.OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)

        return self.OUTPUT_FILE

    def reset(self) -> None:
        """run の累積を fresh から始めるため animals.json を削除する。

        main は collection ループ前に 1 回だけ呼ぶ。
        """
        self.OUTPUT_FILE.unlink(missing_ok=True)

    def _get_current_timestamp(self) -> str:
        """
        現在時刻を ISO 8601 形式で取得

        Returns:
            str: ISO 8601 形式のタイムスタンプ（UTC、Z サフィックス付き）
        """
        return datetime.utcnow().isoformat() + "Z"
