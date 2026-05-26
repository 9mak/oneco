# oneco リリース 2026-05 (Phase 1.5 完了)

## 概要

oneco の Phase 1.5「運用フェーズ」完了をもって、全国 209+ 保護動物サイトの安定収集 + 運用可視化が整った状態をリリースとして告知する。

- **本番稼働中**: Cloud Run (FastAPI) + Vercel (Next.js) + Supabase PostgreSQL
- **自動収集**: 毎日 JST 0:00 に GitHub Actions cron で全国 209+ サイトを巡回
- **公開 URL**: フロントエンド (Vercel) + REST API (Cloud Run)

## このリリースの主要トピック

### 1. 「empty list = 真ゼロ」方針の徹底
旧仕様では「DOM パース成功だが 0 件抽出」を `ParsingError` 扱いし、3 回連続で auto-skip させていた。これにより譲渡完了で動物がいなくなった健全サイトまで止まる false positive が頻発。

PR #35-#36 (`WordPressListAdapter` / `SinglePageTableAdapter` / `PdfTableAdapter`) で「HTML パース成功 + 0 件 = 真ゼロ (= 成功)」に統一。DOM 構造変化による偽陰性は `scripts/zero_count_audit.py` で別途検出する運用に切り替えた。

PR #44 で 4 サイト固有アダプタ (尼崎・岐阜) もこの方針に揃え、サイト別 timeout 拡張 (山梨・高知) も実施。

### 2. DB 制約違反対策 (PR #37, #38)
adapter のフィールド誤割当で長文が `color VARCHAR(100)` / `phone VARCHAR(20)` を超過し、PostgreSQL INSERT 失敗 → トランザクション全体 rollback → サイト全滅していた問題を解消:
- 横須賀「特徴」の長文説明文を adapter 段階で除外
- `DataNormalizer` に `_cap_color()` / `_cap_size()` セーフネットを導入
- `_normalize_phone()` で数字 0 桁時の元文字列フォールバックを排除

### 3. API 入力検証 (PR #38)
`/feeds/archive*` ルートで不正な日付クエリ (例: `?archived_from=not-a-date`) が **HTTP 500** を引き起こしていた問題を **400** にする `_parse_iso_date()` ヘルパで修正。

### 4. PDF ダウンロード DoS 対策 (PR #39)
`PdfTableAdapter._download_pdf` / `PdfFetcher.fetch` を `stream=True` + `iter_content(64KB)` + 20MB サイズ上限ガードに刷新。`Content-Length` 事前 reject + ストリーム中の累積判定で OOM 回避。

### 5. 日付パーサのエッジケース (PR #40)
- 年なし日付 (`12/1` / `12月1日`) で 12 月→1 月クロス時に 1 年ずれる問題: 今日 +30 日を超える未来は前年補完に切替
- `令和0年` を `2018 年` として通過させていた問題: `ValueError` で拒否

### 6. 運用ダッシュボード サイト健全性ページ (PR #42)
`/admin/sites` で全 209+ サイトの健全性 (consec 失敗数 + 最終エラー) を一覧表示。`failing → warning → ok` の順でソートし、運用者が問題サイトを即座に発見できる。

### 7. Slack run サマリアラート (PR #43)
収集 run 終了時に `failure_ratio > 20%` または `critical_sites > 0` の場合に Slack へ Warning/Critical 通知。`SLACK_WEBHOOK_URL` 未設定環境では no-op。

### 8. 日本地図トップページ (M2)
`frontend/components/animals/JapanMap.tsx` で全国 47 都道府県のヒートマップ可視化。Server Component で県別件数 fetch + SVG レンダリング + `og:image` 自動生成。

## 数字で見るリリース内容

| メトリクス | 値 |
|---|---|
| 対応サイト数 | 209+ (全国 47 都道府県) |
| 主力抽出方式 | rule-based (8 基底クラス + 93 サイト固有 adapter) |
| LLM フォールバック | Anthropic Claude / Groq |
| 自動収集頻度 | 毎日 1 回 (JST 0:00) |
| 直近修正 PR 数 | 9 件 (#35-#44) |
| 既知 broken_sites (リセット直後) | 6 → 修正後ゼロ見込み |

## マージ済みコミット (リリース対象)

```
e062941 fix(normalizer): 日付エッジケース修正 (Codex MED #6 + LOW #7) (#40)
fb3ca40 fix(pdf): PDF ダウンロードに 20MB のサイズ上限を導入 (OOM/DoS 防止) (#39)
12ed027 fix: DB 型安全とエラー伝播の改善 (Codex 監査 HIGH×2 + MED×2) (#38)
709f8f6 fix(rule-based): SinglePageTable / PdfTable で empty list を真ゼロ扱い (#36)
32a79c6 fix(yokosuka): 譲渡カテゴリの長文「特徴」を color から除外して DB エラー回避 (#37)
46dc071 fix(rule-based): WordPressListAdapter で detail link 0 件を真ゼロ扱い (#35)
```

## マージ予定 (このリリースに含めるべき)

```
PR #41  chore(broken-sites): 全件リセット (PR #36-#40 効果確認)
PR #42  feat(admin): サイト健全性ページを追加 (M3)
PR #43  feat(notification): run 終了時の Slack サマリアラート (M4)
PR #44  fix(rule-based): broken_sites の DOM 変更/timeout サイトを修正 (M1-2)
```

## 検証手順 (リリース確定までのチェックリスト)

- [x] CI: Lint / TypeCheck / Test / Vercel すべて緑 (#41-44, ※#42 の E2E a11y は preexisting issue)
- [ ] PR #41-44 を main にマージ
- [ ] 翌日 JST 0:00 の自動 run 完了を確認
- [ ] `data/broken_sites.yaml` の自動コミットで残存サイト数を確認 → 理想 0 件
- [ ] `/admin/sites` ページで全 209 サイトが `ok` 状態を確認
- [ ] Slack webhook 未設定環境でも正常終了することを確認

## 残課題 (Phase 2 以降)

### 運用方針の決定が必要
- **譲渡完了 0 件問題**: 「前回 1 件 → 今回 0 件」異常検出が譲渡完了時に false positive を起こす。`zero_count_audit.py` のテキスト検出を収集ループに組み込むか、閾値運用にするか要検討。
- **メンテ画面検出**: HTTP 200 で空 body / Cloudflare チャレンジページ等を検出する仕組みが未実装。

### Phase 2 (クラウドファンディング / OSS 公開) の準備
- OSS 公開: README 整備、CONTRIBUTING、ライセンス、セットアップ手順
- クラウドファンディング: READYFOR / CAMPFIRE 検討、説得材料は本リリースの 209 サイト稼働実績 + ダッシュボード可視化
- 環境省・自治体への提案 (公的機関連携)

## 関連リンク

- Architecture: `ARCHITECTURE.md`
- Roadmap: `.kiro/steering/roadmap.md`
- データ収集設定: `src/data_collector/config/sites.yaml` (209+ サイト定義)
- broken_sites tracker: `data/broken_sites.yaml`
- 監査スクリプト: `scripts/zero_count_audit.py`
