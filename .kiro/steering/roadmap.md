# oneco - ロードマップ

## Phase 0: MVP基盤（完了）
- [x] FastAPI バックエンド（API、DB、正規化パイプライン）
- [x] Next.js フロントエンド（動物一覧、検索UI）
- [x] 高知県アダプター（ルールベース、特別ルール対応済み）
- [x] PostgreSQL インフラ（Redis は任意化済み。PR #160 で不在でも動作）
- [x] 60件のリアルデータで動作確認

## Phase 1: 四国完成 + AI抽出導入（完了）
- [x] LLMベースの汎用データ抽出エンジン構築
  - ページHTML → Anthropic / Groq → RawAnimalData（構造化出力）
  - サイトごとのアダプター不要、YAML設定のみで新規サイト追加
  - HTML前処理 / Playwright（JS必須サイト）/ PDF抽出 にも対応
- [x] 四国4県の新規サイト対応（環境省リンクページより）
  - 徳島県: douai-tokushima.com（収容中・譲渡犬・譲渡猫）
  - 香川県: 高松市わんにゃん高松、さぬき動物愛護センター、東讃・中讃・西讃・小豆保健所
  - 愛媛県: 愛媛県動物愛護センター（収容中・譲渡）、松山市はぴまるの丘
  - 高知県: 既存ルールベースアダプター稼働中
- [x] 定期実行の仕組み（GitHub Actions cron, 毎日 JST 00:00 自動実行）
- [x] MVP公開（Cloud Run + Vercel + Supabase 本番稼働中）

### Phase 1 で当初想定を超えた成果
- 四国 5サイトに留まらず、**全国 211サイト**まで拡張済（`src/data_collector/config/sites.yaml`）
- ※ 2026-05-15 に抽出方式を **rule-based デフォルト**へ転換（LLM コスト $0 化。LLM は adapter 自己修復の修理工に役割変更）
- `image_hashes` テーブルへの URL ハッシュ蓄積（重複検出基盤）
- フロント: お気に入り、キーワード検索、都道府県別マップ（地方別グリッド）、画像 onError フォールバック

## Phase 1.5: 運用フェーズ（完了 2026-06）
- [x] 収集オペレーション可視化ダッシュボード（`/admin` 認証ゲート）
- [x] トップページ刷新（インタラクティブ日本地図 / ヒートマップ）
- [x] 収集成功率の異常検知 + Slack/Discord 通知（PR #213）
- [x] データ品質チェック（フィールド欠損率ドリフト検知 `data/field_quality_drift.yaml`）
- [x] サイト別タイムアウト個別調整（`sites.yaml` で上書き可）
- [x] robots.txt 遵守の自動チェック（`_apply_robots_policy` + `scripts/monitoring/check_robots.py`）

## Phase 1.6: 手離れ運用（現在地、2026-07）
- [x] adapter 自己修復ループ（検知 → Groq 修復 PR → auto-merge。段階リリース中）
- [x] 外形監視 / Secret 失効監視 / 収集品質アラート（Discord）
- [ ] 自己修復の本番化判断（`ONECO_AUTO_FIX_ENABLED` 有効化）
- 並行: 集客 Phase 4 = SNS（Threads 自動投稿は dry_run 稼働中）

## Phase 2: 資金調達 + 認知拡大
- [ ] OSS公開準備（README整備、CONTRIBUTING、ライセンス、セットアップ手順）
- [ ] クラウドファンディング実施（READYFOR / CAMPFIRE）
  - 「全国の保護動物情報を一つに。殺処分ゼロへ」
  - 説得材料: Phase 1.5 のダッシュボード + 全国マップ実績
- [ ] OSS公開 + コミュニティ形成
  - 動物愛護 × エンジニアの仲間を集める
- [ ] コンテスト / ハッカソン出展
- [ ] メディア露出（動物愛護系、テック系）

## Phase 3: 公的機関連携
- [ ] 環境省・自治体への提案
  - 「実績あります」で持ち込む（Phase 2の成果が根拠）
- [ ] 助成金 / 公的資金の獲得
- [ ] 自治体との正式データ連携

## Phase 4: SaaS化 + スケール
- [ ] 自治体向け公式プラットフォーム提供
  - 自治体は「登録許可」を出すだけ
  - AI自動登録でデータ収集・更新
  - 統一サイト構造で検索性向上
- [ ] 協力者採用（運営委託）
- [ ] 全国展開 → 海外展開の検討

## 技術方針

### データ抽出アーキテクチャ（2026-05-15 改訂）
```
[一時期] LLM 抽出エンジン（Groq/YAML設定のみ）を全面採用
  └─ 課題: API コスト・レート制限・抽出品質の揺れ

[現在] rule-based をデフォルトに再転換
  └─ サイト別 adapter（共通基底 WordPressList/SinglePageTable/Playwright/PdfTable で実装コスト圧縮）
  └─ LLM (Groq) は「修理工」: 壊れた adapter を自己修復ループで自動修正
  └─ LLM 抽出はフォールバックとして温存（sites.yaml で extraction: llm 指定可）
```

詳細は `docs/wiki/03-adapters.md` / `docs/wiki/04-self-healing.md`。

---
_created_at: 2026-03-18_
_last_updated: 2026-07-06 (Phase 1.5 完了反映、Phase 1.6 手離れ運用を現在地に、抽出方針を rule-based 改訂に更新)_
