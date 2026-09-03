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
import os
import tempfile
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
        # 並列収集中に複数 worker が同じ latest.json を read-modify-write するため
        # 書き込み区間を直列化する。
        import threading

        self._lock = threading.Lock()

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
        # 内容ベース ID 生成用ハッシュ（暗号用途ではない）
        return hashlib.sha1(key.encode("utf-8"), usedforsecurity=False).hexdigest()

    def save_snapshot(self, items: list[AnimalData]) -> None:
        """AnimalData リストを `snapshots/latest.json` に保存する (merge モード)。

        CollectorService が **サイトごと** に呼び出すため、過去呼び出しで書かれた
        既存ファイルを読み込み、source_url で dedupe (今回 items を優先) してから
        書き直す。これにより、run 内で 209 サイト分のデータが累積される。

        run の境界をクリアにするためには、main の collection ループ開始前に
        snapshot ファイルを削除すること (`SnapshotStore.reset()` を呼ぶ)。
        """
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)

        with self._lock:
            # 既存スナップショットを load (壊れていれば空扱い)
            existing: list[dict] = []
            if self._snapshot_path.exists():
                try:
                    raw = json.loads(self._snapshot_path.read_text(encoding="utf-8"))
                    if isinstance(raw, list):
                        existing = raw
                except (json.JSONDecodeError, OSError):
                    pass

            # 今回 items の source_url を集めて、既存から該当 URL を除外
            new_urls = {str(item.source_url) for item in items}
            merged = [e for e in existing if e.get("source_url") not in new_urls]
            merged.extend(item.model_dump(mode="json") for item in items)

            self._write_atomic(merged)

    def _write_atomic(self, merged: list[dict]) -> None:
        """同ディレクトリの一時ファイルへ書いてから `os.replace` で差し替える。

        `Path.write_text` はファイルを truncate してから書くため、書き込み中は
        `latest.json` が空 or 途中状態で見える。ロックを取らない
        `load_animal_map()` がその瞬間を掴むと JSONDecodeError になり、
        fail-open で空 dict を返して LLM 抽出スキップが無効化されていた (T128)。
        `os.replace` は同一ファイルシステム上で atomic なので、読み手からは
        常に「差し替え前の完全なファイル」か「差し替え後の完全なファイル」の
        どちらかしか見えない。
        """
        fd, tmp_name = tempfile.mkstemp(
            dir=self.snapshot_dir, prefix=".latest-", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(merged, f, ensure_ascii=False, indent=2)
            os.replace(tmp_name, self._snapshot_path)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise

    def reset(self) -> None:
        """次回 run の累積を fresh から始めるため snapshot ファイルを削除する。

        main は collection ループ前に 1 回だけ呼ぶ。テストや手動 run でも使える。
        """
        self._snapshot_path.unlink(missing_ok=True)

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
            url: self.compute_stable_hash(animal) for url, animal in self.load_animal_map().items()
        }

    def load_counts_by_site_url_prefix(self, site_list_urls: dict[str, str]) -> dict[str, int]:
        """サイト別の前回件数を返す。

        Args:
            site_list_urls: `{site_name: list_url}` の dict (sites.yaml 由来)

        Returns:
            `{site_name: count}` の dict。snapshot に存在しないサイトは 0。

        判定ロジック: snapshot 内の `source_url` が `site.list_url` で前方一致
        するものをカウントする。各 adapter は detail URL を `{list_url}#row=N`
        や `{list_url}#h3=N`、または `{list_url}.../detail/{id}.html` 形式で
        生成するため、`list_url` を prefix にしてサイトを識別できる。

        **サイト別の件数集計には使わないこと** (2026-08-03):
            上の前提は「detail URL が list_url の配下にある」サイトでしか
            成立しない。1 頭ごとに独立した詳細ページ URL を持つサイト

                list_url  : https://animal-net.pref.nagasaki.jp/jyouto
                source_url: https://animal-net.pref.nagasaki.jp/animal/no-19847/

            では前方一致せず 0 件になる。実測で公開 729 頭のうち 317 頭 (43%)
            がこの方法では数えられず、収集は成功しているのに
            `site_baselines.yaml` 上は永久に 0 件・`consecutive_zero_runs` が
            加算され続ける状態になっていた。さらに同一ドメインに複数サイトを
            持つ自治体 (旭川市 8 / 福岡県 8 など) は source_url だけでは
            原理的に site を特定できない。

            サイト別件数は adapter の `result.total_collected`、サイト別の
            動物グルーピングは収集時の `{site_name: [source_url, ...]}` を
            使うこと。本メソッドは本番経路からは未使用。
        """
        animals = self.load_animal_map()
        result: dict[str, int] = dict.fromkeys(site_list_urls, 0)
        for url in animals:
            for name, list_url in site_list_urls.items():
                if url.startswith(list_url):
                    result[name] += 1
                    break  # 1 URL は 1 site にしか紐付かない
        return result

    def load_snapshot(self) -> list[AnimalData]:
        """後方互換: DiffDetector が呼ぶ。

        v1 では空リストを返し、DiffDetector の挙動（全件を新規扱い）を維持する。
        LLM スキップは CollectorService が `load_animal_map()` を別途使って実現する。
        """
        return []
