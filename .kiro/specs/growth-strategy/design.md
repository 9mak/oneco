# oneco 集客戦略 (growth-strategy) 設計書

## 0. 設計方針

要件 1-6 を **「インパクト × 工数 × 依存関係」** で並べ直し、5 つの実装フェーズに分解する。1 フェーズあたり週数時間 × 1-2 週で完了させる粒度を目安に切る。

設計上の原則:

1. **計測 → 露出 → 信頼 → 成果** の順で土台を固める。途中段階で施策を増やしすぎない。
2. **AI 自動化前提**。Claude / Codex で半自動化できない手作業は基本やらない（自治体個別営業など）。
3. **ディフェンシブ姿勢を最優先**。攻めの掲載許可申請は行わず、撤去申し立て対応で誠実さを示す。
4. **既存資産の活用**。新規ページ・新規機能は最小限に抑え、既存 LP / 既存集計の強化で寄り倒す。
5. **可逆性の高い実装から着手**。SNS 投稿パイプラインのような可逆な施策を先に、ドメイン取得のような半不可逆な施策を後に。

## 1. 実装フェーズ全体像

| Phase | 期間目安 | 主目的 | 主担当 | 依存 |
|---|---|---|---|---|
| **Phase 1: 計測完成** | 0.5 週 | 要件 1 のカスタムイベントと KPI ダッシュボード化 | Claude (実装) | なし |
| **Phase 2: ディフェンシブ態勢** | 0.5 週 | 要件 4 の /transparency と撤去窓口 | Claude (実装) | Phase 1 |
| **Phase 3: SEO 強化** | 1 週 | 要件 3 の都道府県 LP / 詳細ページ / /about の SEO 詰め | Codex (制作) + Claude (実装) | Phase 1 |
| **Phase 4: SNS 開設・自動投稿** | 1-2 週 | 要件 2 の X 公式アカウントと自動投稿パイプライン | ユーザー (アカウント開設) + Claude (パイプライン) | Phase 1, 3 |
| **Phase 5: 成果可視化拡張** | 0.5 週 | 要件 5 の /stats 拡張と報告フォーム | Claude (実装) | Phase 1 |
| **Phase 6: ドメイン判断** | (条件達成時) | 要件 6 のトリガー監視と切替作業 | ユーザー (取得判断) + Claude (移行) | 全 Phase 後 |

合計工数感: 4-5 週（ユーザー作業 = X アカウント開設・テンプレメール送信判断・ドメイン取得判断 のみ。残りは Claude/Codex で進行可能）。

---

## 2. Phase 1: 計測完成 (要件 1)

### 2.1 GA4 カスタムイベント設計

`@next/third-parties/google` が提供する `sendGAEvent()` を使い、以下 3 イベントを送る。

| イベント名 | 発火タイミング | パラメータ | 実装箇所 |
|---|---|---|---|
| `external_link_click` | 自治体公式 URL or 動物詳細元ページに `target="_blank"` で遷移 | `link_url`, `prefecture`, `animal_id` (詳細ページのみ) | `frontend/components/animals/SourceLink.tsx` (新規 or 既存に hook 注入) |
| `search_used` | 検索バーが空でない状態で送信された | `query_length`, `has_results` | `frontend/components/search/SearchBar.tsx` (既存に hook 注入) |
| `share_clicked` | OGP シェアボタン押下 (実装するなら) | `network` (`x` / `copy_link`) | `frontend/components/animals/ShareButton.tsx` (新規・優先度低) |

実装ポリシー:

- イベント発火は **ユーザー操作にひも付くもののみ**。閲覧時間や滞在は GA4 標準計測 (engagement_time_msec) で十分。
- `sendGAEvent` の wrapper を `frontend/lib/analytics.ts` に集約し、テスト時はモック化。
- 個人情報を含むパラメータは送らない（検索クエリ本文は送らず長さだけ、動物 ID は識別子のみ）。

### 2.2 KPI ダッシュボード

