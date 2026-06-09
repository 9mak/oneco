# Gap Analysis: animal-identity-fields

個体識別4フィールド **breed / name / description / management_number** を、収集 → 正規化(PII伏字) → 保存 → 公開API → frontend → q検索 まで一気通貫で通すための実装ギャップ分析。

- 要件: [requirements.md](requirements.md)
- 先行事例: `.kiro/specs/animal-category-field/`（単一フィールド category 追加の完了済み spec。migration/モデル/スキーマ追加の踏襲パターン）
- 本文中の `file:line` はすべて 2026-06-10 時点のコードで一次確認済み。確信度が低い箇所は明記する。

---

## 1. サマリ（層別ギャップ一覧）

各層の現状と必要作業を1行ずつ。**「配線」= 既に解析済み/スキーマ済みの値を渡すだけ**、**「新規」= ロジック/カラム/フィールドの新設**。

| # | 層 | 現状 | 4フィールドのギャップ | 区分 |
|---|---|---|---|---|
| A | ORM `Animal`（`infrastructure/database/models.py:36-56`） | 4カラム無し（`color`/`size`/`prefecture` 等は存在） | nullable カラム4本追加（breed/name=VARCHAR, description=Text, management_number=VARCHAR）。breed は index | **新規** |
| A' | ORM `AnimalArchive`（`models.py:197-252`） | 同一スキーマを謳うが name/breed/description/management_number 無し | スコープ判断（後述、原則 **非スコープ**） | 判断 |
| A'' | migration（head=`a7b8c9d0e1f2`） | 直近 head 確認済み | head を down_revision にした additive nullable migration | **新規** |
| B | ドメイン `RawAnimalData`/`AnimalData`（`domain/models.py:33-78`） | 4フィールド無し。Raw は全必須 `Field(...)`、Animal は任意 `X|None` パターンあり | Raw=`str Field(default="")`、Animal=`str|None Field(default=None)` で4つ追加 | **新規** |
| C | `DataNormalizer`（`domain/normalizer.py`） | `_cap_color`(254-265)/`_redact_pii`(247-251)/長さ定数(227-231) が手本。新4フィールドの正規化なし | description=PII伏字+長さ丸め、breed/name/mgmt=trim+空→None+長さ丸め。`normalize()` の build ブロック(105-118)に4行 | **新規（伏字は既存流用）** |
| D | repository（`infrastructure/database/repository.py`） | `_to_orm`(67-85)/`_to_pydantic`(97-115)/save_animal更新(143-164) の3箇所に固定列挙 | 3箇所すべてに4フィールド追加 | **配線（機械的）** |
| E | rule-based アダプター（収集層） | **解析済みで捨てている箇所が多数**（後述） | 基底2ファイル+代表サイトの RawAnimalData 配線 | **大半が配線** |
| F | LLM抽出（`llm/providers/groq_provider.py` / `llm/adapter.py`） | 単頭toolに4項目無し。MULTI toolは `management_number`/`features` 済だが adapter が**ドロップ中** | 単頭toolに4項目追加(required外)+プロンプト+マッピング。MULTI はドロップ修正 | **新規+バグ修正** |
| G | 公開スキーマ `AnimalPublic`（`infrastructure/api/schemas.py:26-53`） | 4フィールド無し。`from_attributes=True` 済 | `X|None=None` で4つ追加 | **配線（薄い）** |
| H | q検索（`repository.py` の OR句 **2箇所**: 285-294 / 373-382） | species/color/size/location/prefecture の OR | breed/name/description を OR に追加（mgmt は対象外）。2箇所同時更新 | **配線** |
| I | routes（`infrastructure/api/routes.py:75-79`） | q の description 文言のみ | 説明文更新のみ（ロジックは repository） | **文言** |
| J | frontend 型（`frontend/types/animal.ts:9-37` / `43-65`） | 4フィールド無し。`T \| null` 規約 | AnimalPublic に4つ + (任意で)ArchivedAnimalPublic | **新規** |
| K | frontend 表示（`AnimalCard.tsx` / `AnimalDetailClient.tsx`） | color/size の条件表示が手本。description段落表示要素なし | カード=breed/name、詳細=breed/mgmt/description（段落） | **新規（パターン流用）** |

**結論**: 受け皿（A/B/G/J）は新規だが additive nullable で機械的。値を入れる作業（E）は **大半が「既に解析済みの値を渡すだけ」** で、新規抽出ロジックはほぼ不要。最大の論点は F の MULTI ドロップ修正と、description の PII/命名（`features` vs `description`）整合。

