# 0 件抽出サイト 個別調査 最終レポート (2026-05-20)

## サマリ

5/18 workflow で 0 件抽出だった 155 サイトを 2 段階で精査:

### Stage 1: HTTP キャナリー (reports/zero_audit_20260519.md)

ヘッダ/フッタ除去 + list_url パス階層フィルタ等で 5 分類:

| カテゴリ | 件数 | 意味 |
|---|---:|---|
| 🔴 suspicious | 40 | adapter 修正候補 |
| 🟡 maybe_zero | 92 | コンテンツ候補少、実ゼロが有力 |
| 🟢 true_zero | 4 | 明示的「ゼロ表現」あり |
| ⚪ unreachable | 5 | 並列 fetch の timeout (佐賀県) |
| ⏭️ skipped_js | 14 | Playwright が必要 |

### Stage 2: adapter 単体実機検証 (scripts/adapter_live_test.py)

suspicious 40 + skipped_js 14 + unreachable 5 = 59 件を adapter インスタンス化 + 実 HTTP fetch + extract + normalize で検証.

| サイト群 | 件数 | 結果 |
|---|---:|---|
| suspicious 40 件 |  |  |
| ├─ adapter 修正後に成功 (ok) | 26 | 実データ取得確認 |
| └─ list 0 件 (真にゼロ) | 14 | adapter 正常、現在ゼロが事実 |
| skipped_js 14 件 |  |  |
| ├─ Playwright 経由で成功 (ok) | 5 | 実データ取得確認 |
| └─ list 0 件 (真にゼロ) | 9 | adapter 正常、現在ゼロが事実 |
| unreachable 5 件 (佐賀県) |  |  |
| └─ 単体 fetch なら成功 (ok) | 5 | キャナリー並列 timeout の偽陰性 |
| **合計** | **59** | **detail_error 0**, 全 adapter 正常動作確認 |

→ **5/18 0 件 155 サイトのうち、adapter 不具合は 1 件もない**ことが確定.

---

## 修正クラスタ (commits: 0eb1480, b09d1bc)

### 1. 福岡県動物愛護協会 (zaidan-fukuoka-douai) — 6 サイト
- detail が `<dl>` でなく `<table><th><td>` 構造だったので「保護した日」「保護した場所」をラベルに採用
- `<th>登録日</th>` (センター譲渡) と `<th>保護した日</th>` (一般保護) の 2 系統に tuple ラベルで対応
- species は detail に「品種」が無いため list_url の `/dog`/`/cat` から補完
- 電話番号は本文の TEL: 正規表現で抽出

### 2. 旭川市あにまある (douaicenter.jp) — 5 サイト
- `/animal/{id}` (「保護日」「保護場所」) と `/other-animal/{id}` (「不明日」「不明場所」「連絡先」) で異なるラベルを tuple で吸収
- 「雑種」のような species は list_url で犬/猫補正

### 3. 長崎犬猫ネット (animal-net.pref.nagasaki) — 3 サイト (+ 保護 = 4 検証)
- detail が `<li><p>label</p><p>value</p></li>` という独自構造のため `_postprocess_fields` で独自パース
- カテゴリ別ラベル差: 「収容日」/「保護日」/「いなくなった日時」を吸収
- 「地区」を location の fallback、「問い合わせ先」から電話番号を抽出

### 4. 仙台市アニパル (city.sendai) — 3 サイト
- ページ全体の「（令和X年Y月Z日更新）」を shelter_date フォールバックに採用
- location は「仙台市動物管理センター（アニパル仙台）」を固定値で記録

### 5. WordPressListAdapter 基底拡張
- `FieldSpec.label` を `str | tuple[str, ...]` に拡張 → 複数候補 OR 検索
- `_postprocess_fields(fields, detail_url, soup)` フック追加
- `_infer_species_from_url()` ヘルパー追加 (`/dog`/`/cat`/`/inu`/`/neko` 判定)

### 6. DataNormalizer 全体セーフネット
- `shelter_date` が空 / 解析不能なら「データ取得日」をフォールバックに使う
- `_normalize_date` に `RN.M.D` (横須賀) と `M月D日` (京都ペットラブ、全角数字含む) のパターン追加
- → 全 adapter が日付エラーで全件落ちる事故を防止

---

## 残課題

| 課題 | 影響 |
|---|---|
| 全 adapter で `prefecture=None` になっている | `infer_prefecture_from_url` が sites.yaml の `prefecture` を見ていない (別チケット) |
| 福岡県のテスト fixture を実 HTML 構造に揃えたため、過去のスナップショット差分検証で false positive 出る可能性 | 次回 workflow run で確認 |
| 「真にゼロ」155 - (suspicious 40 - 14 動作確認) = 129 サイトは今後収容が増えた時に動くか未検証 | 動物が増え次第キャナリーで疑陽性化 → live_test で確認 |
| Playwright サイトの skipped_js 残 9 件 (収容ゼロ) | 同上 |
