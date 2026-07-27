---
name: new-site-onboarding
description: 新しい自治体・保護団体サイトをoneco のデータ収集対象に追加する(rule-based adapter新規実装)フロー。「このサイトも収集対象に追加して」「新しい自治体を追加」等の依頼で使う。個体識別フィールド(breed/name/management_number/description)のsilent drop予防が最重要。
---

# 新規サイト追加フロー

過去 Slice 0〜4 の段階的ロールアウトや個別サイト対応(識別フィールドの
横展開・修正)を通じて、`Animal`/`RawAnimalData`絡みの新規/変更PRは
**6回連続で silent drop を再発**させた実績がある(PR #171/#173/#176/#177/#180)。
このスキルは同じ再発を防ぐための手順書。

## 手順

### 1. 候補サイトの構造判定

対象サイトの list_url を確認し、どの基底クラスが合うかを判定する:
- `RuleBasedAdapter` (直接継承): 独自パースが必要な特殊構造
- `SinglePageTableAdapter`: 1ページの表形式(`ROW_SELECTOR`/`COLUMN_FIELDS`/
  `SKIP_FIRST_ROW`/`LOCATION_COLUMN`のクラス変数だけで動くTemplate Method。
  `city_kobe.py`が典型例)
- `WordPressListAdapter` / `PlaywrightAdapter`(JS必須) / `PdfAdapter`: 該当構造の場合

`KochiAdapter`(798行)が最も網羅的な参考実装。

### 2. 法的チェック(スクレイピング適法性 L1-L5)

- L1 アクセス間隔: `politeness.RequestThrottle`が自動で効く(明示対応不要)
- L2 User-Agent: `ONECO_USER_AGENT`が自動付与(明示対応不要)
- L3 robots.txt: `RobotsChecker.crawl_delay()`が自動で尊重(明示対応不要)
- L4 画像利用: next.config.tsの解像度/quality抑制で軽微利用化済み(明示対応不要)
- L5 ライセンス表記: `SiteConfig.license`/`terms_url`は`infer_license()`が
  list_urlから自動推定するが、自明でない場合は`sites.yaml`に明示指定する

新規サイト追加時、通常はこれらを個別に実装する必要はなく、`sites.yaml`への
登録だけで自動的に適用される。判定に迷うケースだけ`project_legal_scraping`を参照。

### 3. sites.yaml 登録

- `list_url`, `category`, `prefecture`, `prefecture_code`等を登録
- list_urlのホストが `.jp` / `.okinawa` 以外の場合、
  `frontend/next.config.ts` の `remotePatterns` にも同じホストを追加する
  (`tests/test_image_remote_patterns.py`がこの一致をCIで強制するので、
  漏れると即座にテスト失敗で気づける)

### 4. adapter 実装(silent drop 予防 3 ルール、最重要)

1. **新規adapterテストは`adapter.normalize(raw)`の戻り値`AnimalData`で
   アサーションする**。`raw_data.breed == "..."`のような`RawAnimalData`段階
   だけのチェックでは不十分。模範: `tests/adapters/test_kochi_adapter.py::
   test_full_scraping_flow`(一覧取得→詳細取得→normalize()のend-to-endを通し、
   `animal_data.breed`/`name`/`management_number`まで明示アサート)
2. **`Animal`に新カラムを追加する場合は`AnimalArchive`にも同時追加する**
   (active から消えたテーブルへの後付け移行はできない)
3. **`normalize()`をoverrideする場合、`RawAnimalData`再構築時に全フィールドを
   名前付き引数で明示的に引き継ぐ**。可能なら`_default_normalize`への委譲を使う

0件表示(「収容していません」等の告知文)は`ParsingError`ではなく正常な0件
として扱う設計を踏襲する(既存adapterの慣習)。品種(breed)をspecies列に
誤代入しない等、既存の誤分類回避コメントも参考にする。

### 5. テスト

- `test_kochi_adapter.py::test_full_scraping_flow`を模範に、raw取得→
  detail取得→`normalize()`のend-to-endテストを書く
- `tests/domain/test_normalize_preserves_identity_fields.py`は全adapter
  横断のパラメタライズテストで、`sites/__init__.py`のpkgutil自動import経由で
  registryに登録された新規adapterも自動的にテスト対象になる(構造的
  トリップワイヤ)。個別に追加登録する必要はないが、このテストが落ちたら
  4識別フィールドのいずれかが`normalize()`で欠落している

### 6. 品質ゲート

```bash
.venv/bin/python -m ruff check src/ tests/
.venv/bin/python -m ruff format --check src/ tests/
PYTHONPATH=src .venv/bin/python -m pytest tests/adapters/ tests/domain/test_normalize_preserves_identity_fields.py tests/test_image_remote_patterns.py -v
```

### 7. 初回収集確認

ローカルで実際にadapterを1回動かし、件数・フィールド充足率を目視確認して
からPRを作成する(テストが通るだけでは実サイトでの動作は保証されない)。

## PRチェックリスト

`.github/pull_request_template.md`に個体識別フィールド系の詳細チェック
リストがある。`Animal`/`RawAnimalData`/`AnimalData`/`AnimalArchive`のいずれか
に触れるPRは必ず従う。
