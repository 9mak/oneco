# 全国自治体保護動物サイト調査結果

**出典:** 環境省 収容動物検索情報サイト（https://www.env.go.jp/nature/dobutsu/aigo/shuyo/link.html）

**取得日:** 2026-05-06

**目的:** oneco の対応都道府県を 4 → 47 に拡大するための原典リスト整備。

---

## 既に対応済み（sites.yaml 統合済み）

| 都道府県 | 自治体 | 備考 |
|---|---|---|
| 徳島県 | 徳島県動物愛護管理センター | 3 サイト（収容中・譲渡犬・譲渡猫） |
| 香川県 | 県+高松市+各保健福祉事務所 | 7 サイト（PDF多め） |
| 愛媛県 | 県+松山市 | 3 サイト |

## 部分対応（旧パイプラインで動作中・LLM 統合候補）

| 都道府県 | 自治体 | 状態 |
|---|---|---|
| 高知県 | kochi-apc.com | KochiAdapter で動作中（67件中の 65件は高知）。sites.yaml 未登録 → Phase 2-A で統合 |

---

## 未対応（Phase 2-B 候補）— 優先度順

### A. 最優先（人口集中・データ量見込み大）

| 都道府県 | 自治体 | URL | 注釈 |
|---|---|---|---|
| 東京都 | 東京都 | https://www.hokeniryo.metro.tokyo.lg.jp/shisetsu/jigyosyo/douso/sissou/jyouhou | metro.tokyo.lg.jp（動的の可能性） |
| 大阪府 | 大阪府動物愛護管理センター | https://www.pref.osaka.lg.jp/o120200/doaicenter/doaicenter/maigoken.html | 県サイト |
| 大阪府 | 大阪市 | https://www.city.osaka.lg.jp/kenko/page/0000224574.html | |
| 神奈川県 | 神奈川県 | https://www.pref.kanagawa.jp/osirase/1594/awc/lost/ | |
| 神奈川県 | 横浜市 | https://www.city.yokohama.lg.jp/kurashi/sumai-kurashi/pet-dobutsu/aigo/maigo/ | |
| 神奈川県 | 横須賀市 | https://www.yokosuka-doubutu.com/ | 専用ドメイン → 構造化されている可能性 |
| 愛知県 | 愛知県 | https://www.pref.aichi.jp/soshiki/doukan-c/ | |
| 愛知県 | 名古屋市 | https://www.city.nagoya.jp/kenkofukushi/page/0000020112.html | |
| 愛知県 | 豊橋市 | https://toyohashi-aikuru.jp/animal_category/lost-found?animal_type=dog | 専用ドメイン・URL パラメータあり → API的 |
| 兵庫県 | 兵庫県 | https://hyogo-douai.sakura.ne.jp/shuuyou.html | sakura.ne.jp（個人サーバ系） |
| 兵庫県 | 神戸市 | https://www.city.kobe.lg.jp/a84140/kenko/health/hygiene/animal/zmenu/index.html | |
| 北海道 | 北海道 | https://www.pref.hokkaido.lg.jp/ks/awc/partner.html | パートナー一覧（中継ページの可能性） |
| 北海道 | 札幌市 | https://www.city.sapporo.jp/inuneko/syuuyou_doubutsu/maigoinuneko.html | |
| 福岡県 | 公益財団法人福岡県動物愛護協会 | https://www.zaidan-fukuoka-douai.or.jp/animals/protections/dog | 専用ドメイン → 一覧構造化されてる可能性高 |
| 福岡県 | 福岡市 | https://www.wannyan.city.fukuoka.lg.jp/ | 専用ドメイン |

### B. 高優先（首都圏・関西の中核都市）

