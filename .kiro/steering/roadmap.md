# oneco - ロードマップ

## Phase 0: MVP基盤（完了）
- [x] FastAPI バックエンド（API、DB、正規化パイプライン）
- [x] Next.js フロントエンド（動物一覧、検索UI）
- [x] 高知県アダプター（ルールベース、特別ルール対応済み）
- [x] PostgreSQL + Redis インフラ
- [x] 60件のリアルデータで動作確認

## Phase 1: 四国完成 + AI抽出導入
- [ ] LLMベースの汎用データ抽出エンジン構築
  - ページHTML → Claude API → RawAnimalData（構造化出力）
  - サイトごとのアダプター不要、YAML設定のみで新規サイト追加
- [ ] 四国4県の新規サイト対応（環境省リンクページより）
  - 徳島県: https://douai-tokushima.com/
  - 香川県: https://www.pref.kagawa.lg.jp/eisei/joto/slpup3191026135548.html
  - 高松市: https://www.city.takamatsu.kagawa.jp/udanimo/ani_top.html
  - 愛媛県: https://www.pref.ehime.jp/page/16976.html
  - 松山市: https://www.city.matsuyama.ehime.jp/kurashi/kurashi/aigo/hogoinu/mayoiinuneko.html
  - 高知県: 既存アダプター稼働中（将来的にAI抽出に移行可能）
- [ ] 定期実行の仕組み（cron / スケジューラー）
- [ ] MVP公開（Vercel + 管理画面）

## Phase 2: 資金調達 + 認知拡大
- [ ] クラウドファンディング実施（READYFOR / CAMPFIRE）
  - 「全国の保護動物情報を一つに。殺処分ゼロへ」
  - デモ可能なMVPが既にある = 説得力
- [ ] OSS公開 + コミュニティ形成
  - 動物愛護 × エンジニアの仲間を集める
- [ ] コンテスト / ハッカソン出展
- [ ] メディア露出（動物愛護系、テック系）

## Phase 3: 公的機関連携
- [ ] 環境省・自治体への提案
  - 「実績あります」で持ち込む（Phase 2の成果が根拠）
- [ ] 助成金 / 公的資金の獲得
- [ ] 自治体との正式データ連携

## Phase 4: SaaS化 + スケール
- [ ] 自治体向け公式プラットフォーム提供
  - 自治体は「登録許可」を出すだけ
  - AI自動登録でデータ収集・更新
  - 統一サイト構造で検索性向上
- [ ] 協力者採用（運営委託）
- [ ] 全国展開 → 海外展開の検討

## 技術方針

### データ抽出アーキテクチャ移行
```
[現在] サイト固有アダプター（ルールベース）
  └─ 高知県: kochi_adapter.py（450行、特別ルール4つ）
  └─ 課題: 1サイトあたり数時間〜1日、保守コスト大

[Phase 1以降] AI抽出エンジン（LLMベース）
  └─ 汎用エンジン + YAML設定
  └─ 新規サイト追加: 設定数行のみ
  └─ サイト構造変更にも頑健
```

### サイト設定例（想定）
```yaml
sites:
  - name: "徳島県動物愛護管理センター"
    prefecture: "徳島県"
    list_url: "https://douai-tokushima.com/"
    list_link_pattern: "a[href*='detail']"  # 最低限のヒント
    extraction: "llm"  # AI抽出
```

---
_created_at: 2026-03-18_