---

## 2. 層別ギャップ詳細

### 層A: DB / ORM / migration

**現状**
- `Animal` テーブル（`infrastructure/database/models.py:21-118`）。任意カラムの手本: `color: Column(String(100), nullable=True)`（54）、`size: Column(String(50), nullable=True)`（55）、`phone: Column(String(20), nullable=True)`（56）。検索対象に index を付ける手本: `prefecture: Column(String(20), nullable=True, index=True)`（39）。長文は `location: Column(Text, ...)`（38）。
- 複合検索 index は `__table_args__`（106-111、`idx_animals_search` 等）。
- `AnimalArchive`（197-252）は「animals と同一スキーマ」を謳うが、実際に持つのは species/sex/age_months/color/size/shelter_date/location/phone/category/status 系のみで、**name/breed/description/management_number は無い**（確認済み）。
- migration head は **`a7b8c9d0e1f2`**（`add_source_site`）。`down_revision = "e4f5a6b7c8d9"`。どの migration もこれを down_revision に参照していない（grep 0件）ため head で確定。チェーン: `33c0ccd7c108 → 6134989ff064(category) → 7a8b9c0d1e2f → 8a9b0c1d2e3f → 9b1c2d3e4f5a(prefecture) → a0b1c2d3e4f5 → b1c2d3e4f5a6 → c2d3e4f5a6b7 → d3e4f5a6b7c8 → e4f5a6b7c8d9 → a7b8c9d0e1f2(head)`。

**必要変更**
- `models.py` の Animal に4カラム追加。`breed=String(50) nullable index`、`name=String(100) nullable`、`management_number=String(50) nullable`、`description=Text nullable`。配置はオプショナル群（54-56 の color/size/phone 付近）。`idx_animals_search` への追加は不要（q検索は別経路の LIKE OR）。
- 新規 migration `{rev}_add_identity_fields_to_animals.py`、`down_revision='a7b8c9d0e1f2'`。upgrade で `op.add_column` ×4 + `op.create_index('idx_animals_breed', ...)`、downgrade で drop_index+drop_column×4。雛形は `9b1c2d3e4f5a_add_prefecture_to_animals.py`（add_column+create_index+drop の対称形）。`server_default` 不要（全 nullable）。

**踏襲する既存パターン**
- category 追加（`6134989ff064`）は `server_default` 付き NOT NULL の別パターン。本 spec は **prefecture（nullable+index）** の方が近い手本。
- migration テストは `tests/test_migration.py` の `expected_columns` リストに新カラム名を追記（Base.metadata で SQLite 検証する方式。実 alembic は走らせない）。

**リスク**
- **`AnimalArchive` 同期**: アーカイブのコピー実装が「列を明示列挙」か「SELECT * 的コピー」かで影響が変わる。明示列挙なら新カラムを無視しても動く。要 design 判断（後述、現状 **非スコープ**寄り）。確信度: コピー実装の中身は未確認のため 70%。
- `test_migration.py` の `expected_columns` 検証は ORM とmigrationの乖離（片方だけ更新）を検出**できない**。ORM と migration を必ず同時更新する。

---

### 層B: ドメインモデル `RawAnimalData` / `AnimalData`

**現状**（`domain/models.py`、確認済み）
- `RawAnimalData`（33-51）: **全11フィールドが必須** `str = Field(..., ...)`（category も `Field(..., ...)`）。
- `AnimalData`（54-: ）: 任意は `color: str | None = Field(default=None)`（73）形式。`@field_validator` は species/sex 等にあるが breed/name/description/mgmt には不要（自由値）。

**必要変更**
- `RawAnimalData` に4フィールドを **`str = Field(default="")`** で追加（既存は全必須だが、新フィールドは省略可にして 100+ アダプターの構築呼び出しの後方互換を保つ）。
- `AnimalData` に4フィールドを **`str | None = Field(default=None)`** で追加（color/size と同列）。validator 追加なし。

**リスク（最重要・全層の前提）**
- **新4フィールドを必須にすると全損**。RawAnimalData は全アダプター/LLM経路で構築されるため、必須化すると即 `ValidationError` で収集が全壊する。必ず default 付き任意にすること（AC 6.2/1.5 のスライス可能性の根拠）。
- `name` は Pydantic/SQLAlchemy で予約語ではなく属性名衝突なし（確信度 95%）。

---

### 層C: `DataNormalizer`（正規化 + PII）

