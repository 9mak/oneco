# レシピの書き方

レシピは「そのページから動物の一覧をどう読むか」の手順書。1 ページ（台帳の 1 エントリ）に 1 ファイル、`recipes/<slug>.yaml`。
プログラムは 1 つ（`collector/recipe.py`）で、レシピを読んで動く。新しいサイトはレシピを 1 枚足すだけ。

## 最小の例（一覧ページに表があるだけ）

```yaml
rows: "table.list tr"          # 動物 1 頭 = この CSS セレクタにマッチする要素 1 つ
image: "img@src"               # 行の中の写真（省略時は img@src）
# image: {selector: "td img@src", exclude: ["noimage"], strip_query: true}   # 除外パターン、?以降の除去（ID の安定化）
# image: {selector: "p.imagecenter img@src", scope: prev_siblings}   # 写真が行の外（直前の兄弟要素）にあるとき。前の行（同じタグ）まで遡り文書順で先の 1 枚
# image: {selector: "img@src", scope: self_or_prev_siblings}        # 行の中を先に探し、無ければ prev_siblings と同じ範囲（ページによって写真が表の中だったり外だったりするとき。岐阜県）
# image: {selector: "p.imageright img@src", scope: prev_siblings, stop_at: row}   # 遡りを「同じタグ名」でなく「前の行（rows に当たる要素）」で止める（行も写真も p のとき。岩手県）
# image: {selector: "p.imagecenter img@src", scope: next_siblings}   # 写真が行の後ろ（直後の兄弟要素）にあるとき。prev_siblings と対称（名古屋市 譲渡猫）。self_or_next_siblings もある
# image: {selector: "img@src", match_field: management_no}   # 写真が本体と別の表にあるとき。行で取った項目（管理番号）の値を src か alt に含む画像を文書全体から探し、文書順で先の 1 枚（仙台市 譲渡猫）。前が英数字・後ろが数字の位置には当てない（C2509 を c25093.jpg に当てない）。後ろに英字 1 文字の枝番が付くもの（c22068b.jpg・alt「C22068B」）は同じ子として当て、英字 2 文字以上や英字の後ろに英数字が続くものは当てない。枝番の英字が別の子を表すサイト（本体の表に C25093A・C25093B がある）では使わない。値が無い・見つからない行は写真なし
fields:
  name: "td:nth-of-type(2)"
  sex:  "td:nth-of-type(3)"
```

## 手順（`steps`）— 一覧にたどり着くまで

`steps` は上から順に実行され、最後に得た HTML に対して `rows` を適用する。
複数のページ（次ページ・複数 PDF・複数の個別ページ）が得られた場合は全部に `rows` を適用して合算する。

```yaml
steps:
  - follow: "iframe#animalFrame@src"      # セレクタ@属性 のリンクを 1 本辿る（相対 URL 可）
  - follow_text: "保護収容情報"            # リンク文字にこの語を含む a を辿る（最初の 1 本）
  - follow_all: "a.detail@href"           # マッチする全リンクを辿る（個別ページ方式。各ページが 1 頭なら rows: "body"）
  - paginate: "div.next a@href"           # 「次へ」がある限り辿る（最大 max_pages、既定 20）
  - pdf_links: "a[href$='.pdf']@href"     # PDF を全部取り、文字と表にする（下記 PDF 方式）
  - render: true                          # JavaScript 描画が必要なとき（Playwright）。最初に置く
  - render: {wait_for: "table.list tr", wait_ms: 3000}   # 描画後にこのセレクタが現れるまで待つ（最長 20 秒）。一覧を JS が後から組み立てるサイト用。現れない日はそのまま続ける（0 頭は empty_text で）
```

`follow` 系の値は `セレクタ@属性`。`@属性` を省くと `@href`。

