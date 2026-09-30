# oneco v2 運用手順

毎日 JST 0:05 に収集サーバー（手元の Mac の launchd。控えは VPS）が全自治体のページを読み、静的サイトを作り直して Cloudflare Pages に置く。人がやるのは「通知が来た日に見る」「月 1 回 discover を回す」「撤去依頼が来たら台帳を 1 行直す」の 3 つ。

## 1. 初期設定（1 回だけ）

### 1-1. Cloudflare（Workers の静的アセット配信）

2026-09-30 時点、Cloudflare Pages の新規プロジェクトは Workers（static assets）に統合されている（`wrangler pages project create` を叩くと Workers へ deploy される）。配信設定は `ops/wrangler.jsonc`（名前 `oneco`、`site/dist` を丸ごと配信、404 は `404.html`）。

1. 認証: 手元の Mac なら `npx wrangler login`（ブラウザで許可。OAuth が `~/Library/Preferences/.wrangler/config/default.toml` に保存され、以後 `CLOUDFLARE_API_TOKEN` は不要）。別マシンなら My Profile → API Tokens → Create Token → Custom token → `Account / Workers Scripts / Edit` で作り `CLOUDFLARE_API_TOKEN` に入れる（作った直後の 1 回しか表示されない）
2. **Account ID**: `npx wrangler whoami` の表に出る 32 桁。`CLOUDFLARE_ACCOUNT_ID`
3. 初回 deploy: `npx wrangler deploy --config v2/ops/wrangler.jsonc`。URL は `https://oneco.<サブドメイン>.workers.dev`（`oneco.pages.dev` は他人が使っていて取れない）
4. 独自ドメインを付けるなら ダッシュボード → Workers & Pages → oneco → Settings → Domains & Routes → Add → Custom domain（ゾーンが Cloudflare にあれば DNS は自動）
5. `ONECO_PAGES_PROJECT` は Worker 名（`oneco`）。collect.sh はこの名前で `wrangler deploy` する

### 1-2. 収集サーバー

収集を動かす場所は 3 択。2026-09-30 におまえさんが「基本起動している Mac の launchd」を選んだ（1-2a）。VPS（1-2b）は Mac で困ったときの控え。GitHub Actions（`ops/github-daily.yml`）は一部自治体が Azure の IP 帯を拒否するため使わない。GCP（Cloud Run Jobs）は 1 日 10 分なら無料枠に収まるが、旧本番で予算超過→billing 停止になった経緯があり、クラウド IP の拒否も未検証。

### 1-2a. Mac の launchd（本命）

前提: このリポジトリが手元にあり `.venv` に `v2/requirements.txt` が入っていること、Playwright の Chromium が入っていること（`.venv/bin/playwright install chromium`）、Node.js（`brew install node`。wrangler を `npx` で呼ぶ）。

```bash
bash v2/ops/macos/install.sh          # ~/.config/oneco/collect.env を置き、~/Library/LaunchAgents に登録
vi ~/.config/oneco/collect.env        # 1-1 で取った CLOUDFLARE_API_TOKEN / CLOUDFLARE_ACCOUNT_ID / ONECO_PAGES_PROJECT を埋める（chmod 600）
launchctl kickstart -k gui/$(id -u)/com.oneco.collect && tail -f v2/logs/launchd.log   # 1 回手で動かして確認
```

- 毎日 0:05 JST に `ops/collect.sh`（run → notify → build → deploy）が動く。Mac が寝ていて逃した日は起きたときに 1 回動く
- ログは `v2/logs/collect-<日付>.log`。`launchctl print gui/$(id -u)/com.oneco.collect` で状態と last exit code
- 解除は `bash v2/ops/macos/install.sh --remove`
- Claude Code のサンドボックスからは `launchctl` が拒否されるので、登録・手動実行はターミナルから

### 1-2b. VPS（控え）

メモリ 2GB 以上（Playwright の Chromium が 1GB 近く使う）、Ubuntu 22.04/24.04 想定。

```bash
# 実行ユーザー
sudo useradd -m -s /bin/bash oneco

# Python 3.11 + venv
sudo apt install -y python3.11 python3.11-venv git curl
sudo -u oneco git clone https://github.com/9mak/oneco /opt/oneco    # 置き場所は /opt/oneco 固定（service ファイルに書いてある）
cd /opt/oneco && sudo -u oneco python3.11 -m venv .venv
sudo -u oneco .venv/bin/pip install -r v2/requirements.txt

# Playwright（JS 描画が要るページ用。--with-deps で Chromium の共有ライブラリも入る）
sudo -u oneco .venv/bin/playwright install chromium
sudo .venv/bin/playwright install-deps chromium

# wrangler（Cloudflare Pages へのアップロード）に Node.js 20 が要る
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - && sudo apt install -y nodejs
sudo -u oneco npx --yes wrangler --version   # 初回にダウンロードされる

# ログ置き場
sudo mkdir -p /var/log/oneco && sudo chown oneco:oneco /var/log/oneco
```

