# collector-alerts — Cloud Run Jobs 実行失敗アラート

Cloud Run Jobs（`oneco-collector`, `asia-northeast1`）の実行失敗を GCP Monitoring で検知し、
メール通知する。

## 経緯 (T109)

- oneco-collector（夜間収集ジョブ、毎日 0:00 JST に Cloud Scheduler が起動）に対する
  GCP 側アラートポリシーが1件も無かった（`gcloud monitoring policies list` の結果が空）。
- OOM・非ゼロ終了・taskTimeout（現行設定 18000s=5h）超過・clone失敗は現状すべて無音。
- 唯一のバックストップは `.github/workflows/uptime-check.yml` の
  `FRESHNESS_MAX_HOURS=26` チェック（`/health` の `last_collected_at` 経由）で、
  検知は「収集が止まった症状」からの間接検知のため最大26時間遅延する。

## 調査結果: 使えるメトリクスは何か

`resource.type="cloud_run_job"` の GA メトリクス（2026-08-28、本番 `oneco-app` プロジェクトの
Monitoring API を実際に叩いて確認）のうち、実行結果を持つのは以下の2つ。

| メトリクス | 説明 | ラベル |
|---|---|---|
| `run.googleapis.com/job/completed_execution_count` | 完了した実行(execution)数とその結果 | `result`（実測値: `succeeded`。補集合として `failed` 等が入る） |
| `run.googleapis.com/job/completed_task_attempt_count` | 完了したタスク試行数とその結果 | `result`, `attempt`（リトライ回数） |

`oneco-collector` は `taskCount=1`（並列タスクなしの単一タスク構成、`deploy-collector.yml` で
宣言）のため、**execution レベルの `result` はタスクレベルの結果とほぼ1対1**になる。
OOM・非ゼロ終了・taskTimeout超過・clone失敗（entrypoint スクリプトが非ゼロ終了する）は、
原因を問わずすべて `completed_execution_count{result="failed"}` に集約される。

このため、**ログベースメトリクスを個別に作る必要はない** —
`run.googleapis.com/job/completed_execution_count` の閾値アラート1本で
「OOM/clone失敗/taskTimeout超過/その他の非ゼロ終了」を包括的に捕捉できる。

過去7日分の実測（`succeeded` のみで `failed` は0件）:
```
$ gcloud monitoring policies list --project=oneco-app   # → 0件 (alertPolicies が空を確認)
$ curl .../timeSeries?filter=metric.type="run.googleapis.com/job/completed_execution_count"...
  → result=succeeded が 2026-08-21〜08-28 の7日間、毎日1件ずつ
```

## アラートポリシーの設計

`policies/job-execution-failed.json` に1ポリシー・2条件（`combiner: OR`）で定義する。

### 条件1: 実行失敗（OOM・非ゼロ終了・taskTimeout超過等）

```
filter: resource.type="cloud_run_job" AND resource.label.job_name="oneco-collector"
        AND metric.type="run.googleapis.com/job/completed_execution_count"
        AND metric.label.result!="succeeded"
comparison: > 0 件（1時間の合計）、duration: 0s（即時発火）
```

**閾値の根拠**: 「1回でも失敗したら即通知」を採用した（何回連続失敗したら発火、という
ガードは入れていない）。理由:

- oneco-collector は **1日1回・`max-retries=0`**（`deploy-collector.yml` で明示設定・
  自動リトライなし）の構成のため、1回の失敗がその日の収集を丸ごと失う。
- サイト単位の `broken_sites.yaml`（`consecutive_failures` 閾値=3・7日猶予で自動スキップ）と
  同じ「連続N回まで待つ」設計をここに持ち込むと、収集パイプライン全体の欠落を
  最大3日間放置することになり、W001 の「宣伝を開始した後の品質維持」という目的に対して
  リスクが大きすぎると判断した。
- 1日1回しか実行されないジョブなので、閾値を1にしても「flap（頻繁な誤通知）」の懸念は
  構造的に存在しない（uptime-check.yml が3回リトライで確証を取っているのは30分毎の
  外形監視だからで、1日1回のジョブには同じ設計は不要）。

### 条件2: 25時間以上、実行完了の記録がない

```
filter: resource.type="cloud_run_job" AND resource.label.job_name="oneco-collector"
        AND metric.type="run.googleapis.com/job/completed_execution_count"
（result での絞り込みなし = 成功・失敗を問わず実行が完了した記録そのものが無いことを検知）
duration: 90000s（25時間）
```

**閾値の根拠**: `completed_execution_count` は実行が完了したときだけ値が記録される
DELTA メトリクスのため、正常時でも1日1回分しかデータ点が無い（＝Cloud Monitoring の
「メトリクス不在」条件と相性がよい）。Cloud Scheduler の起動失敗・IAM権限喪失・イメージ
pull失敗など「実行そのものが始まらない」無音死は、条件1（`result!=succeeded`）では
捕捉できない（実行が完了しないと `result` ラベル自体が記録されないため）。

