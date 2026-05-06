# 関東地方 保護動物サイト 完全調査結果

**対象:** 茨城・栃木・群馬・埼玉・千葉・東京・神奈川（7 都県）
**調査日:** 2026-05-06
**目的:** 県動愛 + 政令指定都市 + 中核市の保護動物サイトを sites.yaml 追加レベルまで網羅

---

## サマリー

| 都県 | 県動愛 + 主要市 | 追加エントリ数 | 取得難易度 |
|---|---|---|---|
| 茨城県 | 県（PDF日次）+ 水戸市 | 4 | ★★ 中 |
| 栃木県 | douai.pref.tochigi（専用ドメイン）+ 宇都宮市 | 4 | ★ 易 |
| 群馬県 | 県（3ページ）+ 前橋市 | 4 | ★ 易 |
| 埼玉県 | さいたま市 + 越谷市 | 5 | ★ 易 |
| 千葉県 | 県動愛（5）+ 千葉市（6）+ 船橋（2）+ 柏（2） | 15 | ★ 易 |
| 東京都 | shuyojoho.metro.tokyo（専用 DB）+ 町田市 | 5 | ★★ 中（要 JS） |
| 神奈川県 | 県（4）+ 横須賀（6）+ 横浜（3）+ 川崎（3） | 16 | ★ 易 |
| **合計** | | **53** | — |

---

## 茨城県

### 1. 茨城県（県動愛指導センター）
- 形式: **日次 PDF 公表**（kouhyou{MMDD}.pdf パターン）
- listing 親ページ:
  - `/hokenfukushi/doshise/hogo/syuuyou.html`（収容中）
  - `/hokenfukushi/doshise/hogo/mayoiinuneko.html`（迷子）
- 既存の香川 PDF パターンを応用

### 2. 水戸市動物愛護センター
- 静的 HTML
- `/site/doubutsuaigo/list358.html`（迷子ペット情報）
- `/site/doubutsuaigo/2043.html`（収容中の動物たち）

---

## 栃木県

### 1. 栃木県動物愛護指導センター（専用ドメイン ★）
- 形式: 静的 HTML、個別詳細あり (`/news/{記事ID}/`)
- `/work_category/custody/`（保護）
- `/jyouto/`（譲渡）
- `/work/custody-lostanimal/`（迷子）

### 2. 宇都宮市
- `/kurashi/pet/pet/1005584.html`（迷子犬・負傷猫）

---

## 群馬県

### 1. 群馬県動物愛護センター（3 URL）
- `/page/167499.html`（保護犬）
- `/page/179441.html`（東部支所保護犬）
- `/page/167523.html`（保護猫）

### 2. 前橋市
- `/soshiki/kenko/eiseikensa/gyomu/1/1/1/9484.html`（保護犬）
- 個別詳細: `/9484/{管理番号}.html`

---

## 埼玉県

### 1. さいたま市
- `/008/004/003/004/p003138.html`（保護犬）
- `/008/004/003/004/p019971.html`（保護猫・その他）

### 2. 越谷市
- `/koshigaya_contents_dog.html`
- `/koshigaya_contents_cat.html`
- `/hogo_kojin.html`（個人保護）

### スキップ
- 川越市（要追加調査）
- 川口市（届出フォームのみ）

---

## 千葉県

### 1. 千葉県動物愛護センター
- `/aigo/pet/inu-neko/shuuyou/shuu-inu.html`（本所収容犬）
- `/aigo/pet/inu-neko/shuuyou/shuu-neko.html`（本所収容猫）
- `/aigo/pet/sonohoka/inu-nekoigai/index.html`（犬猫以外）
- `/aigo/pet/inu-neko/shuuyou/shuu-inu-tou.html`（東葛飾支所収容犬）
- `/aigo/pet/inu-neko/shuuyou/shuu-neko-tou.html`（東葛飾支所収容猫）
- 補足: 個人保護動物・逸走動物は Kintone iframe（未対応）

### 2. 千葉市（6 URL）
- 迷子: dog / cat / 他動物
- 市民保護: dog / cat / 他

### 3. 船橋市
- 収容犬猫 / 譲渡可能犬猫

### 4. 柏市
- 保護動物 / 譲渡対象動物

---

## 東京都

### 1. 東京都収容動物情報（専用 DB ★最大データ量見込み）
- `https://shuyojoho.metro.tokyo.lg.jp/`（犬）
- `https://shuyojoho.metro.tokyo.lg.jp/cat`（猫等）
- 動的検索 DB、要 JS

### 2. 町田市
- `/iryo/hokenjo/pet/mayoi/syuyou.html`（収容動物）
- `/iryo/hokenjo/pet/mayoi/hogo.html`（保護情報）
- `/iryo/hokenjo/pet/mayoi/pet_fumei/index.html`（捜索）

### スキップ
- 八王子市（情報ページのみ）

---

## 神奈川県

### 1. 神奈川県動物愛護センター（4 URL）
- `/osirase/1594/awc/lost/dog.html`
- `/osirase/1594/awc/lost/cat.html`
- `/osirase/1594/awc/lost/other.html`
- `/osirase/1594/awc/lost/outside.html`

### 2. 横須賀市（専用ドメイン ★）
- `yokosuka-doubutu.com/protected-animals-{dog,cat,other}/`（保護）
- `yokosuka-doubutu.com/adopted-animals-{dog,cat,other}/`（譲渡）

### 3. 横浜市
- `/kurashi/sumai-kurashi/pet-dobutsu/aigo/maigo/shuyoinfo.html`（犬）
- `/kurashi/sumai-kurashi/pet-dobutsu/aigo/maigo/20121004094818.html`（猫）
- `/kurashi/sumai-kurashi/pet-dobutsu/aigo/maigo/20121004110429.html`（他）

### 4. 川崎市
- `/350/page/0000077270.html`（犬）
- `/350/page/0000109367.html`（猫）
- `/350/page/0000074729.html`（他）

### スキップ
- 相模原市（現在 0 件）
- 藤沢市（現在 0 件）

---

## 実装状況

- ✅ バッチ1: 25 エントリ（県動愛・主要拠点）→ Merged
- ✅ バッチ2: 28 エントリ（政令指定都市・中核市）→ Merged
- 計 **53 エントリ** が sites.yaml に追加済み

## 関東対応県数: 7/7（全制覇）

### 残タスク（バッチ3 候補）
- 川越市・八王子市・相模原市・藤沢市の追跡（現在不確定 or 0 件）
- 千葉県 Kintone 埋込（個人保護動物・逸走動物）の対応検討
- 茨城県 PDF パターンの動作確認・調整