GA4 標準のレポート機能で代用する（カスタムダッシュボードは作らない）。週次レビュー時に以下 5 指標をスナップショットとして手動メモ:

| 指標 | GA4 画面 | しきい値 |
|---|---|---|
| WAU | レポート > ユーザー属性 > 概要 (期間=7日) | 100 / 500 / 5,000 |
| 平均セッション時間 | レポート > エンゲージメント > 概要 | > 60 秒なら興味あり |
| 外部遷移率 | エンゲージメント > イベント > `external_link_click` ÷ `page_view` | > 5% で CV 健全 |
| 動物詳細 PV | レポート > エンゲージメント > ページとスクリーン (`/animals/`) | - |
| 流入経路 | レポート > 集客 > 概要 | Organic 比率の推移を追う |

レビュー記録は memory として残す (`project_growth_kpi_<YYYY-MM>.md`)。

### 2.3 Search Console モニタリング

- `sitemap.xml` のステータスを週 1 で確認（成功/失敗のみ）。
- 「検索パフォーマンス」のクリック・インプレッション数を月初に取得し記録。
- インデックス カバレッジ画面でエラーが出ていれば対応（404 / noindex 等）。

### 2.4 Phase 1 完了条件

- [ ] `external_link_click` / `search_used` がリアル本番で GA4 リアルタイム画面に届く
- [ ] sitemap.xml が `成功` ステータス
- [ ] 47 都道府県 LP のうち少なくとも 10 件がインデックス済み

---

## 3. Phase 2: ディフェンシブ態勢 (要件 4)

### 3.1 `/transparency` ページ実装

新規ページ: `frontend/app/transparency/page.tsx`

構成:

```
1. oneco について (1 段落)
2. データソース
   - 47 都道府県 91 ホストの一覧 (sites.yaml から生成 or 静的列挙)
   - 各自治体の公式 URL リンク
3. 収集ポリシー
   - robots.txt 遵守 / レート制限 / ONECO_USER_AGENT 明示
   - 収集頻度（日次）
4. 著作権スタンス
   - 自治体公開情報の集約・案内であること
   - 写真・本文の著作権は各自治体に帰属
   - サムネイルは自治体公式画像への直接参照（自前ホスティングなし）
5. 撤去依頼窓口 (最重要)
   - 連絡先: GitHub Issues + メール (どちらでも)
   - 応答 SLA: 7 営業日以内
6. 法的姿勢のサマリ (project_legal_scraping の L1-L5)
7. 運営者・連絡先
```

実装メモ:

- 全 91 ホスト一覧は `sites.yaml` をビルド時に読んで `getStaticProps` 相当 (App Router なら page.tsx で fetch + revalidate) で生成
- ホスト一覧コンポーネントは Phase 2 で初期実装、Phase 5 で「現在 N 件掲載中」を追加して再活用
- Footer から `/transparency` への導線を追加

### 3.2 撤去依頼窓口の運用設計

- メールアドレス: 既存の問い合わせ用アドレス or 新規取得（プロジェクト固有プレフィックス: `oneco-contact@...`）
  - **ユーザー判断項目**: 新規メール取得するか既存利用か
- GitHub Issues テンプレ追加: `.github/ISSUE_TEMPLATE/takedown-request.yml`
  - 自治体名・対象 URL・申立理由・連絡先メール
- 受信時の運用手順を `.kiro/specs/growth-strategy/runbooks/takedown.md` に書く（後続フェーズ）

### 3.3 事前告知テンプレメール

要件 4.1 で定義したテンプレを `docs/templates/` に保存:

- `docs/templates/notify-municipal.md` (自治体向け・敬語)
- `docs/templates/notify-rescue-org.md` (保護団体向け)

送信は **問い合わせベース**。攻めの一斉送信は行わない。

### 3.4 Phase 2 完了条件

- [ ] `/transparency` 公開
- [ ] Footer に「運営方針・撤去依頼」リンク
- [ ] GitHub Issue テンプレ追加
- [ ] テンプレメール 2 種を `docs/templates/` に保存

---

## 4. Phase 3: SEO 強化 (要件 3)