**現状**（`domain/normalizer.py`、確認済み）
- `normalize()` の build ブロック（105-118）が `return AnimalData(...)` の全フィールドマッピング箇所。
- PII伏字 `_redact_pii(text)`（247-251）: `_PII_PHONE_RE`（238-242: 半角/全角ハイフン・ハイフン無し10/11桁）と `_PII_EMAIL_RE`（243）を `███`（244）に置換。文字列全体に作用し長さ非依存 → 複数行 description にそのまま使える。
- `_cap_color(raw)`（254-265）: `not raw→None` → `.strip()` → 空→None → `_redact_pii` → `_COLOR_MAX_LEN=100`(227) で丸め。**description が踏襲すべき最も近い手本**。
- `_cap_size`（267-）は体格語正規化を含むので breed/name/mgmt には過剰。
- 長さ定数は 225-231 に集約（`_COLOR_MAX_LEN=100` 等、VARCHAR値とコメントで紐付け）。
- タスク記載の `_coarsen_location`/`_sanitize_public_phone` は **src に存在しない**（grep 0件）。location は `raw_data.location if ... else "不明"`（112）のパススルーのみで粗粒度化は未実装。requirements の「location 粗粒度化と整合」（23, 63）は**将来方針への言及**で既存関数ではない（確認済み）。

**必要変更**
- 長さ定数を 227-231 隣に追加: `_BREED_MAX_LEN=50`/`_NAME_MAX_LEN=100`/`_MANAGEMENT_NUMBER_MAX_LEN=50`（**ORM の列長と必ず一致**）。description は Text 列なら実質無制限だが暴走ガードとして `_DESCRIPTION_MAX_LEN`（例 2000）を任意で設定。
- 汎用ヘルパ `_cap_text(raw, max_len)`: `_cap_color` から `_redact_pii` 行を抜いた形。breed/name/management_number に適用。
- description 専用 `_normalize_description(raw)`（または `_cap_color` を max_len 引数化）: `not raw→None` → strip → 空→None → **`_redact_pii` 適用** → 長さ丸め（伏字を**丸めの前**に行う＝伏字後の文字数で丸める）。
- `normalize()` build ブロック（105-118）に4行追加。

**踏襲する既存パターン**
- 空/空白→None・トリムは `if not raw: return None` → `strip()` → `if not text: return None` の3段（`_cap_color:256-260`）。
- 長さ定数は VARCHAR/Text 型をコメントで明記（既存 `_COLOR_MAX_LEN` の規約）。

**リスク**
- **列長 < 定数だと切り詰めをすり抜けて INSERT 失敗 → rollback で1サイト全損**（既存コメント 223-227 が警告する事故）。定数は実列長と一致必須。
- `_PII_PHONE_RE` が management_number を誤伏字化しうる。`R7-249` は `\d{2,4}-\d{2,4}-\d{3,4}` に1ハイフンでマッチせず安全だが、長い数字ハイフン列の管理番号は反応しうる → **mgmt には PII を適用しない方針**で回避（description のみ伏字）。
- email正規表現が description 内の `@ユーザー名` SNS表記を伏字化しうる（過剰伏字）。公開リスク低減側に倒れるため許容だが、非PII温存テストで副作用を可視化する。
- **氏名は伏字化されない**（`_redact_pii` は電話・メールのみ）。requirements AC2.5 の「発見者の個人情報」のうち**氏名は現状未対応**。description では電話/メール伏字+長さ丸めに留める判断を design で明記する必要（後述）。

---

### 層D: repository（マッピング3箇所）

**現状**（`infrastructure/database/repository.py`、確認済み）
- `_to_orm`（67-85）/ `_to_pydantic`（97-115）/ save_animal の既存行更新ブロック（143-164）の **3箇所すべて**に各カラムを明示列挙。prefecture が3箇所にある（手本）。
- 更新ブロック（143-164）は **core フィールド（category 含む）は無条件上書き**、拡張フィールド（status/status_changed_at/outcome_date/local_image_paths）は `if ... is not None` ガード付き（確認済み）。

**必要変更**
- 3箇所に breed/name/description/management_number を追加。更新ブロックでは category 同様に**無条件上書き**（再収集で自然充填の方針 = AC 6.4 と整合。`if not None` ガードを付けるとサイトから値が消えた時に古い値が残留する）。

**リスク**
- 3箇所のいずれか1つでも漏れるとラウンドトリップで欠落。必ず同時更新。

---

### 層E: rule-based アダプター（収集層の配線）