環境変数は `/etc/oneco/collect.env` に置く（`sudo install -d -m 750 -o root -g oneco /etc/oneco`、ファイルは `0640 root:oneco`）:

```bash
CLOUDFLARE_API_TOKEN=...
CLOUDFLARE_ACCOUNT_ID=...
ONECO_PAGES_PROJECT=oneco
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
HEALTHCHECK_URL=https://hc-ping.com/...
ANTHROPIC_API_KEY=sk-ant-...
ONECO_AI_REPAIR=1
```

systemd:

```bash
sudo cp /opt/oneco/v2/ops/oneco-collect.service /opt/oneco/v2/ops/oneco-collect.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now oneco-collect.timer
systemctl list-timers oneco-collect.timer      # 次回実行時刻
sudo systemctl start oneco-collect.service     # 今すぐ 1 回試す
journalctl -u oneco-collect -f                 # ログ（/var/log/oneco/collect-<日付>.log にも同じものが残る）
```

### 1-3. Discord webhook

通知用チャンネル → チャンネル設定 → 連携サービス → ウェブフック → 新しいウェブフック → URL をコピー。`DISCORD_WEBHOOK_URL`。
試す: `DISCORD_WEBHOOK_URL=... /opt/oneco/.venv/bin/python -m collector notify`（直近の report に異常があれば送る。無ければ「異常なし。送らない」）。

### 1-4. healthchecks（死活監視）

