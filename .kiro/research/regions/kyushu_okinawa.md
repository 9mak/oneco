# 九州・沖縄 保護動物サイト 完全調査結果

**対象:** 福岡・佐賀・長崎・熊本・大分・宮崎・鹿児島・沖縄（8 都県）
**調査日:** 2026-05-06
**目的:** 各県内のすべての保護動物サイトを sites.yaml 追加レベルまで網羅する

---

## サマリー

| 県 | 主要サイト | 推定エントリ数 | 取得難易度 |
|---|---|---|---|
| 福岡県 | 4 サイト群（県動愛 + 北九州・福岡・久留米） | 約 14 | ★ 易〜★★ 中 |
| 佐賀県 | 県+5 地域別 | 6 | ★ 易 |
| 長崎県 | 県アニマルネット + 長崎市 + 佐世保市 | 約 8 | ★ 易〜★★ 中 |
| 熊本県 | 県動愛 + 熊本市 | 約 16 | ★★ 中 |
| 大分県 | 県動愛 + 11 市町村別 + 大分市 | 約 14 | ★★ 中 |
| 宮崎県 | 県動愛 + 宮崎市 | 約 13 | ★★★ 高（CMS） |
| 鹿児島県 | 鹿児島市のみ（県は SSL エラー） | 2 | ★★ 中 |
| 沖縄県 | 県動愛 + 那覇市 | 約 7 | ★★ 中 |
| **合計** | | **約 80 エントリ** | — |

**Tier 1 即実装推奨:** 福岡県動愛 8 + 北九州市 2 + 福岡市 4 + 長崎県アニマルネット 4 + 沖縄県動愛 6 + 大分県動愛主要 4 + 熊本県動愛主要 6 = **約 34 エントリ**

---

## 福岡県

### 1. 福岡県動物愛護協会（公益財団法人）★最優先

**ドメイン:** `zaidan-fukuoka-douai.or.jp` （静的 HTML、個別詳細あり）
**個別詳細 URL パターン:** `/animals/protection-detail/{UUID}`
**注釈:** 「収容翌日から 5 日間掲載」（更新頻度高）

| 一覧 URL | category |
|---|---|
| `/animals/protections/dog` | lost（保健所収容犬） |
| `/animals/protections/cat` | lost（保健所収容猫） |
| `/personal-animals/hogo/dog` | sheltered（個人保護犬） |
| `/personal-animals/hogo/cat` | sheltered（個人保護猫） |
| `/animals/centers/dog` | adoption（センター譲渡犬） |
| `/animals/centers/cat` | adoption（センター譲渡猫） |
| `/animals/groups/dog` | adoption（団体譲渡犬） |
| `/animals/groups/cat` | adoption（団体譲渡猫） |

### 2. 北九州市

**ドメイン:** `city.kitakyushu.lg.jp` （静的 HTML）

| 一覧 URL | category |
|---|---|
| `/contents/924_11831.html` | sheltered（保護犬） |
| `/contents/924_11834.html` | adoption（譲渡犬） |

### 3. 福岡市わんにゃんよかネット

**ドメイン:** `wannyan.city.fukuoka.lg.jp` （動的・パラメータ駆動、要 JS 検証）

| 一覧 URL | category |
|---|---|
| `/yokanet/animal/animal_posts/index?type_id=1&sorting_id=4` | sheltered（犬保護中） |
| `/yokanet/animal/animal_posts/index?type_id=2&sorting_id=4` | sheltered（猫保護中） |
| `/yokanet/animal/animal_posts/index?type_id=1&sorting_id=5` | adoption（犬譲渡） |
| `/yokanet/animal/animal_posts/index?type_id=2&sorting_id=5` | adoption（猫譲渡） |

### 4. 久留米市
現在保護動物 0 件。後回し可能。

---

## 佐賀県

**ドメイン:** `pref.saga.lg.jp` （静的 HTML、地域別）

| 一覧 URL | 地域 | category |
|---|---|---|
| `/kiji00349237/index.html` | 佐賀市・多久・小城・神埼・神埼郡 | sheltered |
| `/kiji00334357/index.html` | 鳥栖・三養基郡 | sheltered |
| `/kiji00365042/index.html` | 唐津・東松浦郡 | sheltered |
| `/kiji00334505/index.html` | 伊万里・西松浦郡 | sheltered |
| `/kiji00334341/index.html` | 武雄・鹿島・嬉野・杵島・藤津 | sheltered |
| `/kiji00314888/index.html` | 全県（譲渡） | adoption |

---

## 長崎県

### 1. 長崎犬猫ネット ★最優先