`follow_all` と `pdf_links` に `skip_errors: true` を付けると、子が「ページが無い」（HTTP 404・410）ときはその 1 本だけ捨てて続ける（一覧に消えた個別ページへのリンクが残る群馬県・岐阜県）。捨てた子は `collector show` の trace（`skip <URL>: <理由>`）と report.json の `skipped` に残る。

```yaml
steps:
  - follow_all: "div.detail_free a[href*='/page/']@href"
    skip_errors: true
```

- サーバーエラー・接続失敗・robots 拒否は捨てない（一時的なことが多く、黙って頭数を減らすより読めなかったと通知する方がよい）
- 辿ろうとした子が全部失敗した日は従来どおり失敗（全部 404 の日を 0 頭にしない）。リンクが 1 本も無い日は文書 0 で続き、0 頭かどうかは empty_text / empty_selector で決まる
- 404 の URL を `:not([href=...])` で固定除外しない（ページが戻っても読めなくなる。岐阜県の揖斐センターは 2026-10-05 に戻っていた）。動物でない導線（「一覧へ戻る」等）の除外は従来どおりセレクタで

一覧が API 応答にしか無く `<a href>` が無い SPA（愛知わんにゃんナビ = Bubble）は `render_json`。入口を描画しながら `match` を含む URL の JSON 応答を捕まえ、`path` の値を `follow` の `{value}` に差し込んで個体ページを（既定では描画して）辿る:

```yaml
steps:
  - render_json:
      match: "elasticsearch/search"      # 応答 URL の一部
      path: "hits.hits[]._id"            # 値の場所（[] は配列の各要素）
      follow: "https://example.jp/?page=detail&no={value}"
      max: 200                           # 辿る上限（既定 100）
      render: true                       # 個体ページも描画する（既定 true）
rows: "body"                             # 個体ページ 1 枚 = 1 頭
```

## 行の絞り込み

```yaml
rows: "ul.news > li"
row_filter:
  text_has_any: ["収容日", "管理番号"]   # どれかを含む行だけ
  text_lacks: ["見出し", "譲渡済"]        # 含む行は捨てる
  min_text_length: 10
  field_lacks: {name: ["探しています"]}   # 取った項目にこの語があれば捨てる（rows: body で行の全文にメニュー文言が混ざるとき用）。全部捨てた日は「該当なし」扱い
  field_has_any: {name: ["探しています"]} # field_lacks の逆。取った項目にこの語が 1 つも無い行は捨てる（同じ一覧から一部だけを別 slug で拾う。旭川市の「探してます」）
```

## 1 頭分が兄弟要素に分かれているページ（`row_until`）

「h2（管理番号）→ p（写真）→ p（種類：…）→ p（性別：…）」のように、1 頭を包む要素が無く兄弟要素が平らに並ぶページ（鹿児島市・大分市・千葉市・長野県 等）。`rows` に当たった要素を 1 頭の始まりとし、後ろの兄弟要素を次のどれかの手前までまとめて 1 行にする。

- 次の始まり（`rows` に当たる要素）か、それを中に含む要素（さいたま市: 2 頭目だけ div に包まれている）
- `row_until` に当たる要素（節や掲載日の見出しなど、1 頭分でない区切り）

```yaml
rows: "#tmp_contents > h2"     # 1 頭の始まり。row_filter はまとめた行の全文に効くので本文の範囲に絞る
row_until: "h2"                # 区切り。次の始まりで止めるだけなら rows と同じでよい（まとめを有効にするのに必要）
fields:
  management_no: {selector: "h2", regex: "No\\.?\\s*(\\d+)"}   # 自分の見出しは selector で（下の注意）
  sex: {label: "性別"}
image: "img@src"               # まとめた行の中の 1 枚目
```