**現状: 解析済みで捨てている箇所が多数（=配線で済む）**（確認済み）
- **kochi**（`adapters/kochi_adapter.py:305`）: `breed = self._extract_from_structured_data(entry_content, ["品種","種類","しゅるい"])` で品種を読むが、species判定（309）にだけ使い、`RawAnimalData(...)`（333）に **breed を渡していない（破棄）**。`_detect_species_from_content`（571-605）は breed を引数に取り species 判定にのみ使用。name/management_number は kochi では構造化抽出していない（ラベル追加で拾える可能性は **実HTML未検証**）。
- **city_wakayama**（`sites/city_wakayama.py:160`）: `breed = _extract_field(full_text, "種類")` を計算済みだが `RawAnimalData`（164）に渡さず、エラーメッセージ（180）にしか使われず破棄。**24行に「RawAnimalData には含めない」コメントが明示的に存在**（要更新）。「仮名」「性格等」も card 内（15-20）にあり `_extract_field` で即取得可能。
- **city_kashiwa**（`sites/city_kashiwa.py`）: `_LABEL_TO_FIELD`（83-）に「特徴→`_features`」（96）。`_features`（266）は size/age 補完（267）にだけ使い description 保存せず。形式B(satoya.html, 21)は仮名+管理番号が同居しうる自由文を `_features`（334）に連結保持。
- **city_sendai**（`sites/city_sendai.py:13,53`）: `_KANRI_BANGO_RE=re.compile("管理番号")`（53）で `<h3>...管理番号 XXX（愛称：YYY）...</h3>`（13/51）を**アンカーとして検出済み**。値（管理番号・愛称）は h3 テキストに居るのに `RawAnimalData` に渡さず破棄。

**breed を species/species_detail に潰して品種名を失っている群（横展開対象多数）**
- grep（`犬種|猫種|species_detail`）で確認した対象: pref_wakayama, city_machida, pref_ishikawa, city_maebashi, kyoto_ani_love, city_saitama, city_koshigaya_kojin, city_sasebo, pref_yamanashi, city_nagoya, city_nara, city_hirakata, city_higashiosaka, city_takatsuki, pref_iwate, city_otsu, city_akashi, city_kitakyushu, hama_aikyou, pref_toyama 等（**20+サイト**）。すでに種類値を抽出済みなので、breed 用キーに二重登録 or species_detail を breed として渡すだけで充填できる。

**共通基底の構造**（確認済み）
- `wordpress_list.py`: `FIELD_SELECTORS`（54）。`extract_animal_details`（93）は fields dict を作るが `RawAnimalData`（117）に固定キーのみ渡す。
- `single_page_table.py`: `COLUMN_FIELDS`（36）。`extract_animal_details`（66）→ `RawAnimalData`（87）に固定キーのみ。
- `CollectorService` は raw→normalize を素通しするだけ（**改修不要**）。

**必要変更**
- 基底2ファイル（`wordpress_list.py:117` / `single_page_table.py:87`）の `RawAnimalData(...)` に `breed/name/description/management_number=fields.get(...)` を配線。これで派生は `FIELD_SELECTORS`/`COLUMN_FIELDS` にキー1行追加するだけで開通する（**広く効く手の核**）。
- 代表サイト: kochi（305の既存 breed を渡す）、wakayama（160の既存 breed + 仮名/性格等）、sendai（h3 から管理番号/愛称）、kashiwa（`_features`→description、形式B から仮名+番号を正規表現抽出）。

**リスク**
- **breed と species の混同**: 多くのアダプターは「種類」を species に入れている。breed は species 正規化（犬/猫/その他 3値制約）とは別物として**自由値・無検証**で保存し、species ロジックには手を入れない（AC3.5）。
- **kochi の「管理番号」「仮名」ラベルは docstring（248付近）にあるが実HTMLでの存在は未検証**。ラベル追加しても0件のままの可能性 → adapter_live_test での実値確認が必須（AC3.4を満たすには高知 or 柏で実取得確認）。確信度: 60%。
- 柏 形式B の `コッタ （031001）` パース: 全角/半角括弧・全角スペース揺れ。誤拾い回避のためカード内キャプション `<p>` に限定する必要。
- description の PII: 自由文に氏名・電話が混入しうる。`_redact_pii` は電話/メールのみで**氏名は伏字化しない**（層C と同論点）。

---

### 層F: LLM抽出（groq_provider tool schema/プロンプト + adapter マッピング）