**ドメイン:** `animal-net.pref.nagasaki.jp` （動的・URL明確）
**個別詳細:** `/animal/no-{ID}/`

| 一覧 URL | category |
|---|---|
| `/syuuyou` | sheltered（保健所収容） |
| `/jyouto` | adoption（譲渡） |
| `/maigo` | lost（迷子） |
| `/hogo` | sheltered（保護） |

### 2. 長崎市

**ドメイン:** `city.nagasaki.lg.jp` （静的 HTML）

| 一覧 URL | category |
|---|---|
| `/site/doubutsuaigo/list7-19.html` | adoption（犬里親募集） |
| `/site/doubutsuaigo/list7-18.html` | adoption（猫里親募集） |

### 3. 佐世保市

**ドメイン:** `city.sasebo.lg.jp` （静的 HTML、個別詳細あり）
**個別詳細:** `/hokenhukusi/seikat/YYYYMMDD_{dog,cat}NN.html`

| 一覧 URL | category |
|---|---|
| `/hokenhukusi/seikat/hogodoubutsu.html` | sheltered（保護犬） |
| `/hokenhukusi/seikat/mayoinekohogo.html` | sheltered（保護猫） |

---

## 熊本県

### 1. 熊本県動物愛護センター ★

**ドメイン:** `kumamoto-doubutuaigo.jp` （動的 DB、URL構造化）
**個別詳細:** `/animals/detail/{ID}`, `/post_animals/detail/{ID}`

| 一覧 URL | category |
|---|---|
| `/animals/index/type_id:2/animal_id:1` | adoption（センター譲渡犬） |
| `/animals/index/type_id:2/animal_id:2` | adoption（センター譲渡猫） |
| `/animals/group/type_id:2/animal_id:1` | adoption（団体譲渡犬） |
| `/animals/group/type_id:2/animal_id:2` | adoption（団体譲渡猫） |
| `/post_animals/index/type_id:2/animal_id:1` | sheltered（個人保護犬） |
| `/post_animals/index/type_id:2/animal_id:2` | sheltered（個人保護猫） |
| `/animals/index/type_id:1/animal_id:1` | lost（迷子犬） |
| `/animals/index/type_id:1/animal_id:2` | lost（迷子猫） |

### 2. 熊本市

**ドメイン:** `city.kumamoto.jp` （混在、静的 list + 動的 search）
**個別詳細:** `/doubutuaigo/kiji{ID}/index.html`

| 一覧 URL | category |
|---|---|
| `/doubutuaigo/list03612.html` | lost（迷子犬一覧） |
| `/doubutuaigo/list03615.html` | lost（迷子猫一覧） |
| `/dynamic/doubutuaigo/hpkiji/pub/search.aspx?c_id=3&kbn=jdog` | adoption（譲渡犬検索） |
| `/dynamic/doubutuaigo/hpkiji/pub/search.aspx?c_id=3&kbn=jcat` | adoption（譲渡猫検索） |

---

## 大分県

### 1. おおいた動物愛護センター ★

**ドメイン:** `oita-aigo.com` （動的、市町村別ページあり）
**個別詳細:** `/lostchild/{日付ベース}/`

メインリスト：
| URL | category |
|---|---|
| `/lostchild/` | sheltered（迷子情報メイン） |
| `/information_doglist/anytimedog/` | adoption（譲渡犬） |
| `/information_catlist/anytimecat/` | adoption（譲渡猫） |

市町村別（11 自治体）：
- `/lostchildlist/maigo_saiki/` 佐伯市
- `/lostchildlist/maigo_beppu/` 別府市
- `/lostchildlist/maigo_kunisaki/` 国東市
- `/lostchildlist/maigo_himeshima/` 姫島村
- `/lostchildlist/maigo_hiji/` 日出町
- `/lostchildlist/maigo_kitsuki/` 杵築市
- `/lostchildlist/maigo_tsukumi/` 津久見市
- `/lostchildlist/maigo_yufu/` 由布市
- `/lostchildlist/maigo_taketa/` 竹田市
- `/lostchildlist/maigo_usuki/` 臼杵市
- `/lostchildlist/maigo_bungoono/` 豊後大野市

### 2. 大分市
`city.oita.oita.jp/kurashi/pet/inunohogo/index.html` （静的、現在 4 件保護）

---

## 宮崎県

### 1. 宮崎県動物愛護センター（CMS 構造）

**ドメイン:** `dog.pref.miyazaki.lg.jp` （動的・モジュール CMS）
**個別詳細:** `/modules/addon_module/?a=doglove&p=information_detail&cd={ID}`