### 4.1 都道府県 LP (`/areas/[prefecture]`) の SEO 強化

既存ページの metadata と本文を強化:

```tsx
// 例: app/areas/[prefecture]/page.tsx の metadata
export async function generateMetadata({ params }) {
  const { prefecture } = await params;
  const name = prefectureName(prefecture);
  const count = await countAnimalsInPrefecture(prefecture);
  return {
    title: `${name}の保護犬・保護猫 一覧（${count}頭掲載中）`,
    description: `${name}の動物愛護センター・保健所で保護されている犬・猫の最新情報を集約。里親募集・迷子情報を一覧で検索できます。`,
    alternates: { canonical: `/areas/${prefecture}` },
  };
}
```

本文には以下を含める:

- h1: `${name}の保護動物 一覧`
- リード文: `${name}内の N 自治体から取得した最新の保護動物情報を集約しています。`
- 自治体公式リンク (信頼性)
- 動物カードグリッド (既存)

### 4.2 動物詳細ページ (`/animals/[id]`) の SEO

要件 3.2 に従い title/description のテンプレを整える:

```tsx
title: `${species}の${name || managementNumber} - ${prefecture}の${category}`
description: `${prefecture}${city}で保護されている${species}。${truncate(description, 120)} ${prefecture}公式情報の集約。`
```

