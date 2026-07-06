# 監視・アラート体制

「何が・どこで・どう通知されるか」の全体図。個別の対応手順は [docs/RUNBOOK.md](../RUNBOOK.md)。

## 全体図

```
外形監視      uptime-check.yml (30分毎)
              Cloud Run /health・Vercel トップ・/areas/東京都 → 失敗で Discord

Secret 監視   secret-health.yml (日次 JST9:00)
              Groq / Threads トークンを実呼び出し、401/403 → Discord

収集ラン監視   data-collector.yml 内 _send_run_summary_alert() [__main__.py]
              ├ 失敗率 > 20%              → CRITICAL (Slack/Discord)
              ├ 連続失敗サイト            → WARNING
              ├ ゼロ件回帰 (baseline比較)  → WARNING
              ├ フィールド欠損率ドリフト   → WARNING
              └ auto-fix dispatch 失敗    → WARNING

Workflow 失敗  各 workflow の「Notify Discord on failure」ステップ
```

## 各監視の詳細

### 外形監視（`uptime-check.yml`）

- 3 エンドポイントを curl で HTTP 200 検証、3 回リトライで flap 誤検知を回避
- `/areas/東京都` を含めるのは「トップは 200 なのに SSR サブルートだけ 500」という盲点（PR #229 の /areas 500 事件）の再発検知のため
- 失敗時: Discord 通知 + workflow 自体も failure にする二重ガード

### Secret 失効監視（`secret-health.yml` → `scripts/monitoring/check_secret_health.py`）

- 背景: Groq key が約 6 週間 silent 失効し、SNS 投稿文がフォールバックテンプレに劣化していた事故
- 401/403 のみ失効と判定して通知。5xx / timeout は通知しない（誤報防止）
- 実装は `infrastructure/secret_health.py`

### 収集品質監視（`__main__.py`）

- 閾値は `ONECO_MAX_FAIL_RATIO` / `ONECO_MAX_ZERO_RATIO` で調整可能
- 状態は `data/broken_sites.yaml` / `data/site_baselines.yaml` / `data/field_quality_drift.yaml` に永続化（→ [データフロー](02-data-flow.md)）
- 検知結果は [自己修復ループ](04-self-healing.md) のトリガーにもなる

## 通知チャネル

- `infrastructure/notification_client.py` の `NotificationClient`。webhook 未設定なら自動で no-op
- 環境変数: `SLACK_WEBHOOK_URL` / `DISCORD_WEBHOOK_URL`（GitHub Secrets）

## 補助スクリプト（`scripts/monitoring/`）

- `check_robots.py` — robots.txt 一括確認
- `health_check.sh` / `monitor.sh` — 手動ヘルスチェック
- `scripts/zero_count_audit.py` — 0 件サイトの監査
