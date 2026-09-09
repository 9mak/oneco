# Adapter アーキテクチャ

サイトごとのスクレイピングは **rule-based adapter**（デフォルト）で行う。LLM 抽出は `sites.yaml` の `default_extraction: rule-based` によりフォールバック扱い（LLM = Groq は [自己修復](04-self-healing.md) の修理工として使う）。

## クラス階層

```
MunicipalityAdapter (ABC)                  adapters/municipality_adapter.py
└─ RuleBasedAdapter                        adapters/rule_based/base.py
   │   _http_get (politeness throttle付き) / _absolute_url
   │   _normalize_phone / _filter_image_urls / _default_normalize
   ├─ SinglePageTableAdapter               rule_based/single_page_table.py
   ├─ WordPressListAdapter                 rule_based/wordpress_list.py
   ├─ PdfTableAdapter (pdfplumber)         rule_based/pdf_table.py
   └─ + PlaywrightFetchMixin (JS必須サイト) rule_based/playwright.py
        ├─ サイト個別 adapter (bespoke Python)   rule_based/sites/*.py
        └─ GenericAdapter (YAML spec 駆動, T405) rule_based/generic_adapter.py
             └─ config/site_specs/*.yaml
```

- 1ファイルが複数 site_name（例: 収容犬/収容猫）を登録するため、adapter ファイル数 < `sites.yaml` エントリ数(213)
- CSS セレクタ + ラベル辞書 + 軽い後処理だけで完結する「declarative only」なサイトは
  Python モジュールを書かず `config/site_specs/<slug>.yaml` だけで済ませられる
  (`GenericAdapter`、詳細は下記「spec ファイルでサイトを追加する」節)
- JS 必須サイト（`requires_js: true`、3サイト）は `PlaywrightFetchMixin` が `_http_get` を override

## registry（`rule_based/registry.py`）

- `SiteAdapterRegistry` が静的 dict で site_name → adapter クラスを管理
- 各サイトモジュールが末尾で `SiteAdapterRegistry.register("site_name", AdapterClass)` を呼ぶ（副作用登録）
- `__main__.py` が `from .adapters.rule_based import sites` で全モジュールを import して登録を発火
- 二重登録は `ValueError`。bespoke Python adapter と GenericAdapter (spec) が同名で
  衝突した場合は **bespoke が優先**され、spec 側は WARNING ログを出してスキップする
  (`sites/__init__.py` が bespoke モジュール群を先に import してから spec を読み込む順序で保証)
- `coverage_stats()` で rule-based / LLM の進捗を集計

## spec ファイルでサイトを追加する（GenericAdapter, T405）

CSS セレクタ + ラベル辞書 + 軽い後処理だけで完結する「declarative only」なサイト
（一覧→詳細で dt/dd・th/td を CSS セレクタで抜くだけ、または常に 0 件を返す
案内/ハブページ）は、Python ファイルを新規作成せず `config/site_specs/<slug>.yaml`
だけで rule-based 化できる。

### いつ GenericAdapter を使うべきか

- 一覧→詳細の抽出が `LIST_LINK_SELECTOR` + `FIELD_SELECTORS`（label 指定）だけで
  完結する（`WordPressListAdapter._extract_by_label` の label/selector 指定を
  超えるカスタム DOM 走査が要らない）
- species/phone/location の補完が `generic_transforms.py` の既存変換
  (`species_from_list_url_dog_cat` / `weight_to_size` / `phone_fallback` /
  `phone_fallback_if_invalid` / `location_fallback`) で表現できる
- サイトが「動物一覧を持たない案内・ハブページ」で常に 0 件 (`always_empty: true`)
  か、案内ページかどうかをタイトル/見出しの正規表現で判定できる
  (`empty_state_patterns`)

上記に当てはまらない複雑なパース（PDF、独自のテーブル走査、JS 必須の複雑な DOM 操作
等）は従来どおり `sites/<site>.py` を書く。

### spec の書き方（1 サイト分の最小例）

```yaml
# src/data_collector/config/site_specs/example_city.yaml
names:
  - "例市動物愛護センター（譲渡犬）"
mode: list_detail  # list_detail | table_horizontal | table_vertical
list_link_selector: "a[href*='/animal/']"
image_selector: "img"
field_selectors:
  species:
    label: "種類"
  sex:
    label: "性別"
  shelter_date:
    label: ["収容日", "保護日"]  # tuple 指定は OR 検索 (完全一致優先→部分一致)
  phone:
    label: "連絡先"
species:
  strategy: from_url  # literal | from_url | from_site_name | none
postprocess:
  - "phone_fallback:012-345-6789"  # 引数は `:` 区切り
```

- `names` は複数指定でき、同一テンプレートを共有する sites.yaml の複数エントリを
  1 spec で束ねられる（例: `douaicenter.yaml` は旭川市あにまある 8 サイトを 1 つの
  spec にまとめている）
- `mode: table_horizontal` / `table_vertical` は `SinglePageTableAdapter` ベース
  (`row_selector` / `header_fields` or `column_fields` / `skip_first_row` 等)
- `always_empty: true` または `empty_state_patterns: [...]` を指定すると、
  「動物一覧を持たない案内・ハブページ」を常に 0 件として扱う
  (`fetch_animal_list` を GenericAdapter 側で自動オーバーライドする)
- `sites.yaml` の `fields` / `phone` / `requires_js` はこれまでどおり sites.yaml
  側に残す（spec は「DOM からどう抜くか」だけを持つ）

### scaffold script

```bash
uv run python scripts/new_site_spec.py <slug> <list_url> \
  --name "例市動物愛護センター（譲渡犬）"
```

`config/site_specs/<slug>.yaml` の雛形を生成する（best-effort: 一覧リンクの
候補セレクタ、テーブルならヘッダ文字列を検出して埋める。必ず実ページを見て
手直しすること）。

