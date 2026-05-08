# oneco に貢献する

oneco は全国の自治体保護動物情報を一元化するプロジェクトです。
コード貢献・データ整備・ドキュメント・Issue 報告など、あらゆる形の貢献を歓迎します。

## 貢献の前に

- プロダクトの方向性は [`.kiro/steering/roadmap.md`](.kiro/steering/roadmap.md) を参照してください
- 仕様駆動開発（Kiro）を採用しており、機能仕様は [`.kiro/specs/`](.kiro/specs/) に整備されています

## 開発フロー

### 1. Issue を立てる（または既存 Issue を確認）

- バグ報告: 再現手順、期待動作、実際の動作を明記
- 機能要望: ユーザーストーリー（誰が／何を／なぜ）を明記
- 大きな変更は実装前に Issue で方針合意してください

### 2. ブランチを作成

```bash
git checkout -b feature/short-description
# または
git checkout -b fix/short-description
```

`main` への直接コミットは禁止です。

### 3. テストドリブンで実装

- **テストを先に書く**（Red）→ **実装で通す**（Green）→ **整理する**（Refactor）
- 実装中にテストを変更しないでください
- モックは外部依存（HTTP、LLM API）のみに使用

### 4. ローカルで検証

```bash
# Backend
python3 -m pytest tests/ -q
python3 -m ruff check src/ tests/

# Frontend
cd frontend
npm test
npx tsc --noEmit
npm run build
```

### 5. コミット

- 1 コミット = 1 つの論理的変更
- メッセージは日本語可。`feat:` `fix:` `docs:` `refactor:` などのプレフィックスを推奨
- `--no-verify` で hook をスキップしないでください

### 6. PR を作成

- タイトル: 70 文字以内、日本語可
- 本文: 概要・テスト計画（チェックリスト）を記載
- 関連 Issue を `Closes #N` で紐付け

## サイト追加（コード変更不要）

新しい自治体サイトに対応する場合は [`src/data_collector/config/sites.yaml`](src/data_collector/config/sites.yaml) に設定を追加するだけで動きます（LLM 抽出エンジンが汎用対応）。

```yaml
- name: "○○市 動物愛護センター（収容中）"
  prefecture: "○○県"
  prefecture_code: "01"
  list_url: "https://example.lg.jp/animals"
  list_link_pattern: "a[href*='detail']"  # 任意（CSSセレクター）
  category: "lost"
  requires_js: false  # JS 必須サイトは true
```

追加後、`scripts/monitoring/check_robots.py` で robots.txt 遵守を確認してください。

## 行動規範

このプロジェクトでは [Contributor Covenant](https://www.contributor-covenant.org/version/2/1/code_of_conduct/) を行動規範として採用します。
ハラスメント・差別的言動は許容しません。

## ライセンス

貢献されたコードは [MIT License](LICENSE) の下で公開されます。