**現状**（**パスは `src/data_collector/llm/...`**。タスク記載の `adapters/llm/` は誤り。確認済み）
- 単頭 `ANIMAL_EXTRACTION_TOOL`（`llm/providers/groq_provider.py`）: species/sex/age/color/size/shelter_date/location/phone/image_urls の**9項目のみ**、全9が required。breed/name/description/management_number は皆無。
- 単頭プロンプト `EXTRACTION_SYSTEM_PROMPT`: 9項目の指示のみ。breed は「品種名から推定」（ルール1）で species 推定に既出。
- MULTI `MULTI_ANIMAL_EXTRACTION_TOOL`: item に **`management_number` と `features` を既に持つ**が、両方 required 外（required は同9項目）。breed/name は無い。MULTI プロンプトは「2. 管理番号(management_number)」を**既に指示**（品種/仮名/性格は無し）。
- マッピング `LlmAdapter.extract_animal_details`（`llm/adapter.py:138-151`）: `fields.get` で9項目のみ拾い新4フィールドを破棄。
- **複数頭経路 `_expand_multi_animal_pdf`（adapter.py:220-234）**: 同9項目のみマッピングし、**スキーマに既にある `management_number`/`features` の値すら RawAnimalData に渡していない（現状ドロップ＝バグ）**（確認済み）。

**必要変更**
- 単頭 tool の properties に4項目追加（**required には入れない**）+ プロンプトに項目追記。MULTI は management_number 既存なので breed/name/features を追記。
- マッピングは `fields.get(key, "")` で4項目を RawAnimalData に渡す。MULTI ドロップ修正（management_number/features を渡し始める）。
- 検証 `validate_extraction` は species/shelter_date のみ必須なので**追加不要**。

**リスク**
- **★命名不整合（最大の論点）**: LLM/複数 rule-based は性格・特徴を **`features`** と呼ぶが、本spec/DB/ドメインは **`description`**。RawAnimalData を `description` に統一するなら、LLM/既存 adapter のマッピングで `features→description` 変換が必要。domain層と連動する判断 → design で決定（後述）。
- MULTI ドロップ修正で**現状ロスしていた値が初めて流れる**ため、受け皿(B)→normalizer(C) が先行している前提でのみ配線する（スライス順序の制約）。
- required を増やすと Groq の `tool_use_failed` 多発の温床。新フィールドは required 外を厳守。
- name/description の自由文抽出は幻覚リスク。「ページに無ければ空文字」指示を新項目にも明示適用。

---

### 層G/H/I: 公開API + q検索

**現状**（確認済み）
- `AnimalPublic`（`infrastructure/api/schemas.py:35-51`）に4フィールド無し。`model_config = ConfigDict(from_attributes=True)`（53）済 → ORMにカラムを足せば `model_validate` が自動で拾う。`ArchivedAnimalPublic`（114-）は別途複製。
- routes: `list_animals`（56-）が `list_animals_orm`（125-138）→ `AnimalPublic.model_validate`（141）。`get_animal`（180-185）も同様。q パラメータ（75-79）は `description="...species/color/size/location/prefecture を OR 部分一致"`、`max_length=100`。q はそのまま repository に渡るだけ（ルート側に検索フィールド列挙なし）。
- q OR句は repository に **2箇所重複**: `list_animals`（285-294）と **公開APIが使う `list_animals_orm`（373-382）**。両方とも `or_(species/color/size/location/prefecture .ilike(keyword, escape="\\"))`、`keyword = f"%{_escape_like(q)}%"`。`_escape_like`（20-28）が `\ % _` をエスケープ。

**必要変更**
- `schemas.py`: AnimalPublic に `breed/name/description/management_number: str|None = None` を4つ追加（拡張フィールドブロック付近）。
- `repository.py`: **両OR句**（285-294 / 373-382）に `Animal.breed.ilike(...)` / `Animal.name.ilike(...)` / `Animal.description.ilike(...)` を追加。**management_number は検索対象に含めない**（AC4.2 が breed/name/description のみ指定。迷子同定用途で全文検索ノイズになる）。`_escape_like`+`escape="\\"` を流用。
- `routes.py`: q の description 文言を「.../breed/name/description を OR 部分一致」に更新（ロジック変更なし、`max_length=100` 据え置き）。

**リスク**
- OR句2箇所の片方だけ更新すると検索挙動が経路で食い違う。**両方同時更新必須**（DRY化は本spec外）。
- management_number を OR に入れない点を厳守。
- スキーマだけ先行追加して ORM 未追加だと、from_attributes は欠落属性で None フォールバックする想定（pydantic v2）だが、層スライス時は **ORM→schema を必ずペアで**進める。確信度: from_attributes の欠落フォールバック挙動 85%（要 design で確認）。
- description（Text）への ilike はインデックス無しフルスキャン。現状件数規模では問題ないが将来課題（本spec では対応不要）。