既に JSON-LD は実装済み (PR #180 系)。本フェーズは metadata 文字列の最適化のみ。

### 4.3 `/about` ページ充実

新規 or 既存 `/about` に以下を追加:

- 活動の目的 (殺処分ゼロへの寄与)
- データソース (自治体公開情報の集約) と /transparency への内部リンク
- 運営者 (個人運営である旨と GitHub プロフィール)
- 連絡先 (GitHub Issues + メール)

### 4.4 `/blog` `/news` は実装しない

要件 3.4 で明示済み。著作権・個人情報リスク回避のため、ブログ形式の動物紹介は範囲外。

### 4.5 内部リンク構造の整理

- トップ → 47 都道府県 LP への導線（既存）
- 都道府県 LP → 動物詳細（既存）
- 全ページ Footer → `/transparency`, `/about`, `/privacy`
- 動物詳細 → 自治体公式リンク（既存・`external_link_click` 計測対象）

### 4.6 Phase 3 完了条件

- [ ] 47 都道府県 LP の metadata に動的件数表示
- [ ] 動物詳細 metadata テンプレ最適化
- [ ] /about 充実
- [ ] Footer 内部リンク整理

---

## 5. Phase 4: SNS 開設・自動投稿 (要件 2)

### 5.1 X 公式アカウント開設 (ユーザー作業)

ユーザータスク:

- [ ] X アカウント作成（ユーザー名候補: `@oneco_pet` / `@oneco_pets` / `@oneco_jp`）
- [ ] プロフィール文・ヘッダー画像・ピン留めツイート設定
- [ ] サイト URL を Bio に貼る

Claude 作業: プロフィール文 3 案・ヘッダー画像用 Codex プロンプト・ピン留めツイート文案を提供。

### 5.2 自動投稿パイプライン設計

実装場所: `backend/src/syndication_service/x_publisher/` (新規モジュール)

データフロー:

```
日次 cron (Cloud Run Job, GitHub Actions)
  ↓
1. DB から候補抽出 (status=available, image_urls あり, shelter_date 降順 top N)
  ↓
2. Claude API で投稿文生成 (テンプレベース、200 字以内、ハッシュタグ付与)
  ↓
3. テキストカード画像生成 (next/og の ImageResponse 流用、または Cloudflare Workers)
  ↓
4. X API v2 で投稿 (画像 + 本文 + 自治体公式 URL リンク)
  ↓
5. 投稿結果を DB に記録 (動物 ID, 投稿時刻, X URL, 成否)
```

投稿頻度: 1 日 1-3 件（cron で 1 件、ユーザー手動で追加可能なバッファ運用）。

### 5.3 Claude プロンプト設計 (投稿文生成)

```
役割: 保護動物情報サイト oneco の SNS 運用担当
入力: 動物データ (種別/性別/地域/特徴/自治体URL)
出力: X 投稿用テキスト (180 字以内、ハッシュタグ含む)
制約:
- 主観的形容詞（「可愛い」「優しい」等）は避ける
- 公式情報の要約に徹する
- 「詳細・問い合わせは自治体公式へ」を必ず含める
- ハッシュタグ: #保護犬 or #保護猫 + #里親募集 + #<都道府県名>
- 動物の名前・管理番号がある場合は記載
```

LLM 選定: [[project_extraction_strategy]] と [[feedback_llm_provider_selection]] に従い **Groq 優先** で開始、品質が足りなければ Claude Haiku に切替。

### 5.4 テキストカード画像生成

`next/og` の `ImageResponse` (既存 OGP 流用) で「タイトル + 種別 + 地域」のテキストカードを動的生成。

実装場所: `frontend/app/sns/x-card/[id]/opengraph-image.tsx`

X API には公開 URL の画像を添付するため、これを X 投稿ジョブから fetch して up する。

### 5.5 X API クライアント

- API キー: X Developer Portal の Basic プラン (月 200 投稿) で開始
- シークレット保管: `.envrc` + Keychain (`oneco-x-api-key`, `oneco-x-api-secret`, `oneco-x-access-token`, `oneco-x-access-secret`)
- ライブラリ: Python `tweepy` (実績豊富) or `requests` 直叩き
  - **判断**: `tweepy` 採用 (実装速度優先、依存は許容)

### 5.6 投稿前モデレーション

- 死亡個体 (status=deceased) は除外（既に repository 側で除外済み、念のため二重防御）
- description に PII が残っていないかチェック（既存 normalizer の sanitize 済み前提だが、投稿前に再 grep）
- 文字数オーバーは自動切詰め

### 5.7 失敗・成果のログ

- 投稿失敗時はログ + Slack/Discord webhook 通知（ユーザー判断: 通知先を決める）
  - **ユーザー判断項目**: 通知先（Slack / Discord / メール / なし）
- GA4 referral で X からの流入を週次でレビュー（自動で `utm_source=x` を URL に付与）

### 5.8 Phase 4 完了条件

- [ ] X アカウント開設 (ユーザー作業)
- [ ] 自動投稿パイプライン実装 + 1 日 1 件の cron 稼働
- [ ] 投稿前モデレーション (PII / deceased / 文字数)
- [ ] GA4 で X 流入が `utm_source=x` で計測される

---

## 6. Phase 5: 成果可視化拡張 (要件 5)

### 6.1 `/stats` ページ強化

既存 `/stats` ページに以下を追加:

- 累計掲載数 (active + archive)
- アーカイブ理由別の内訳 (transferred / returned / completed)
- 都道府県別ヒートマップ (Phase 5 後半・優先度低)
- 月次推移グラフ (累計のみ・recharts)

データソース: 既存 `/api/v1/stats` (なければ新規追加) または ISR で生成。

### 6.2 ユーザー報告フォーム (優先度低)

- GitHub Issues template: `.github/ISSUE_TEMPLATE/reunion-report.yml`
- 「うちの子が見つかりました」「里親になりました」を匿名で投稿できる
- 当面は Google Forms / Tally でも可（ユーザー判断）

### 6.3 OGP 画像の成果表示

OGP 画像（Codex 改善後）に「累計 N 件掲載中」を動的表示。トップ OGP のみ。

### 6.4 Phase 5 完了条件

- [ ] `/stats` 拡張 (アーカイブ理由別内訳まで)
- [ ] 報告フォーム導線 (GitHub or Google Forms)

---

## 7. Phase 6: ドメイン判断と切替 (要件 6)

### 7.1 トリガー監視

Phase 1 の週次 KPI レビュー時に以下をチェック:

- 月間 PV >= 5,000 ?
- 自治体・プレスからの問い合わせが 1 件でも来た ?
- マネタイズ着手判断が出たか ?

いずれか達成で取得判断。

### 7.2 取得時の作業 (チェックリスト)

要件 6.2 に列挙済み。実装時に `runbooks/domain-cutover.md` として展開する。

優先順位: `.com` のみ取得を初期方針。`.jp` はマネタイズ判断後。

### 7.3 移行時の互換性

- vercel.app は当面残す（既存ユーザーの bookmark 保護）
- 301 リダイレクト設定で SEO 評価を新ドメインに引き継ぐ
- Search Console の住所移転ツールを使用

---

## 8. 横断的設計事項

### 8.1 シークレット管理

新規発生するシークレット:

| 用途 | Keychain サービス名 | 環境変数 |
|---|---|---|
| X API キー | `oneco-x-api-key` | `X_API_KEY` |
| X API シークレット | `oneco-x-api-secret` | `X_API_SECRET` |
| X アクセストークン | `oneco-x-access-token` | `X_ACCESS_TOKEN` |
| X アクセストークンシークレット | `oneco-x-access-secret` | `X_ACCESS_TOKEN_SECRET` |
| 撤去依頼メール SMTP (ユーザー判断時) | `oneco-smtp-password` | `SMTP_PASSWORD` |

CI / Cloud Run 本番側は GitHub Actions Secrets / Secret Manager に同名で登録。

### 8.2 監視

- X 投稿 cron: Cloud Run Jobs の失敗通知 + GitHub Issue 自動起票
- GA4 / Search Console: 週次手動レビュー
- 撤去依頼: GitHub Issue label `takedown` で受信、SLA 7 営業日内に対応

### 8.3 テスト戦略

- `/transparency` / `/about`: snapshot テストのみ（静的ページ）
- GA4 イベント発火: `sendGAEvent` モック + dispatch 確認
- X 投稿パイプライン: 
  - unit: 投稿文生成プロンプトの出力検証
  - integration: X API モック (`tweepy` の mock_calls) で投稿フロー検証
  - dry-run モード必須（本番 X に流れないように環境変数で切替）

### 8.4 リスクと緩和策

| リスク | 影響度 | 緩和策 |
|---|---|---|
| X 投稿で誤った情報を発信 | 高 | dry-run モード必須、初週は手動レビューで本番投稿、PII 二重 grep |
| 自治体からの撤去要請対応遅延 | 高 | SLA 7 営業日明記、GitHub Issue 自動 label でアラート |
| GA4 計測の精度不足 | 中 | カスタムイベント実装後リアルタイムで確認、外部遷移率 < 1% なら計測不備を疑う |
| ドメイン取得タイミングの判断ミス | 低 | 要件 6 で明確なトリガーを定義済み |
| AI 自動投稿の文体ぶれ | 低 | プロンプトを memory に保存し再現性確保、評価モデルを別途用意 |

---

## 9. 優先順位マトリクス

| 施策 | インパクト | 工数 | 優先度 |
|---|---|---|---|
| Phase 1: 計測 (`external_link_click`) | 高 | 0.5 d | 🔴 最優先 |
| Phase 2: `/transparency` | 高 (信頼性) | 1 d | 🔴 最優先 |
| Phase 3: 都道府県 LP SEO | 高 (流入) | 2 d | 🟡 次点 |
| Phase 4: X 自動投稿 | 中 (露出) | 5 d | 🟡 次点 |
| Phase 3: 動物詳細 SEO | 中 (流入) | 1 d | 🟢 余裕で |
| Phase 5: `/stats` 拡張 | 中 (信頼性) | 2 d | 🟢 余裕で |
| Phase 5: 報告フォーム | 低 | 0.5 d | 🔵 任意 |
| Phase 6: ドメイン取得 | 高 (条件達成時) | 1 d | ⏳ 条件待ち |

着手順: Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5 → Phase 6 (条件達成時)。

---

## 10. 次フェーズ

design.md レビュー後、tasks.md でタスク分解（粒度: 1 タスク = PR 1 本相当）。Phase 単位で実装ブランチを切り、PR 単位でレビュー・マージする。
