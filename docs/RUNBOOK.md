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
| `収集完了: 失敗率 …` `件数ゼロ回帰` `フィールド品質ドリフト` | data-collector（日次） | 低 | [C. 収集の異常](#c-収集の異常) |
| `SNS publisher (Threads) failed` | sns-publish.yml（日次） | 低 | [D. SNS 投稿失敗](#d-sns-投稿失敗) |
| auto-fix PR が溜まっている（GitHub 上） | auto-fix-adapter（自己修復） | 低 | [E. auto-fix PR の確認](#e-auto-fix-pr-の確認) |

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
   よくある原因: 環境変数欠落 / DB 接続断 / Supabase 側のメンテ。
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

- **失敗率が高い**: 一過性（自治体サイトの一時メンテ・GitHub runner の IP ブロック）が大半。数日続くなら該当サイトの adapter を確認。
- **件数ゼロ回帰**（過去 ≥1 件 → 今 0 件が継続）: そのサイトの HTML 構造変更の疑い。`data/site_baselines.yaml` に記録されている。
- **連続失敗でスキップされたサイト**: `data/broken_sites.yaml` に溜まる。`consecutive_failures >= 3` で自動スキップ。ただし **`BROKEN_SITE_RECHECK_DAYS=7` で7日後に自動再チェック**されるので、サイト側が直れば自動復活する。手動で即復活させたいときだけ:
  ```bash
  # 該当エントリの consecutive_failures を 0 にするか、行ごと削除して commit
  ```
- **adapter の修理**: auto-fix-adapter が観察モード（後述 E）。本番モードに上げれば AI が自動修理する。それまでは手動 or 放置（7日後の再チェック待ち）。

---

## D. SNS 投稿失敗

**通知**: `:warning: SNS publisher (Threads) failed`

その日の 1 件が投稿できなかっただけ。**実害は小さい**（失敗個体は post_log に記録されないので翌日再選定される）。

- run ログで原因を確認:
  ```bash
  gh run list --workflow "SNS Publish (Threads)" --limit 5
  gh run view <run-id> --log | grep -iE "error|401|400|reason"
  ```
- `401` → Threads token 失効 → [B](#b-シークレット失効) の Threads 手順
- `400` → container 処理タイミング（Step 3 のポーリングで大幅減のはず）。単発なら放置で翌日回収。
- 文章が fallback テンプレになっている → Groq 失効 → [B](#b-シークレット失効) の Groq 手順

---

## E. auto-fix PR の確認

auto-fix-adapter（自己修復ループ）の段階リリース状態に応じて対応する。

- **観察モード**（`ONECO_AUTO_FIX_ENABLED=true`, `ONECO_AUTO_FIX_DRY_RUN=true`）: PR は作られない。`auto-fix-adapter.yml` の run ログと Discord で「検知件数・修理案がガードを通ったか」を見るだけ。誤修理が無さそうなら本番モードへ:
  ```bash
  gh variable set ONECO_AUTO_FIX_DRY_RUN --body "false"   # 本番モード: 修理 PR を自動作成
  ```
- **本番モード**: `label: auto-fix` の PR が作られる。CI が緑なら `auto-merge-fix-pr.yml` が自動マージ（完全自動には PAT `ONECO_AUTO_FIX_TOKEN` が必要。無ければ手動マージ）。
- PR が溜まる・怪しい修理がある場合は、diff を見て手動マージ or close。暴走時は緊急停止:
  ```bash
  gh variable set ONECO_AUTO_FIX_ENABLED --body "false"   # kill switch OFF
  ```

---

## 平常時に自動で回っているもの（参考）

これらは通知が来ない限り放置でよい:

- **Backend / Frontend CI/CD**: push で自動テスト → Cloud Run / Vercel 自動デプロイ（alembic migration も自動）
- **Data Collector**: 毎日 JST 0:00、211 サイト収集 → 本番 DB 直書き
- **SNS Threads**: 毎日 JST 9:00 自動投稿
- **Uptime Check**: 30 分毎に死活監視
- **Secret Health**: 毎日 JST 9:00 にトークン失効チェック
- **件数ゼロ回帰検知**: 永続ベースラインで毎 run チェック
- **GCP コスト**: ゼロスケール + Artifact Registry 自動クリーンアップで月 ¥0

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

## 関連

- デプロイ手順: [DEPLOYMENT.md](../DEPLOYMENT.md) / [PRODUCTION_CHECKLIST.md](../PRODUCTION_CHECKLIST.md)
- 「手離れ」ロードマップの全体像と Phase 2-4（SaaS/API）の位置づけは個人メモ参照。
