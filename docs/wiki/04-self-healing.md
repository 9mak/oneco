# 自己修復ループ（auto-fix-adapter）

サイト側の HTML 変更で adapter が壊れたとき、検知 → LLM による修復 PR 作成 → 自動マージまでを無人で回す仕組み。**rule-based 抽出 100% を維持し、LLM（Groq）は修理工としてのみ使う**のが設計方針。

## 3フェーズ構成

```
Phase 1: 検知               data-collector.yml (毎日の収集ラン内)
   ├ BrokenSitesTracker     連続失敗（閾値3でスキップ対象化）
   ├ SiteBaselineTracker    ゼロ件回帰（過去≥1件 → 今0件）
   └ FieldQualityTracker    フィールド欠損率ドリフト
        │ _trigger_auto_fix() が対象サイトを集約 [__main__.py]
        ▼
Phase 2: 修復               auto-fix-adapter.yml (workflow_dispatch)
   scripts/auto_fix_adapter.py
   ├ Groq (llama-3.3-70b-versatile) にパッチ生成を依頼
   ├ 二重ガード: ユニットテスト通過 + live test で改善を定量確認
   ├ 通過 → fix/auto-* ブランチで `auto-fix` ラベル付き PR 作成
   └ 失敗 → Issue 起票
        ▼
Phase 3: 自動マージ          auto-merge-fix-pr.yml
   `auto-fix` ラベル PR に CI green 後の squash auto-merge を有効化
```

## Phase 1 → 2 の安全弁（`__main__.py`）

| 環境変数 | 既定 | 役割 |
|---|---|---|
| `ONECO_AUTO_FIX_ENABLED` | `false` | kill switch。false なら dispatch しない |
| `ONECO_AUTO_FIX_DRY_RUN` | `true` | true なら検知ログのみ |
| `ONECO_AUTO_FIX_MAX_SITES` | `3` | 1ランで dispatch する最大サイト数 |

dispatch は `gh workflow run auto-fix-adapter.yml` で行い、dedup・best-effort（失敗しても収集ランは続行）。

## Phase 2 の実装ポイント（`scripts/auto_fix_adapter.py`）

- **SEARCH/REPLACE 方式**: LLM の応答は `<<<<<<< SEARCH ... >>>>>>> REPLACE` ブロック形式。unified diff の行番号幻覚で全失敗した経緯があり、PR #232 でこの方式に変更して解消
- **TPM 対策**: HTML を 6000 字に圧縮して Groq 無料枠（TPM 12,000）に収める（PR #231）
- **二重ガード**: ① `run_unit_tests()` でユニットテスト通過、② `scripts/adapter_live_test.py` の `measure()` で実サイトに対する抽出件数の改善を定量確認。両方通らないと PR を作らない

## token の注意点

`GITHUB_TOKEN` で作ったイベントは GitHub の recursion prevention により後続 workflow を発火できない。そのため Phase 1 → 2 の dispatch は `ONECO_AUTO_FIX_TOKEN`（PAT / App token）を優先使用する（`data-collector.yml`）。

## 運用トグル・障害対応

段階リリースのトグル操作と、暴走時の止め方は [docs/RUNBOOK.md](../RUNBOOK.md) を参照。
