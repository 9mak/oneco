# SNS アカウント開設チェックリスト

ユーザーが進める作業のチェックリスト。Claude は文案・申請ドラフトを別ファイルに用意済み。

## 共通

- [ ] ハンドル決定: 第 1 候補 `@oneco_pet` / 第 2 `@oneco_pets` / 第 3 `@oneco_jp`
- [ ] 表示名決定: `oneco — 全国の保護動物情報をひとつに` / `oneco（保護動物ポータル）` / `oneco`
- [ ] プロフィール文選定: `docs/sns-launch/profiles.md` の 案 A/B/C から選ぶ
- [ ] プロフィール画像準備: oneco ロゴ（既存の Header にあるシンボル）を 400x400 で書き出し
- [ ] ヘッダー画像: Codex プロンプトで生成（`docs/codex-prompts/sns-header.md` 別途用意予定）

## 1. Threads (本命)

### アカウント開設

- [ ] Instagram アカウントが必要（無ければ Instagram 先に作成）
- [ ] https://www.threads.net/ で Threads アカウント開設（Instagram 連携）
- [ ] ハンドル・表示名・プロフィール文・プロフィール画像を設定
- [ ] Bio に以下を含める:
  - サイト URL: `https://frontend-psi-ten-73.vercel.app`
  - 「AI 補助投稿あり / 公式情報のみ集約」（Bot 開示）
- [ ] 初回投稿: `docs/sns-launch/profiles.md` の「ピン留め投稿文案」を投稿

### Meta for Developers (App Review)

- [ ] https://developers.facebook.com/ で開発者アカウント作成
- [ ] 新規 App 作成（App Type: Business、App Name: `oneco`）
- [ ] Threads use case を追加
- [ ] 必要 permissions を要求: `threads_basic` + `threads_content_publish` + `threads_manage_insights`
- [ ] App Review 申請（申請文ドラフト: `docs/sns-launch/threads-app-review.md`）
- [ ] デモ動画を準備（dry-run パイプライン実行を録画、3-5 分）
- [ ] 申請後 1-2 週間で結果待ち

### シークレット保管 (App 作成後)

- [ ] Threads App ID を Keychain に保存:
  ```bash
  security add-generic-password -a "$USER" -s "oneco-threads-app-id" -w
  ```
- [ ] Threads App Secret を Keychain に保存:
  ```bash
  security add-generic-password -a "$USER" -s "oneco-threads-app-secret" -w
  ```
- [ ] long-lived Access Token を取得して Keychain に保存:
  ```bash
  security add-generic-password -a "$USER" -s "oneco-threads-access-token" -w
  ```

## 2. X (Twitter) アカウント開設のみ・自動化は for-good 結果待ち

### アカウント開設

- [ ] https://x.com/ で X アカウント開設
- [ ] ハンドル・表示名・プロフィール文（Threads と統一）
- [ ] ヘッダー画像 (1500x500) を設定
- [ ] Bio に以下を含める:
  - サイト URL
  - 「AI 補助投稿（for-good 承認時のみ）/ 公式情報のみ集約」
- [ ] ピン留めツイートを投稿（`docs/sns-launch/profiles.md` のピン留め投稿文案）

### X Developer Portal & for-good 申請

- [ ] https://developer.x.com/ で開発者アカウント作成
- [ ] 「Free Access for Public Utility / For-Good」フォームを探して申請
  - 申請文: `docs/sns-launch/x-for-good-application.md` (英語版を提出推奨)
- [ ] 申請受付確認メールを保管
- [ ] 1-4 週間で結果連絡を待つ

### 結果別の挙動

- ✅ **承認時**:
  - API キー一式を Keychain に保管 (`oneco-x-api-key` 等 4 種)
  - 自動投稿パイプライン (`syndication_service/sns_publisher`) で `X_PUBLISH_ENABLED=true`
- ❌ **否決時**:
  - X アカウントは休眠状態のまま残す
  - `runbooks/x-for-good-followup.md` の手順で X を spec から外す
  - 月間 PV 1,000 を超えた時点で Pay-per-use ($6/月～) 採用を再評価

## 共通: アカウント取得後の運用テスト

- [ ] Threads で手動 1 投稿してみる（自動化前の動作確認）
- [ ] 投稿の embed や reach を確認
- [ ] サイト側の `utm_source=threads` 計測が GA4 に流れることを確認 (Phase 1 で実装済み)

## 関連ファイル

- プロフィール文 3 案: `docs/sns-launch/profiles.md`
- X for-good 申請文: `docs/sns-launch/x-for-good-application.md`
- Threads App Review 申請文: `docs/sns-launch/threads-app-review.md`
- 全体仕様: `.kiro/specs/growth-strategy/design.md` §5 Phase 4
