"""
スナップショットストア

`snapshots/latest.json` に前回収集した AnimalData を JSON で永続化し、
次回実行時に **既知 source_url の LLM 抽出をスキップ** するために使う。

設計方針：
- DiffDetector との後方互換のため `load_snapshot()` は空リストを返したまま
  （DiffDetector は引き続き「全件が新規」として扱う）
- LLM スキップ判定は CollectorService が `load_animal_map()` を直接使う

GitHub Actions では `.github/workflows/data-collector.yml` の `git add
output/animals.json snapshots/latest.json` で commit & push されるので、
リポジトリを介して run 跨ぎで状態保持される。
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from ..domain.models import AnimalData

logger = logging.getLogger(__name__)


class SnapshotStore:
    """前回収集の永続化ストア"""

    SNAPSHOT_FILENAME = "latest.json"

    def __init__(self, snapshot_dir: Path | str | None = None) -> None:
        if snapshot_dir is None:
            snapshot_dir = Path("snapshots")
        self.snapshot_dir = Path(snapshot_dir)

    @property
    def _snapshot_path(self) -> Path:
        return self.snapshot_dir / self.SNAPSHOT_FILENAME

    @staticmethod
    def compute_stable_hash(animal: AnimalData) -> str:
        """`location | phone | species` の SHA-1 を 40 桁の hex で返す。

        v1 では LLM スキップ判定は URL 一致のみで行うが、将来的に
        「URL 一致でも内容が変わったら再抽出」する判定に使う想定で
        ここに置いておく。
        """
        key = f"{animal.location}|{animal.phone or ''}|{animal.species}"
        return hashlib.sha1(key.encode("utf-8")).hexdigest()

    def save_snapshot(self, items: list[AnimalData]) -> None:
        """全 AnimalData を `snapshots/latest.json` に JSON dump する。"""
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        payload = [item.model_dump(mode="json") for item in items]
        self._snapshot_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load_animal_map(self) -> dict[str, AnimalData]:
        """`{source_url: AnimalData}` の dict を返す。

        ファイルが無い、JSON が壊れている、要素が AnimalData にバリデートできない
        場合は空 dict を返す（fail-open: 失敗したら全件 LLM 抽出に戻る）。
        """
        path = self._snapshot_path
        if not path.exists():
            return {}

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Snapshot 読み込み失敗（破損 or I/O）: {e}")
            return {}

        if not isinstance(raw, list):
            logger.warning(f"Snapshot 形式不正（list でない）: {type(raw).__name__}")
            return {}

        result: dict[str, AnimalData] = {}
        for entry in raw:
            try:
                animal = AnimalData.model_validate(entry)
            except Exception as e:
                logger.warning(f"Snapshot エントリのバリデーション失敗、スキップ: {e}")
                continue
            # AnimalData.source_url は HttpUrl 型なので str に正規化してキーにする
            result[str(animal.source_url)] = animal
        return result

    def load_url_hash_map(self) -> dict[str, str]:
        """`{source_url: stable_hash}` の dict を返す。"""
        return {
            url: self.compute_stable_hash(animal)
            for url, animal in self.load_animal_map().items()
        }

    def load_snapshot(self) -> list[AnimalData]:
        """後方互換: DiffDetector が呼ぶ。

        v1 では空リストを返し、DiffDetector の挙動（全件を新規扱い）を維持する。
        LLM スキップは CollectorService が `load_animal_map()` を別途使って実現する。
        """
        return []
