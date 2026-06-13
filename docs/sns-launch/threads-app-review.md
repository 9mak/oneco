# Threads API (Meta Graph API) App Review 申請文ドラフト

## 申請の流れ

1. **Meta for Developers** (https://developers.facebook.com/) でアカウント作成（個人 Facebook アカウントでログイン）
2. **新規 App を作成**
   - App Type: **Business**（commercial use OK のため）
   - App Name: `oneco` （または `oneco-sns-publisher`）
3. **Threads use case を追加**: Dashboard → Use Cases → 「Threads API」を Add
4. **Permissions を要求**:
   - `threads_basic` （プロフィール情報取得・必須）
   - `threads_content_publish` （投稿作成・**App Review 必須**）
   - `threads_read_replies` (任意、リプライ分析する場合)
   - `threads_manage_replies` (任意)
   - `threads_manage_insights` （投稿効果計測、推奨）
5. **App Review に申請**: Dashboard → App Review → Permissions and Features → 各 permission の「Request」

## App Review 申請文ドラフト (英語)

### How will your app use the {permission_name}? (each permission)

#### threads_basic

```
oneco uses threads_basic to read the public profile information of the
oneco official Threads account in order to:
1. Confirm that the access token has the expected account context before
   posting (sanity check, avoids posting to the wrong account)
2. Surface the official Threads profile URL in the oneco web portal's
   /about page as part of operator transparency
3. Display follower count and bio updates in our internal monitoring
   dashboard to track community growth

We do NOT read other users' profiles, only our own (the operator's) account.
```

#### threads_content_publish

```
oneco is a non-profit web portal that aggregates publicly disclosed shelter
animal information from 91 Japanese municipal animal welfare centers.

Our app will use threads_content_publish to:

1. Post one announcement per day featuring a newly listed shelter animal
   (volume: ~1 post per day, ~30 posts per month)
2. Each post includes:
   - Factual description of the animal (species, sex, age, location)
   - A text-card image generated server-side (no copyrighted photos used,
     all images are programmatically generated text cards)
   - A link back to the originating municipal animal welfare center's
     official page (full source attribution)
   - Hashtags: #保護犬 / #保護猫 / #里親募集 (Japanese: "shelter dog",
     "shelter cat", "looking for adopters")

3. Strict moderation rules:
   - Animals with status "deceased" are excluded
   - PII (phone numbers, addresses of finders) is removed before posting
   - Subjective adjectives ("cute", "lovely") are prohibited; only factual
     descriptions are allowed
   - Posts are reviewed manually for the first week before fully automating

4. The account bio clearly states "AI-assisted posting" (Bot disclosure).

The goal is to redirect potential adopters and missing-pet owners to
official municipal information that is otherwise scattered across 91
different government websites. This reduces euthanasia rates by connecting
shelter animals with families faster.

Operator transparency: full data source list and takedown policy at
https://frontend-psi-ten-73.vercel.app/transparency
```

#### threads_manage_insights

```
oneco will use threads_manage_insights to evaluate the effectiveness of
its daily announcements:
1. Measure impressions and link clicks per post to identify what types of
   content (species, age range, region) drive the most engagement
2. Adjust the posting strategy weekly based on aggregated metrics
3. Report aggregated insights (no individual user data) on our /stats page
   as part of operator transparency

We do NOT track or store data about individual users who interact with our
posts; only aggregated, anonymized counts are used.
```

### Demo video / screencast (required for content_publish)

App Review では「実際に動作している様子」のデモ動画提出が求められる。事前準備:

1. **dry-run モードで自動投稿パイプラインをローカル実行**
2. 動画 (3-5 分) で以下を画面録画:
   - パイプライン起動 (DB から動物 1 件を抽出)
   - 投稿文生成 (Claude/Groq からの出力)
   - テキストカード画像生成
   - Threads API 投稿リクエスト（dry-run なので実投稿はしない、または test app で本物投稿）
   - 投稿後のログ (utm_source=threads が付いた URL を確認)
3. 動画は YouTube 非公開アップロードで URL を申請に貼る

## 申請時の補足情報

- **Privacy Policy URL**: https://frontend-psi-ten-73.vercel.app/privacy
- **Terms of Service URL**: https://frontend-psi-ten-73.vercel.app/terms
- **Data Deletion URL**: https://frontend-psi-ten-73.vercel.app/transparency (撤去ポリシー含む)
- **Business Verification**: 個人運営の場合は省略可能だが、要求されたら GitHub プロフィール + 運転免許証等で対応
- **Use Case Description (Japanese)**:
  ```
  自治体公開の保護動物情報を集約する非営利ポータルから、
  Threads 公式アカウントに 1 日 1 件の告知投稿を行う。
  投稿には自治体公式ページへの URL を必ず併記し、
  里親候補・迷子の飼い主の流入経路を作る。
  ```

## 審査期間と対応

- 通常 1-2 週間で結果
- 追加情報要請が来たら速やかに返信
- 否決時は理由を読み、修正して再申請可能（多くは「デモ動画不足」「Use Case 説明不足」が原因）
