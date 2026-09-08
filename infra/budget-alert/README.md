# budget-alert — 予算90%到達時のDiscord通知（T143）

GCP予算（`oneco-monthly-cap-500`, ¥500/月）が **90%到達** したときに Discord へ通知する
Cloud Function。[stop-billing](../stop-billing/README.md)（100%到達で課金を自動解除する）
とは別Functionで、**stop-billingのコード・デプロイ・IAMには一切変更を加えていない**。

## なぜ別Functionか

- stop-billingは「課金を止める」実行系、budget-alertは「早めに気づかせる」通知系で
  責務が違う。同じFunctionに混ぜると、通知ロジックの変更が課金解除ロジックに影響する
  リスクが生まれる（stop-billingは本番未検証のパスを持つため、触る変更は最小にしたい）。
- 権限も分離できる。budget-alertは `roles/billing.projectManager` を一切必要としない
  （課金操作をしないため）。stop-billingの実行SAは同ロールを持つが、budget-alertの
  専用SA（`oneco-budget-alert@<project>.iam.gserviceaccount.com`）はGCSとSecret Manager
  への最小権限のみで構成する（下記「IAM」参照）。

## 構成

```
Cloud Billing 予算 (oneco-monthly-cap-500, ¥500/月, 閾値50/90/100%)
  → Pub/Sub topic: budget-alerts (oneco-app)  ※stop-billingと同じtopicを独立購読
  → Cloud Function gen2: budget-alert (asia-northeast1)
  → costAmount / budgetAmount を自前で計算し、90%・100%到達でDiscordへ通知
```

- **閾値判定**: Pub/Sub payloadの `alertThresholdExceeded` フィールドは信用しない。
  `costAmount / budgetAmount` を自前で計算し、`>= 0.9` を90%到達、`>= 1.0` を100%到達
  として扱う（100%到達時は「stop-billingが課金解除しているはず」という情報メッセージを
  追加で出す。実際にstop-billingが動いたかの確認はこのFunctionの責務外）。
- **重複通知の防止（dedup）**: GCS上に `gs://<bucket>/<YYYY-MM>/<threshold>` という
  マーカーオブジェクトを `if_generation_match=0`（存在しない場合のみ作成、という条件付き
  書き込み）で作る。既に存在すれば `PreconditionFailed` になるので「今月・この閾値は
  通知済み」と判定してスキップする。月をまたぐと自然に新しいキーになるため、月次で
  自動的にリセットされる（TTL/削除ロジック不要）。GCP Budget通知は閾値に関係なく
  1日に複数回届くため、この仕組みがないとメッセージが届くたびにDiscordへ再送してしまう。
  `<YYYY-MM>` はメッセージ受信時刻ではなく、payload の `costIntervalStart`（請求期間の
  開始日）から導出する。処理時刻基準にすると、Pub/Subの再配信や処理遅延で月境界を
  またいで届いた古い期間のメッセージが新しい月のマーカーを誤って消費し、本物の通知が
  抑止されうるため（欠損・不正値時はERRORログを残した上で処理時刻へフォールバックする）。
- **例外安全性**: entrypoint は広めのtry/exceptで囲み、パース失敗・型不正・GCS障害等の
  想定外例外はERRORログを残した上で正常終了する（Pub/Subへ非2xxを返さない）。gen2の
  Pub/Subトリガーは再配信ポリシーに従うため、例外を伝播させると同一メッセージが
  繰り返し再配信されるリスクがある。壊れた入力は再配信しても直らないため、ログのみ
  残して握りつぶす方針にしている。
- **Discord送信**: `DISCORD_WEBHOOK_URL`（既存の Secret Manager secret を
  stop-billingとは別のIAMバインディングで参照。secret自体は共有・再利用する）。
  best-effort（タイムアウト10秒、4xx/5xxはログのみでraiseしない）。
  マーカー作成が成功した後にDiscord送信を試みるため、Discord側が落ちていても
  「今月は通知済み」の判定は正しく維持される（再送はしないが、再送しても実害は小さい
  通知目的のFunctionなのでこの順序を許容している）。

## IAM（権限分離）

専用サービスアカウント `oneco-budget-alert@<project>.iam.gserviceaccount.com` に付与するのは:

- `roles/storage.objectCreator`・`roles/storage.objectViewer`（マーカーバケットのみ）
- `roles/secretmanager.secretAccessor`（`DISCORD_WEBHOOK_URL` secretのみ）

**`roles/billing.projectManager` は付与しない。** このFunctionは通知専用で課金操作を
一切行わないため、billing系ロールを持たせる理由がない（最小権限原則）。
`requirements.txt` にも `googleapiclient` / `google-api-python-client`
（Cloud Billing APIクライアント、stop-billingが使っているもの）を含めていない —
依存関係レベルでも「このFunctionは課金APIを呼べない」ことを示す。

## デプロイ

```bash
./deploy.sh --dry-run   # 実行されるgcloudコマンドを表示するだけ（何も変更しない）
./deploy.sh              # 実際にデプロイ
```

環境変数で上書き可（既定値は `deploy.sh` 冒頭参照）: `GCP_PROJECT_ID` / `GCP_REGION` /
`BUDGET_ALERT_BUCKET` / `BUDGET_ALERT_SA` / `DISCORD_SECRET_NAME`。

## テスト手順

### ローカル単体テスト（モック、90%/100%分岐まで検証可能）

```bash
uv run pytest -q tests/infra/test_budget_alert.py
```

GCS・Discordをモックして `>= 0.9` 分岐を検証する。実GCP・実Discordには一切触れない。

### 本番Pub/Subへのsyntheticメッセージ送信（要注意）

寄せてよいのは **`costAmount < budgetAmount`（予算内）のメッセージのみ**。
`budget-alerts` topicは stop-billing も購読しているため、`costAmount >= budgetAmount` の
メッセージを送ると **stop-billingが実際に課金解除を実行してoneco-apiが停止する**。
90%/100%分岐の実地検証はローカル単体テストのモックで行い、本番topicでは行わない。

```bash
# 予算内メッセージのみ。budget-alert側はDiscordへ通知しないことを確認する用途。
gcloud pubsub topics publish budget-alerts \
  --project=oneco-app \
  --message="$(python3 -c '
import base64, json
payload = {"budgetDisplayName": "oneco-monthly-cap-500-synthetic-test",
           "costAmount": 100, "budgetAmount": 500,
           "currencyCode": "JPY"}
print(json.dumps(payload))
')"
```

Cloud Functionのログで受信・ratio計算（0.2、閾値未到達でスキップ）を確認する:

```bash
gcloud functions logs read budget-alert --project=oneco-app --region=asia-northeast1 --limit=20
```

## 注意

- 予算のコスト集計には数時間〜1日程度の反映遅延がある（stop-billingと同じ制約）。
  90%通知も同じ遅延を受けるため、通知が届いた時点で実コストは90%を上回っている可能性がある。
- 90%到達通知には**自動的な緩和措置はない**（課金は止めない。人間が確認して対応する
  ための早期警告）。対応手順は [docs/RUNBOOK.md](../../docs/RUNBOOK.md) のF節を参照。
- マーカーバケットは月次で自動的に新しいキーになるが、オブジェクト自体は削除されない
  （費用は無視できるレベル: 月2オブジェクト×数十バイト）。ライフサイクルルールでの
  自動削除は将来課題（今回はスコープ外）。