---

### 層J/K: フロントエンド

**現状**（確認済み）
- 型 `frontend/types/animal.ts`: `AnimalPublic`（9-37）。任意は `color: string | null;`（`?:` ではなく `| null`）。各フィールドに JSDoc。`ArchivedAnimalPublic`（43-65）は**型を共有せず手動複製**。
- `AnimalCard.tsx`: 見出し `<h3>`（59-60）が `animal.species`/`animal.sex` を表示。任意は `{animal.color && (<div><dt>毛色</dt><dd>{animal.color}</dd></div>)}`（70-75）の条件表示。dl は `grid grid-cols-2`（65）、location は `col-span-2`（86）。
- `AnimalDetailClient.tsx`: h1（97-98）が `animal.species` のみ。詳細 dl（129-）に color/size 条件表示（145-157）。description（自由文/複数行）向け段落要素は**未存在**。連絡先は `ContactInfo`（15）。
- API クライアント `lib/animals.ts`: `fetchAnimals` は `res.json()`（38）をそのまま返す（フィールド毎マッピング無し）→ **型とAPIに足せば自動透過**。`buildQuery`（10-22）に品種等の専用クエリ追加は不要（q検索はバックエンド側）。

**必要変更**
- 型に4フィールドを `string | null` + JSDoc で追加（ArchivedAnimalPublic にも揃えるか判断）。
- `AnimalCard.tsx`: 見出し付近に name/breed（条件表示）。description/management_number はカードに出さない。
- `AnimalDetailClient.tsx`: 詳細 dl に breed/management_number（color/size と同形）。description は dl の外に `whitespace-pre-line` の段落セクションで表示。全て None で非描画。

**踏襲する既存パターン**
- 任意は `| null`（`undefined` 不可）。条件表示は `{animal.field && (...)}` で欠損時 div ごと非描画 → レイアウト不変（AC5.4）。
- `lib/animals.ts` はマッピング追加不要。

**リスク**
- `ArchivedAnimalPublic` は型を共有せず手動複製。AnimalPublic だけ追加して放置すると、ArchivedAnimalCard へ渡す箇所で型不整合になりうる。両方更新するか extends にリファクタするか design で判断。
- description は **XSS 注意**: `dangerouslySetInnerHTML` を使わずテキストノード `{animal.description}` で描画。`whitespace-pre-line` で改行保持は可だが HTML 注入は不可。
- 全 mockAnimal（AnimalCard.test / AnimalDetailClient.test / AnimalCard.a11y.test / ArchivedAnimalCard.test）を型追加と**同一コミット**で更新しないと strict 型でテストがコンパイル落ち。
- 見出しを name 主体に変えると既存見出しテストの期待値修正が必要（AnimalDetailClient.test の `name:'柴犬'`、AnimalCard.test の `/犬の男の子/` 等）。a11y 見出し階層にも波及。

---

## 3. スライス実装戦略

要件 AC6.2 の「breed 先行でも他3フィールド未配線でエラーなし」を成立させる前提は **B層（Raw=default ""/ Animal=default None）が最初に入ること**。これにより未配線フィールドが None でも収集・保存・取得・公開が従来どおり成功する。

### Slice 0 — 基盤（空配線・一気通貫）

**目的**: 4フィールドの空配線を全層に通す。値は入らないが、migration → ORM → ドメイン → repository → スキーマ → frontend型 まで None で一周する。

- **含む層**: A（ORM 4カラム + migration）、B（Raw/Animal 4フィールド）、D（repository 3箇所）、G（AnimalPublic 4フィールド）、J（frontend 型 4フィールド + 全 mockAnimal 更新）。
- **値の充填**: なし（normalizer も渡さない＝常に None）。
- **テスト**: `test_animal_model.py`（hasattr+nullable）、`test_migration.py`（expected_columns 追記）、`test_models.py`（Raw/Animal が省略時 None で構築可）、`test_animal_repository.py`（_to_orm/_to_pydantic ラウンドトリップで None 保持）、`test_api_schemas.py`（4フィールド任意）、frontend の型コンパイル。
- **受入基準**: 既存スイート全 Green のまま、4カラム/4フィールドが DB→API→型に存在し None で透過する（AC1.1-1.5, 6.1, 6.4）。
- **リスク**: AnimalArchive の扱い決定（非スコープなら明記）。migration head 取り違え（→ `a7b8c9d0e1f2` で確定済み）。