| 都道府県 | 自治体 | URL |
|---|---|---|
| 千葉県 | 千葉県 | https://www.pref.chiba.lg.jp/aigo/pets/animal-info.html?pagePrint=1 |
| 千葉県 | 千葉市 | https://www.city.chiba.jp/hokenfukushi/iryoeisei/seikatsueisei/dobutsuhogo/escape.html |
| 千葉県 | 船橋市 | https://www.city.funabashi.lg.jp/kurashi/doubutsu/003/p013242.html |
| 埼玉県 | 埼玉県 | https://www.pref.saitama.lg.jp/b0716/doubutu-kaikata-shuuyou-top.html |
| 埼玉県 | さいたま市 | https://www.city.saitama.lg.jp/008/004/003/004/index.html |
| 埼玉県 | 川口市 | https://www.city.kawaguchi.lg.jp/soshiki/01090/seikatueiseika/doubutsu/lost/index.html |
| 京都府 | 京都府 | https://www.pref.kyoto.jp/doubutsu/maigoinuneko.html |
| 京都府 | 京都市 | https://kyoto-ani-love.com/lost-animal/dog/ | 専用ドメイン |
| 兵庫県 | 姫路市 | https://www.city.himeji.lg.jp/kurashi/0000001412.html |
| 大阪府 | 堺市 | https://www.eonet.ne.jp/~sakai-doshi/ | eonet（個人系） |
| 静岡県 | 静岡県 | https://www.pref.shizuoka.jp/kenkofukushi/fukushicenter/1046799/1049628/1047507.html |
| 静岡県 | 静岡市 | https://www.city.shizuoka.lg.jp/s3276/s001870.html |
| 静岡県 | 浜松市 | https://www.hama-aikyou.jp/hogoinu/ | 専用ドメイン |

### C. 中優先（中国・四国 残り、九州）

| 都道府県 | 自治体 | URL |
|---|---|---|
| 広島県 | 広島県動物愛護センター | https://www.pref.hiroshima.lg.jp/site/apc/contents-yukuehumei.html |
| 広島県 | 広島市（犬） | https://www.city.hiroshima.lg.jp/living/pet-doubutsu/1021301/1026245/1037461.html |
| 広島県 | 広島市（猫） | https://www.city.hiroshima.lg.jp/living/pet-doubutsu/1021301/1026245/1039097.html |
| 岡山県 | 岡山県 | https://www.pref.okayama.jp/page/859555.html |
| 岡山県 | 岡山市 | https://www.city.okayama.jp/kurashi/category/1-15-1-0-0-0-0-0-0-0.html |
| 岡山県 | 倉敷市 | https://www.city.kurashiki.okayama.jp/kurashi/pet/1013042/index.html |
| 山口県 | 山口県 | https://www.pref.yamaguchi.lg.jp/site/doubutuaigo/list25-151.html |
| 鳥取県 | 鳥取県 | https://www.pref.tottori.lg.jp/221001.htm |
| 島根県 | 島根県 | https://www.pref.shimane.lg.jp/infra/nature/animal/animal_protection/maigo/ |
| 熊本県 | 熊本県動物愛護センター | https://www.kumamoto-doubutuaigo.jp/ | 専用ドメイン |
| 熊本県 | 熊本市 | https://www.city.kumamoto.jp/doubutuaigo/ |
| 大分県 | 大分県 | https://www.pref.oita.jp/site/doubutuaigo/hogo-syokuan.html |
| 沖縄県 | 沖縄県 | https://www.aniwel-pref.okinawa/ | 専用ドメイン |

### D. 低優先（東北・北陸・甲信越）

