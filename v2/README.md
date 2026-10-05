# oneco v2

全国の自治体が公開している保護犬猫を 1 か所で探せて、その自治体に連絡できる場所。

設計の原則（2026-09-28 決定）:

- 個体を追跡しない。毎日「今日その自治体にいる子の集合」を作り、公開はその日の分だけ
- DB も API サーバーも持たない。日次 JSON と静的サイトだけ
- 読み方はコードでなく「レシピ」（`recipes/*.yaml`）。壊れたときと新規のときだけ AI に書かせる
- 電話・所在地・都道府県・区分は台帳（`registry/sources.yaml`）の固定値。ページからは読まない
- 失敗した日は「昨日のサイトがそのまま出続ける」。サイトが落ちることはない
- 通知は異常のある日だけ 1 通

## ディレクトリ

```
v2/
  registry/sources.yaml   台帳（自治体・ページ・区分・電話・所在地）
  recipes/<slug>.yaml     ページごとの読み方（手順書）
  collector/              レシピ実行エンジンと CLI
  site/                   静的サイト生成
  data/                   日次 JSON（git 管理外、収集サーバーと配信元に置く）
  tests/
  docs/RECIPE.md          レシピの書き方
```

## 使い方

```bash
# 依存: python 3.11、httpx、beautifulsoup4、lxml、pyyaml、pdfplumber（PDF）、playwright（JS 描画）
PY=/Users/k/Desktop/oneco/.venv/bin/python
cd v2
$PY -m collector show douai_tokushima-2          # 1 ページを読んで結果を表示（デバッグ）
$PY -m collector fetch https://example.jp/ --text  # ページを取って本文を表示
$PY -m collector run --date 2026-09-28            # 全ページ収集 → data/animals-2026-09-28.json, data/latest.json, data/report-*.json
$PY -m collector run --only pref_saga             # slug の前方一致で絞る
$PY site/build.py                                  # data/latest.json → site/dist/（-m site.build は標準ライブラリの site と衝突して使えない）
$PY -m collector discover                          # 環境省リンク集と台帳の差分
$PY -m collector notify                            # 直近の report を見て異常があれば Discord へ
$PY -m collector repair <slug>                     # 読めなくなった slug のレシピを Claude に書き直させる（ANTHROPIC_API_KEY 必須）
```

日次運用（VPS の systemd、Cloudflare Pages、通知、AI 修復、費用）は `docs/OPERATIONS.md`。運用部品は `ops/`。

## データ（animals JSON）

```json
{
  "date": "2026-09-28",
  "animals": [
    {
      "id": "a1b2c3d4e5f6",
      "source": "douai_tokushima-2",
      "municipality": "徳島県動物愛護管理センター",
      "prefecture": "徳島県",
      "phone": "088-636-6122",
      "address": "…",
      "kind": "adoption",            // adoption=里親募集 sheltered=保護中 stray=迷子（飼い主不明のまま保護） lost=探してます（飼い主が探している迷子）
      "species": "dog",              // dog | cat | other（犬猫以外） | null（種別なし: 自治体のページで犬か猫か決められない子。サイトでは犬・猫の絞り込みに出ない）
      "image_url": "https://…/photo2-1.JPG",   // 無いこともある（その場合 management_no か shelter_date がある）
      "source_url": "https://…",     // 個体ページがあればそれ、なければ一覧ページ
      "name": null, "sex": "メス", "age": null, "breed": null,
      "management_no": null, "shelter_date": null, "note": null
    }
  ],
  "sources": [ {"slug": "…", "status": "ok|empty|failed", "count": 10, "error": null} ]
}
```

ID は `source | image_url` のハッシュ。写真が無ければ `source | management_no`、それも無ければ `source | name | shelter_date`。同じ子は翌日も同じ ID になる。