- まとめた行は元の要素を複製した div。`fields`・`image`・`row_filter` はその中を探す。`from: heading` と `image` の `prev_siblings` / `next_siblings` は、元の文書上の始まりの要素を基準にする
- 始まりの要素が見出しそのもの（`rows: h2` 等）のとき、`from: heading` は「前の子の見出し」を指す。自分の見出しは `selector` で取る
- 始まりの候補に動物でないもの（先頭の注意書き・区切りだけの div・空の雛形）が混ざるときは `text_has_any`（保護日・管理番号 等）や `text_lacks` で落とす
- 1 頭ごとに区切りの h3 を包む div が前に付くページは、その div を始まりにする（川崎市 その他動物: `rows: "div.main_naka_kiji div:has(> h3)"`、`row_until: "div:has(> h2)"`）。写真が表の前でも後ろでも同じ子に付く。同じ CMS でも包みの無いページ（川崎市 収容犬は h3 が本文の div の直下に並ぶ）では本文全体が 1 行になり 2 頭目以降が消えるので、動物が載った日の実物で確かめてから使う
- 始まりの間にある裸の文字（`<h3>No.1</h3>種類：柴<br>…`）もまとめた行に入る。区切りが兄弟の中にある（`<div><h2>お家が決まりました</h2>…</div>`）ときも、その兄弟の手前で止まる
- 最後の子は、区切りが無ければ親要素の終わりまでをまとめる。後ろにバナー等の画像があるページでは、写真の無い最後の子がそれを拾わないよう `image` の selector か `exclude` で絞る
- row_until に切り替える前に、動物が複数いる日・0 頭の日・最後の子に写真が無い日の 3 種類の保存ページ（Wayback Machine 等）に、変更前と変更後のレシピを当てて比べる。今日のページだけで確かめると、別の日の作りで子が消えたり偽の 1 頭やバナー画像が付いたりする（川崎市 収容犬・千葉市 迷子猫で 2 回起きた。2026-10-05）。写真は本文の p 直下の img のように絞る（`image: "p > img@src"`）
- 1 枚目が文字入りのポスターのときは `image: {selector: "img@src", exclude: ["maigo_pos"]}` のように外す（越谷市）
- 項目が 1 つの p に `<br>` 区切りでまとまるページ（千葉市 迷子犬・迷子猫）は、文字にすると「収容場所：若葉区御殿町 種類：雑種 …」と空白でつながる。空白を含みうる値は、その p を指して次の「項目名：」の手前まで取る（`city_chiba-1.yaml` の location・breed・color）。p の最後の項目（特徴）は行末まで

```yaml
location: {selector: "p:-soup-contains('収容場所')", regex: "収容場所[:：]\\s*(?=\\S)(?![^\\s\\d:：]{1,8}[:：])(.+?)(?=\\s+(?![A-Za-zＡ-Ｚａ-ｚ])[^\\s\\d:：]{1,8}[:：]|$)"}
```

## 項目（`fields`）

値は次のどれか。

```yaml
fields:
  name: "h3"                                # CSS セレクタ → その要素のテキスト
  sex: {selector: "td.sex", attr: "data-v"} # 属性を取る
  age: {label: "年齢"}                       # 「年齢」と書かれた th/dt/td の隣の値を取る（表の縦横どちらでも）
  breed: {regex: "犬種[:：]\\s*(\\S+)"}      # 行のテキストに正規表現、group(1)
  shelter_date: {label: "収容日", regex: "(\\d+年\\d+月\\d+日)"}   # 組み合わせ可
  note: {selector: "td.memo", default: null}
  management_no: {index: 0}                 # PDF 表の列番号（HTML の行には効かない。HTML の表の n 列目は下の :nth-child）
  management_no: {selector: ":scope > :nth-child(1)"}   # HTML の表の行の 1 列目（th・td どちらでも。見出しも値も th の表＝島根県の収容動物の表）
  management_no: {from: heading, selector: "h3", regex: "番号[:：]\\s*(\\d\\S*)"}   # 行より前にある直近の見出しから取る（regex は見出しの文字に当たる）
```

使える項目名: `name` `sex` `age` `breed` `color` `size` `management_no` `shelter_date` `note` `species` `detail`（個体ページの URL）`location`（同じページに複数センターが混ざるときだけ）。

