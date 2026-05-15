# 209サイト → ルールベース移行 テンプレート集約解析

**実施日**: 2026-05-15
**目的**: Path A (完全 rule-based 化) の工数見積もりとロードマップ策定

## サマリー

- 209サイトは **92個のユニークテンプレート** に集約可能
- (domain × single_page × requires_js × pdf) の signature でグループ化
- **総工数見積**: 約 92時間 (テンプレート数ベース)
- **Top 30 adapters で 62% カバー** → 段階リリース戦略可能

## 累積カバレッジ

| #adapters | sites covered | coverage |
|----:|----:|---:|
| 5 | 36 | 17.2% |
| 10 | 65 | 31.1% |
| 15 | 86 | 41.1% |
| **20** | **103** | **49.3%** |
| **30** | **130** | **62.2%** |
| 40 | 150 | 71.8% |
| **50** | **167** | **79.9%** |
| 60 | 177 | 84.7% |
| 70 | 187 | 89.5% |
| 80 | 197 | 94.3% |
| 92 | 209 | 100.0% |

## 種別ごとの分布

| 種別 | サイト数 | 想定工数/テンプレ | 既存資産 |
|---|---:|---|---|
| standard (list+detail) | 44 | 45-90 min | KochiAdapter (798行) |
| single_page | 129 | 30-60 min | 新規パターン必要 |
| requires_js (Playwright) | 25 | 90-180 min | Playwright runner 既存 |
| PDF | 11 | 60-120 min | PdfFetcher 既存 |

## Top 30 テンプレート（実装優先順）

| # | ドメイン | サイト数 | 種別 |
|--:|---|--:|---|
| 1 | www.zaidan-fukuoka-douai.or.jp | 8 | standard |
| 2 | www.kumamoto-doubutuaigo.jp | 8 | requires_js |
| 3 | www.douaicenter.jp | 8 | standard |
| 4 | www.pref.saga.lg.jp | 6 | single_page |
| 5 | www.aniwel-pref.okinawa | 6 | requires_js |
| 6 | www.yokosuka-doubutu.com | 6 | standard |
| 7 | www.city.chiba.jp | 6 | single_page |
| 8 | www.pref.yamanashi.jp | 6 | single_page |
| 9 | www.pref.fukushima.lg.jp | 6 | single_page |
| 10 | www.pref.chiba.lg.jp | 5 | single_page |
| 11 | www.pref.kyoto.jp | 5 | single_page |
| 12 | www.pref.kagawa.lg.jp | 4 | pdf_link |
| 13 | animal-net.pref.nagasaki.jp | 4 | standard |
| 14 | www.wannyan.city.fukuoka.lg.jp | 4 | requires_js |
| 15 | www.city.miyazaki.miyazaki.jp | 4 | single_page |
| 16 | www.pref.kanagawa.jp | 4 | single_page |
| 17 | www.city.osaka.lg.jp | 4 | single_page |
| 18 | douai-tokushima.com | 3 | requires_js |
| 19 | oita-aigo.com | 3 | single_page |
| 20 | www.douai.pref.tochigi.lg.jp | 3 | standard |
| 21 | www.pref.gunma.jp | 3 | single_page |
| 22 | www.city.koshigaya.saitama.jp | 3 | single_page |
| 23 | www.city.machida.tokyo.jp | 3 | single_page |
| 24 | www.city.yokohama.lg.jp | 3 | single_page |
| 25 | www.city.kawasaki.jp | 3 | single_page |
| 26 | www.city.nagoya.jp | 3 | single_page |
| 27 | www.city.sendai.jp | 3 | single_page |
| 28 | www.city.takamatsu.kagawa.jp | 2 | standard |
| 29 | www.pref.ehime.jp | 2 | single_page |
| 30 | www.city.kitakyushu.lg.jp | 2 | single_page |

## 長尾分析

- 2サイト以上のテンプレ: **47グループ** (実装すれば 164 sites = 78% カバー)
- 1サイトのみのテンプレ: **45グループ** (残り 45 sites = 21%, 工数の半分を占める)

## 推奨ロードマップ

```
Phase A2 (基底クラス整備, 4-8h):
  - WordPressListAdapter (jaidan-fukuoka-douai 等)
  - SinglePageTableAdapter (pref.*.jp 系の共通テーブル)
  - PlaywrightAdapter (kumamoto, aniwel-pref.okinawa 等)
  - PdfTableAdapter (pref.kagawa.lg.jp 等)

Phase A3a (Top 30 = 62%カバー, 30h):
  - 高ボリューム順に実装、TDD で snapshot テスト

Phase A3b (Top 60 = 85%カバー, 30h):
  - 中ボリューム実装、共通パターンの抽出を継続

Phase A3c (長尾 = 100%カバー, 30h):
  - 1サイトテンプレを順次潰す
  - ここが消化試合、根性勝負

Phase A4 (統合 + リリース, 4h):
  - sites.yaml extraction を全 rule-based に
  - LLM provider をオプション fallback に格下げ
  - リリース！
```

## リスク

- **長尾 45テンプレが工数の半分** = 90% 達成後のラストワンマイルが重い
- **requires_js 25サイト** = Playwright のメンテも継続的に必要
- **HTML drift** = 実装した adapter が壊れる頻度（推定 10-20% / 年）

## 次のアクション

1. Kiro spec init: `data-collector-rule-based-migration`
2. Phase A2 で基底クラス整備
3. Phase A3a で Top 30 を実装
