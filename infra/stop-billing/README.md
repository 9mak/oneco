# stop-billing — 予算超過時の課金自動遮断

月額予算（¥500）の100%到達時に oneco-app プロジェクトの課金を自動解除する Cloud Function。

## 経緯

- 2026-07-30 に GCP 無料トライアル（2026-04-30〜07-30、90日）が期限切れになり、課金無効化で oneco-api が503停止
- 2026-08-02 にフルアカウント化して復旧。再発防止と費用上限のためこの仕組みを導入

## 構成

```
Cloud Billing 予算 (oneco-monthly-cap-500, ¥500/月, 閾値50/90/100%)
  → Pub/Sub topic: budget-alerts (oneco-app)
  → Cloud Function gen2: stop-billing (asia-northeast1)
  → costAmount >= budgetAmount のとき projects.updateBillingInfo で課金解除
```

- 閾値50/90/100%で請求先アカウント管理者宛にメール通知も飛ぶ（GCP標準機能）
- 実行SA: `462233676125-compute@developer.gserviceaccount.com`（`roles/billing.projectManager` を oneco-app に付与済み）

## デプロイ

```bash
gcloud functions deploy stop-billing \
  --gen2 --project=oneco-app --region=asia-northeast1 \
  --runtime=python312 --trigger-topic=budget-alerts \
  --entry-point=stop_billing --source=infra/stop-billing \
  --memory=512Mi --cpu=1 --max-instances=3 --no-allow-unauthenticated
```

## 注意

- 予算のコスト集計には数時間〜1日程度の反映遅延があり、¥500ちょうどでは止まらない（多少の超過はありうる）
- 遮断が発動するとサイト全体（oneco-api）が停止する。復旧は請求コンソールから oneco-app に課金アカウントを再リンクする
- 課金解除パス（updateBillingInfo）は本番発火が初回実行になる（テストすると実際にサイトが落ちるため未検証）。予算内メッセージでの実行成功（HTTP 200）と IAM 権限付与までは検証済み
- 予算上限の変更: `gcloud billing budgets list --billing-account=01F439-B06BD4-15DEF1` でID確認後、`gcloud billing budgets update <ID> --budget-amount=1000JPY`