- `label` の値は、見出しセル（th・td・dt）の隣の td・dd。値が label の文字を含んでも取る（「保健所」→「菊池保健所」）。隣のセルが見出しに見えるとき（th・dt で label を含む・label そのもの・中に「備考: …」とある・見出しも隣も td で隣が label で始まる）だけ捨て、次の行の同じ列 → 表の先頭行 → 「label：値」の順に探す
- `label` は候補の並びでも書ける（`{label: ["収容日", "収容期日"]}`）。前から順に試し、最初に取れた値を使う
- `header_row: true` は、label が表の **見出し行**（1 行に項目名が並ぶ）にあるときの読み方。見出しの語と一致するセル（記号・空白を除いて label と同じ）の列を、同じ表の次の行から読む（thead と tbody をまたぐ）。隣のセルは見ない。見出し行の書き方（th・td、thead・tbody）が日によって変わるページで使う（越谷市: 2023 年は tbody の td で見出しを書き、label だけだと隣の見出し「収容期限」を収容日に取った。2024〜2025 年は thead の th と tbody の td で値が取れなかった。列の位置で読むと、列順が違う日〔種類・性別・毛色・年齢〕に取り違える）
- `join` は、並べた指定（上のどれでも）で取った値を `sep`（既定は空白）でつなぐ。取れなかった値と、前と同じ値は飛ばす。状態の印と本文が別のセルにあるとき（明石 飼い主募集の猫: `note: {join: [{label: "仮名", regex: "(トライアル(?:中|予定))"}, {label: "性格"}], sep: "。"}` →「トライアル中。<性格>」）
- 「label：値」の書き方から取るときは最初の空白までの 1 語になる。文中に空白が入る項目（特徴・備考）は `note: {selector: "p:-soup-contains('特徴')", regex: "特徴[:：]\\s*(.+)"}` のように regex で行末まで取る
- 項目の値（selector・label・from: heading の文字と、regex を当てる全文）は、span・a・b・strong・font などインライン要素の境目に空白を入れない（佐世保市 `<span>令</span>和8年…` →「令和8年…」）。セル・p・div・li・見出し・br・img の境目と元の HTML の空白は従来どおり空白 1 つ
- row_filter・種別の `from: text`・empty_text は、従来どおり全部の境目に空白を入れた文字で照合する（`<span>0</span>匹` は「0 匹」。福島県の text_lacks はこれに頼っている）

## 種別（犬か猫か）

台帳の `species` が `dog` か `cat` ならそれを使う。`mixed` のページはレシピで決める。

```yaml
species:
  from: heading                 # heading | field | text
  selector: "h3"                # heading: 行より前にある直近の見出し
  # from: field なら fields.species の値、from: text なら行のテキスト全体、from: url なら文書の URL（dog.pdf / cat.pdf で分かれるとき）
  map: {"犬": dog, "猫": cat, "ねこ": cat, "イヌ": dog}   # 部分一致。どれにも当たらなければ種別なし（下記）
  # allow_other: true           # どれにも当たらない子を other（犬猫以外）にする。map に当たらない＝犬猫以外、と言い切れる一覧だけ
  # infer: true                 # 下記
```

決まる順: 台帳の `species`（dog / cat）→ `map` → `infer`。どれでも決まらない子は捨てずに **種別なし**（JSON の `species: null`）で載る（2026-10-05 から。それまでは「犬か猫か分からない」で捨てていた）。
サイトでは種別のバッジを出さず、犬・猫の絞り込みには入れず「すべて」でだけ出る。見出しは「保護中の子」のように種別の語を使わない。
犬か猫かを無理に決めない（既定値を置かない）。「その他」（other）は犬猫以外と分かっている子だけで、種別なしとは別。

| レシピ | map に当たる | 当たらない |
|---|---|---|
| `allow_other` なし | dog / cat（map の値） | 種別なし（null） |
| `allow_other: true` | dog / cat（map の値） | other（犬猫以外） |

