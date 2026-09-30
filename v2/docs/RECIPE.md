# レシピの書き方

レシピは「そのページから動物の一覧をどう読むか」の手順書。1 ページ（台帳の 1 エントリ）に 1 ファイル、`recipes/<slug>.yaml`。
プログラムは 1 つ（`collector/recipe.py`）で、レシピを読んで動く。新しいサイトはレシピを 1 枚足すだけ。

## 最小の例（一覧ページに表があるだけ）

```yaml
rows: "table.list tr"          # 動物 1 頭 = この CSS セレクタにマッチする要素 1 つ
image: "img@src"               # 行の中の写真（省略時は img@src）
# image: {selector: "td img@src", exclude: ["noimage"], strip_query: true}   # 除外パターン、?以降の除去（ID の安定化）
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
```

`follow` 系の値は `セレクタ@属性`。`@属性` を省くと `@href`。

## 行の絞り込み

```yaml
rows: "ul.news > li"
row_filter:
  text_has_any: ["収容日", "管理番号"]   # どれかを含む行だけ
  text_lacks: ["見出し", "譲渡済"]        # 含む行は捨てる
  min_text_length: 10
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
  management_no: {index: 0}                 # PDF 表の列番号
```

使える項目名: `name` `sex` `age` `breed` `color` `size` `management_no` `shelter_date` `note` `species` `detail`（個体ページの URL）`location`（同じページに複数センターが混ざるときだけ）。

## 種別（犬か猫か）

台帳の `species` が `dog` か `cat` ならそれを使う。`mixed` のページはレシピで決める。

```yaml
species:
  from: heading                 # heading | field | text
  selector: "h3"                # heading: 行より前にある直近の見出し
  # from: field なら fields.species の値、from: text なら行のテキスト全体、from: url なら文書の URL（dog.pdf / cat.pdf で分かれるとき）
  map: {"犬": dog, "猫": cat, "ねこ": cat, "イヌ": dog}   # 部分一致。どれにも当たらなければ other
```

## 動物とみなす条件（自動・レシピに書かない）

行は次のどれかを満たすときだけ動物として通る。満たさない行は捨てる。

- 写真がある（`image` で取れ、その URL が元の HTML に実在する）。自治体の「写真なし」プレースホルダ（`noimage01.jpg`・`no_photo`・`準備中` 等）は写真とみなさず、サイトでは「写真はありません」になる
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
恒常的に 0 頭でリンクだけ出したいページ（動物が SNS に移った等）は、台帳で `mode: link_only` にする。

## 文字コード・その他

```yaml
encoding: euc-jp          # 自動判定で化けるときだけ
max_pages: 30             # paginate の上限
base_url: https://…       # 相対 URL の基準を変えたいとき（通常不要）
```

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