### テスト

`tests/adapters/rule_based/sites/test_<site>.py` で
`SiteAdapterRegistry.get("サイト名")` からクラスを取得し、`adapter.normalize(raw)`
の戻り値でアサーションする（bespoke adapter と同じ方針）。

## sites.yaml（`src/data_collector/config/sites.yaml`）

- 213 エントリ / 47都道府県。category 内訳: sheltered 96 / lost 67 / adoption 50
- `default_provider: groq / openai/gpt-oss-120b`（フォールバック用に保持）

## サイト追加手順

> ⚠️ CONTRIBUTING.md に古い「YAML だけでコード変更不要」という記述があった時期があるが、現在のデフォルトは rule-based であり **adapter コードの実装が必要**。

1. **`config/sites.yaml` にエントリ追加**（name / url / prefecture / category / requires_js 等）
   - ⚠️ 画像ホストが増える場合は `frontend/next.config.ts` の `remotePatterns` にも追加。`tests/test_image_remote_patterns.py` が CI で一致を強制する。`python3 scripts/sync_remote_patterns.py --fix` で不足ホストを自動追記できる (T104)
2. **robots.txt を確認**: `python scripts/monitoring/check_robots.py`
3. **サイト構造に合う基底クラスを選ぶ**
   - 1ページに table でまとまっている → `SinglePageTableAdapter`
   - WordPress の記事一覧形式 → `WordPressListAdapter`
   - PDF 掲載 → `PdfTableAdapter`
   - JS レンダリング必須 → 上記 + `PlaywrightFetchMixin`
4. **`adapters/rule_based/sites/<site>.py` を実装**し、末尾で `SiteAdapterRegistry.register()` を呼ぶ
   - 命名例: `city_kawasaki.py` / `pref_osaka.py`
   - `normalize()` を override する場合、`RawAnimalData` 再構築時に**全フィールドを名前付き引数で明示的に引き継ぐ**（可能なら `_default_normalize` に委譲）
5. **end-to-end テストを書く**（`tests/adapters/`）
   - **必須**: `adapter.normalize(raw)` の戻り値 `AnimalData` でアサーションする（`raw.breed == ...` だけでは不十分）。模範: `tests/adapters/test_kochi_adapter.py::test_full_scraping_flow`
6. **ローカルで動作確認**: `PYTHONPATH=src .venv/bin/python -m pytest tests/adapters/test_<site>.py`
7. live 確認は `scripts/adapter_live_test.py` を利用可能

## SinglePageTableAdapter: COLUMN_FIELDS と HEADER_FIELDS の使い分け（T402）

`SinglePageTableAdapter` は 1 ページに複数動物が table/カードで並ぶサイト用の共通基底
（`rule_based/single_page_table.py`）。列 → `RawAnimalData` フィールドの対応付けには
2 通りの方式があり、サイトの実 HTML 構造に合わせて選ぶ。

- **`COLUMN_FIELDS: dict[int, str]`**（列インデックス駆動）
  - 例: `{0: "shelter_date", 3: "sex"}`
  - 列順が固定でヘッダ行が無い/信用できない（`<th>` が無い、装飾用など）サイト向け
  - 列順がサイトごとに変わる同一テンプレートの複数サイトでは、サイトの数だけ
    別の辞書を用意する必要がある（従来の `pref_kagawa` 系など）
- **`HEADER_FIELDS: dict[str | tuple[str, ...], str]`**（ヘッダテキスト駆動）
  - 例: `{"収容日": "shelter_date", ("性別", "性別（推定）"): "sex"}`
  - ヘッダ行 (`<thead>` の `<tr>`、無ければ `<th>` を含む最初の `<tr>`) の**セル文字列**
    から実際の列インデックスをテーブルごとに動的解決する
  - マッチングは `_extract_by_label` と同じ仕様: 完全一致優先 → 部分一致フォールバック、
    `tuple` は OR 検索（複数表記ゆれを 1 エントリで吸収できる）
  - `colspan`/`rowspan` を考慮した実効列オフセットを計算する
  - 1 ページに複数 `<table>` がある場合もテーブル単位で個別解決される（`table id()` で
    キャッシュ）
  - ヘッダ行が見つからない場合は `COLUMN_FIELDS` へフォールバックする。`HEADER_FIELDS`
    がヘッダを解決できず、かつ `COLUMN_FIELDS` も未設定（空辞書）の場合は、そのテーブルの
    行を 0 件として除外し WARNING ログ（サイト名入り）を出す
  - 監査・list_selector_resolution 等で HTTP を発生させずに解決結果を見たい場合は
    `adapter.resolve_header_fields(table_or_soup)` を呼ぶ

**選び方の目安**:
- ヘッダ行にラベル (`<th>種類</th>` 等) があり、それがサイトごと/セクションごとに
  同じ意味で使われている → `HEADER_FIELDS` を優先する（列順が変わっても壊れにくい）
- ヘッダ行が無い、または `<th>` の意味が実データと対応しない（レイアウト用テーブル等）
  → `COLUMN_FIELDS` を使う
- 両方設定した場合、`HEADER_FIELDS` が解決できた列を優先し、`COLUMN_FIELDS` は
  それ以外の列を補う

`extract_animal_details` を独自オーバーライドしている adapter でも、
`self._resolve_and_cache_header_fields(table)` を呼べば `HEADER_FIELDS` の解決結果
(`dict[int, str]`) をそのまま利用できる（`city_kitakyushu.py` / `city_maebashi.py` が実例）。

## politeness

同一ドメインへのリクエストは `adapters/politeness.py` の throttle をドメイン単位で共有し、間隔を空ける。robots.txt の Crawl-delay があればそれを優先。