これまで「犬か猫か分からない」で偶然落ちていた **動物でない行**（「譲渡が決まりました」「飼い主に戻りました」の報告・表の見出し行・案内・雛形）は、
種別なしで載ってしまうので `row_filter` や `rows` で明示的に落とす（釜石: `text_has_any` で動物種別・種類・性別のある行だけ、水戸: `text_lacks: ["飼い主に戻りました"]`、山形: `rows: "#tmp_main table tr:has(> td), #tmp_main table tr:has(img)"` で th だけの見出し行を除きつつ th で書いたデータ行（写真あり）は読み、`text_lacks: ["返還することができました"]` で返還済みの行を落とす）。

エンジンも種別なしの行に限って次の 2 つを自動で捨てる（種別が決まる行・`allow_other` の行には効かない。レシピの指定の代わりにはしない）:

- 掲載が終わった言い方（返還しました・返還済・飼い主が見つかり・譲渡先が決まりました・里親さんが決まりました・譲渡決定 等。「見つかりますように」「見つかり次第」「戻りたい」「譲渡済みの場合があります」のような願い・条件・注意書きは除く）が、行の文か、行の直前の見出し（h2・h3・h4）にある行。見出しにだけ書く作り（二戸「譲渡先が決まりました。」の下の子）があるので見出しも見る
- 写真が無く、`breed`・`color`・`sex`・`age`・`size`・`location`・`note` のうち埋まっている項目が 2 つ未満の行（0 頭の雛形に番号だけ残ったもの。佐賀）。このため記述の項目を 1 つ以下しか取らないレシピでは、写真の無い種別なしの子は載らない。種別なしの子を載せたいページでは記述の項目を 2 つ以上取る

動物種の欄が無く犬猫が混ざる表（山口県 周南）は `infer: true`。`map` で決まらない行に限り、`breed`・`color` の欄に犬だけ・猫だけに使う語（柴・チワワ・プードル・テリア… / キジ・サバトラ・三毛・ハチワレ・シャム…。エンジンが持つ表）があればそれで決める。両方当たる行・どちらも無い行は決めず、種別なしで載る。雑種・MIX・茶トラ・サビ・大きさ（小・中・大）は犬猫どちらにも使われるので見ない。保護場所や備考も見ない（「柴田町」で犬にしない）。既定値（全部犬 等）を `map` に置くと猫を犬と誤表示するので使わない。

## 動物とみなす条件（自動・レシピに書かない）

行は次のどれかを満たすときだけ動物として通る。満たさない行は捨てる。

- 写真がある（`image` で取れ、その URL が元の HTML に実在する）。自治体の「写真なし」プレースホルダ（`noimage01.jpg`・`no_photo`・`no_gazou.png`・`準備中` 等）は写真とみなさず、サイトでは「写真はありません」になる
- `management_no` または `shelter_date` が取れた
- `detail`（個体ページの URL）が取れた

見出し行・案内文・広告はどれも持たないので落ちる。

## 元ページのリンク（source_url）

個体の「自治体のページで詳細を見る」は、`detail` があればその URL、無ければ読んだ文書の URL。
ただし PDF は日次で差し替わってファイル名が変わる（香川 `r8-9-28.pdf`、茨城 `inu0924.pdf`）ので、PDF の子は既定で入口ページ（台帳の URL か `url:`）を指す。PDF そのものを指したいときだけ:

```yaml
source_url: doc
```

## 空のとき

```yaml
empty_text: ["現在いません", "現在収容している犬はいません"]
```