### Slice 1 — breed（最小・伏字不要でパイプライン疎通確認）

- **含む層**: C（`_cap_text` で breed 正規化、normalize build に1行）、E（基底2ファイル + kochi:305/wakayama:160/sendai の breed 配線、breed潰し群へ FIELD_SELECTORS キー追加で横展開）、F（単頭tool に breed プロパティ+プロンプト1行+マッピング1行）、H（両OR句に `Animal.breed.ilike`）、K（カード見出し下に breed サブテキスト + 詳細 dl に breed 行）。
- **テスト**: normalizer の breed trim/空→None/長さ丸め。アダプター（kochi/wakayama/sendai の fixture HTML → raw.breed が入る）。groq tool が breed を素通し（モック）。repository の `list_animals_orm(q='チワワ')` で breed 一致ヒット。frontend カード/詳細表示 + null 非表示。
- **受入基準**: 代表アダプターで breed に実値が入り（AC3.4）、q='品種名' でヒットし（AC4.2）、カード/詳細に表示され（AC5.1）、name/description/mgmt 未配線でもエラーなし（AC6.2）。
- **リスク**: breed/species 混同（species ロジック不変を厳守、AC3.5）。kochi のラベル実在は未検証 → live test で確認。

### Slice 2 — description（PII伏字 + 詳細段落表示）

- **含む層**: C（`_normalize_description` = `_redact_pii` + 長さ丸め）、E（kashiwa `_features`→description、wakayama 性格等→description）、F（単頭tool に description、MULTI の `features` ドロップ修正 + features→description マッピング統一）、H（両OR句に `Animal.description.ilike`）、K（詳細に `whitespace-pre-line` 段落セクション、XSS安全描画）。
- **テスト**: `_normalize_description` が電話（全角/半角/ハイフン無し10-11桁）・メールを `███` 化、伏字後に丸め、空→None、非PII温存。統合（description に `090-1234-5678` を含む入力 → 出力に含まれない）。repository の `q='人懐っこい'` で description 一致ヒット。frontend で HTML がテキスト描画（`<b>` が要素化されない regression）。
- **受入基準**: description が PII 伏字済みのみ保存・返却（AC2.1/2.5/4.5）、詳細に表示・改行保持（AC5.2）、q で検索可（AC4.2）。
- **リスク**: **`features` vs `description` 命名統一**（design で決定）。**氏名未伏字**の許容範囲を design で明記。MULTI ドロップ修正は受け皿先行が前提。

### Slice 3 — name / management_number

- **含む層**: C（`_cap_text` で name/mgmt、mgmt は PII 非適用）、E（kashiwa 形式B キャプション、sendai h3、nyantomo:name 既存→配線、kochi ラベル追加）、F（単頭tool に name/mgmt、MULTI は mgmt 既存）、H（**name のみ** OR追加、mgmt は応答のみ）、K（カード見出しを name 主体に + 詳細 dl に management_number 行）。
- **テスト**: name/mgmt の trim。q='仮名' で name ヒット、mgmt 値だけ一致する子は q 非ヒット。見出し name 化に伴う既存見出しテストの期待値更新 + name無し→species フォールバック。
- **受入基準**: name/mgmt が表示され（AC5.1/5.3）、name は検索対象・mgmt は応答のみ（AC4.2）。
- **リスク**: 見出し変更で既存テスト/a11y 波及。mgmt の PII 誤伏字（非適用方針で回避）。

### 本番DB migration の集約是非

**結論: Slice 0 に1回の additive nullable migration として集約することを推奨。**

- 4カラムとも nullable・後方互換・`server_default` 不要のため、1 migration にまとめても既存行は NULL で埋まりエラーなし（AC1.4）。本番 Supabase への適用回数を最小化でき、運用リスクが下がる。
- スライスを PR 分割しても、**migration だけは Slice 0 で先に全カラムを入れておく**のが安全。後続 Slice（breed→description→name/mgmt）はコード配線のみで migration を伴わないため、head チェーンの競合や本番への複数回 DDL 適用を避けられる。
- 代替案（フィールドごとに migration を重ねて head チェーンを伸ばす）は、PR を完全独立にできる利点はあるが、本番 DDL を4回打つことになり、additive nullable の利点（1回で安全）を捨てる。**非推奨**。
- ただし「Slice 0 を出す前に breed だけ先に動かしたい」場合は breed のみ migration → 後続で追加 migration、も技術的には可能（全 nullable なので害なし）。運用判断。