[healthchecks.io](https://healthchecks.io) で Check を 1 つ作る。Period = 1 day、Grace = 3 hours（収集は最長 3 時間）。Ping URL が `HEALTHCHECK_URL`。
collect.sh は全部成功したときだけこの URL を叩き、どこかが失敗した日は `URL/fail` を叩く。0:00 を過ぎても ping が来ない（VPS が落ちた・cron が動かない）と healthchecks からメールが来る。Integrations で Discord にも流せる。

### 1-5. ANTHROPIC_API_KEY（AI 修復）

[console.anthropic.com](https://console.anthropic.com) → API Keys で発行。`/etc/oneco/collect.env` に `ANTHROPIC_API_KEY` と `ONECO_AI_REPAIR=1` を書く。
`ONECO_AI_REPAIR=1` が無いと修復は動かない（キーだけ置いても課金されない）。使うモデルは既定 `claude-sonnet-5`、変えるなら `ONECO_AI_MODEL`。

## 2. 毎日自動で起きること

`ops/collect.sh`（JST 0:00、`oneco-collect.timer`）:

1. `collector run` — 台帳（`registry/sources.yaml`）の `enabled: true` のページを 1 秒間隔で全部読み、`data/animals-<日付>.json` `data/latest.json` `data/report-<日付>.json` を書く
   - ページが読めず `status: failed` になったものは、`ONECO_AI_REPAIR=1` なら **その場で 1 回だけ** Claude にレシピを書き直させる。新レシピで 1 頭以上取れたら `recipes/<slug>.yaml` を上書きして読み直す。取れなければレシピは元のまま、failed のまま
2. `collector notify` — report に異常（failed、または AI がレシピを書き直した）があるときだけ Discord に 1 通。平常時は何も送らない
3. `site/build.py` — `data/latest.json` から `site/dist/` を作る
4. `wrangler pages deploy` — `site/dist/` を Cloudflare Pages へ
5. 全部成功したら `HEALTHCHECK_URL` へ ping

途中で失敗しても止まらない。収集が全滅した日でも `data/latest.json` は前日のものが残っているので、サイトは「昨日のまま」出続ける（落ちない）。

## 3. 通知が来た日の見方

Discord の文面はこの形:

```
読めなかった自治体 2 件
- 徳島県動物愛護管理センター（譲渡犬）: follow: 'iframe#animalFrame@src' が見つからない (https://…)（AI 修復に失敗: 新レシピでも 0 頭（行 3・捨てた 3））
- 佐賀県（保護犬猫）: HTTP 404: https://…
AI がレシピを書き直した自治体 1 件（recipes/<slug>.yaml が変わっている。中身を確認して repo に反映する）
- 三重県動物愛護管理センター（迷い犬情報）: AI がレシピを書き直した（4 頭）
（公開 812 頭・成功 198 ページ）
```

| 行 | 意味 | やること |
| --- | --- | --- |
| `読めなかった自治体 N 件` | その日その自治体の子はサイトに出ていない（前日分も消えている） | 1 日目は放置でよい（自治体側の一時障害が多い）。2 日続いたら下の手順 |
| `HTTP 404` / `HTTP 5xx` / `ConnectError` | ページ自体が無い・落ちている | ブラウザで URL を開く。移転していれば台帳の `url` を直す。掲載をやめたなら `mode: link_only` か `enabled: false` |
| `robots.txt により拒否` | 自治体が bot を断っている | 読まない。`enabled: false` にして、必要なら電話で確認 |
| `follow: '…' が見つからない` / `0 頭で empty_text も無い` | ページ構造が変わった。AI 修復も失敗している | VPS で `sudo -u oneco env $(sudo cat /etc/oneco/collect.env | xargs) /opt/oneco/.venv/bin/python -m collector repair <slug> --show` を手で回す。それでも駄目なら `collector show <slug>` と `collector fetch <url> --selectors` を見て `recipes/<slug>.yaml` を人が直す（書き方は `docs/RECIPE.md`） |
| `AI がレシピを書き直した自治体 N 件` | VPS 上の `recipes/<slug>.yaml` が変わり、読めるようになった | VPS の `git -C /opt/oneco diff v2/recipes` を見て、妥当なら commit して push（放置すると次の `git pull` で戻る）。取り方が変（写真が広告、頭数が異常）なら `git checkout` で戻して人が直す |
| `（公開 N 頭・成功 M ページ）` | その日の全体 | 前日と大きく違えば異常。`data/report-<日付>.json` を見る |

通知が来ない日 = 全ページ読めた日。healthchecks から「ping が来ない」メールが来たら VPS 自体を見る（`systemctl status oneco-collect.timer`、`journalctl -u oneco-collect --since yesterday`）。

## 4. 月 1 回: `collector discover`（新しい自治体を拾う）

環境省の「収容動物の情報を掲載している自治体リンク先一覧」と台帳を突き合わせる。

```bash
cd /opt/oneco/v2   # ローカルでもよい
/opt/oneco/.venv/bin/python -m collector discover
```

出力:

- `台帳に無いドメイン N 件` — 候補。1 つずつブラウザで開き、犬猫の一覧ページなら台帳に足す
- `台帳にあるがリンク集に無いドメイン N 件` — リンク集の網羅漏れが多い。自治体が掲載をやめていたら `enabled: false`

台帳に足す手順（1 自治体 = 1 ページ = 1 エントリ。譲渡と収容が別ページなら 2 エントリ）:

1. `registry/sources.yaml` の末尾に追記。`slug` は `<ドメインの主部>-<連番>`（例 `pref_saga-1`）で重複しないこと。`kind`（adoption / sheltered / stray）、`species`（dog / cat / mixed）、電話・所在地はページの問い合わせ欄から人が書き写す
   ```yaml
   - slug: city_example-1
     name: 例市動物愛護センター（譲渡犬猫）
     municipality: 例市動物愛護センター
     prefecture: 例県
     phone: 000-000-0000
     address: 例県例市…
     url: https://www.city.example.lg.jp/animal/list.html
     kind: adoption
     species: mixed
     mode: recipe
     recipe: recipes/city_example-1.yaml
     enabled: true
   ```
2. レシピを作る。まず AI に書かせる: `ANTHROPIC_API_KEY=... python -m collector repair city_example-1 --show`（レシピが無い slug は新規作成になる。1 頭以上取れた時だけ保存される）。駄目なら `python -m collector fetch <url> --selectors` で表・リストの候補を見て `docs/RECIPE.md` の通り手で書く
3. `python -m collector show city_example-1` で取れた行・捨てた行を確認。写真・性別・収容日が合っていること
4. `python -m pytest tests -q`（台帳とレシピが読めることを確認するテストが入っている）
5. commit → push → VPS で `git -C /opt/oneco pull`。翌日 0:00 から載る。すぐ載せたいなら `sudo systemctl start oneco-collect.service`

## 5. 撤去依頼が来たら

自治体から「掲載をやめてほしい」と来たら、`registry/sources.yaml` のその自治体のエントリを `enabled: false` にして push、VPS で `git pull`。翌日 0:00 の収集でその自治体の子は `latest.json` から消え、サイトも消える。その日のうちに消したいなら `sudo systemctl start oneco-collect.service` で即時に作り直す。

エントリを消さず `enabled: false` にするのは、二度と載せない記録を残すため。返信では「翌日 0:00 までに消えます」と伝える。

## 6. 費用の見込み（概算・未検証）

| 項目 | 月額 |
| --- | --- |
| 収集サーバー（本命は手元の Mac の launchd） | 0 円 |
| 控え: VPS 2GB（さくらのVPS / ConoHa / Vultr など） | 1,000〜1,500 円 |
| 控え: GCP Cloud Run Jobs（1 日 10 分・2GB。無料枠 vCPU 18 万秒/月の内側） | 0〜100 円（billing の再有効化が要る） |
| Cloudflare Pages（Free プラン。静的配信・独自ドメイン込み） | 0 円（Direct Upload は 1 日 500 デプロイまで、1 日 1 回なので余裕） |
| healthchecks.io（Free、20 checks まで） | 0 円 |
| Discord webhook | 0 円 |
| Anthropic API（AI 修復） | 1 回あたり入力 3〜6 万トークン・出力 1 千トークン前後。claude-sonnet-5（入力 $2 / 出力 $10 per 1M）で 1 回 15〜30 円程度。壊れるのは月に数ページなので通常 100〜500 円。サイト改修が重なる年度替わり（4 月）に 1 日 10 件走っても 1 日 300 円が上限目安 |
| 合計（Mac で動かす場合） | 100〜500 円（AI 修復の分だけ） |

Anthropic のコンソールで Usage limits に月 $10 程度の上限を入れておくと、暴走しても止まる。
