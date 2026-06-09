# Research & Design Decisions: animal-identity-fields

> 詳細な層別ギャップ調査（file:line 一次確認）は [gap-analysis.md](gap-analysis.md) を参照。本書は設計判断とトレードオフに絞る。

## Summary
- **Feature**: `animal-identity-fields`
- **Discovery Scope**: Extension（既存パイプラインへの 4 フィールド追加）
- **Key Findings**:
  - 受け皿（ORM/ドメイン/スキーマ/型）は無く新設だが、すべて additive nullable で機械的。migration head = `a7b8c9d0e1f2`、雛形は `9b1c2d3e4f5a`(prefecture, nullable+index)。
  - 値入れ（収集層）は**大半が「既に解析済みの値を渡すだけ」**。基底2ファイル（`wordpress_list.py` / `single_page_table.py`）に配線すれば、派生は `FIELD_SELECTORS`/`COLUMN_FIELDS` のキー1行で開通。breed を species に潰して品種名を捨てている群が 20+ サイト。
  - LLM 複数頭経路（`adapter.py:220-234 _expand_multi_animal_pdf`）が、スキーマに既にある `management_number`/`features` を RawAnimalData に渡さず破棄している実バグ。
  - 命名不整合: LLM/一部 rule-based は性格・特徴を `features`、本 spec/DB は `description`。
  - PII: 既存 `_redact_pii` は電話/メールのみ（氏名は非対応）。`_cap_color`(254-265) が description 正規化の手本。

## Research Log

### 収集層の「解析済みで破棄」箇所
- **Context**: 「抽出済みなのに捨てている」が実態か検証。
- **Findings**: kochi(`kochi_adapter.py:305` breed を species 判定だけに使い破棄)、city_wakayama(`:160` breed 計算済みだが RawAnimalData に渡さず、24行に「含めない」コメント有)、city_sendai(`:53` 管理番号 h3 をアンカー検出済みだが破棄)、city_kashiwa(特徴→`_features`(:96) を age 補完だけに使用)。
- **Implications**: Slice 1/2/3 の配線は新規抽出ではなく「既存値を RawAnimalData に渡す」+ 基底2ファイルの汎用配線で広く効く。

### migration チェーンと head
- **Findings**: 全11 migration を追跡し head = `a7b8c9d0e1f2`(add_source_site) を確定。prefecture migration が nullable+index の対称形雛形。
- **Implications**: 新 migration の down_revision を `a7b8c9d0e1f2` に。Slice 0 で1回に集約。

## Design Decisions

### Decision: フィールド命名は `description` に統一、LLM 側 `features` は境界でマップ
- **Alternatives**: (A) DB/ドメインも `features` に揃える (B) LLM tool キーを `description` にリネーム (C) ドメイン=`description`、LLM tool キーは `features` のまま LlmAdapter でマップ。
- **Selected**: (C)。ドメイン/DB/API/frontend は `description`。LLM 抽出 tool の JSON キーは `features`（プロンプトの自然さ優先）のまま、`LlmAdapter` で `features → description` にマップ。rule-based adapter の `特徴` も `description` フィールドへ。
- **Rationale**: LLM プロンプト/スキーマの破壊的変更を避けつつ、ドメインの語彙を1つに統一。
- **Trade-offs**: 境界で1箇所マッピングが要るが、影響局所。

### Decision: description の PII は電話/メールのみ伏字（氏名は将来対応）
- **Context**: AC2.5 は「飼い主・発見者の個人情報」除去を要求。既存 `_redact_pii` は電話/メールのみ、氏名は非対応。
- **Selected**: description に `_redact_pii`（電話/メール）+ 長さ丸めを適用。**氏名伏字は本 spec の非対象**とし将来課題に明記。management_number には PII を適用しない（番号の誤伏字回避）。
- **Rationale**: 確定した高リスク PII（本番で実在した個人携帯）は電話で、それはカバーされる。保護動物の性格記述に第三者の氏名が入るケースは稀。氏名伏字は NER/ヒューリスティクスが必要で別タスク規模。
- **Trade-offs**: 氏名が稀に残存しうる。削除依頼窓口で対応。フロントは伏字済み前提で**テキストノード描画**（XSS 回避）。

### Decision: カラム長と normalizer 長さ定数を厳密一致
- **Selected**: breed=VARCHAR(50)/name=VARCHAR(100)/management_number=VARCHAR(50)/description=Text。normalizer 定数 `_BREED_MAX_LEN=50`/`_NAME_MAX_LEN=100`/`_MANAGEMENT_NUMBER_MAX_LEN=50`/`_DESCRIPTION_MAX_LEN=2000`（Text の暴走ガード）。
- **Rationale**: 列長 < 定数だと丸めをすり抜けて INSERT 失敗→トランザクション rollback で1サイト全損（既存 normalizer コメントが警告する事故）。

### Decision: q 検索は breed/name/description を対象に、management_number は応答のみ
- **Selected**: repository の OR句 **2箇所**(`list_animals`:285-294 / `list_animals_orm`:373-382) に breed/name/description の ilike を追加。management_number は検索ノイズになるため非対象。
- **Trade-offs**: description(Text) の ilike はインデックス無しフルスキャン。現状件数では許容、将来課題。OR句2箇所の同時更新が必須（DRY 化は本 spec 外）。

### Decision: スライス分割（Slice 0→1→2→3）と migration 集約
- **Selected**: Slice 0(基盤: migration 1回 + 空配線) → Slice 1(breed) → Slice 2(description+PII) → Slice 3(name/management_number)。migration は Slice 0 に集約（additive nullable で本番 DDL 1回）。
- **Rationale**: 全フィールド任意なので breed 単体でも他3つ未配線でエラー無し（AC6.2）。本番 Supabase への DDL を最小化。

### Decision: AnimalArchive は非スコープ
- **Selected**: `AnimalArchive` テーブル/型への 4 フィールド追加は本 spec 対象外。
- **Rationale**: アーカイブは卒業済み履歴で個体識別の価値が薄く、コピー実装の確認が別途必要。スコープを限定して安全に。

## Risks & Mitigations
- **RawAnimalData 必須化で全損** — 新4フィールドは必ず `Field(default="")`（任意）。必須化禁止。
- **列長 < normalizer 定数で INSERT 失敗→サイト全損** — 列長と定数を一致させ、test で丸めを検証。
- **MULTI ドロップ修正で値が初めて流れる** — 受け皿(B)→normalizer(C) 先行を前提に Slice 2 で配線。
- **frontend 既存テスト波及** — 見出しは現状維持で name/breed を追加表示し、mockAnimal は型追加と同コミットで更新。
- **PR #157 の PII 関数（`_coarsen_location` 等）は本ブランチ(main起点)に無い** — description PII は `_redact_pii`(main 在)のみ使用し、PR #157 への依存を持たせない。

## References
- [gap-analysis.md](gap-analysis.md) — 6層 × file:line の詳細ギャップ調査
- `.kiro/specs/animal-category-field/` — 単一フィールド追加の完了済み先行 spec（migration/モデル/スキーマの踏襲手本）