25時間にした理由は、通常運用（0:00 JST 起動・Scheduler ジッターは通常数分程度）であれば
確実に収まる猶予を持たせつつ、既存の `uptime-check.yml` の26時間 freshness チェックより
**1時間早く**、かつ「実行記録なし」という具体的な一次診断ヒント付きで気づけるようにする
ため。freshness チェックは削除・置き換えせずそのまま残す（Cloud Monitoring 側で
何らかの障害が起きた場合の二重の安全網として維持する。uptime-check.yml 自体も
`/health` 200 チェック + SSRサブルート + 画像レイヤー + freshness の多層防御を採用しており、
同じ設計思想を踏襲する）。

### 通知チャンネル: メール（Discord ではない理由）

既存の Discord 連携（`DISCORD_WEBHOOK_URL`、uptime-check.yml・data-collector.yml で使用）は
GitHub Actions からの直接 POST で完結しているが、GCP Monitoring からアラートを Discord に
飛ばすには **Pub/Sub → Cloud Function（stop-billing と同型の追加インフラ）が必要**で、
実装・運用コストがこのタスクのスコープに対して過大と判断した。

GCP Monitoring はメール通知チャンネルを標準機能として持ち、`stop-billing` の予算アラート
（閾値50/90/100%到達時に請求先アカウント管理者へメール通知・GCP標準機能）と同じパターンを
踏襲できる。まずメール通知に留め、Discord 連携は将来課題とする（下記「将来課題」参照）。

## 適用方法（PRマージ後に手動実行）

このタスク（T109）のスコープは「アラートポリシー定義をコード化してPRにする」までで、
本番 GCP への実適用（`gcloud monitoring policies create` の実行）は行っていない
（本番GCP変更は HIL 事項）。PRマージ後、以下を手動実行して適用する。

```bash
# 事前確認（推奨）: 実行されるコマンドだけを表示し、実際には作成しない
DRY_RUN=true ALERT_EMAIL='9mak.org@gmail.com' \
  ./infra/collector-alerts/setup_alerts.sh

# 本番適用
ALERT_EMAIL='9mak.org@gmail.com' \
  ./infra/collector-alerts/setup_alerts.sh
```

`ALERT_EMAIL` は既存の GCP 予算アラート（`stop-billing`）と同じ、プロジェクトオーナー
（`9mak.org@gmail.com`）宛てを既定の想定にしている。変更する場合は環境変数で上書きする。

`setup_alerts.sh` がやること:
1. 同名の通知チャンネル（Email）が無ければ作成、あれば再利用する
2. 同名のアラートポリシーが既に存在する場合は重複作成せず中断する（更新は
   `gcloud monitoring policies update` を使う）
3. `policies/job-execution-failed.json` + 作成した通知チャンネルID でポリシーを作成する

`gcloud monitoring policies create` に `--dry-run` オプションは存在しない
（`gcloud monitoring policies create --help` で確認済み・2026-08-28）。そのため
「実際に作成しない検証」は (a) `policies/job-execution-failed.json` の JSON構文検証
（`python3 -m json.tool` / `jq .` で確認済み）と (b) `setup_alerts.sh` 側の
`DRY_RUN=true`（実行コマンドを表示するだけで `gcloud ... create` を呼ばない）の
2つで代替している。

### 前提

- `gcloud beta monitoring channels` を使うため beta コンポーネントが必要
  （`gcloud components install beta`。ローカル CLI への追加のみで GCP 側には影響しない）。
- 実行アカウントに `roles/monitoring.editor` 相当の権限が必要（対象プロジェクト:
  `oneco-app`）。

## 適用後の確認

```bash
gcloud monitoring policies list --project=oneco-app --format="table(displayName,enabled)"
gcloud beta monitoring channels list --project=oneco-app --format="table(displayName,type)"
```

配線検証（実際にアラートを発火させる）は、次回の taskTimeout や max-retries=0 の性質上、
本番収集を意図的に落とすテストは推奨しない。`gcloud alerting policies` の代わりに、
Cloud Monitoring コンソールの「テスト通知を送信」機能（通知チャンネル作成直後に使える）
でメール到達だけを確認するのが安全。

## 将来課題（このタスクのスコープ外）

- **Discord 通知**: Pub/Sub topic + Cloud Function（`stop-billing` と同型）を追加すれば
  Discord への転送が可能。運用に組み込む価値が出てきたら別タスク化する。
- **部分的な件数激減の検知**: T107（`site_baselines.yaml` の `high_water_count` 比較）と
  役割が異なる。本ポリシーはジョブ全体の実行失敗のみを見ており、「実行は成功したが
  収集件数が激減した」ケースは対象外。
- **Terraform管理化**: 現状 `infra/` 配下は Terraform 管理されていないため、
  `stop-billing` と同じく gcloud コマンド + JSON 定義の組み合わせを踏襲した。
  IaC 化する場合は本 JSON をベースに `google_monitoring_alert_policy` リソースへ
  移植できる。