---

## 4. 横断リスク

1. **PII（description）— 最大リスク**: `_redact_pii` は電話/メールのみで**氏名は伏字化しない**。requirements AC2.5 の「飼い主・発見者の個人情報」のうち氏名は現状未対応。「電話/メール伏字+長さ丸めに留め、氏名は location 粗粒度化と同じく将来対応」とするか、description で別途氏名対策を入れるかを **design で必ず明記**。フロントは伏字済み前提で描画（バックエンドが契約を保証、AC4.5）+ XSS 回避（テキストノード描画）。
2. **100+ アダプターの配線コスト**: 基底2ファイル（wordpress_list/single_page_table）の RawAnimalData 配線を入れれば、派生は `FIELD_SELECTORS`/`COLUMN_FIELDS` にキー1行で開通する設計。breed 潰し群は20+サイトあるが各1-2行。**一括ではなく段階横展開**（充填率はサイト依存・None 許容で破綻しない）。
3. **本番 migration**: additive nullable 4カラムを Slice 0 で1回。`server_default` 不要、既存行 NULL 埋め。`AnimalArchive` を揃えるかは別判断（アーカイブのコピー実装次第、現状非スコープ寄り・要確認）。
4. **q検索の ILIKE コスト**: description（Text）への ilike はインデックス無しフルスキャン。現状件数では問題なし、将来課題として留意。OR句が repository **2箇所**にある点に注意（両方更新必須）。
5. **既存テストへの影響**: frontend の全 mockAnimal は型追加と同一コミットで更新しないと strict 落ち。見出しを name 主体に変えると既存見出しテスト（AnimalCard/AnimalDetailClient/a11y）の期待値修正が必要。バックエンドは新フィールドが任意なので既存テストは原則無改変で Green 維持（AC6.5）。

---

## 5. 設計フェーズへの申し送り（design.md で決める技術判断）

1. **カラム長の確定**: breed=VARCHAR(50)? name=VARCHAR(100)? management_number=VARCHAR(50)? description=Text。**normalizer の長さ定数と必ず一致**させる（不一致は INSERT 失敗→サイト全損）。
2. **`features` vs `description` の命名統一**: RawAnimalData/AnimalData/DB を `description` に統一する場合、LLM（MULTI の `features`）と既存 rule-based adapter（city_chiba 等が `features` にマッピング）の扱いをどうするか。`features→description` 変換を入れるか、`features` キー自体を `description` にリネームするか。**Slice 2 の前提**。
3. **description の検索対象化（コスト判断）**: q OR に description（Text）を含めるか。AC4.2 は含める指定だが、ilike フルスキャンの将来コストと迷子同定用途の価値のトレードオフ。含める場合のパフォーマンス留意点を明記。
4. **PII 範囲の確定**: description で氏名を伏字化するか（現状 `_redact_pii` は未対応）。「電話/メールのみ + 将来氏名対応」で要件 AC2.5 を満たすとするかを明文化。
5. **frontend 表示の優先順位**: カード見出しを name 主体に変えるか（既存テスト波及あり）、breed をサブテキストに留めるか。description の詳細での配置（dl 外の独立セクション）。management_number の表示位置。
6. **LLM プロンプト追記の文言方針**: 単頭プロンプトに breed/name/description の指示を追加する際、「ページに無ければ空文字」を新項目にも明示。required は増やさない（tool_use_failed 回避）。幻覚リスクの高い name/description の抽出指示の慎重な表現。
7. **AnimalArchive の扱い**: 4カラムをアーカイブにも追加するか（アーカイブのコピー実装が明示列挙か SELECT * かで影響が変わる。要コード確認）。現状は **非スコープ**で整理する是非。
8. **q検索 OR句の DRY 化**: repository 2箇所の重複を本spec で統合するか（本spec外だが、片方更新漏れリスクの観点で言及）。

---

### 確信度メモ（低い箇所）
- kochi の「管理番号」「仮名」ラベルの実HTML存在: **60%**（docstring にはあるが実コード未抽出。live test 必須）。
- AnimalArchive のコピー実装が列を明示列挙か: **70%**（コピー実装の中身を本調査では未読）。
- pydantic v2 from_attributes の欠落属性 None フォールバック: **85%**（スキーマ先行時の安全性。ORM→schema ペア進行を推奨）。
- 上記以外の file:line 参照は実コードで一次確認済み（確信度 95%+）。
