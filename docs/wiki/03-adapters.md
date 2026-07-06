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
        └─ サイト個別 adapter 93ファイル    rule_based/sites/*.py
```

- 1ファイルが複数 site_name（例: 収容犬/収容猫）を登録するため、adapter ファイル数(93) < `sites.yaml` エントリ数(211)
- JS 必須サイト（`requires_js: true`、27サイト）は `PlaywrightFetchMixin` が `_http_get` を override

## registry（`rule_based/registry.py`）

- `SiteAdapterRegistry` が静的 dict で site_name → adapter クラスを管理
- 各サイトモジュールが末尾で `SiteAdapterRegistry.register("site_name", AdapterClass)` を呼ぶ（副作用登録）
- `__main__.py` が `from .adapters.rule_based import sites` で全モジュールを import して登録を発火
- 二重登録は `ValueError`。`coverage_stats()` で rule-based / LLM の進捗を集計

## sites.yaml（`src/data_collector/config/sites.yaml`）

- 211 エントリ / 47都道府県。category 内訳: sheltered 96 / lost 66 / adoption 49
- `default_provider: groq / llama-3.3-70b-versatile`（フォールバック用に保持）

## サイト追加手順

> ⚠️ CONTRIBUTING.md に古い「YAML だけでコード変更不要」という記述があった時期があるが、現在のデフォルトは rule-based であり **adapter コードの実装が必要**。

1. **`config/sites.yaml` にエントリ追加**（name / url / prefecture / category / requires_js 等）
   - ⚠️ 画像ホストが増える場合は `frontend/next.config.ts` の `remotePatterns` にも追加。`tests/test_image_remote_patterns.py` が CI で一致を強制する
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

## politeness

同一ドメインへのリクエストは `adapters/politeness.py` の throttle をドメイン単位で共有し、間隔を空ける。robots.txt の Crawl-delay があればそれを優先。
