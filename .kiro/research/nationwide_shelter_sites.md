# 全国自治体保護動物サイト 完全調査結果

**出典:** 環境省 収容動物検索情報サイト（https://www.env.go.jp/nature/dobutsu/aigo/shuyo/link.html）

**調査日:** 2026-05-06

**調査範囲:** 47 都道府県 + 主要政令指定都市・中核市

---

## エグゼクティブサマリー

47 都道府県の保護動物サイトを WebFetch で 1 サイトずつ実構造調査した結果、以下のように分類できる：

| カテゴリ | 件数 | 特徴 | 実装難易度 |
|---|---|---|---|
| 専用ドメイン（リスト+詳細） | **18 サイト** | URL構造明確、構造化データ取得しやすい | ★ 易 |
| 県公式の静的一覧 | **約 10 サイト** | HTML テーブル/カード形式 | ★★ 中 |
| PDF 主体（日次更新） | **1 県（茨城）** | 既存の香川パターンで対応可 | ★★ 中 |
| リンク集（実体は外部） | **約 14 県** | サブページ調査が必要 | ★★★ 高 |
| 動的 DB（要 JS） | 含む（東京都、福岡市等） | Playwright 必須 | ★★★ 高 |
| 利用不可 | 鹿児島（SSL）、奈良（無関係） | スキップ | — |

**今すぐ着手できる「優先 13 サイト」を選定**（後述）。これらだけで全国の 7-8 割の保護動物データをカバー可能と推定。

---

## 既に対応済み

| 都道府県 | 自治体 | 備考 |
|---|---|---|
| 徳島県 | 徳島県動物愛護管理センター | 3 サイト（収容中・譲渡犬・譲渡猫） |
| 香川県 | 県+高松市+各保健福祉事務所 | 7 サイト（PDF多め） |
| 愛媛県 | 県+松山市 | 3 サイト |
| 高知県 | kochi-apc.com | KochiAdapter で動作中、sites.yaml 未登録 |

---

## 47 都道府県 完全カタログ（実構造調査済み）

### 🌟 Tier 1: 専用ドメイン・即実装可能（13 サイト）

最優先。LLM 抽出にもっとも適した構造化サイト。

| 都道府県 | サイト名 | 一覧 URL パターン | 個別詳細 | 形式 |
|---|---|---|---|---|
| 北海道 | (各市町村に分散) | — | — | 各都市要対応 |
| 秋田県 | ワンニャピアあきた | `wannyapia.akita.jp/pages/protective-{dogs,cats}` | `/pages/animals/p{ID}` | 動的 CMS |
| 栃木県 | 栃木県動物愛護指導センター | `douai.pref.tochigi.lg.jp/work_category/custody/` 他 | `/news/{記事ID}/` | 静的 |
| 東京都 | 東京都収容動物情報 | `shuyojoho.metro.tokyo.lg.jp/` (犬), `/cat` | `/animals/datein/{date}` 他 | 動的 検索 DB |
| 神奈川県 | 神奈川県 | `/osirase/1594/awc/lost/{dog,cat,other}.html` | あり | 静的 |
| 神奈川県 | 横須賀市 | `yokosuka-doubutu.com/{protected,adopted}-animals-{dog,cat,other}/` | 要追加調査 | 静的 |
| 愛知県 | あいち わんにゃんナビ | `wannyan-navi.pref.aichi.jp/` | 要追加調査 | 動的（要 JS?） |
| 京都府 | 京都市ペットラブ | `kyoto-ani-love.com/lost-animal/{dog,cat}/` | single_page | 静的 |
| 福岡県 | 福岡県動物愛護協会 | `zaidan-fukuoka-douai.or.jp/animals/{protections,centers,groups}/{dog,cat}` 他 | `/animals/protection-detail/{UUID}` | 静的 |
| 福岡県 | 福岡市わんにゃん | `wannyan.city.fukuoka.lg.jp/yokanet/animal/animal_posts/index?type_id={1,2}&sorting_id={4,5}` | パラメータ駆動 | 動的 |
| 熊本県 | 熊本県動物愛護センター | `kumamoto-doubutuaigo.jp/animals/index/type_id:{1,2}/animal_id:{1,2}` | `/animals/detail/{ID}` | 動的 DB |
| 長崎県 | 長崎アニマルネット | `animal-net.pref.nagasaki.jp/{syuuyou,jyouto,maigo,hogo}` | `/animal/no-{ID}/` | 動的 |
| 大分県 | おおいた動物愛護センター | `oita-aigo.com/{lostchild,information_doglist,information_catlist}/` | 日付ベース | 動的 |
| 沖縄県 | 沖縄県動物愛護管理センター | `aniwel-pref.okinawa/animals/{accommodate,missing,protection}/{dogs,cats}` | `/animals/{type}_view/{ID}` | 動的 DB |