1 頭も取れず、かつ `empty_text` のどれかがページにあれば「本当に 0 頭」。どれもなければ「読めなかった」扱いになり通知に載る。
照合するのは本文と画像の alt（0 頭のときだけ「現在、掲載する情報はありません」の画像を出すサイトがある。豊中市）。
**常に出ている説明文（「下の欄に情報がない場合は…」「写真をクリックすると…」など）を empty_text にしない**。構造が変わって行が取れなくなった日も「0 頭」に見えて通知が来なくなる。0 頭の日にだけ出る文言を選ぶ。
恒常的に 0 頭でリンクだけ出したいページ（動物が SNS に移った等）は、台帳で `mode: link_only` にする。

0 頭の日に文言を出さず、一覧の器が空になるだけのサイトは `empty_selector`（文字列か列）。合う要素があり、合った要素がすべて空（子要素も文字も無い。空白とコメントは無視）なら 0 頭。器が無い日（構造が変わった日）や、器に中身があるのに行が取れない日は「読めなかった」で通知に載る。empty_text と併用でき、どちらかが当たれば 0 頭。常に出ている見出しを empty_text に入れて代用しない。

```yaml
empty_selector: "div.dog-cat-list"     # 豊橋市あいくる。福岡県動物愛護センターは "div.animals-list ul"
```

0 頭の日に一覧の器ごと消え、文言も出ないサイトは `empty_absent`。`page`（0 頭の日も出る枠。見出し等）に合う要素があり、`none`（一覧の器と個体ページへのリンク）に合う要素が 1 つも無い文書があれば 0 頭。枠が無い日（ブロック画面・作り替え）や、器の名前が変わってもリンクが残る日は「読めなかった」で通知に載る。`none` には器だけでなく個体ページへのリンクも入れる（器の名前だけだと、名前が変わった日を 0 頭に見せる）。

```yaml
empty_absent:                          # 静岡県 迷い犬情報一覧（0 頭の日は ul.listlink が出ない。Wayback 2025-08-31・10-10 も同じ）
  page: "article#content h1:-soup-contains('迷い犬情報一覧')"
  none: "article#content ul.listlink, article#content a[href*='dobutsuaigo/1066835/']:not([href*='index.html'])"
```

## 文字コード・その他

```yaml
encoding: euc-jp          # 自動判定で化けるときだけ
max_pages: 30             # paginate の上限
base_url: https://…       # 相対 URL の基準を変えたいとき（通常不要）
```

## 取得の失敗と取り直し（エンジンの既定・レシピに書かない）

- 同じホストへの要求は 1 秒あける
- 確立した接続をサーバーが閉じた・切ったとき（RemoteProtocolError「Server disconnected without sending a response」・ReadError・WriteError）だけ、2 秒、次に 5 秒待って新しい接続で 2 回まで取り直す。熊本県動物愛護センターは Keep-Alive の timeout が 1 秒でこの間隔とほぼ同じため、空いた接続を使い回した瞬間に閉じられることがある
- 接続失敗（DNS 不達・回線断）・タイムアウト・HTTP 4xx/5xx は取り直さず、その slug は failed（回線断の日を長引かせない。その日は読めないページが 2 割を超え、latest.json は前日のまま）
- render（Playwright）は取り直さない（Chromium が自分で処理する）

## 1 つのページに区分が混ざるとき（slug を分ける）

台帳の kind は slug に 1 つ。1 ページに迷子（stray）と譲渡（adoption）が混ざるときは、節ごとに slug を分ける（岩手県 大船渡・一関）。

- 同じ url の slug を 2 つ作り、rows を節の見出しで絞る（`h2:-soup-contains('【譲渡】') + p.imagecenter + p`）
- 元の slug は載っている子が多い側に残す（ID は slug ごとに決まるので、新しい slug の子は ID が新しくなる）
- `image` に `scope: prev_siblings, stop_at: row` を使うときは、image の selector も節の見出しで絞る。stop_at: row は「この slug の rows」で止まるので、別の節の行が rows に無いと遡りが別の節まで届く
- 0 頭の文言は節ごとに empty_text に入れる
- 索引から別ページに分かれるとき（一関）は、台帳 url は索引のまま、follow_all のリンク文言を slug ごとに絞る
- 支所ごとにページが分かれるとき（兵庫県動物愛護センター）は、一覧からの follow_all をやめ、支所ごとに url を固定した slug にする

