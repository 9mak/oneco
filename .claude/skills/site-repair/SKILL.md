---
name: site-repair
description: oneco の自治体・団体サイト収集で異常(0件検知・品質ドリフト・内容不正疑い・長期0件等)が検知された時に、原因が「adapter側の破損(HTML構造変更)」か「検知ロジック側の誤判定」かを切り分けてTDDで修正する定型フロー。Discord通知やCollector実行ログの内容から対象サイトと異常タイプを自動判断する。
---

# サイト収集異常の調査・修理フロー

自治体・団体サイトの収集は、サイト側のHTML構造変更や検知ロジックの見落としで
継続的に異常が出る。広島県(PR #254, HTML構造変更)・鳥取県(PR #255, 検知ロジック
誤判定)のように原因タイプが異なるため、決め打ちで直しにいかず必ず切り分けてから
着手する。

## いつ使うか

次のいずれかが Discord 通知 / `gh run view <id> --log` / ユーザーの一言
(「失敗してるとこ直して」等、対象未指定でもよい)で確認できた時:

- 件数ゼロ回帰検知
- 長期0件サイト検知
- フィールド品質ドリフト
- 内容不正疑い(content anomaly)
- 特定サイト名を挙げての「動かない/直して」

対象が未指定なら、まず直近の Data Collector 実行ログか Discord 通知から
対象サイトと異常種別を自機で特定する(ユーザーに聞き返さない)。

## 手順

### 1. 対象特定

```bash
gh run list --workflow "Data Collector" --limit 5
gh run view <id> --log | grep -iE "ゼロ回帰|品質ドリフト|内容不正|0件検知|WARNING"
```

該当サイト名・カテゴリ・異常種別をログから確定する。

### 2. 実サイト構造の直接確認

`src/data_collector/config/sites.yaml` から該当サイトの `list_url` を確認し、
実際に取得する(adapterのUser-Agent前提に合わせる)。

```bash
curl -s -A "Mozilla/5.0" "<list_url>" -o /tmp/site.html
```

BeautifulSoup で見出し(h2/h3)・table構造・0件時のプレースホルダ表現を
ダンプして、現在の実サイト構造を把握する。

### 3. adapter コードの前提を確認

`src/data_collector/adapters/rule_based/sites/` 配下の該当ファイルを読み、
どのセレクタ・正規表現・見出し文言・列インデックスに依存しているかを洗い出す。

### 4. 原因タイプの切り分け(最重要ステップ)

adapter を直接実行し、**現在** 実際に何件返すかを確認する。

```bash
PYTHONPATH=src .venv/bin/python -c "
from pathlib import Path
from data_collector.llm.config import SiteConfigLoader
from data_collector.adapters.rule_based.sites.<module> import <AdapterClass>
cfg = [c for c in SiteConfigLoader.load(Path('src/data_collector/config/sites.yaml')).sites if c.name == '<サイト名>'][0]
adapter = <AdapterClass>(cfg)
print(adapter.fetch_animal_list())
"
```

- **adapter が実サイトと矛盾しない正しい件数を返す** →
  検知ロジック側(`zero_count_verifier.py` 等)の誤判定を疑う。
  `_compress_for_judge` のテキスト抽出結果や `verify_zero_count` の各段階を
  直接呼んで、どの段階でどう誤判定しているかを再現する。
- **adapter が実サイトと食い違う件数(0件 or 過不足)を返す** →
  HTML構造変更による adapter 側の破損。セレクタ・正規表現・見出し文言・
  `COLUMN_FIELDS` 等を新しい構造に合わせて直す。

決め打ちで「LLM判定を疑う」「HTML変わったに違いない」と仮説先行で修正に
入らない。必ずこのステップで再現してから着手する。

### 5. TDD で修正

1. 実際に取得したHTML(の該当部分を最小化したfixture)で回帰テストを書く
2. Red確認(既存テストは崩さず、狙ったテストだけ落ちることを確認)
3. 実装
4. Green確認
5. `Animal` / `RawAnimalData` / `AnimalData` / `AnimalArchive` に触れる変更なら
   `.github/pull_request_template.md` のチェックリストと feedback memory
   (silent drop 防止8ルール)に必ず従う

### 6. 実サイトでの再検証

テストが通っただけでは「実サイトでも直ったか」は分からない。修正後のコードを
もう一度、直接実サイトの最新HTMLに対して実行し、期待通りの件数/判定になる
ことを確認する。これを省略すると「テストは緑だが本番はまだ壊れている」を
見逃す。

### 7. 品質ゲート → PR

```bash
.venv/bin/python -m ruff check src/ tests/
.venv/bin/python -m ruff format --check src/ tests/
PYTHONPATH=src .venv/bin/python -m pytest tests/ -q
```

feature branch → 原因と対策を明記したコミット → push → `gh pr create`
(PR本文に実サイトでの実地検証結果と Test plan を含める) → CI通過まで監視。

## 過去の実例

- 広島県 (PR #254): サイトのHTML構造変更で adapter が壊れていた → セレクタ修正
- 鳥取県 (PR #255): adapter 自体は正しく0件を返していたが、空プレースホルダ表
  (ヘッダー行+全セル空行)のテキスト抽出でヘッダー項目名だけが残り、LLM分類が
  「動物が掲載されている」と誤認していた → 検知ロジック側の空表除去処理を追加
