# 自己修復ループ（撤去済み）→ 半自動構造診断（T406）

サイト側の HTML 変更で adapter が壊れたとき、旧来は「検知 → LLM による修復 PR 作成 → 人によるマージ」の無人ループ（`auto-fix-adapter.yml` + `scripts/auto_fix_adapter.py`）を回していたが、**2026-09 (T406) に dispatch を停止し、人が10分で読める構造診断を Phase 2 の代わりに導入した**。

## なぜ LLM 自動修復を停止したか

- `_trigger_auto_fix()`（旧 `__main__.py`）経由の dispatch は 48 run 動かして **修復 PR 0 件**（project_self_healing memory, T150）。
- 自動マージ (`auto-merge-fix-pr.yml`) はこれ以前の 2026-09-08 に既に撤去済み（48 回起動して PR 0 件という実績に対し、`auto-fix` ラベルだけでレビュー無し本番デプロイに到達する経路を残す価値がなかったため）。
- つまり「検知 → LLM 修復」ループは Phase 1 (検知) までしか価値を出しておらず、Phase 2 (LLM 修復) は稼働コストだけを払い続けていた。

`scripts/auto_fix_adapter.py` 自体は削除せずファイルとして残す（将来 Groq モデル精度が上がった時の再評価用）が、`data-collector.yml` からの dispatch (`ONECO_AUTO_FIX_*` 環境変数・`gh workflow run auto-fix-adapter.yml` 呼び出し) は撤去した。`.github/workflows/auto-fix-adapter.yml` も手動 workflow_dispatch 専用として残しているが、収集パイプラインからは呼ばれない。

## 現行フロー: 検知 → 半自動診断 → 人が直す

```
Phase 1: 検知               data-collector.yml (毎日の収集ラン内、変更なし)
   ├ BrokenSitesTracker     連続失敗（閾値3でスキップ対象化）
   ├ SiteBaselineTracker    ゼロ件回帰（過去≥1件 → 今0件）
   └ FieldQualityTracker    フィールド欠損率ドリフト
        │ diagnose_sites() が対象サイトを集約 [infrastructure/diagnosis.py]
        ▼
Phase 2: 構造診断            同一 run 内、追加 GET 1 回/サイトのみ
   infrastructure/diagnosis.py
   ├ SiteAdapterRegistry 経由で adapter class を解決し、
   │ LIST_LINK_SELECTOR / ROW_SELECTOR / NEXT_PAGE_SELECTOR /
   │ FIELD_SELECTORS / HEADER_FIELDS を現在のページに対して評価
   ├ HTTP status / リダイレクト / charset を記録
   ├ 直前 snapshot の動物 URL が現ページにまだ含まれるか確認
   └ 全チェック失敗時は候補ラベル (`<th>`/`<dt>` 頻度上位) と
     候補リンクパターンをその場で提示
        ▼
Phase 3: 人が直す
   Discord にコンパクトな要約（1サイト最大15行・1run最大5サイト、
   残りは reports/diagnosis/ の artifact を参照）が届く。
   人が selector/label を10分程度で特定してコード修正 → 通常の PR フロー。
```

## 診断の kill switch

| 環境変数 | 既定 | 役割 |
|---|---|---|
| `ONECO_DIAGNOSIS_ENABLED` | `true` | false なら診断・追加 GET を一切行わない |

診断は検知サイト最大5件/run（それ以上は次回 run 持ち越し）。ネットワーク断・HTTP エラー・タイムアウト由来の検知は HTTP status 自体が原因を語るため診断対象から除外する（`_is_selector_diagnosable_error`。2026-07 に山梨県のネットワーク断続エラーが旧 auto-fix の日次枠を2週間占有し、本当に壊れていた柏市・群馬に修理が回らなかった反省を踏襲）。

## artifact / 通知

- Discord: `NotificationClient.send_alert` で WARNING レベル通知（`build_discord_summary`）
- 全件: `reports/diagnosis/diagnosis_<timestamp>.json` (機械可読) / `.md` (人が読む全件)

## 旧実装の参考情報

- `scripts/auto_fix_adapter.py`: SEARCH/REPLACE 方式のパッチ生成、Groq TPM 対策、二重ガード（ユニットテスト + live test 定量確認）の実装は残したまま。再稼働させる場合は dispatch を `__main__.py` / `data-collector.yml` に再度配線する必要がある。
- `.github/workflows/auto-fix-adapter.yml`: 手動 `workflow_dispatch` では引き続き実行可能（1サイトを指定して人が明示的に試す用途）。