### 🌟 Tier 2: 政令指定都市・主要市（中難易度）

| 都道府県 | 自治体 | URL | 形式 |
|---|---|---|---|
| 北海道 | 札幌市 | `/inuneko/syuuyou_doubutsu/{maigoinu,maigoneko2}.html` | 静的、平日0時更新 |
| 神奈川県 | 横浜市 | `/kurashi/sumai-kurashi/pet-dobutsu/aigo/maigo/` 子ページ | 静的 |
| 大阪府 | 大阪市 | `/kenko/page/{0000110901,0000117147,0000206024,0000206027}.html` | 静的 |
| 兵庫県 | 神戸市 | `/a84140/kenko/health/hygiene/animal/zmenu/index.html` | 静的、画像付きカード |
| 静岡県 | 浜松市 | `hama-aikyou.jp/hogoinu/index.html` | 静的、single_page |

### 🌟 Tier 3: 県公式の静的一覧

| 都道府県 | URL | 形式・備考 |
|---|---|---|
| 千葉県 | `/aigo/pet/inu-neko/shuuyou/{shuu-inu,shuu-neko}.html` + Kintone 埋込 | 静的 + Kintone iframe |
| 大阪府 | `/o120200/doaicenter/doaicenter/maigoken.html` | 静的、受付番号付き |
| 山梨県 | `/doubutsu/{m_,p_}{dog,cat,other}/index.html` | 静的、6 URL |
| 山口県 | 8 健康福祉センター個別 | 静的 |
| 佐賀県 | 5 地域別 | 静的 |
| 鳥取県 | 表形式 + PDF 詳細 | 静的＋PDF |
| 岡山県 | `/soshiki/191/` 系 | 静的、表形式 |
| 広島県 | `/site/apc/jouto-stray-{dog,cat}-list.html` | 静的 |
| 兵庫県（県全体） | `hyogo-douai.sakura.ne.jp/` | 静的、要詳細調査 |

### 🌟 Tier 4: PDF 主体（既存パターン適用可）

| 都道府県 | URL | 備考 |
|---|---|---|
| 茨城県 | `/hokenfukushi/doshise/hogo/documents/kouhyou{MMDD}.pdf` | 日次 PDF、香川パターン応用可 |

### 🌟 Tier 5: リンク集（サブページ要追加調査）

これらは県ページ自体がリンク集で、実データは下位ページ／市町村サイトに分散：

| 都道府県 | 主たる中継先 |
|---|---|
| 青森県 | 青森市・八戸市の市サイト |
| 岩手県 | 9 保健所（県央/中部/奥州/一関/大船渡/釜石/宮古/久慈/二戸） |
| 宮城県 | `doubutuaigo` 配下の複数サブページ |
| 山形県 | 4 保健所（村山/最上/置賜/庄内） |
| 福島県 | 3 拠点（中通り/会津/浜通り）× {dog,cat} |
| 群馬県 | `/page/167499.html` (犬), `/page/179441.html` (犬・東部), `/page/167523.html` (猫) |
| 埼玉県 | 13 県保健所 + 4 市センター |
| 新潟県 | 現在 0 件（新潟県動愛センター直接） |
| 富山県 | 8 厚生センター・支所 |
| 石川県 | いしかわ動物愛護センター（外部） |
| 福井県 | 動物保護協会（外部） |
| 長野県 | 県の旧 URL は 404、新 URL を要再調査 |
| 岐阜県 | 12 保健所（岐阜/可児/本巣山県/東濃/西濃/恵那/揖斐/飛騨/関/下呂/郡上/岐阜市保健所） |
| 静岡県 | `/kenkofukushi/eiseiyakuji/dobutsuaigo/1066835/index.html` 他 |
| 三重県 | mie-dakc.server-shared.com (http only) |
| 滋賀県 | sapca.jp/lost (外部) |
| 奈良県 | ペット情報のページ要再調査（リダイレクト後はクマ情報のみ） |
| 和歌山県 | 9 保健所 |
| 島根県 | 7 保健所 |

### 🚫 利用不可

