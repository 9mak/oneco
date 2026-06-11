<!--
PR の概要を 1-3 文で。「何を変えたか」より「なぜ変えたか / どんな問題を解くか」を先に書く。
-->

## Summary

## Test plan
- [ ] 関連箇所のユニットテスト追加・更新
- [ ] backend: `PYTHONPATH=src .venv/bin/python -m pytest` がローカルで pass
- [ ] backend: `python3 -m ruff check src/ tests/` および `ruff format --check src/ tests/` が clean
- [ ] frontend を変更した場合: `npx tsc --noEmit` と `npm run lint` が clean

---

## 🛑 Animal / 個体識別フィールド を触る PR のチェックリスト

**触っていなければスキップ可。** `Animal` / `RawAnimalData` / `AnimalData` / `AnimalArchive` / `breed` / `name` / `management_number` / `description` のいずれかを変更した場合は以下を確認すること。
過去6回連続で同じサイレントドロップを踏んだ反省 (PR #171/#173/#176/#177/#180)。詳細: `feedback_oneco_silent_drop_prevention` memory。

### 新規 adapter または adapter で個体識別フィールドを抽出するように変更した
- [ ] `extract_animal_details` で抽出したフィールドを `RawAnimalData(...)` 構築子に**渡している**
- [ ] `adapter.normalize(raw)` を呼び出して **`AnimalData` レベル** でアサーションするテストを書いた
  - `raw.breed == "..."` だけは不十分。`animal.breed == "..."` まで確認すること
  - 模範: `tests/adapters/test_kochi_adapter.py::test_full_scraping_flow`
- [ ] adapter で `normalize()` を override している場合、`RawAnimalData` 再構築時に `breed/name/management_number/description` を**明示的に名前付き引数で渡している**
  - 可能なら `return self._default_normalize(raw_data)` に委譲する

### `Animal` ORM (active テーブル) に新カラムを追加した
- [ ] `AnimalArchive` ORM にも**同じカラム**を追加した (列長厳密一致)
- [ ] archive 用の alembic migration を追加した (additive nullable)
- [ ] `archive_repository.insert_archive` の引数追加
- [ ] `archive_repository._to_pydantic` の `AnimalData` 構築に追加
- [ ] `ArchivedAnimalPublic` schema (`schemas.py`) に追加
- [ ] frontend `types/animal.ts` の `ArchivedAnimalPublic` interface に追加

### 全層配線 (新フィールドを公開 API まで届ける)
- [ ] ORM `Animal` + migration
- [ ] ORM `AnimalArchive` + migration
- [ ] `RawAnimalData` / `AnimalData` (domain/models.py)
- [ ] `DataNormalizer.normalize()` の `AnimalData(...)` 構築
- [ ] `repository._to_orm` / `_to_pydantic` / `save_animal`
- [ ] `AnimalPublic` / `ArchivedAnimalPublic` schema
- [ ] frontend `types/animal.ts` の両 interface
- [ ] frontend 表示コンポーネント (未設定時の条件付きレンダリング)
- [ ] 検索対象に含めるなら `repository.list_animals_orm` の OR 句 + `routes.py` の Query description 文字列

### ORM index を追加した
- [ ] `Column(..., index=True)` ではなく `__table_args__` の `Index("idx_<table>_<col>", ...)` で **明示命名**した (migration の命名規約 `idx_*` と一致させるため)

### `sites.yaml` に新しい自治体を追加した
- [ ] 新ホストが `.jp` / `.okinawa` 以外なら `frontend/next.config.ts` の `remotePatterns` にも追加した
- [ ] `tests/test_image_remote_patterns.py` が pass する (自動検出される)

### `_PII_PHONE_RE` などの PII regex を拡張した
- [ ] 追加する各フォーマットに対して `tests/domain/test_normalizer.py::TestDescriptionNormalization` に Red 確認できるテストを追加した
- [ ] 管理番号 `2026-001` / 体重 `5.5kg` / 年号 `2026年` 等の**誤検知防止テスト**も追加した

🤖 Generated with [Claude Code](https://claude.com/claude-code)