| 都道府県 | 自治体 | URL |
|---|---|---|
| 青森県 | 青森県 | http://www.aomori-animal.jp/01_MAIGO/Shuyo.html | http のみ・専用ドメイン |
| 岩手県 | 岩手県 | https://www.pref.iwate.jp/kurashikankyou/anzenanshin/pet/1004615.html |
| 宮城県 | 宮城県 | https://www.pref.miyagi.jp/life/joto-hogo/index.html |
| 宮城県 | 仙台市 | https://www.city.sendai.jp/dobutsu/kurashi/shizen/petto/hogodobutsu/joho/jyoutojigyou.html |
| 秋田県 | 秋田県 | https://www.pref.akita.lg.jp/pages/genre/11645 |
| 山形県 | 山形県 | https://www.pref.yamagata.jp/020071/kenfuku/doubutsuaigo/aigo/kainushisagashi/keijiban.html |
| 福島県 | 福島県 | https://www.pref.fukushima.lg.jp//sec/21620a/maigo-dog-cat.html |
| 茨城県 | 茨城県 | https://www.pref.ibaraki.jp/hokenfukushi/doshise/hogo/kouji.html |
| 栃木県 | 栃木県動物愛護指導センター | https://www.douai.pref.tochigi.lg.jp/ | 専用ドメイン |
| 群馬県 | 群馬県 | https://www.pref.gunma.jp/page/7895.html |
| 新潟県 | 新潟県 | https://www.pref.niigata.lg.jp/sec/seikatueisei/1333314133188.html |
| 富山県 | 富山県 | https://www.pref.toyama.jp/1207/kurashi/seikatsu/seikatsu/doubutsuaigo/syuyou/index.html |
| 石川県 | 石川県 | https://www.pref.ishikawa.lg.jp/yakuji/doubutsu/hogoinuneko.html |
| 福井県 | 福井県 | https://www.pref.fukui.lg.jp/doc/doukansi/doubutukanrisidou/doukansi-c-4.html |
| 山梨県 | 山梨県 | https://www.pref.yamanashi.jp/doubutsu/find_me.html |
| 長野県 | 長野県 | https://www.pref.nagano.lg.jp/shokusei/kurashi/aigo/kaishu/information/index.html |
| 岐阜県 | 岐阜県 | https://www.pref.gifu.lg.jp/page/1638.html |
| 三重県 | 三重県動物愛護管理センター | http://mie-dakc.server-shared.com/maigoinujyouhou.html | http のみ |
| 滋賀県 | 滋賀県 | https://www.pref.shiga.lg.jp/doubutsuhogo/azukari/102881.html |
| 奈良県 | 奈良県 | https://www.pref.nara.jp/dd.aspx?menuid=8439 |
| 和歌山県 | 和歌山県 | https://www.pref.wakayama.lg.jp/prefg/031601/d00156970.html |
| 佐賀県 | 佐賀県 | https://www.pref.saga.lg.jp/list02388.html |
| 長崎県 | 長崎県 | https://animal-net.pref.nagasaki.jp/ | 専用ドメイン |
| 宮崎県 | 宮崎県 | http://dog.pref.miyazaki.lg.jp/ | 専用ドメイン (http) |
| 鹿児島県 | 鹿児島県 | http://dogcat.pref.kagoshima.jp/Search/Lost_index | 専用ドメイン (http) |

---

---

## 詳細構造調査結果（優先サイト・2026-05-06 調査）

各サイトの実物にアクセスし、sites.yaml に登録するための情報を収集した。

### ✅ 横須賀市 — `https://www.yokosuka-doubutu.com/`
**6 リスト URL:**
- 保護中（sheltered）: `/protected-animals-{dog,cat,other}/`
- 譲渡（adoption）: `/adopted-animals-{dog,cat,other}/`

**形式:** 静的 HTML（個別詳細ページ要追加調査）

### ✅ 福岡県動物愛護協会 — `https://www.zaidan-fukuoka-douai.or.jp/`
**8 リスト URL（保護4 + 譲渡4）:**
- 保健所収容（lost）: `/animals/protections/{dog,cat}`
- 一般保護（sheltered）: `/personal-animals/hogo/{dog,cat}`
- センター譲渡（adoption）: `/animals/centers/{dog,cat}`
- 団体譲渡（adoption）: `/animals/groups/{dog,cat}`

**形式:** 静的 HTML、個別詳細あり (`/animals/protection-detail/{UUID}`)
**セレクタ候補:** `a[href*="/animals/protection-detail/"]`
**注釈:** 「収容翌日から5日間掲載」と明記（更新頻度高）

### ✅ 福岡市わんにゃん — `https://www.wannyan.city.fukuoka.lg.jp/`
**4 リスト URL（パラメータ駆動）:**
- 犬保護中: `/yokanet/animal/animal_posts/index?type_id=1&sorting_id=4`
- 猫保護中: `/yokanet/animal/animal_posts/index?type_id=2&sorting_id=4`
- 犬譲渡: `/yokanet/animal/animal_posts/index?type_id=1&sorting_id=5`
- 猫譲渡: `/yokanet/animal/animal_posts/index?type_id=2&sorting_id=5`

**形式:** 動的（DB 駆動）、`requires_js: true` の可能性高