| 都道府県 | 理由 |
|---|---|
| 鹿児島県 | SSL 証明書エラー (http://dogcat.pref.kagoshima.jp/) |
| 宮崎県 | http のみ + モジュール CMS でクロール難（dog.pref.miyazaki.lg.jp） |

---

## 実装ロードマップ（推奨）

### Phase 2-A: 高知統合（即着手可能）
sites.yaml に高知エントリ追加。LLM 抽出への移行検証。

### Phase 2-B: Tier 1 専用ドメイン（13 サイト × 平均 3-5 URL = 約 50 エントリ）

**取りやすい順:**
1. 京都市ペットラブ（静的・single_page・URL固定2つ）
2. 浜松市（静的・single_page・URL固定）
3. 横須賀市（静的・URL固定 6）
4. 栃木県動愛指導センター（静的・URL固定 3）
5. 福岡県動物愛護協会（静的・URL固定 8 + 詳細あり）
6. 神奈川県（静的・URL固定 4）

**動的だが構造化:**
7. 秋田 ワンニャピアあきた（動的 CMS、URL明確）
8. 沖縄 aniwel-pref.okinawa（動的・URL構造美しい）
9. 長崎 animal-net（動的・URL明確）
10. 熊本 kumamoto-doubutuaigo（動的 DB）
11. 大分 oita-aigo.com（動的）
12. 福岡市わんにゃん（パラメータ駆動）
13. 東京都 shuyojoho.metro.tokyo.lg.jp（動的検索 DB ★最大データ量）

### Phase 2-C: Tier 2-3 政令指定都市・県静的一覧（10+ サイト）
- 札幌市、横浜市、大阪市、神戸市
- 千葉県、大阪府、山梨県、広島県、岡山県
- 山口県、佐賀県、鳥取県

### Phase 2-D: Tier 4-5 リンク集を掘り下げ（残り 14 県）
青森、岩手、宮城、山形、福島、群馬、埼玉、富山、岐阜、静岡、三重、滋賀、和歌山、島根

### スキップ枠
- 鹿児島（SSL要修正待ち）
- 宮崎（CMS構造クロール難）
- 奈良（公式ページにペットリンク見当たらず）
- 新潟（データ 0 件、要定期確認）

---

## sites.yaml への追加例（テンプレート）

### 京都市ペットラブ（静的・single_page）
```yaml
  - name: "京都市ペットラブ（迷子犬）"
    prefecture: "京都府"
    prefecture_code: "26"
    list_url: "https://kyoto-ani-love.com/lost-animal/dog/"
    category: "lost"
    single_page: true
```

### 福岡県動物愛護協会（静的・個別詳細あり）
```yaml
  - name: "福岡県動物愛護協会（保健所収容犬）"
    prefecture: "福岡県"
    prefecture_code: "40"
    list_url: "https://www.zaidan-fukuoka-douai.or.jp/animals/protections/dog"
    list_link_pattern: "a[href*='/animals/protection-detail/']"
    category: "lost"
```

### 沖縄県（動的・URL構造化）
```yaml
  - name: "沖縄県動物愛護管理センター（収容犬）"
    prefecture: "沖縄県"
    prefecture_code: "47"
    list_url: "https://www.aniwel-pref.okinawa/animals/accommodate/dogs"
    list_link_pattern: "a[href*='/animals/accommodate_view/']"
    category: "sheltered"
    requires_js: true  # 要検証
```

### 東京都（動的検索 DB）
```yaml
  - name: "東京都収容動物情報（犬）"
    prefecture: "東京都"
    prefecture_code: "13"
    list_url: "https://shuyojoho.metro.tokyo.lg.jp/"
    category: "sheltered"
    requires_js: true
```

---

## 完全 URL リスト（環境省 link.html 由来・130件超）

> 元の URL リストは下記 [付録: 全 130 件] 参照（既存記録）。
> 上記の Tier 分類で全て参照済み。
> 必要時は環境省サイトから最新版を取得すること。

---

## 次のアクション提案

1. **Tier 1 のうち静的サイト 6 つ**（京都市、浜松、横須賀、栃木、福岡県動愛、神奈川）を一度に sites.yaml に追加
2. ローカルで `make collect` を実行し各サイトの取得結果を検証
3. LLM 抽出が動かないサイトのみ requires_js: true に切替
4. 動的サイト（東京都、沖縄、長崎等）を1つずつ追加・検証
5. 月次ペースで Tier 2-5 を消化していく

総工数の見立て：Tier 1 完了で **対応県 4 → 17 県（人口カバー率 50%超）**。
