# 0 件抽出サイト キャナリー監査レポート (2026-05-19 23:24)

対象サイト数: **155**

| カテゴリ | 件数 | 説明 |
|---|---:|---|
| 🔴 suspicious | 40 | adapter 不具合疑い・要修正調査 |
| 🟡 maybe_zero | 92 | コンテンツ候補が少なく現状ゼロが有力だが要再確認 |
| 🟢 true_zero | 4 | 明示的「ゼロ」表現あり、現状正常 |
| ⚪ unreachable | 5 | 404 / timeout / 接続エラー |
| ⏭️ skipped_js | 14 | requires_js: true (Playwright 監査 TODO) |

## 🔴 suspicious — adapter 修正候補（優先度高） (40 件)

| サイト | 都道府県 | 理由 | シグナル | URL |
|---|---|---|---|---|
| 東讃保健福祉事務所（収容動物） | 香川県 | detail 系リンクが 7 件ある | imgs=1, animal_alt_imgs=0, detail_links=7, table_rows=0, pdf_links=1, text_len=3674 | [link](https://www.pref.kagawa.lg.jp/tosanhoken/tosanhoken/animal/sjiaen191105113550.html) |
| 中讃保健福祉事務所（収容動物） | 香川県 | PDF リンクが 3 件ある | imgs=1, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=3, text_len=4884 | [link](https://www.pref.kagawa.lg.jp/chusanhoken/chusanhoken/inu-neko/s058kw191105221746.html) |
| 愛媛県動物愛護センター（譲渡予定） | 愛媛県 | 非空 table 行が 32 行ある | imgs=30, animal_alt_imgs=0, detail_links=0, table_rows=32, pdf_links=0, text_len=12460 | [link](https://www.pref.ehime.jp/page/17125.html) |
| 福岡県動物愛護協会（一般保護犬） | 福岡県 | detail 系リンクが 6 件ある | imgs=4, animal_alt_imgs=2, detail_links=6, table_rows=0, pdf_links=0, text_len=2238 | [link](https://www.zaidan-fukuoka-douai.or.jp/personal-animals/hogo/dog) |
| 福岡県動物愛護協会（センター譲渡犬） | 福岡県 | 動物 alt の img が 4 件ある | imgs=6, animal_alt_imgs=4, detail_links=4, table_rows=0, pdf_links=0, text_len=2512 | [link](https://www.zaidan-fukuoka-douai.or.jp/animals/centers/dog) |
| 福岡県動物愛護協会（一般保護猫） | 福岡県 | 動物 alt の img が 9 件ある | imgs=11, animal_alt_imgs=9, detail_links=13, table_rows=0, pdf_links=0, text_len=2489 | [link](https://www.zaidan-fukuoka-douai.or.jp/personal-animals/hogo/cat) |
| 福岡県動物愛護協会（センター譲渡猫） | 福岡県 | 動物 alt の img が 7 件ある | imgs=9, animal_alt_imgs=7, detail_links=4, table_rows=0, pdf_links=0, text_len=2687 | [link](https://www.zaidan-fukuoka-douai.or.jp/animals/centers/cat) |
| 福岡県動物愛護協会（団体譲渡犬） | 福岡県 | 動物 alt の img が 6 件ある | imgs=8, animal_alt_imgs=6, detail_links=5, table_rows=0, pdf_links=0, text_len=3204 | [link](https://www.zaidan-fukuoka-douai.or.jp/animals/groups/dog) |
| 福岡県動物愛護協会（団体譲渡猫） | 福岡県 | 動物 alt の img が 4 件ある | imgs=6, animal_alt_imgs=4, detail_links=5, table_rows=0, pdf_links=0, text_len=2949 | [link](https://www.zaidan-fukuoka-douai.or.jp/animals/groups/cat) |
| 長崎犬猫ネット（保健所収容） | 長崎県 | detail 系リンクが 16 件ある | imgs=16, animal_alt_imgs=0, detail_links=16, table_rows=0, pdf_links=0, text_len=3581 | [link](https://animal-net.pref.nagasaki.jp/syuuyou) |
| 長崎犬猫ネット（譲渡） | 長崎県 | detail 系リンクが 37 件ある | imgs=37, animal_alt_imgs=0, detail_links=37, table_rows=0, pdf_links=0, text_len=4722 | [link](https://animal-net.pref.nagasaki.jp/jyouto) |
| 長崎犬猫ネット（迷子） | 長崎県 | detail 系リンクが 13 件ある | imgs=13, animal_alt_imgs=0, detail_links=13, table_rows=0, pdf_links=0, text_len=3539 | [link](https://animal-net.pref.nagasaki.jp/maigo) |
| 北九州市（保護犬） | 福岡県 | 非空 table 行が 9 行ある | imgs=6, animal_alt_imgs=0, detail_links=0, table_rows=9, pdf_links=0, text_len=6029 | [link](https://www.city.kitakyushu.lg.jp/contents/924_11831.html) |
| 北九州市（譲渡犬） | 福岡県 | PDF リンクが 6 件ある | imgs=7, animal_alt_imgs=0, detail_links=0, table_rows=5, pdf_links=6, text_len=9122 | [link](https://www.city.kitakyushu.lg.jp/contents/924_11834.html) |
| 那覇市（保護犬猫情報） | 沖縄県 | PDF リンクが 2 件ある | imgs=7, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=2, text_len=8799 | [link](https://www.city.naha.okinawa.jp/kurasitetuduki/animal/1002271/1002278.html) |
| 神奈川県動物愛護センター（センター外保護動物） | 神奈川県 | PDF リンクが 3 件ある | imgs=2, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=3, text_len=3908 | [link](https://www.pref.kanagawa.jp/osirase/1594/awc/lost/outside.html) |
| 越谷市（保護猫） | 埼玉県 | 非空 table 行が 12 行ある | imgs=15, animal_alt_imgs=0, detail_links=1, table_rows=12, pdf_links=0, text_len=8986 | [link](https://www.city.koshigaya.saitama.jp/kurashi_shisei/fukushi/hokenjo/pet/hogo/koshigaya_contents_cat.html) |
| 船橋市（譲渡可能犬猫） | 千葉県 | 非空 table 行が 22 行ある | imgs=9, animal_alt_imgs=0, detail_links=0, table_rows=22, pdf_links=0, text_len=8849 | [link](https://www.city.funabashi.lg.jp/kurashi/doubutsu/003/joutoindex.html) |
| 川崎市（収容猫） | 神奈川県 | 非空 table 行が 21 行ある | imgs=3, animal_alt_imgs=0, detail_links=0, table_rows=21, pdf_links=0, text_len=9114 | [link](https://www.city.kawasaki.jp/350/page/0000109367.html) |
| 京都市ペットラブ（迷子犬） | 京都府 | 非空 table 行が 16 行ある | imgs=11, animal_alt_imgs=0, detail_links=1, table_rows=16, pdf_links=1, text_len=1389 | [link](https://kyoto-ani-love.com/lost-animal/dog/) |
| 京都市ペットラブ（迷子猫） | 京都府 | 非空 table 行が 24 行ある | imgs=11, animal_alt_imgs=0, detail_links=1, table_rows=24, pdf_links=1, text_len=1473 | [link](https://kyoto-ani-love.com/lost-animal/cat/) |
| 豊中市（迷子犬猫） | 大阪府 | 非空 table 行が 9 行ある | imgs=11, animal_alt_imgs=0, detail_links=0, table_rows=9, pdf_links=0, text_len=10067 | [link](https://www.city.toyonaka.osaka.jp/kurashi/pettp-inuneko/maigo.html) |
| 鳥取県（迷子動物情報） | 鳥取県 | 動物 alt の img が 3 件ある | imgs=25, animal_alt_imgs=3, detail_links=1, table_rows=9, pdf_links=0, text_len=2907 | [link](https://www.pref.tottori.lg.jp/221001.htm) |
| 富山県（迷い犬猫情報） | 富山県 | 非空 table 行が 11 行ある | imgs=5, animal_alt_imgs=0, detail_links=0, table_rows=11, pdf_links=0, text_len=7421 | [link](https://www.pref.toyama.jp/1207/kurashi/seikatsu/seikatsu/doubutsuaigo/syuyou/index.html) |
| 名古屋市（譲渡猫） | 愛知県 | PDF リンクが 2 件ある | imgs=12, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=2, text_len=10511 | [link](https://www.city.nagoya.jp/kurashi/pet/1015473/1015483/1015488.html) |
| 岡崎市（保護動物） | 愛知県 | PDF リンクが 3 件ある | imgs=7, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=3, text_len=5883 | [link](https://www.city.okazaki.lg.jp/1100/1107/1149/p008181.html) |
| 旭川市あにまある（譲渡犬） | 北海道 | 動物 alt の img が 3 件ある | imgs=6, animal_alt_imgs=3, detail_links=7, table_rows=0, pdf_links=0, text_len=1587 | [link](https://www.douaicenter.jp/animal/list/transfer/dog) |
| 旭川市あにまある（譲渡猫） | 北海道 | 動物 alt の img が 6 件ある | imgs=12, animal_alt_imgs=6, detail_links=7, table_rows=0, pdf_links=0, text_len=1688 | [link](https://www.douaicenter.jp/animal/list/transfer/cat) |
| 旭川市あにまある（譲渡その他） | 北海道 | detail 系リンクが 7 件ある | imgs=6, animal_alt_imgs=2, detail_links=7, table_rows=0, pdf_links=0, text_len=1602 | [link](https://www.douaicenter.jp/animal/list/transfer/other) |
| 旭川市あにまある（収容猫） | 北海道 | 動物 alt の img が 3 件ある | imgs=6, animal_alt_imgs=3, detail_links=7, table_rows=0, pdf_links=0, text_len=1601 | [link](https://www.douaicenter.jp/animal/list/sheltered/cat) |
| 旭川市あにまある（市民保護猫） | 北海道 | 動物 alt の img が 7 件ある | imgs=14, animal_alt_imgs=7, detail_links=0, table_rows=0, pdf_links=0, text_len=1766 | [link](https://www.douaicenter.jp/other-animal/list/cat) |
| 函館どうなん動物愛護センター（里親募集） | 北海道 | 非空 table 行が 10 行ある | imgs=33, animal_alt_imgs=0, detail_links=0, table_rows=10, pdf_links=3, text_len=4561 | [link](https://nyantomo.jp/donanhakodate/) |
| 仙台市アニパル（譲渡犬） | 宮城県 | 非空 table 行が 15 行ある | imgs=12, animal_alt_imgs=0, detail_links=0, table_rows=15, pdf_links=3, text_len=9958 | [link](https://www.city.sendai.jp/dobutsu/kurashi/shizen/petto/hogodobutsu/joho/inu.html) |
| 仙台市アニパル（譲渡猫） | 宮城県 | 非空 table 行が 16 行ある | imgs=21, animal_alt_imgs=0, detail_links=0, table_rows=16, pdf_links=6, text_len=13346 | [link](https://www.city.sendai.jp/dobutsu/kurashi/shizen/petto/hogodobutsu/joho/neko.html) |
| 仙台市アニパル（譲渡子猫） | 宮城県 | PDF リンクが 6 件ある | imgs=7, animal_alt_imgs=0, detail_links=0, table_rows=2, pdf_links=6, text_len=8419 | [link](https://www.city.sendai.jp/dobutsu/kurashi/shizen/petto/hogodobutsu/joho/koneko.html) |
| 福島県（中通り 迷子犬） | 福島県 | 非空 table 行が 36 行ある | imgs=11, animal_alt_imgs=0, detail_links=0, table_rows=36, pdf_links=1, text_len=4758 | [link](https://www.pref.fukushima.lg.jp/sec/21620a/maigo-dog-miharu.html) |
| 福島県（中通り 迷子猫） | 福島県 | 非空 table 行が 27 行ある | imgs=0, animal_alt_imgs=0, detail_links=0, table_rows=27, pdf_links=0, text_len=3524 | [link](https://www.pref.fukushima.lg.jp/sec/21620a/maigo-cat-miharu.html) |
| 福島県（会津 迷子犬） | 福島県 | 非空 table 行が 9 行ある | imgs=2, animal_alt_imgs=0, detail_links=0, table_rows=9, pdf_links=1, text_len=3148 | [link](https://www.pref.fukushima.lg.jp/sec/21621a/maigo-dog-aizu.html) |
| 福島県（相双 迷子犬） | 福島県 | 非空 table 行が 11 行ある | imgs=4, animal_alt_imgs=0, detail_links=0, table_rows=11, pdf_links=2, text_len=3128 | [link](https://www.pref.fukushima.lg.jp/sec/21622a/maigo-dog-soso.html) |
| 福島県（相双 迷子猫） | 福島県 | 非空 table 行が 59 行ある | imgs=2, animal_alt_imgs=0, detail_links=0, table_rows=59, pdf_links=0, text_len=2606 | [link](https://www.pref.fukushima.lg.jp/sec/21622a/maigo-cat-soso.html) |

## ⚪ unreachable — URL 失効・要対応 (5 件)

| サイト | 都道府県 | 理由 | シグナル | URL |
|---|---|---|---|---|
| 佐賀県（佐賀市・多久・小城・神埼）保護犬猫 | 佐賀県 | fetch error: HTTPSConnectionPool(host='www.pref.saga.lg.jp', port=443): Read timed out. (read | - | [link](https://www.pref.saga.lg.jp/kiji00349237/index.html) |
| 佐賀県（唐津・東松浦郡）保護犬猫 | 佐賀県 | fetch error: HTTPSConnectionPool(host='www.pref.saga.lg.jp', port=443): Read timed out. (read | - | [link](https://www.pref.saga.lg.jp/kiji00365042/index.html) |
| 佐賀県（鳥栖・三養基郡）保護犬猫 | 佐賀県 | fetch error: HTTPSConnectionPool(host='www.pref.saga.lg.jp', port=443): Read timed out. (read | - | [link](https://www.pref.saga.lg.jp/kiji00334357/index.html) |
| 佐賀県（伊万里・西松浦郡）保護犬猫 | 佐賀県 | fetch error: HTTPSConnectionPool(host='www.pref.saga.lg.jp', port=443): Read timed out. (read | - | [link](https://www.pref.saga.lg.jp/kiji00334505/index.html) |
| 佐賀県（武雄・鹿島・嬉野・杵島・藤津）保護犬猫 | 佐賀県 | fetch error: HTTPSConnectionPool(host='www.pref.saga.lg.jp', port=443): Read timed out. (read | - | [link](https://www.pref.saga.lg.jp/kiji00334341/index.html) |

## 🟡 maybe_zero — 現状ゼロが有力だが手動確認推奨 (92 件)

| サイト | 都道府県 | 理由 | シグナル | URL |
|---|---|---|---|---|
| 西讃保健福祉事務所（収容動物） | 香川県 | ゼロ表現もコンテンツ候補も少ない | imgs=1, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=1, text_len=3758 | [link](https://www.pref.kagawa.lg.jp/seisanhoken/seisanhoken/doubutuaigo/sqvuo1191030100247.html) |
| 松山市 はぴまるの丘（収容中） | 愛媛県 | ゼロ表現もコンテンツ候補も少ない | imgs=17, animal_alt_imgs=0, detail_links=0, table_rows=5, pdf_links=0, text_len=6330 | [link](https://www.city.matsuyama.ehime.jp/kurashi/kurashi/aigo/index.html) |
| 高松市 わんにゃん高松（収容中猫） | 香川県 | ゼロ表現もコンテンツ候補も少ない | imgs=12, animal_alt_imgs=0, detail_links=0, table_rows=3, pdf_links=0, text_len=392 | [link](https://www.city.takamatsu.kagawa.jp/udanimo/ani_infolist1.html?infotype=1&animaltype=2) |
| 長崎犬猫ネット（保護） | 長崎県 | ゼロ表現もコンテンツ候補も少ない | imgs=3, animal_alt_imgs=0, detail_links=3, table_rows=0, pdf_links=0, text_len=2937 | [link](https://animal-net.pref.nagasaki.jp/hogo) |
| 佐世保市（保護犬） | 長崎県 | ゼロ表現もコンテンツ候補も少ない | imgs=1, animal_alt_imgs=0, detail_links=0, table_rows=2, pdf_links=0, text_len=3565 | [link](https://www.city.sasebo.lg.jp/hokenhukusi/seikat/hogodoubutsu.html) |
| 佐世保市（保護猫） | 長崎県 | ゼロ表現もコンテンツ候補も少ない | imgs=1, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=0, text_len=3296 | [link](https://www.city.sasebo.lg.jp/hokenhukusi/seikat/mayoinekohogo.html) |
| 大分市（保護犬） | 大分県 | ゼロ表現もコンテンツ候補も少ない | imgs=2, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=0, text_len=1977 | [link](https://www.city.oita.oita.jp/kurashi/pet/inunohogo/index.html) |
| 宮崎市（センター保護犬・飼い主募集） | 宮崎県 | ゼロ表現もコンテンツ候補も少ない | imgs=8, animal_alt_imgs=1, detail_links=0, table_rows=0, pdf_links=0, text_len=1383 | [link](https://www.city.miyazaki.miyazaki.jp/life/pet/protection/109676.html) |
| 宮崎市（センター保護猫・飼い主募集） | 宮崎県 | ゼロ表現もコンテンツ候補も少ない | imgs=6, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=0, text_len=1071 | [link](https://www.city.miyazaki.miyazaki.jp/life/pet/protection/339718.html) |
| 鹿児島市（保護犬） | 鹿児島県 | ゼロ表現もコンテンツ候補も少ない | imgs=3, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=0, text_len=3798 | [link](https://www.city.kagoshima.lg.jp/kenkofukushi/hokenjo/seiei-jueki/kurashi/dobutsu/kainushi/joho/inu.html) |
| 鹿児島市（保護猫） | 鹿児島県 | ゼロ表現もコンテンツ候補も少ない | imgs=8, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=0, text_len=5049 | [link](https://www.city.kagoshima.lg.jp/kenkofukushi/hokenjo/seiei-jueki/kurashi/dobutsu/kainushi/joho/neko.html) |
| 熊本市（迷子犬一覧） | 熊本県 | ゼロ表現もコンテンツ候補も少ない | imgs=17, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=0, text_len=3411 | [link](https://www.city.kumamoto.jp/doubutuaigo/list03612.html) |
| 熊本市（迷子猫一覧） | 熊本県 | ゼロ表現もコンテンツ候補も少ない | imgs=14, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=0, text_len=2953 | [link](https://www.city.kumamoto.jp/doubutuaigo/list03615.html) |
| おおいた動物愛護センター（譲渡犬） | 大分県 | ゼロ表現もコンテンツ候補も少ない | imgs=14, animal_alt_imgs=1, detail_links=0, table_rows=0, pdf_links=0, text_len=2262 | [link](https://oita-aigo.com/information_doglist/anytimedog/) |
| おおいた動物愛護センター（譲渡猫） | 大分県 | ゼロ表現もコンテンツ候補も少ない | imgs=14, animal_alt_imgs=1, detail_links=0, table_rows=0, pdf_links=0, text_len=2085 | [link](https://oita-aigo.com/information_catlist/anytimecat/) |
| 栃木県動物愛護指導センター（保護動物） | 栃木県 | ゼロ表現もコンテンツ候補も少ない | imgs=7, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=0, text_len=965 | [link](https://www.douai.pref.tochigi.lg.jp/work_category/custody/) |
| 栃木県動物愛護指導センター（迷子動物） | 栃木県 | ゼロ表現もコンテンツ候補も少ない | imgs=6, animal_alt_imgs=0, detail_links=0, table_rows=3, pdf_links=0, text_len=2457 | [link](https://www.douai.pref.tochigi.lg.jp/work/custody-lostanimal/) |
| 群馬県動物愛護センター（保護犬） | 群馬県 | ゼロ表現もコンテンツ候補も少ない | imgs=7, animal_alt_imgs=0, detail_links=0, table_rows=2, pdf_links=0, text_len=1153 | [link](https://www.pref.gunma.jp/page/167499.html) |
| 千葉県動愛センター本所（収容猫） | 千葉県 | ゼロ表現もコンテンツ候補も少ない | imgs=4, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=0, text_len=4991 | [link](https://www.pref.chiba.lg.jp/aigo/pet/inu-neko/shuuyou/shuu-neko.html) |
| 千葉県動愛センター本所（収容犬猫以外） | 千葉県 | ゼロ表現もコンテンツ候補も少ない | imgs=3, animal_alt_imgs=0, detail_links=0, table_rows=2, pdf_links=0, text_len=4292 | [link](https://www.pref.chiba.lg.jp/aigo/pet/sonohoka/inu-nekoigai/index.html) |
| 千葉県動愛センター東葛飾支所（収容犬） | 千葉県 | ゼロ表現もコンテンツ候補も少ない | imgs=4, animal_alt_imgs=0, detail_links=0, table_rows=2, pdf_links=0, text_len=5456 | [link](https://www.pref.chiba.lg.jp/aigo/pet/inu-neko/shuuyou/shuu-inu-tou.html) |
| 神奈川県動物愛護センター（保護犬） | 神奈川県 | ゼロ表現もコンテンツ候補も少ない | imgs=0, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=1, text_len=2937 | [link](https://www.pref.kanagawa.jp/osirase/1594/awc/lost/dog.html) |
| 神奈川県動物愛護センター（保護猫） | 神奈川県 | ゼロ表現もコンテンツ候補も少ない | imgs=0, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=1, text_len=2139 | [link](https://www.pref.kanagawa.jp/osirase/1594/awc/lost/cat.html) |
| 神奈川県動物愛護センター（その他動物） | 神奈川県 | ゼロ表現もコンテンツ候補も少ない | imgs=0, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=1, text_len=3138 | [link](https://www.pref.kanagawa.jp/osirase/1594/awc/lost/other.html) |
| 横須賀市（保護猫） | 神奈川県 | ゼロ表現もコンテンツ候補も少ない | imgs=3, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=0, text_len=681 | [link](https://www.yokosuka-doubutu.com/protected-animals-cat/) |
| 横須賀市（譲渡犬） | 神奈川県 | ゼロ表現もコンテンツ候補も少ない | imgs=2, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=0, text_len=686 | [link](https://www.yokosuka-doubutu.com/adopted-animals-dog/) |
| 横須賀市（譲渡猫） | 神奈川県 | ゼロ表現もコンテンツ候補も少ない | imgs=9, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=0, text_len=784 | [link](https://www.yokosuka-doubutu.com/adopted-animals-cat/) |
| 水戸市（迷子ペット情報） | 茨城県 | ゼロ表現もコンテンツ候補も少ない | imgs=0, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=0, text_len=1206 | [link](https://www.city.mito.lg.jp/site/doubutsuaigo/list358.html) |
| 宇都宮市（迷子犬・負傷猫） | 栃木県 | ゼロ表現もコンテンツ候補も少ない | imgs=7, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=0, text_len=8135 | [link](https://www.city.utsunomiya.lg.jp/kurashi/pet/pet/1005584.html) |
| さいたま市（保護犬） | 埼玉県 | ゼロ表現もコンテンツ候補も少ない | imgs=1, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=0, text_len=6076 | [link](https://www.city.saitama.lg.jp/008/004/003/004/p003138.html) |
| さいたま市（保護猫・その他） | 埼玉県 | ゼロ表現もコンテンツ候補も少ない | imgs=2, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=0, text_len=6327 | [link](https://www.city.saitama.lg.jp/008/004/003/004/p019971.html) |
| 越谷市（保護犬） | 埼玉県 | ゼロ表現もコンテンツ候補も少ない | imgs=12, animal_alt_imgs=0, detail_links=1, table_rows=4, pdf_links=0, text_len=8647 | [link](https://www.city.koshigaya.saitama.jp/kurashi_shisei/fukushi/hokenjo/pet/hogo/koshigaya_contents_dog.html) |
| 千葉市（迷子猫） | 千葉県 | ゼロ表現もコンテンツ候補も少ない | imgs=1, animal_alt_imgs=0, detail_links=0, table_rows=2, pdf_links=0, text_len=6458 | [link](https://www.city.chiba.jp/hokenfukushi/iryoeisei/seikatsueisei/dobutsuhogo/lost_cat.html) |
| 千葉市（迷子その他動物） | 千葉県 | ゼロ表現もコンテンツ候補も少ない | imgs=1, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=0, text_len=6048 | [link](https://www.city.chiba.jp/hokenfukushi/iryoeisei/seikatsueisei/dobutsuhogo/lost_another_animal.html) |
| 千葉市（市民保護犬） | 千葉県 | ゼロ表現もコンテンツ候補も少ない | imgs=0, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=0, text_len=5433 | [link](https://www.city.chiba.jp/hokenfukushi/iryoeisei/seikatsueisei/dobutsuhogo/hogo_dog.html) |
| 千葉市（市民保護猫） | 千葉県 | ゼロ表現もコンテンツ候補も少ない | imgs=8, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=0, text_len=7282 | [link](https://www.city.chiba.jp/hokenfukushi/iryoeisei/seikatsueisei/dobutsuhogo/hogo_cat.html) |
| 千葉市（市民保護その他） | 千葉県 | ゼロ表現もコンテンツ候補も少ない | imgs=1, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=0, text_len=5721 | [link](https://www.city.chiba.jp/hokenfukushi/iryoeisei/seikatsueisei/dobutsuhogo/lost_others.html) |
| 船橋市（収容犬猫） | 千葉県 | ゼロ表現もコンテンツ候補も少ない | imgs=5, animal_alt_imgs=0, detail_links=0, table_rows=1, pdf_links=0, text_len=5016 | [link](https://www.city.funabashi.lg.jp/kurashi/doubutsu/003/p013242.html) |
| 柏市（保護動物） | 千葉県 | ゼロ表現もコンテンツ候補も少ない | imgs=3, animal_alt_imgs=0, detail_links=1, table_rows=7, pdf_links=0, text_len=5532 | [link](https://www.city.kashiwa.lg.jp/dobutsuaigo/shiseijoho/shisei/health_hospital/mainmenu/dobutsu/hogo/hogo.html) |
| 柏市（譲渡対象動物） | 千葉県 | ゼロ表現もコンテンツ候補も少ない | imgs=19, animal_alt_imgs=0, detail_links=1, table_rows=0, pdf_links=0, text_len=7535 | [link](https://www.city.kashiwa.lg.jp/dobutsuaigo/shiseijoho/shisei/health_hospital/mainmenu/dobutsu/hogo/satoya.html) |
| 町田市（収容動物のお知らせ） | 東京都 | ゼロ表現もコンテンツ候補も少ない | imgs=4, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=0, text_len=6150 | [link](https://www.city.machida.tokyo.jp/iryo/hokenjo/pet/mayoi/syuyou.html) |
| 横浜市（収容犬） | 神奈川県 | ゼロ表現もコンテンツ候補も少ない | imgs=15, animal_alt_imgs=0, detail_links=0, table_rows=2, pdf_links=0, text_len=9084 | [link](https://www.city.yokohama.lg.jp/kurashi/sumai-kurashi/pet-dobutsu/aigo/maigo/shuyoinfo.html) |
| 横浜市（収容猫） | 神奈川県 | ゼロ表現もコンテンツ候補も少ない | imgs=17, animal_alt_imgs=0, detail_links=0, table_rows=4, pdf_links=0, text_len=9644 | [link](https://www.city.yokohama.lg.jp/kurashi/sumai-kurashi/pet-dobutsu/aigo/maigo/20121004094818.html) |
| 横浜市（収容その他動物） | 神奈川県 | ゼロ表現もコンテンツ候補も少ない | imgs=15, animal_alt_imgs=0, detail_links=0, table_rows=2, pdf_links=0, text_len=9180 | [link](https://www.city.yokohama.lg.jp/kurashi/sumai-kurashi/pet-dobutsu/aigo/maigo/20121004110429.html) |
| 川崎市（収容犬） | 神奈川県 | ゼロ表現もコンテンツ候補も少ない | imgs=3, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=0, text_len=7939 | [link](https://www.city.kawasaki.jp/350/page/0000077270.html) |
| 川崎市（収容その他動物） | 神奈川県 | ゼロ表現もコンテンツ候補も少ない | imgs=3, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=0, text_len=8039 | [link](https://www.city.kawasaki.jp/350/page/0000074729.html) |
| 四日市市（保護動物情報） | 三重県 | ゼロ表現もコンテンツ候補も少ない | imgs=1, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=1, text_len=4171 | [link](https://www.city.yokkaichi.lg.jp/www/contents/1001000000924/index.html) |
| 滋賀県動物保護管理センター（迷い犬猫） | 滋賀県 | ゼロ表現もコンテンツ候補も少ない | imgs=5, animal_alt_imgs=1, detail_links=0, table_rows=0, pdf_links=0, text_len=1070 | [link](https://www.sapca.jp/lost) |
| 大津市動物愛護センター（迷い犬猫） | 滋賀県 | ゼロ表現もコンテンツ候補も少ない | imgs=0, animal_alt_imgs=0, detail_links=0, table_rows=2, pdf_links=0, text_len=5126 | [link](https://www.city.otsu.lg.jp/soshiki/021/1442/g/pet/mayoi/1387775941679.html) |
| 大阪市（迷子犬） | 大阪府 | ゼロ表現もコンテンツ候補も少ない | imgs=16, animal_alt_imgs=0, detail_links=0, table_rows=7, pdf_links=0, text_len=6776 | [link](https://www.city.osaka.lg.jp/kenko/page/0000110901.html) |
| 大阪市（迷子猫） | 大阪府 | ゼロ表現もコンテンツ候補も少ない | imgs=11, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=0, text_len=5930 | [link](https://www.city.osaka.lg.jp/kenko/page/0000117147.html) |
| 大阪市（譲渡犬） | 大阪府 | ゼロ表現もコンテンツ候補も少ない | imgs=30, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=0, text_len=7669 | [link](https://www.city.osaka.lg.jp/kenko/page/0000206024.html) |
| 大阪市（譲渡猫） | 大阪府 | ゼロ表現もコンテンツ候補も少ない | imgs=45, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=0, text_len=8916 | [link](https://www.city.osaka.lg.jp/kenko/page/0000206027.html) |
| 高槻市（迷子犬猫） | 大阪府 | ゼロ表現もコンテンツ候補も少ない | imgs=1, animal_alt_imgs=0, detail_links=0, table_rows=7, pdf_links=1, text_len=10556 | [link](https://www.city.takatsuki.osaka.jp/soshiki/39/2752.html) |
| 東大阪市（保護収容動物） | 大阪府 | ゼロ表現もコンテンツ候補も少ない | imgs=3, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=0, text_len=5933 | [link](https://www.city.higashiosaka.lg.jp/0000005910.html) |
| 兵庫県動物愛護センター（収容動物） | 兵庫県 | ゼロ表現もコンテンツ候補も少ない | imgs=8, animal_alt_imgs=0, detail_links=0, table_rows=4, pdf_links=1, text_len=2713 | [link](https://hyogo-douai.sakura.ne.jp/shuuyou.html) |
| 神戸市動物管理センター（収容動物） | 兵庫県 | ゼロ表現もコンテンツ候補も少ない | imgs=1, animal_alt_imgs=0, detail_links=1, table_rows=0, pdf_links=0, text_len=3752 | [link](https://www.city.kobe.lg.jp/a84140/kenko/health/hygiene/animal/zmenu/index.html) |
| あかし動物センター（迷子犬） | 兵庫県 | ゼロ表現もコンテンツ候補も少ない | imgs=1, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=0, text_len=2246 | [link](https://www.city.akashi.lg.jp/kankyou/dobutsu/info/maigo/dog.html) |
| あかし動物センター（迷子猫） | 兵庫県 | ゼロ表現もコンテンツ候補も少ない | imgs=1, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=0, text_len=2246 | [link](https://www.city.akashi.lg.jp/kankyou/dobutsu/info/maigo/cat.html) |
| 奈良市（保護動物情報） | 奈良県 | ゼロ表現もコンテンツ候補も少ない | imgs=0, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=0, text_len=5054 | [link](https://www.city.nara.lg.jp/life/4/34/134/) |
| 和歌山県（保護犬猫情報） | 和歌山県 | ゼロ表現もコンテンツ候補も少ない | imgs=0, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=0, text_len=2379 | [link](https://www.pref.wakayama.lg.jp/prefg/031601/d00156970.html) |
| 和歌山市動物愛護管理センター（譲渡候補） | 和歌山県 | ゼロ表現もコンテンツ候補も少ない | imgs=27, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=0, text_len=9683 | [link](https://www.city.wakayama.wakayama.jp/kurashi/kenko_iryo/1009125/1035775/1002096.html) |
| 島根県 松江保健所（収容動物） | 島根県 | ゼロ表現もコンテンツ候補も少ない | imgs=1, animal_alt_imgs=0, detail_links=1, table_rows=4, pdf_links=0, text_len=1203 | [link](https://www.pref.shimane.lg.jp/infra/nature/animal/matsue_hoken/doubutu/hogozyouhou_kakobunn/syuyouari.html) |
| 岡山市（保護動物情報） | 岡山県 | ゼロ表現もコンテンツ候補も少ない | imgs=4, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=0, text_len=3155 | [link](https://www.city.okayama.jp/kurashi/category/1-15-1-0-0-0-0-0-0-0.html) |
| 広島県動物愛護センター（迷い猫） | 広島県 | ゼロ表現もコンテンツ候補も少ない | imgs=0, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=0, text_len=4906 | [link](https://www.pref.hiroshima.lg.jp/site/apc/jouto-stray-cat-list.html) |
| 広島市（迷子犬） | 広島県 | ゼロ表現もコンテンツ候補も少ない | imgs=4, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=0, text_len=6824 | [link](https://www.city.hiroshima.lg.jp/living/pet-doubutsu/1021301/1026245/1037461.html) |
| 広島市（迷子猫） | 広島県 | ゼロ表現もコンテンツ候補も少ない | imgs=4, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=0, text_len=6922 | [link](https://www.city.hiroshima.lg.jp/living/pet-doubutsu/1021301/1026245/1039097.html) |
| 福山市（保護犬） | 広島県 | ゼロ表現もコンテンツ候補も少ない | imgs=0, animal_alt_imgs=0, detail_links=0, table_rows=2, pdf_links=0, text_len=3329 | [link](https://www.city.fukuyama.hiroshima.jp/soshiki/dobutsuaigo/237722.html) |
| 福山市（保護猫） | 広島県 | ゼロ表現もコンテンツ候補も少ない | imgs=0, animal_alt_imgs=0, detail_links=0, table_rows=2, pdf_links=0, text_len=3322 | [link](https://www.city.fukuyama.hiroshima.jp/soshiki/dobutsuaigo/60970.html) |
| 山口県動物愛護センター（収容動物） | 山口県 | ゼロ表現もコンテンツ候補も少ない | imgs=8, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=0, text_len=2532 | [link](https://www.pref.yamaguchi.lg.jp/site/doubutuaigo/list25-151.html) |
| 石川県（保護犬・猫情報） | 石川県 | ゼロ表現もコンテンツ候補も少ない | imgs=15, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=0, text_len=4106 | [link](https://www.pref.ishikawa.lg.jp/yakuji/doubutsu/hogoinuneko.html) |
| 山梨県（探している犬） | 山梨県 | ゼロ表現もコンテンツ候補も少ない | imgs=42, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=0, text_len=4366 | [link](https://www.pref.yamanashi.jp/doubutsu/m_dog/index.html) |
| 山梨県（探している猫） | 山梨県 | ゼロ表現もコンテンツ候補も少ない | imgs=117, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=0, text_len=7892 | [link](https://www.pref.yamanashi.jp/doubutsu/m_cat/index.html) |
| 山梨県（探している他のペット） | 山梨県 | ゼロ表現もコンテンツ候補も少ない | imgs=19, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=0, text_len=3423 | [link](https://www.pref.yamanashi.jp/doubutsu/m_other/index.html) |
| 山梨県（保護されている犬） | 山梨県 | ゼロ表現もコンテンツ候補も少ない | imgs=1, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=0, text_len=2769 | [link](https://www.pref.yamanashi.jp/doubutsu/p_dog/index.html) |
| 山梨県（保護されている猫） | 山梨県 | ゼロ表現もコンテンツ候補も少ない | imgs=29, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=0, text_len=4219 | [link](https://www.pref.yamanashi.jp/doubutsu/p_cat/index.html) |
| 山梨県（保護されている他のペット） | 山梨県 | ゼロ表現もコンテンツ候補も少ない | imgs=2, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=0, text_len=2806 | [link](https://www.pref.yamanashi.jp/doubutsu/p_other/index.html) |
| 静岡県（保護犬猫情報） | 静岡県 | ゼロ表現もコンテンツ候補も少ない | imgs=15, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=0, text_len=5553 | [link](https://www.pref.shizuoka.jp/kenkofukushi/eiseiyakuji/dobutsuaigo/1066835/index.html) |
| 浜松市はぴまるの丘（保護犬） | 静岡県 | ゼロ表現もコンテンツ候補も少ない | imgs=1, animal_alt_imgs=0, detail_links=0, table_rows=6, pdf_links=0, text_len=2823 | [link](https://www.hama-aikyou.jp/hogoinu/index.html) |
| 名古屋市（飼主不明動物） | 愛知県 | ゼロ表現もコンテンツ候補も少ない | imgs=3, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=0, text_len=6815 | [link](https://www.city.nagoya.jp/kurashi/pet/1015473/1015489/1015493.html) |
| 名古屋市（譲渡犬） | 愛知県 | ゼロ表現もコンテンツ候補も少ない | imgs=4, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=0, text_len=7052 | [link](https://www.city.nagoya.jp/kurashi/pet/1015473/1015483/1015484.html) |
| 豊橋市あいくる（迷い犬） | 愛知県 | ゼロ表現もコンテンツ候補も少ない | imgs=2, animal_alt_imgs=0, detail_links=0, table_rows=4, pdf_links=0, text_len=1095 | [link](https://toyohashi-aikuru.jp/animal_category/lost-found?animal_type=dog) |
| 豊橋市あいくる（迷い猫） | 愛知県 | ゼロ表現もコンテンツ候補も少ない | imgs=1, animal_alt_imgs=0, detail_links=0, table_rows=4, pdf_links=0, text_len=1034 | [link](https://toyohashi-aikuru.jp/animal_category/lost-found?animal_type=cat) |
| 豊田市動物愛護センター（迷子動物） | 愛知県 | ゼロ表現もコンテンツ候補も少ない | imgs=3, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=1, text_len=6495 | [link](https://www.city.toyota.aichi.jp/kurashi/sumai/pet/1003696.html) |
| 札幌市（迷子犬） | 北海道 | ゼロ表現もコンテンツ候補も少ない | imgs=17, animal_alt_imgs=0, detail_links=0, table_rows=6, pdf_links=0, text_len=5272 | [link](https://www.city.sapporo.jp/inuneko/syuuyou_doubutsu/maigoinu.html) |
| 札幌市（迷子猫） | 北海道 | ゼロ表現もコンテンツ候補も少ない | imgs=17, animal_alt_imgs=0, detail_links=0, table_rows=6, pdf_links=0, text_len=3991 | [link](https://www.city.sapporo.jp/inuneko/syuuyou_doubutsu/maigoneko2.html) |
| アニウェル北海道（猫の里親募集） | 北海道 | ゼロ表現もコンテンツ候補も少ない | imgs=10, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=0, text_len=1161 | [link](https://aniwel.jp/cats/) |
| ワンニャピアあきた（譲渡犬） | 秋田県 | ゼロ表現もコンテンツ候補も少ない | imgs=0, animal_alt_imgs=0, detail_links=1, table_rows=7, pdf_links=0, text_len=862 | [link](https://wannyapia.akita.jp/pages/protective-dogs) |
| ワンニャピアあきた（譲渡猫） | 秋田県 | ゼロ表現もコンテンツ候補も少ない | imgs=0, animal_alt_imgs=0, detail_links=2, table_rows=7, pdf_links=0, text_len=801 | [link](https://wannyapia.akita.jp/pages/protective-cats) |
| 岩手県（保護動物情報・ハブ） | 岩手県 | ゼロ表現もコンテンツ候補も少ない | imgs=3, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=0, text_len=9603 | [link](https://www.pref.iwate.jp/kurashikankyou/anzenanshin/pet/1004615.html) |
| 山形県（飼い主探し掲示板・ハブ） | 山形県 | ゼロ表現もコンテンツ候補も少ない | imgs=5, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=0, text_len=2586 | [link](https://www.pref.yamagata.jp/020071/kenfuku/doubutsuaigo/aigo/kainushisagashi/keijiban.html) |
| 福井県（動物保護センター） | 福井県 | ゼロ表現もコンテンツ候補も少ない | imgs=4, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=0, text_len=2890 | [link](https://www.pref.fukui.lg.jp/doc/doukansi/doubutukanrisidou/doukansi-c-4.html) |

## 🟢 true_zero — 現状ゼロが正常（対応不要） (4 件)

| サイト | 都道府県 | 理由 | シグナル | URL |
|---|---|---|---|---|
| 栃木県動物愛護指導センター（譲渡動物） | 栃木県 | 明示的ゼロ表現あり | imgs=3, animal_alt_imgs=0, detail_links=0, table_rows=0, pdf_links=0, text_len=1822 | [link](https://www.douai.pref.tochigi.lg.jp/jyouto/) |
| 群馬県動物愛護センター東部支所（保護犬） | 群馬県 | 明示的ゼロ表現あり | imgs=7, animal_alt_imgs=0, detail_links=0, table_rows=2, pdf_links=0, text_len=1092 | [link](https://www.pref.gunma.jp/page/179441.html) |
| 群馬県動物愛護センター（保護猫） | 群馬県 | 明示的ゼロ表現あり | imgs=7, animal_alt_imgs=0, detail_links=0, table_rows=3, pdf_links=0, text_len=1151 | [link](https://www.pref.gunma.jp/page/167523.html) |
| 水戸市（愛護センター収容中の動物たち） | 茨城県 | 明示的ゼロ表現あり | imgs=5, animal_alt_imgs=0, detail_links=0, table_rows=12, pdf_links=0, text_len=1563 | [link](https://www.city.mito.lg.jp/site/doubutsuaigo/2043.html) |

## ⏭️ skipped_js — Playwright 監査が別途必要 (14 件)

| サイト | 都道府県 | 理由 | シグナル | URL |
|---|---|---|---|---|
| 徳島県動物愛護管理センター（譲渡犬） | 徳島県 | requires_js: true (Playwright 必要) | - | [link](https://douai-tokushima.com/transfer/doglist) |
| 徳島県動物愛護管理センター（譲渡猫） | 徳島県 | requires_js: true (Playwright 必要) | - | [link](https://douai-tokushima.com/transfer/catlist) |
| さぬき動物愛護センター（譲渡犬猫） | 香川県 | requires_js: true (Playwright 必要) | - | [link](https://www.pref.kagawa.lg.jp/s-doubutuaigo/sanukidouaicenter/jyouto/s04u6e190311095146.html) |
| 徳島県動物愛護管理センター（収容中） | 徳島県 | requires_js: true (Playwright 必要) | - | [link](https://douai-tokushima.com/stray/) |
| 福岡市わんにゃん（犬保護中） | 福岡県 | requires_js: true (Playwright 必要) | - | [link](https://www.wannyan.city.fukuoka.lg.jp/yokanet/animal/animal_posts/index?type_id=1&sorting_id=4) |
| 福岡市わんにゃん（猫保護中） | 福岡県 | requires_js: true (Playwright 必要) | - | [link](https://www.wannyan.city.fukuoka.lg.jp/yokanet/animal/animal_posts/index?type_id=2&sorting_id=4) |
| 福岡市わんにゃん（犬譲渡） | 福岡県 | requires_js: true (Playwright 必要) | - | [link](https://www.wannyan.city.fukuoka.lg.jp/yokanet/animal/animal_posts/index?type_id=1&sorting_id=5) |
| 福岡市わんにゃん（猫譲渡） | 福岡県 | requires_js: true (Playwright 必要) | - | [link](https://www.wannyan.city.fukuoka.lg.jp/yokanet/animal/animal_posts/index?type_id=2&sorting_id=5) |
| 熊本県動愛（団体譲渡犬） | 熊本県 | requires_js: true (Playwright 必要) | - | [link](https://www.kumamoto-doubutuaigo.jp/animals/group/type_id:2/animal_id:1) |
| 熊本県動愛（個人保護犬） | 熊本県 | requires_js: true (Playwright 必要) | - | [link](https://www.kumamoto-doubutuaigo.jp/post_animals/index/type_id:2/animal_id:1) |
| 熊本県動愛（個人保護猫） | 熊本県 | requires_js: true (Playwright 必要) | - | [link](https://www.kumamoto-doubutuaigo.jp/post_animals/index/type_id:2/animal_id:2) |
| 熊本県動愛（迷子猫） | 熊本県 | requires_js: true (Playwright 必要) | - | [link](https://www.kumamoto-doubutuaigo.jp/animals/index/type_id:1/animal_id:2) |
| 東京都収容動物情報（犬） | 東京都 | requires_js: true (Playwright 必要) | - | [link](https://shuyojoho.metro.tokyo.lg.jp/) |
| 愛知県わんにゃんナビ | 愛知県 | requires_js: true (Playwright 必要) | - | [link](https://wannyan-navi.pref.aichi.jp/) |