### ✅ 京都市 ペットラブ — `https://kyoto-ani-love.com/`
**2 リスト URL:**
- 迷子犬: `/lost-animal/dog/`
- 迷子猫: `/lost-animal/cat/`
- 譲渡: `/information/owner/recruit/`

**形式:** 静的、`single_page: true`（詳細なし、一覧に統合表示）
**注釈:** 受入日から約 2 週間掲載

### ✅ 浜松市動物愛護教育センター — `https://www.hama-aikyou.jp/`
**1 リスト URL:**
- 保護犬: `/hogoinu/index.html`

**形式:** 静的、`single_page: true`、PDF リンク含む可能性
**注釈:** 「迷い犬」中心で猫の収容情報は薄め

### ✅ 熊本県動物愛護センター — `https://www.kumamoto-doubutuaigo.jp/`
**12 リスト URL:**
- 譲渡（adoption）: `/animals/index/type_id:{1,2}/animal_id:{1,2}` × group/post variants
- 迷子（lost）: `type_id` 切替

**形式:** 動的（DB 駆動・カードベース UI）、個別詳細あり (`/animals/detail/{ID}`, `/post_animals/detail/{ID}`)
**セレクタ候補:** `a[href*="/animals/detail/"]`, `a[href*="/post_animals/detail/"]`

---

## 次のアクション（Phase 2 詳細プラン）

### Step 1: 高知統合（Phase 2-A）
- [x] sites.yaml に高知県エントリ追加
- [ ] LLM 抽出で kochi-apc.com から正しくデータ取得できるか検証
- [ ] 旧 KochiAdapter の段階的廃止判断

### Step 2: 専用ドメイン優先攻略（取りやすい順）
専用ドメインは構造化されている可能性が高く、LLM 抽出が機能しやすい：

1. **横須賀市** https://www.yokosuka-doubutu.com/
2. **公益財団法人福岡県動物愛護協会** https://www.zaidan-fukuoka-douai.or.jp/
3. **福岡市わんにゃん** https://www.wannyan.city.fukuoka.lg.jp/
4. **京都市 kyoto-ani-love** https://kyoto-ani-love.com/
5. **熊本県動物愛護センター** https://www.kumamoto-doubutuaigo.jp/
6. **長崎県 animal-net** https://animal-net.pref.nagasaki.jp/
7. **沖縄県 aniwel** https://www.aniwel-pref.okinawa/
8. **栃木県動物愛護指導センター** https://www.douai.pref.tochigi.lg.jp/
9. **浜松市 hama-aikyou** https://www.hama-aikyou.jp/hogoinu/
10. **豊橋市アイクル** https://toyohashi-aikuru.jp/

### Step 3: 大都市（人口・データ量大）
1. 東京都
2. 大阪府・大阪市
3. 神奈川県・横浜市・川崎市
4. 愛知県・名古屋市
5. 兵庫県・神戸市
6. 札幌市

### Step 4: 残りの都道府県（順次）
低優先帯（東北・北陸・甲信越・中四国残り）を 1 サイトずつ追加。

---

## サイト追加時の調査チェックリスト

各サイトに対して以下を確認：

- [ ] そもそも一覧ページか、それとも案内ページのみか
- [ ] 個別動物の詳細ページがあるか（無い場合は `single_page: true`）
- [ ] JavaScript レンダリングが必要か（`requires_js: true`）
- [ ] PDF 形式で配布されているか（`pdf_link_pattern` 設定）
- [ ] category（adoption / lost）の判定
- [ ] 一覧URL のクエリ・パスパターン

## 作業効率化のヒント

- **専用ドメイン > 自治体公式サイトの一画面** で取得しやすい傾向
- **政令市は県より動物数が多い**ことが多い
- **PDF 中心**のサイトは PDF パターンが固定なら容易（香川の保健福祉事務所が既存のパターン）
- **HTTP のみ**のサイトは `https://` への自動アップグレードに失敗する可能性あり

---

## 参考データ

総リンク数: **130 件以上**（47 都道府県 + 政令指定都市・中核市）

このリストは環境省の link.html ページから 2026-05-06 時点で取得。サイト URL は予告なく変更される可能性があるため、各サイト追加時に最新を確認すること。
