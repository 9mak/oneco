# X API for-good public utility apps 申請文ドラフト

## 申請窓口

X Developer Portal の Free tier 申請、または X 開発者サポートへの問い合わせ。
2026 年 6 月時点で公開申請フォームの場所は流動的なため、以下のいずれかで送る:

1. **X Developer Portal** (https://developer.x.com/) アカウント作成 → Free アクセス申請フォーム
2. **X 開発者サポート** (https://help.x.com/forms/developers) から「Free access for nonprofit / public utility」を選択
3. **Developer Platform 公式 X アカウント** (@XDevelopers) への DM

## 申請文 (英語版・正式提出用)

```
Subject: Application for "for-good public utility apps" free X API access

Hello X Developer team,

I am applying for free API access under the "for-good public utility apps"
program for a non-profit, non-commercial service.

== About oneco ==

oneco (https://frontend-psi-ten-73.vercel.app) is a non-profit web portal
that aggregates information about animals (mainly dogs and cats) currently
under municipal protection across all 47 prefectures of Japan.

The goal is to reduce euthanasia rates by connecting potential adopters and
owners of missing pets to publicly disclosed shelter information that is
otherwise scattered across 91 different municipal websites.

== Operational facts ==

* Non-profit, no ads, no paid plans, no commercial monetization
* Solely operated by one individual (no organization, no funding round)
* Aggregates *only publicly available data* from municipal animal welfare
  centers (open government data)
* No personally identifiable information about adopters / owners is collected
* Sourced under the open government data terms of each municipality
* Full data source disclosure and takedown policy are publicly documented:
  https://frontend-psi-ten-73.vercel.app/transparency
  with a 7-business-day SLA for takedown requests

== Intended X API usage ==

* Posting volume: 1 post per day (~30 posts per month)
* Purpose: Daily announcement of newly listed shelter animals, each with
  link to the originating municipal page
* Strict moderation: deceased / PII-redacted entries excluded; subjective
  language ("cute", "lovely") prohibited; only factual descriptions
* Bot disclosure: account bio clearly states "AI-assisted posting"
* No reading of other users' content beyond owned posts metrics
* No follower automation, no quote retweets, no liking automation

== Why this qualifies as "for-good public utility" ==

* Animal welfare is a core public benefit (Japan's "zero euthanasia"
  national initiative)
* The service redistributes only public-sector data with full attribution
  back to municipal sources
* No advertising, no data monetization, no commercial intent
* Pay-per-use ($0.20/post with URL) is not financially sustainable for a
  zero-revenue individual operator; a denial would force us to discontinue
  the X channel entirely

If additional documentation is required (proof of non-profit status, system
architecture, data source list), I will provide them on request.

Thank you for considering this application.

Best regards,
Kazuki Oguma
GitHub: https://github.com/9mak
Service: https://frontend-psi-ten-73.vercel.app
Contact: (記入時にメールアドレスを補完)
```

## 申請文 (日本語版・参考)

```
件名: 非営利公益サービス向け Free X API アクセス申請

X 開発者チーム様

oneco（https://frontend-psi-ten-73.vercel.app）は、日本全国 47 都道府県・91 の自治体に
保護されている犬・猫の情報を一元化する非営利のウェブポータルです。

殺処分ゼロに少しでも近づけることを目的に、自治体公開情報を集約して
里親候補・迷子の飼い主に届けることを使命としています。

【運営条件】
- 非営利・広告なし・有料機能なし
- 個人運営（法人化なし、資金調達なし）
- 自治体が公開している事実情報のみ集約（オープンガバナンスデータ）
- 個人情報は収集しません
- データソース一覧と撤去依頼ポリシーは /transparency で全公開
  （撤去申立て 7 営業日以内に対応 SLA）

【X API 想定利用】
- 投稿頻度: 1 日 1 件（月 30 件想定）
- 用途: 新規掲載された保護動物の告知（各投稿に自治体公式 URL を併記）
- モデレーション: 死亡個体除外、PII 除去、主観形容詞禁止、事実情報のみ
- Bot 開示: Bio に「AI 補助投稿」と明示
- 他ユーザーコンテンツの読み取りは行いません
- フォロー自動化・引用 RT 自動化・いいね自動化は行いません

【for-good 該当性】
- 動物福祉は公共利益（殺処分ゼロは日本国の取り組みでもある）
- 公的セクターデータの再配信のみ、出典は必ず自治体に戻す
- 広告・データ販売・商用意図なし
- Pay-per-use ($0.20/投稿) は無収益の個人運営者には経済的に持続不可能
  否決された場合、X チャネルは運用停止せざるを得ません

追加資料（非営利性の証明、システム構成、データソース一覧など）は
ご要望あれば提出いたします。

ご検討よろしくお願いいたします。

小熊 一輝
GitHub: https://github.com/9mak
サービス: https://frontend-psi-ten-73.vercel.app
連絡先: (記入時にメールアドレスを補完)
```

## 添付/参照リンク (申請時に貼る)

- サービス本体: https://frontend-psi-ten-73.vercel.app
- 運営方針・データソース一覧・撤去ポリシー: https://frontend-psi-ten-73.vercel.app/transparency
- このサイトについて: https://frontend-psi-ten-73.vercel.app/about
- GitHub リポジトリ (オープンソース): https://github.com/9mak/oneco

## 申請後のフォローアップ

- 返信目安: 1〜4 週間（X 公式の明確な SLA は無し）
- 否決連絡が来たら → spec.md 通り X は休眠状態に
- 承認連絡が来たら → spec.md 通り `X_PUBLISH_ENABLED=true` で自動投稿パイプラインに統合
- 1 ヶ月返事がない場合 → X 開発者サポートへ進捗確認
