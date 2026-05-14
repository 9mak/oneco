# Requirements Document

## Project Description (Input)
ロードマップ Phase 1.5 の「収集オペレーション可視化ダッシュボード」を実装する。`/admin` 配下に認証ゲート付き（Supabase Auth or Basic Auth）でダッシュボードを設置し、運用者がデータ収集の健全性を一目で把握できるようにする。

### 主要パネル
1. サイト別 直近実行ステータス（成功/失敗/スキップ + 最終実行時刻）
2. 県別件数の時系列推移
3. LLM 利用コスト累計（Groq / Anthropic 別）
4. 抽出失敗ランキング（Top 10 サイト）
5. sites.yaml の全 209 サイト一覧と次回実行予定

### データソース
- 既存 PostgreSQL（Supabase）
- `output/animals.json` / `snapshots/latest.json`
- GitHub Actions API（ワークフロー実行履歴）

### 技術スタック
- フロント: Next.js 16 App Router + Tailwind、Recharts でグラフ描画
- バックエンド: FastAPI に `/api/admin/...` を追加

### SLO
- 操作レイテンシ 2s 以内
- 自動更新 30s

### 副次目的
Phase 2 のクラウドファンディング時に「実績ある」と見せる説得材料も兼ねるため、公開可能なメトリクス（累計件数、対応自治体数）は別 URL で OG 画像も出せる構成にしておく。

## Requirements
<!-- Will be generated in /kiro:spec-requirements phase -->
