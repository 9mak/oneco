# Research & Design Decisions

---
**Purpose**: data-collector の発見フェーズで得られた調査結果、アーキテクチャ検討、技術選定の根拠を記録。

**Usage**:
- 技術調査の活動と結果をログ
- design.md に記載するには詳細すぎるトレードオフを文書化
- 将来の監査や再利用のための参照と証跡提供
---

## Summary
- **Feature**: `data-collector`
- **Discovery Scope**: New Feature (greenfield)
- **Key Findings**:
  - BeautifulSoup + requests の組み合わせがシンプルな自治体サイトスクレイピングに最適（Scrapy は過剰）
  - Pydantic による型安全なデータモデルとバリデーションが正規化要件に適合
  - GitHub Actions の cron スケジューラーが無料枠内で毎日実行要件を満たす
  - Adapter パターンにより自治体ごとの差異を吸収し、拡張性を確保

## Research Log

### Web スクレイピングライブラリの選定

**Context**: 自治体サイトから HTML を取得・解析し、保護動物情報を抽出する技術スタックの決定

**Sources Consulted**:
- [Scrapy vs. Beautiful Soup: A Comparison](https://oxylabs.io/blog/scrapy-vs-beautifulsoup)
- [Best Web Scraping Tools in 2026](https://scrapfly.io/blog/posts/best-web-scraping-tools-in-2026)
- [Scrapy vs BeautifulSoup: Which Is Better For You?](https://www.zenrows.com/blog/scrapy-vs-beautifulsoup)

**Findings**:
- **BeautifulSoup**: シンプルな HTML パーサー。小〜中規模プロジェクトに最適。学習コストが低く、単一ページまたは少数ページのスクレイピングに向く
- **Scrapy**: 大規模クロール向けフレームワーク。非同期リクエストをサポートし、複数ページを並行処理可能。Production レベルの大規模スクレイピングに適する
- **ハイブリッドアプローチ**: Scrapy のコールバック内で BeautifulSoup を使用する組み合わせも可能

**Implications**:
- 高知県の自治体サイトは単一または少数のページからデータ取得するため、BeautifulSoup + requests で十分
- 将来的に都道府県が増えても、アダプター単位での並行実行で対応可能（Scrapy のオーバーヘッド不要）
- シンプルな技術スタックにより保守性とチーム参入障壁を低減

### データバリデーション・型安全性の確保

**Context**: 自治体間で異なる形式のデータを統一スキーマに正規化し、型安全性を保証する仕組み

**Sources Consulted**:
- [Type Safety in Python: Pydantic vs. Data Classes](https://www.speakeasy.com/blog/pydantic-vs-dataclasses)
- [Pydantic: A Guide With Practical Examples](https://www.datacamp.com/tutorial/pydantic)
- [Pydantic Validation Documentation](https://docs.pydantic.dev/latest/)

**Findings**:
- **Pydantic**: ランタイム型検証、自動バリデーション、JSON シリアライゼーション、Rust ベースの高速パフォーマンス
- **Dataclasses**: シンプルなデータコンテナ。ランタイムバリデーションなし
- **Pydantic の優位性**: 外部データ（自治体サイトの HTML から抽出）の検証、型変換、エラーハンドリングが組み込み

**Implications**:
- Pydantic BaseModel を使用して正規化スキーマを定義
- フィールドバリデーター（field_validator）で性別・動物種別の正規化ロジックを実装
- 必須フィールド（動物種別、収容日、元ページURL）の欠損を自動検出
- animal-repository への出力 JSON スキーマを厳密に型安全化

### アダプターパターンの適用

**Context**: 自治体ごとに異なるサイト構造に対応し、将来的な拡張を容易にするアーキテクチャパターン

**Sources Consulted**:
- [Adapter Pattern in Python](https://www.geeksforgeeks.org/python/adapter-method-python-design-patterns/)
- [Design Patterns in Python](https://refactoring.guru/design-patterns/python)
- [Architecture Patterns with Python](https://www.oreilly.com/library/view/architecture-patterns-with/9781492052197/)

**Findings**:
- Adapter パターン: 互換性のないインターフェースを統一するデザインパターン。データパイプラインでの再利用性向上
- Python での実装: ABC（Abstract Base Class）を使用した抽象インターフェース定義、具象アダプタークラスでの実装
- ドメイン駆動設計との整合: アダプターは特定技術（自治体サイト）への依存を抽象化

**Implications**:
- `MunicipalityAdapter` 抽象基底クラスを定義（fetchAnimalList, extractAnimalDetails, normalize メソッド）
- `KochiAdapter` として高知県用の具象実装を提供
- 新規自治体追加時は既存コードに影響なく新アダプタークラスを追加するだけ
- アダプターのエラーは分離され、他自治体の処理を継続

### スケジューリング戦略

**Context**: 毎日1回の自動実行と手動実行の両立、コスト効率的な実装方法

**Sources Consulted**:
- [How to Run Scheduled Cron Jobs in GitHub Workflows](https://dylanbritz.dev/writing/scheduled-cron-jobs-github/)
- [Schedule Cron Jobs With GitHub Actions](https://betterprogramming.pub/schedule-cron-jobs-with-github-actions-d279e8519cec)
- [How to schedule Python scripts with GitHub Actions](https://www.python-engineer.com/posts/run-python-github-actions/)

**Findings**:
- **GitHub Actions**: 無料（パブリックリポジトリ）、最小5分間隔、UTC タイムゾーン、シークレット環境変数サポート
- **Traditional Cron**: サーバー運用が必要、柔軟な間隔設定、ローカルタイムゾーン
- **GitHub Actions の制約**: プライベートリポジトリでも月2,000分の無料枠あり

**Implications**:
- GitHub Actions の `schedule` トリガーで毎日実行（例: `0 15 * * *` で日本時間深夜0時に相当）
- 手動実行は `workflow_dispatch` トリガーで対応
- サーバー運用コストゼロ、インフラ管理不要
- 将来的にスケールする場合は専用サーバーへ移行可能（コードの互換性維持）

### 差分検知戦略

**Context**: 前回収集時からの変更を効率的に検出し、新規・更新・削除を識別

**Sources Consulted**:
- 内部設計判断（外部ソースなし）

**Findings**:
- スナップショット比較: 前回の収集結果 JSON を保持し、今回結果と比較
- ユニークキー: 元ページ URL を個体識別子として使用（自治体が変更しない限り安定）
- 差分分類: 新規（未登録URL）、更新（既存URLの情報変更）、削除候補（今回リストに不在）

**Implications**:
- ファイルベーススナップショット（`snapshots/latest.json`）として保存
- 差分検知は単純な辞書比較で実装可能（パフォーマンス問題なし）
- 通知システム（notification-manager）への差分情報提供が容易

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| Adapter Pattern | 自治体ごとの抽象インターフェース + 具象実装 | 拡張性高、既存コード影響なし、エラー分離 | アダプター数増加時の管理コスト | Requirements 3 に完全適合 |
| Monolithic Scraper | 単一スクレイパーで条件分岐 | 実装が単純 | 拡張困難、自治体間の結合度高 | 要件「自治体追加の容易性」に不適合 |
| Plugin System | 動的ロード可能なプラグイン | 最大の拡張性 | 複雑度高、デバッグ困難 | 現時点では過剰設計 |

**選定**: Adapter Pattern（要件と将来性のバランス最適）

## Design Decisions

### Decision: BeautifulSoup + requests によるスクレイピング

**Context**: 自治体サイトから HTML を取得・解析する技術選定

**Alternatives Considered**:
1. **Scrapy** — 大規模クロールフレームワーク、非同期処理、並行リクエスト
2. **BeautifulSoup + requests** — シンプルな HTML パーサー + HTTP ライブラリ
3. **Selenium** — ブラウザ自動化、JavaScript レンダリング対応

**Selected Approach**: BeautifulSoup + requests

**Rationale**:
- 高知県の自治体サイトは静的 HTML が中心（JavaScript レンダリング不要の可能性高）
- 毎日1回の実行頻度では Scrapy の非同期処理メリットが小さい
- チームの学習コストとメンテナンス性を重視
- 将来的に JavaScript 必要な自治体が出た場合、Selenium をアダプター単位で追加可能

**Trade-offs**:
- ✅ Benefits: シンプル、学習容易、依存少ない、デバッグ容易
- ⚠️ Compromises: 大規模並行処理には不向き（現時点で不要）

**Follow-up**: 高知県サイト調査で JavaScript 必要性を実装時に確認

### Decision: Pydantic による型安全なデータモデル

**Context**: 自治体間で異なる形式を統一スキーマに正規化し、型安全性を保証

**Alternatives Considered**:
1. **Dataclasses** — 型ヒント付きデータコンテナ、バリデーションなし
2. **Pydantic** — ランタイム型検証、自動バリデーション、JSON シリアライゼーション
3. **手動検証** — if 文による条件分岐

**Selected Approach**: Pydantic BaseModel

**Rationale**:
- 外部データ（自治体サイト）の信頼性が低く、ランタイムバリデーション必須
- 正規化ロジック（性別・動物種別の3値化）を field_validator で宣言的に記述可能
- animal-repository への出力 JSON スキーマを厳密に型安全化
- TypeScript と同等の型安全性を Python で実現（steering の Type Safety 原則に準拠）

**Trade-offs**:
- ✅ Benefits: 型安全、自動検証、エラーメッセージ明確、JSON シリアライゼーション組み込み
- ⚠️ Compromises: 若干のパフォーマンスオーバーヘッド（Rust 実装により軽微）

**Follow-up**: なし（確定）

### Decision: GitHub Actions によるスケジューリング

**Context**: 毎日1回の自動実行と手動実行の両立

**Alternatives Considered**:
1. **GitHub Actions** — 無料、サーバーレス、cron 構文
2. **Traditional Cron + VPS** — 柔軟、サーバー運用必要
3. **AWS Lambda + EventBridge** — スケーラブル、AWS 依存、コスト発生

**Selected Approach**: GitHub Actions (`schedule` + `workflow_dispatch`)

**Rationale**:
- MVP フェーズでは無料インフラを最大活用
- サーバー運用コストゼロ、インフラ管理不要
- 毎日1回の実行頻度では Lambda のコールドスタート問題も GitHub Actions の5分制約も影響なし
- リポジトリと CI/CD が統合され、デプロイが簡素化

**Trade-offs**:
- ✅ Benefits: 無料、管理不要、GitHub との統合
- ⚠️ Compromises: 最小5分間隔、UTC のみ、GitHub 依存

**Follow-up**: スケール時は専用サーバーまたは Lambda へ移行検討（コード互換性維持）

### Decision: ファイルベーススナップショット差分検知

**Context**: 前回収集時からの変更を検出する仕組み

**Alternatives Considered**:
1. **ファイルベーススナップショット** — JSON ファイルに前回結果保存、Git 管理
2. **データベース比較** — animal-repository DB と直接比較
3. **ハッシュベース** — 各個体のハッシュ値を計算して比較

**Selected Approach**: ファイルベーススナップショット（`snapshots/latest.json`）

**Rationale**:
- data-collector は animal-repository への依存を最小化（疎結合）
- ファイルは Git で履歴追跡可能、デバッグ容易
- 高知県の収容動物数は多くても数十〜数百件程度（ファイルサイズ問題なし）
- 実装がシンプル（辞書比較のみ）

**Trade-offs**:
- ✅ Benefits: シンプル、DB 不要、Git 管理可能、デバッグ容易
- ⚠️ Compromises: 大規模データには不向き（現時点で不要）

**Follow-up**: なし（確定）

## Risks & Mitigations

- **Risk 1: 自治体サイトの構造変更** — Mitigation: ページ構造検証ロジックを実装し、変更検知時に即座通知（Requirement 1-5）
- **Risk 2: JavaScript レンダリングが必要なサイト** — Mitigation: アダプターパターンにより Selenium 統合を個別対応可能、BeautifulSoup との共存
- **Risk 3: スクレイピング頻度制限・ブロック** — Mitigation: 毎日1回の低頻度実行、User-Agent 設定、リトライ間隔を適切に設定
- **Risk 4: GitHub Actions の実行時間制限（6時間）** — Mitigation: 高知県単独では数分で完了見込み、都道府県追加時も並行実行で対応可能

## References

- [Scrapy vs. Beautiful Soup Comparison](https://oxylabs.io/blog/scrapy-vs-beautifulsoup)
- [Best Web Scraping Tools in 2026](https://scrapfly.io/blog/posts/best-web-scraping-tools-in-2026)
- [Type Safety in Python: Pydantic vs. Data Classes](https://www.speakeasy.com/blog/pydantic-vs-dataclasses)
- [Pydantic Validation Documentation](https://docs.pydantic.dev/latest/)
- [Adapter Pattern in Python](https://www.geeksforgeeks.org/python/adapter-method-python-design-patterns/)
- [Schedule Cron Jobs With GitHub Actions](https://betterprogramming.pub/schedule-cron-jobs-with-github-actions-d279e8519cec)
- [How to schedule Python scripts with GitHub Actions](https://www.python-engineer.com/posts/run-python-github-actions/)

---
_研究完了日: 2026-01-06_