## PDF 方式

```yaml
steps:
  - pdf_links: "a[href$='.pdf']@href"
pdf:
  mode: table              # table: 表の 1 行 = 1 頭。 text: 文字列を regex で分割
  header_row: 0            # table のとき、見出し行の位置
fields:
  management_no: {header: "管理番号"}   # 見出し名で列を指す
  sex: {header: "性別"}
  shelter_date: {header: "収容日"}
```

`mode: text` のときは `rows_regex: "^(\\d{2}-\\d{4}).*$"` で 1 頭分の塊を切り、`fields` は `regex` で取る。

table モードの行は表のセルしか見えない（表の外の本文・写真は取れない）。番号が 1 桁で収容日が本文にしか無い公示（四日市市「保護・収容犬の公示」）は、表の行だけでは動物として通らないので、text モードで公示 1 枚を 1 行にして読む（`rows_regex: "^.*収容\\S*の公示"`、収容日は本文から、種類・性別等は番号で始まる表の行から regex で取る）。1 枚に 2 頭以上が並ぶと 2 頭目以降は読めない（`city_yokkaichi_pdf.yaml` の制約）。

ページ最下行の下の横罫線が引かれていない表（縦罫線だけが下まで伸びている。神奈川県 センター外保護猫 cat.pdf）は、エンジンが縦罫線の下端に横罫線を補って最下行も表に入れる（レシピに書かない）。補うのは、表の中から始まる縦罫線の半分以上（2 本以上）が表の下端より下へ伸び、その長さが行の高さの 3 倍以内で、伸びた先に横罫線が無いときだけ。複数行のセル（場所が 2 行に割れる等）がある表を `mode: text` に替えると、割れた行が前後の子に混ざるので替えない。

1 ページが左右 2 段組みの PDF（茨城県）は、丸ごと読むと左右の行が 1 行に混ざる。`columns` で各ページを等分して列ごとに読む:

```yaml
pdf:
  mode: text
  columns: 2               # 左列を全部読んでから右列。表も列ごとに取る
```

## 転置表（1 列 = 1 頭）

栃木県の子犬ページのように「1 行 = 1 項目、1 列 = 1 頭」の表は `rows` の代わりに `transpose` に表のセレクタを書く。
セルが N 個（N ≥ 2）の行は個体別、セルが 1 個の行（枠名や「5 月生まれ ワクチン接種済」）は全頭共通として各列に付く。
全部の行が 1 セルの表は表全体で 1 頭になる。`fields` は `regex` で取る（行の並び順は表ごとに違ってよい）。

```yaml
transpose: "table.has-fixed-layout"
row_filter:
  text_lacks: ["飼い主さん決まりました"]
fields:
  management_no: {regex: "番号[:：]\\s*(\\d\\S*)"}
  sex: {regex: "性別[:：]\\s*(\\S+)"}
```

`species: {from: heading}` は転置表では使えない（列は元の HTML の位置を持たない）。台帳の species か `from: text` を使う。

## デバッグ

```bash
$PY -m collector show <slug>              # 取れた行と捨てた行の理由を表示
$PY -m collector show <slug> --html       # 最終 HTML を保存して場所を表示
$PY -m collector fetch <url> --text       # ページ本文をテキストで
$PY -m collector fetch <url> --selectors  # 表・リスト・画像の候補セレクタを列挙
```

## 入口 URL の上書き

台帳の URL でなく別の URL を入口にしたいとき（iframe の中身を直接指す、絞り込みパラメータ付きにする等）:

```yaml
url: https://example.jp/list?animal-type=dog
```

## 0 頭判定の補足

`empty_text` は最終文書だけでなく、入口から辿った全ページ（PDF が 0 本の日の入口ページ等）に対して照合される。