| 一覧 URL | category |
|---|---|
| `/modules/addon_module/?a=doglove&p=information_list` | mixed（ニュース一覧） |

★ CMS の取り扱いが特殊なため要 LLM 抽出検証。スキップ判断もあり。

### 2. 宮崎市

**ドメイン:** `city.miyazaki.miyazaki.jp` （静的 HTML、12 サブページ）

| 一覧 URL | category |
|---|---|
| `/life/pet/protection/411116.html`（猫・直近） | sheltered |
| `/life/pet/protection/411118.html`（犬・直近） | sheltered |
| `/life/pet/protection/109676.html` | adoption（センター保護犬） |
| `/life/pet/protection/339718.html` | adoption（センター保護猫） |
| `/life/pet/protection/84989.html` | adoption（市民飼い主募集犬） |
| `/life/pet/protection/51367.html` | adoption（市民飼い主募集猫） |
| `/life/pet/protection/51360.html` | sheltered（市民迷子犬保護） |
| `/life/pet/protection/57782.html` | lost（市民迷子犬捜索） |
| `/life/pet/protection/109685.html` | sheltered（市民迷子猫保護） |
| `/life/pet/protection/109681.html` | lost（市民迷子猫捜索） |

---

## 鹿児島県

### 1. 鹿児島県（県システム）
**ドメイン:** `dogcat.pref.kagoshima.jp` — **SSL 証明書エラーで取得不可**。要対応待ち。

### 2. 鹿児島市

**ドメイン:** `city.kagoshima.lg.jp` （静的 HTML）

| 一覧 URL | category |
|---|---|
| `/kenkofukushi/hokenjo/seiei-jueki/kurashi/dobutsu/kainushi/joho/inu.html` | sheltered（保護犬） |
| `/kenkofukushi/hokenjo/seiei-jueki/kurashi/dobutsu/kainushi/joho/neko.html` | sheltered（保護猫） |
| `/kenkofukushi/hokenjo/seiei-jueki/kurashi/dobutsu/kainushi/boshu/index.html` | adoption（飼い主募集） |

---

## 沖縄県

### 1. 沖縄県動物愛護管理センター ★

**ドメイン:** `aniwel-pref.okinawa` （動的 DB、美しい URL 構造）
**個別詳細:** `/animals/{type}_view/{ID}` 例: `/animals/accommodate_view/24540`

| 一覧 URL | category |
|---|---|
| `/animals/accommodate/dogs` | sheltered（収容犬） |
| `/animals/accommodate/cats` | sheltered（収容猫） |
| `/animals/missing/dogs` | lost（行方不明犬） |
| `/animals/missing/cats` | lost（行方不明猫） |
| `/animals/protection/dogs` | sheltered（迷い込み保護犬） |
| `/animals/protection/cats` | sheltered（迷い込み保護猫） |
| `/hapianiokinawa` | adoption（譲渡） |

### 2. 那覇市

**ドメイン:** `city.naha.okinawa.jp` （PDF 配布のみ）
| 一覧 URL | category |
|---|---|
| `/kurasitetuduki/animal/1002271/1002278.html` | sheltered（PDF リンク掲載ページ） |

---

## 実装計画（バッチ単位）

### バッチ 1（最優先・静的・取得確実）— 約 24 エントリ
1. 福岡県動物愛護協会（8 URL）
2. 長崎県アニマルネット（4 URL）
3. 沖縄県動物愛護管理センター（6 URL、要 JS）
4. 佐賀県（5 地域＋譲渡 6 URL）

### バッチ 2（中規模・自治体）— 約 16 エントリ
5. 北九州市（2）
6. 福岡市わんにゃん（4、要 JS）
7. 長崎市（2）
8. 佐世保市（2）
9. 鹿児島市（3）
10. 大分市（1）
11. 那覇市（1、PDF 含む）
12. 宮崎市（10〜12）

### バッチ 3（動的・要検証）— 約 20 エントリ
13. 熊本県動物愛護センター（8 URL、要 JS）
14. 熊本市（4 URL）
15. 大分県動愛 メイン + 市町村別（14 URL）
16. 宮崎県動愛（CMS、検証次第でスキップ）

### スキップ（現状）
- 鹿児島県動物検索 DB（SSL 証明書エラー）
- 久留米市（現在 0 件）

---

## 次のアクション

1. **バッチ 1 を sites.yaml に追加**（最も取りやすい 24 エントリ）
2. ローカルで `make collect` を 1 サイトずつ動作確認
3. データが取れたサイトから順に main マージ
4. バッチ 2 → バッチ 3 と順次拡大

これで 九州・沖縄完了 → 対応県数 4 → 12 県（人口カバー率 +約 11%）
