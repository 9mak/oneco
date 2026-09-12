# oneco 運用ランブック（手離れ運用の対応手順）

oneco は「人が手をかけなくても回り続ける」ことを目標に自動化されている。
平常時はこの文書を開く必要はない。**Discord に通知が来たときだけ**、該当セクションの手順で対応する。

> 前提: 大半の障害は自動回復するか、放置しても翌日の自動実行で回収される。
> 「すぐ直さないと致命的」なものは外形監視ダウン（本番が見えない）だけ。他は数日の猶予がある。

---

## 通知 → 対応の早見表

| Discord 通知に出る文言 | 発火元 | 緊急度 | セクション |
|---|---|---|---|
| `uptime check 失敗` | uptime-check.yml（30分毎） | 高（本番ダウン） | [A. 外形監視ダウン](#a-外形監視ダウン) |
| `シークレット失効検知` | secret-health.yml（日次） | 中（機能劣化） | [B. シークレット失効](#b-シークレット失効) |
| `収集完了: 失敗率 …` `件数ゼロ回帰` `フィールド品質ドリフト` | 収集ジョブ（GCP Cloud Run Jobs、日次） | 低 | [C. 収集の異常](#c-収集の異常) |
| `SNS publisher (Threads) failed` | sns-publish.yml（日次） | 低 | [D. SNS 投稿失敗](#d-sns-投稿失敗) |
| `壊れサイト構造診断` | 構造診断（旧・自己修復） | 低 | [E. 壊れサイト構造診断の確認](#e-壊れサイト構造診断の確認旧-auto-fix-pr-の確認) |
| `:warning: 予算90%到達` | 予算アラート → `budget-alert` Function | 中（早期警告、まだ本番は動いている） | [F. 課金遮断/予算アラート](#f-課金遮断予算アラート) |
| （Discord 通知なし。100%到達はメールのみ。症状は A の外形監視ダウンとして出る） | 予算アラート → `stop-billing` Function | 高（本番ダウン） | [F. 課金遮断/予算アラート](#f-課金遮断予算アラート) |
| `[GA4 週次]` | ga4-weekly.yml（週次月曜） | 情報のみ（対応不要） | 通常は読むだけ。`レポート生成に失敗しました` の場合のみ GA4 API 認証 (WIF/SA) を確認 |

---

## A. 外形監視ダウン

**通知**: `:rotating_light: oneco uptime check 失敗`（backend / frontend）

唯一の「すぐ確認」案件。本番 API かフロントが落ちている可能性。

1. まず手元で生死確認:
   ```bash
   curl -sS -o /dev/null -w '%{http_code}\n' https://oneco-api-tvlsrcvyuq-an.a.run.app/health
   curl -sS -o /dev/null -w '%{http_code}\n' https://frontend-psi-ten-73.vercel.app/
   ```
   両方 200 なら一過性（GitHub Actions runner の一時的ネットワーク）→ 対応不要。
2. backend が 5xx/タイムアウトなら Cloud Run ログ:
   ```bash
   gcloud run services logs read oneco-api --region asia-northeast1 --limit 50 --project oneco-app
   ```
   よくある原因: 環境変数欠落 / DB 接続断 / Supabase 側のメンテ / 予算超過による課金停止（→ [F](#f-課金遮断予算アラート)）。
3. frontend が落ちているなら Vercel ダッシュボードのデプロイ状態を確認。
4. 復旧後、配線確認したいときは手動で通知パスをテスト:
   ```bash
   gh workflow run uptime-check.yml -f force_failure=true
   ```

---

## B. シークレット失効

**通知**: `シークレット失効検知: N 件無効 (groq / threads)`

外部 API トークンが失効した。SNS 投稿文が fallback 化する等の機能劣化。致命的ではないが放置すると劣化が続く。

### Groq key の場合
2026-06-27 の実績手順（Keychain の有効 key で GitHub secret を上書き）:
```bash
# Keychain の有効性を先に確認 (200 なら有効)
KEY=$(security find-generic-password -a "$USER" -s "oneco-groq-api-key" -w)
curl -s -o /dev/null -w '%{http_code}\n' https://api.groq.com/openai/v1/models -H "Authorization: Bearer $KEY"

# 有効なら GitHub secret を更新 (値はパイプ経由・表示しない)
security find-generic-password -a "$USER" -s "oneco-groq-api-key" -w | tr -d '\n' | gh secret set GROQ_API_KEY

# 失効していたら先に Groq Console で再発行 → Keychain 更新 → 上記
#   security add-generic-password -a "$USER" -s "oneco-groq-api-key" -w  (-U で上書き)
```

### Threads access_token の場合
long-lived token も期限切れする。Meta for Developers ダッシュボードで再発行:
1. Meta for Developers → アプリ `oneco-sns-publisher` → Threads → User Token Generator で新 token 取得
2. GitHub secret 更新:
   ```bash
   gh secret set THREADS_ACCESS_TOKEN   # プロンプトに新 token を貼る (履歴に残さない)
   ```

### 更新後の確認
```bash
gh secret list | grep -iE "groq|threads"      # 更新日時が今日になっているか
gh workflow run secret-health.yml             # 手動チェックを回して緑になるか
```

---

## C. 収集の異常

**通知**: `収集完了: 成功 X/Y (失敗 Z, 失敗率 …)` / `件数ゼロ回帰 N 件` / `フィールド品質ドリフト N 件`

データ収集の劣化シグナル。**緊急度は低い**（データは前回分が残り、翌日の自動実行で回収されることが多い）。

収集本体は GCP Cloud Run Jobs（`oneco-collector` / `asia-northeast1`）で実行される（2026-08-14 移設。旧 GitHub Actions runner の IP 帯が自治体サイトから累積アクセスペナルティを受けていたため）。Cloud Scheduler が毎日 JST 0:00 に起動する。`.github/workflows/data-collector.yml` は GCP が使えないときの手動フォールバック（`workflow_dispatch` のみ）として残している。

- 実行履歴とログの確認:
  ```bash
  gcloud run jobs executions list --job=oneco-collector --region asia-northeast1 --project oneco-app --limit 5
  gcloud logging read 'resource.type=cloud_run_job AND resource.labels.job_name=oneco-collector' \
    --project oneco-app --limit 50 --format 'value(timestamp,textPayload)'
  ```
- 手動で今すぐ回したい場合:
  ```bash
  gcloud run jobs execute oneco-collector --region asia-northeast1 --project oneco-app
  # GCP 側が使えない場合の代替経路 (GitHub Actions フォールバック)
  gh workflow run "Data Collector" --ref main
  ```
- **失敗率が高い**: 一過性（自治体サイトの一時メンテ）が大半。数日続くなら該当サイトの adapter を確認。
- **件数ゼロ回帰**（過去 ≥1 件 → 今 0 件が継続）: そのサイトの HTML 構造変更の疑い。`data/site_baselines.yaml` に記録されている。
- **連続失敗でスキップされたサイト**: `data/broken_sites.yaml` に溜まる。`consecutive_failures >= 3` で自動スキップ。ただし **`BROKEN_SITE_RECHECK_DAYS=7` で7日後に自動再チェック**されるので、サイト側が直れば自動復活する。手動で即復活させたいときだけ:
  ```bash
  # 該当エントリの consecutive_failures を 0 にするか、行ごと削除して commit
  ```
- **adapter の修理**: LLM 自動修復ループは 2026-09 (T406) に撤去済み（48 run 0 PR）。代わりに検知サイトごとに構造診断が Discord + `reports/diagnosis/` artifact で「どの selector/label が壊れたか」を提示する（後述 E）。人がそれを見て手動で adapter コードを修正する。

---

## D. SNS 投稿失敗

**通知**: `:warning: SNS publisher (Threads) failed`

その日の 1 件が投稿できなかっただけ。**実害は小さい**（失敗個体は post_log に記録されないので翌日再選定される）。

- run ログで原因を確認:
  ```bash
  gh run list --workflow "SNS Publish (Threads)" --limit 5
  gh run view <run-id> --log | grep -iE "error|401|400|reason|OAuthException|\"code\""
  ```
- `401` → Threads token 失効 → [B](#b-シークレット失効) の Threads 手順
- `400` で body に `OAuthException` / `"code":190` を含む → **これも token 失効**（Meta は失効を 401 でなく 400 + `error.code=190` (OAuthException) で返すことがある。2026-08-22 に実際に発生）→ [B](#b-シークレット失効) の Threads 手順
- `400` で上記が無い（container 処理タイミング等） → 一時障害。単発なら放置で翌日回収
- 文章が fallback テンプレになっている → Groq 失効 → [B](#b-シークレット失効) の Groq 手順

---

## E. 壊れサイト構造診断の確認（旧 auto-fix PR の確認）

2026-09 (T406) に LLM 自動修復ループ（`auto-fix-adapter.yml` への dispatch）を撤去し、代わりに構造診断を Discord + artifact で出す運用に切り替えた（48 run 0 PR の実績のため。詳細は [docs/wiki/04-self-healing.md](wiki/04-self-healing.md)）。

- Discord 通知（`壊れサイト構造診断 (N 件)`）本文に、サイトごとの HTTP status / selector マッチ件数 / 候補ラベル・リンクパターンが最大15行で出る（1 run 最大5サイト、残りは artifact 参照）
- 全件は `reports/diagnosis/diagnosis_<timestamp>.{json,md}` にコミットされる（このリポジトリ配下）
- 対応: 通知/artifact を見て該当 adapter (`src/data_collector/adapters/rule_based/sites/`) のセレクタ/ラベルを人が修正し、通常の PR フローでマージする
- 緊急停止したい場合（診断自体の追加 GET を止めたい等）:
  ```bash
  gh variable set ONECO_DIAGNOSIS_ENABLED --body "false"
  ```
- `scripts/auto_fix_adapter.py` と `auto-fix-adapter.yml` は削除していない。手動 `workflow_dispatch`（site_name 指定）で個別に試すことは引き続き可能

---

## F. 課金遮断/予算アラート

### 90%到達（Discord通知あり、まだ本番は動いている）

**通知**: `:warning: 予算90%到達`（`budget-alert` Function、[infra/budget-alert](../infra/budget-alert/README.md)）

90%到達には**自動的な緩和措置はない**（課金は止めない、早期警告のみ）。月1回だけ通知される
（GCS上のマーカーで dedup）。対応は任意だが、GCP請求コンソールでコスト内訳を確認し、
想定外の急増がないか見ておくと 100% 到達（下記）を未然に防げる。

### 100%到達（Discord通知なし、本番停止）

**症状**: `oneco-api` を含むサイト全体が突然応答しなくなる。Discord 通知は無い（予算アラートは請求先アカウント管理者宛のメールのみ、GCP 標準機能）。[A. 外形監視ダウン](#a-外形監視ダウン) の通知経由で気づくことが多い。

月額予算 ¥500（`oneco-monthly-cap-500`）の 100% 到達で Cloud Function `stop-billing` が `oneco-app` プロジェクトの課金を自動解除し、Cloud Run 含む全リソースが停止する仕組みが入っている（2026-07-30 に無料トライアル失効で本番が落ちた事故の再発防止）。

1. [A](#a-外形監視ダウン) の手順で生死確認 → Cloud Run ログすら取得できない/プロジェクトが無効化されている挙動なら課金停止を疑う。
2. GCP 請求コンソール（Billing）で `oneco-app` の課金アカウントのリンク状態を確認する。「この projects に請求先アカウントがありません」等になっていれば課金停止が発動している。
3. 復旧: 請求コンソールから `oneco-app` に課金アカウントを再リンクする（**自動では戻らない、手動操作必須**）。
4. 復旧後、生死を再確認:
   ```bash
   curl -sS -o /dev/null -w '%{http_code}\n' https://oneco-api-tvlsrcvyuq-an.a.run.app/health
   ```
5. 予算上限の変更や仕組みの詳細は [infra/stop-billing/README.md](../infra/stop-billing/README.md) 参照:
   ```bash
   gcloud billing budgets list --billing-account=01F439-B06BD4-15DEF1
   gcloud billing budgets update <ID> --budget-amount=1000JPY
   ```

> 予算のコスト集計には数時間〜1日程度の遅延があり、¥500 ちょうどでは止まらない（多少の超過はありうる）。課金解除パス自体は本番未検証（テストすると実際にサイトが落ちるため）。

---

## 平常時に自動で回っているもの（参考）

これらは通知が来ない限り放置でよい:

- **Backend / Frontend / Collector CI/CD**: push で自動テスト・自動ビルド → Cloud Run（API）/ Cloud Run Jobs（Collector）/ Vercel 自動デプロイ（alembic migration も自動）
- **Data Collector**: 毎日 JST 0:00、GCP Cloud Run Jobs（`oneco-collector`）で 213 サイト収集 → 本番 DB 直書き
- **SNS Threads**: 毎日 JST 9:00 自動投稿
- **Uptime Check**: 30 分毎に死活監視（収集鮮度チェック込み）
- **Secret Health**: 毎日 JST 9:00 にトークン失効チェック
- **件数ゼロ回帰検知**: 永続ベースラインで毎 run チェック
- **GA4 週次読上**: 毎週月曜 JST 9:10 にユーザー数・動物詳細PV・外部リンククリックの前週比を Discord へ通知
- **GCP コスト**: ゼロスケール + Artifact Registry 自動クリーンアップで月 ¥0。予算 ¥500 到達時は自動遮断（→ [F](#f-課金遮断予算アラート)）

## よく使うコマンド

```bash
# 全ワークフローの直近 run 状態
gh run list --limit 15

# 失敗 run だけ
gh run list --status failure --limit 10

# repo variables / secrets 一覧
gh variable list
gh secret list

# 本番 API の生死とデータ件数
curl -s https://oneco-api-tvlsrcvyuq-an.a.run.app/public/stats | jq .
```

---

## 撤去依頼が来た時の履歴消去

保護団体・自治体等から「掲載していた個体情報を公開履歴から消してほしい」という撤去依頼が来た場合の手順。**実行は HIL（人間承認必須）。無条件で実行しない。**

### 2026-09-11 実施済み（T404）

撤去依頼を待たず、W004 Plan 6「データを git から外す」の一環として先行実施した。現在の main とその履歴からは個体情報が消え、以後の収集分は `9mak/oneco-state`（private）側にのみ残る。

force push した時点では public としての公開範囲は縮まっていなかった。PR 参照 `refs/pull/<n>/head` が書き換え前のコミットを指し続け、全 387 PR のうち 307 PR が除去対象ファイルを含んでいた。詳細は下の「force push では消えない」節。

### 2026-09-12 リポジトリ再作成で完了（T404 クローズ）

force push では消えないと判明したため、おまえさん決定でリポジトリを削除して同名で作り直した。

| 手順 | 実施 |
| --- | --- |
| PR #388 を main へマージ | RUNBOOK の実施記録を残すため |
| クリーンなミラーを用意 | `refs/pull/*` 397 本を削除し reflog expire + gc。除去対象パスの履歴 0・到達不能オブジェクト 0 を検証 |
| リポジトリ削除 | Web UI から。GitHub Mobile で sudo 認証 |
| 同名で再作成し push --mirror | ブランチ 62 本 |
| 設定復元 | 変数 10 件・ruleset・branch protection・環境 2 つ・homepage |

検証結果: 旧コミット SHA を直接指定しても `No commit found` が返る。force push 後は 1,091,074 バイトの全件ダンプが取得できていたので、これで実際に消えた。

失ったもの: PR 387 件（merged 329 / closed 48 / open 10）、Issue、Actions 実行履歴、シークレット 8 件。PR のメタデータと本文は削除前に退避した。

**`git clone --mirror` は `refs/pull/*` も取得する。** そのまま `push --mirror` すると GitHub が PR 参照への書き込みを拒否する前にオブジェクトがアップロードされ、新リポジトリで SHA 直指定により再取得できてしまう。push 前に `refs/pull/*` を削除して gc すること。

除去したパス（旧 main `e9b2962` → 新 main `b62a003`）:

| パス | 除去前の履歴 | 除去後 |
| --- | --- | --- |
| `output/animals.json` | 121 版 | 0 |
| `snapshots/latest.json` | 109 版 | 0 |
| `data/broken_sites.yaml` | 収集状態 | 0 |
| `data/field_quality_drift.yaml` | 収集状態 | 0 |
| `data/site_baselines.yaml` | 収集状態 | 0 |
| `data/sns_posts.yaml` | 58 コミット | **除去せず維持**（現在も使用中。置き場所は T151 の結論後に判断） |

バックアップは `~/Desktop/oneco-backup-20260911.git`（`git clone --mirror`）。戻す場合は `git push --mirror`。

### 手順

前提: `git-filter-repo` が必要。brew で入れたくない場合は `uvx git-filter-repo ...` で一時実行できる。

1. バックアップを取る（必須。これが唯一の復旧手段）
   ```bash
   git clone --mirror https://github.com/9mak/oneco.git oneco-backup-$(date +%Y%m%d).git
   ```
2. fresh clone を作る（作業用の使い捨てクローン。既存 worktree を汚さない）
   ```bash
   git clone https://github.com/9mak/oneco.git oneco-history-purge
   cd oneco-history-purge
   ```
3. `git filter-repo` で該当パスの履歴を除去する
   ```bash
   git filter-repo --invert-paths --path output/animals.json --path snapshots/latest.json
   ```
4. 結果を確認する（対象パスの履歴が 0、残すべきファイルが tree に居ること）
   ```bash
   git log --oneline --all -- output/animals.json | wc -l   # 0
   git ls-files data
   ```
5. main の保護を**二層とも**外す（下の「保護の外し方」を参照）
6. force push する。`filter-repo` は origin を外すので付け直す
   ```bash
   git remote add origin https://github.com/9mak/oneco.git
   git push origin --force --all
   git push origin --force --tags
   git push origin --force main
   ```
7. 保護を復元する（push 成功後すぐ）
8. 全 PR の CI を再実行させる。dependabot PR は `@dependabot rebase` コメントで足りる
9. 旧履歴を持つローカル clone / worktree をすべて破棄して再同期する
10. **ここまでやっても public では消えていない。** PR 参照が旧コミットを固定するため、下の「force push では消えない」節を読んで次の手を決める

### 保護の外し方（実測。ここで一度つまずいた）

main は**二層**で守られている。片方だけ外しても GH013 / GH006 で弾かれる。

- ruleset `main-force-push-protection`（`deletion` + `non_fast_forward`、bypass actor ゼロ）
  ```bash
  gh api repos/9mak/oneco/rulesets > /tmp/rulesets-backup.json        # 先に退避
  gh api -X PUT repos/9mak/oneco/rulesets/<id> -f enforcement=disabled
  # 復元: -f enforcement=active
  ```
- classic branch protection の `allow_force_pushes`
  ```bash
  gh api repos/9mak/oneco/branches/main/protection > /tmp/protection-backup.json   # 先に退避
  # PUT は全項目置換。allow_force_pushes だけ true にした JSON を --input で渡す
  # 復元: 同じ JSON の allow_force_pushes を false に戻して再 PUT
  ```

**`enforce_admins: false` では force push は通らない。** 管理者バイパスと force push 許可は別の設定。

force push が通ると `remote: Bypassed rule violations for refs/heads/main` が出る。必須ステータスチェックを飛ばした記録なので、push 後に main の CI が緑であることを別途確認する。

### force push では消えない（最重要・当初の理解は誤りだった）

**public リポジトリでは `filter-repo` + force push で公開範囲は実質縮まらない。** 2026-09-11 に実測して判明した。

当初は「到達不能になったオブジェクトが GitHub 側に残っているだけで、GC を依頼すれば消える」と理解していたが違った。旧コミットは到達不能ではない。GitHub の PR 参照 `refs/pull/<n>/head` が旧コミットを指し続けており、**到達可能な参照なので GC では永久に消えない**。

```bash
gh api repos/9mak/oneco/git/ref/pull/300/head --jq '.object.sha'
# → 951b7fff3eeae92b68f6d80799142e952c67022e（書き換え前のコミット）
```

しかもこの SHA は事前知識なしに列挙できる。公開 API でマージ済み PR のコミット一覧を引けば旧 SHA が返る。

```bash
gh api repos/9mak/oneco/pulls/300/commits --jq '.[].sha'
gh api -H "Accept: application/vnd.github.raw" \
  "repos/9mak/oneco/contents/output/animals.json?ref=951b7fff3eeae92b68f6d80799142e952c67022e" | wc -c
# → 994871
```

`Accept: application/vnd.github.raw` は必須。1MB 超のファイルは Contents API が `content` を返さないため、ヘッダーなしではサイズしか見えず「まだ取れる」ことを確認できない。

2026-09-11 時点で、全 387 PR のうち **307 PR** の head commit が除去対象ファイルを含んでいる。

### GitHub Support は原則として応じない

[Removing sensitive data from a repository](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository) に明記されている。

> GitHub Support won't remove non-sensitive data, and will only assist in the removal of sensitive data in cases where we determine that the risk can't be mitigated by rotating affected credentials.

認証情報が絡まない限り応じない方針。依頼する場合は公式手順が要求する次を揃える。

| 項目 | 取得元 |
| --- | --- |
| 影響 PR 数 | 全 PR の `head.sha` を走査し除去対象パスを含むものを数える |
| First Changed Commit(s) | `.git/filter-repo/first-changed-commits` |
| LFS オブジェクト | `.git/filter-repo/` の lfs 関連ファイル（なければ none） |

### 撤去依頼が来たときに現実に取れる手

force push は前処理にすぎない。本当に消すには次のいずれかが要る。

1. **GitHub Support が PR ref ごと削除する** — 機微データと認定された場合のみ。期待しない
2. **リポジトリを private にする** — 即時・可逆。PR ref ごと公開範囲から外れる。公開ポートフォリオとしての価値を失う
3. **リポジトリを削除して作り直す** — 確実だが PR・Issue の記録とリンクをすべて失う

撤去依頼元への回答は、この 3 つのどれを取るかを決めてから行う。**force push した時点で「消しました」と回答してはいけない。**

### 注意

- `git filter-repo` は破壊的操作。バックアップなしに実行しない
- 全履歴の書き換えになるため、fork している第三者がいる場合はその fork には反映されない旨を撤去依頼元に伝える（2026-09-11 時点で `9mak/oneco` の fork は 0）
- 旧 clone を残したまま push すると古い履歴が復活する。手順 9 を飛ばさない
- ローカルの `git stash` も旧コミットを生かす。`git stash list` を確認してから `reflog expire` する（2026-09-11 に確認せず expire して stash の reflog を消す事故があった）
- ブランチが squash merge されている場合、worktree の HEAD は新 main の祖先にならない。破棄の可否は `merge-base --is-ancestor` ではなく対応 PR が MERGED / CLOSED かで判断する

---

## 関連

- デプロイ手順: [DEPLOYMENT.md](../DEPLOYMENT.md) / [PRODUCTION_CHECKLIST.md](../PRODUCTION_CHECKLIST.md)
- 「手離れ」ロードマップの全体像と Phase 2-4（SaaS/API）の位置づけは個人メモ参照。
