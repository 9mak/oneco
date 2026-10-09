"""行 → 動物。動物とみなす条件、種別、ID。"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin

from bs4 import Tag

from .recipe import (
    Doc,
    Recipe,
    Row,
    extract_rows,
    field_value,
    image_url,
    looks_like_date,
    looks_like_mgmt,
    nearest_heading,
)
from .registry import Source

FIELD_NAMES = ["name", "sex", "age", "breed", "color", "size", "management_no", "shelter_date", "note", "location"]
_SPECIES_DEFAULT_MAP = {"犬": "dog", "いぬ": "dog", "イヌ": "dog", "猫": "cat", "ねこ": "cat", "ネコ": "cat", "仔猫": "cat", "子猫": "cat", "子犬": "dog", "仔犬": "dog"}

# species.infer: true のときだけ使う「品種・毛色の欄にあれば犬猫が確実に言える語」（部分一致）。
# 全国の掲載（2026-10-05 の 1,622 頭）で、反対の種別に一度も使われていない語だけを置く。
# 使わない語: 雑種・MIX・ミックス・不明（両方に使う）、茶トラ・サビ・トラ・虎（犬の例あり: 山梨「お尻の部分が茶トラ」・
# 高知「茶サビ」・甲斐犬の「虎毛」）、大きさ（小・中・大、小型・中型・大型は猫にも使う。周南 8-3-99 は猫で「小」）
_INFER_DOG = (
    "犬", "いぬ", "イヌ",
    "柴", "秋田", "紀州", "狆", "チワワ", "チワプー", "ダックス", "プードル", "マルプー", "ポメ", "シーズー", "シー・ズー",
    "マルチーズ", "ヨークシャー", "ヨーキー", "パピヨン", "ビーグル", "コーギー", "ラブラド", "レトリ", "シェパード",
    "ハスキー", "コリー", "シェルティ", "シェットランド", "ポインター", "セッター", "テリア", "ハウンド", "ブルドッグ",
    "ブルドック", "パグ", "シュナウザー", "ドーベルマン", "ペキニーズ", "キャバリア", "スピッツ", "ピンシャー",
    "ピットブル", "ピット・ブル", "サモエド", "ピレニーズ", "バーナード",
)
_INFER_CAT = (
    "猫", "ねこ", "ネコ",
    "キジ", "サバトラ", "サバ白", "三毛", "ミケ", "ハチワレ", "はちわれ", "タビー",
    "スコティッシュ", "アメリカンショート", "アメショ", "ブリティッシュ", "ロシアンブルー", "シャム", "ペルシャ",
    "ヒマラヤン", "メインクーン", "ノルウェージャン", "ラグドール", "マンチカン", "ミヌエット", "ベンガル", "アビシニアン",
    "ソマリ", "エキゾチック", "キンカロー", "サイベリアン", "ラパーマ", "セルカーク", "バーマン", "トンキニーズ",
    "シンガプーラ", "スフィンクス", "オシキャット", "ターキッシュ",
)
_INFER_FIELDS = ("breed", "color")   # 保護場所（柴田町）や備考（「子犬 4 頭授乳中」）は見ない


@dataclass
class Dropped:
    reason: str
    text: str


@dataclass
class Result:
    animals: list[dict[str, Any]] = field(default_factory=list)
    dropped: list[Dropped] = field(default_factory=list)
    docs: int = 0
    rows: int = 0
    empty_confirmed: bool = False
    empty_evidence: str | None = None    # 0 頭を確定した根拠: empty_selector / empty_absent / empty_text / all_excluded+headings / all_excluded+container
    ambiguous_empty: bool = False        # 全行除外だが肯定的な証拠が無く、0 頭とも読み取り失敗とも言い切れない（W006 T605）
    ambiguous_reason: str | None = None


def resolve_species(source: Source, recipe: Recipe, row: Row, fields: dict[str, str | None]) -> str | None:
    """台帳の species → レシピの map → infer の順で決める。決まらなければ None（種別なし。サイトでは犬・猫の絞り込みに出ず「すべて」でだけ出る）。
    allow_other のレシピは決まらない行を other（犬猫以外）にする（build 側）。"""
    if source.species in ("dog", "cat"):
        return source.species
    spec = recipe.species or {}
    mapping = spec.get("map") or _SPECIES_DEFAULT_MAP
    src = spec.get("from", "text")
    text: str | None
    if src == "field":
        text = fields.get("species")
    elif src == "heading" and row.origin is not None:
        text = nearest_heading(row.origin, spec.get("selector", "h2, h3, h4"))   # まとめた行（row_until）は元の始まりの位置から
    elif src == "url":
        text = row.doc.url          # dog.pdf / cat.pdf のように文書の URL で決まるとき
    else:
        text = row.text()
    if text:
        for k, v in mapping.items():
            if k in text:
                return v
    if spec.get("infer"):
        inferred = infer_species(fields)
        if inferred:
            return inferred
    return None


def infer_species(fields: dict[str, str | None]) -> str | None:
    """品種・毛色の欄に犬だけ・猫だけの語（柴・チワワ・キジトラ・三毛 等）があれば種別を返す。
    動物種の欄が無い表（山口県 周南）で使う。犬の語と猫の語が両方当たる、またはどちらも無いときは None（決めない）。"""
    text = " ".join(fields.get(k) or "" for k in _INFER_FIELDS)
    dog = any(w in text for w in _INFER_DOG)
    cat = any(w in text for w in _INFER_CAT)
    if dog and not cat:
        return "dog"
    if cat and not dog:
        return "cat"
    return None


# 掲載が終わったことを示す言い方（「返還期限」「〇〇で見つかりました」のような迷子の説明と、「見つかりますように」
# 「見つかり次第」「戻りたい」「譲渡済みの場合があります」のような願い・条件・注意書きには当たらないものだけ）
_CLOSED_LISTING = re.compile(
    r"返還(?:しました|済|することができました|されました|いたしました|となりました|になりました)"
    r"|飼い?主(?:さん|様)?(?:が見つかり(?!ます|ません|次第)|の(?:元|もと)(?:に|へ)戻り(?!たい)|に戻りました)"
    r"|(?:譲渡先?|飼い?主(?:さん|様)?|里親(?:さん|様)?|新しい(?:飼い?主(?:さん|様)?|家族))が(?:決まり|見つかり)(?!ます|ません|次第)"
    r"|譲渡済(?!みの場合)|譲渡(?:されました|しました|決定)")
_DESCRIPTIVE = ("breed", "color", "sex", "age", "size", "location", "note")


def _empty_or_closed(row: Row, f: dict[str, str | None], img_abs: str | None) -> bool:
    """種別が決まらない行のうち、捨てるもの（T518 再レビュー F-10）。

    種別が決まらない行は以前「犬か猫か分からない」で捨てていたので、動物でない行もそこで偶然落ちていた。種別なしで
    載せるようにしたので、掲載が終わった行（山形「飼い主さんが見つかり、返還することができました」）と、写真が無く
    項目も 2 つ未満の行（0 頭の雛形に番号だけ残ったもの。佐賀「保護動物（251118-1）現在保護中の動物はいません」）は捨てる。
    掲載が終わった言い方は、行の文と、行の直前の見出し（h2・h3・h4）の両方に当てる。
    """
    if _CLOSED_LISTING.search(row.text()):
        return True
    # 掲載が終わったことが行でなく見出しにだけ書かれている作り（二戸「譲渡先が決まりました。」の下の子。3 回目のゲート G-01）
    heading = nearest_heading(row.origin, "h2, h3, h4") if row.origin is not None else None
    if heading and _CLOSED_LISTING.search(heading):
        return True
    return not img_abs and sum(bool(f.get(k)) for k in _DESCRIPTIVE) < 2


def make_id(source: Source, image_raw: str | None, f: dict[str, str | None], detail: str | None = None) -> str:
    """写真 → 管理番号 → 個体ページの URL → 名前＋収容日 の順で決める。同じ子は翌日も同じ ID になる。"""
    if image_raw:
        key = f"{source.slug}|{image_raw}"
    elif f.get("management_no"):
        key = f"{source.slug}|{f['management_no']}"
    elif detail:
        key = f"{source.slug}|{detail}"
    else:
        key = f"{source.slug}|{f.get('name')}|{f.get('shelter_date')}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def _is_blank(el: Tag) -> bool:
    """子要素も文字も無い（空白・コメントだけ）。"""
    return el.find(True) is None and not el.get_text(strip=True)


def _blank_container(doc: Doc, selectors: list[str]) -> bool:
    """empty_selector: いずれかのセレクタに合う要素がこの文書にあり、合った要素がすべて空なら True。

    0 頭の日に文言が出ず、一覧の器が空になるだけのサイト用（豊橋市あいくる div.dog-cat-list、
    福岡県動物愛護センター div.animals-list ul）。器が無い日（構造が変わった日）は False で、failed として通知される。
    """
    if doc.soup is None:
        return False
    for sel in selectors:
        found = doc.soup.select(sel)
        if found and all(_is_blank(el) for el in found):
            return True
    return False


def _absent_list(doc: Doc, spec: dict[str, str]) -> bool:
    """empty_absent: この文書に枠（page）があり、一覧の器や個体へのリンク（none）が 1 つも無ければ True。

    0 頭の日に一覧の器ごと消え、文言も出ないサイト用（静岡県 迷い犬情報一覧の ul.listlink）。枠が無い日（ブロック画面・
    作り替え）や、器の名前が変わってもリンクが残る日は False で、failed として通知される。
    """
    if doc.soup is None:
        return False
    return bool(doc.soup.select(spec["page"])) and not doc.soup.select(spec["none"])


def expected_labels(recipe: Recipe) -> set[str]:
    """レシピが項目名で引いている語（fields の label / header。join の中も含む）。見出しの照合に使う。"""
    return {lb for g in _label_groups(recipe) for lb in g}


def _label_groups(recipe: Recipe) -> list[list[str]]:
    """項目ごとの期待する見出し語の候補（label に候補の並びを書いた項目は 1 項目 = 1 グループ）。"""
    groups: list[list[str]] = []

    def walk(spec: Any) -> None:
        if not isinstance(spec, dict):
            return
        for sub in spec.get("join") or []:
            walk(sub)
        raw = spec.get("label", spec.get("header"))
        if raw is None:
            return
        names = [raw] if isinstance(raw, str) else list(raw)
        names = [_norm_label(str(n)) for n in names]
        names = [n for n in names if n]
        if names:
            groups.append(names)

    for spec in recipe.fields.values():
        walk(spec)
    return groups


def _norm_label(text: str) -> str:
    return re.sub(r"[\s:：]+", "", unicodedata.normalize("NFKC", text))


def _table_headings(el: Tag) -> set[str]:
    table = el if el.name == "table" else el.find_parent("table")
    if table is None:
        return set()
    # 見出しは th、無ければ最初の行の td。縦並びの表（左の列が項目名・右の列が値。福島県 相双支所）も読むため、
    # 各行の最初のセルのうち短いもの（値の長文を見出しと取り違えない）も見る
    cells = table.find_all("th")
    if not cells:
        tr = table.find("tr")
        cells = tr.find_all("td") if tr else []
    for tr in table.find_all("tr"):
        first = tr.find(["th", "td"])
        if first is not None:
            cells.append(first)
    texts = (_norm_label(c.get_text(" ", strip=True)) for c in cells)
    return {t for t in texts if t and len(t) <= 20}


def _split_parent(selector: str) -> str | None:
    """セレクタの最後の 1 段を除いたもの。括弧・引用符の中の空白や > は区切りにしない。単一段・カンマ列は None。"""
    depth, quote, last = 0, "", -1
    for i, ch in enumerate(selector):
        if quote:
            quote = "" if ch == quote else quote
        elif ch in "'\"":
            quote = ch
        elif ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        elif depth == 0 and ch == ",":
            return None
        elif depth == 0 and ch in " >+~":
            last = i
    if last < 0:
        return None
    parent = selector[:last].strip().rstrip(">+~ ").strip()
    return parent or None


def _all_excluded_evidence(recipe: Recipe, docs: list[Doc]) -> tuple[str | None, str]:
    """全行除外の 0 頭を確定する肯定的な証拠。(根拠, 無いときの理由)。"""
    html_docs = [d for d in docs if getattr(d, "soup", None) is not None]
    groups = _label_groups(recipe)
    seen_headings: set[str] = set()
    if groups:
        for d in html_docs:
            for row in extract_rows(recipe, d):
                if row.el is None:
                    continue
                heads = _table_headings(row.el)
                seen_headings |= heads
                hit = sum(1 for g in groups if any(lb in h for lb in g for h in heads))
                if hit * 2 >= len(groups):
                    return "all_excluded+headings", ""
    exp = "・".join(sorted(expected_labels(recipe))) or "なし"
    act = "・".join(sorted(seen_headings)) or "なし"
    reasons = [f"全行除外だが見出しの項目名が一致しない（期待 {exp}・実際 {act}）"]
    if seen_headings:
        # 見出しを読めたのに項目名が合わない＝表の作りが変わった証拠。コンテナが残っていても 0 頭にしない
        return None, reasons[0]
    sel = recipe.empty_container or _split_parent(recipe.rows)
    if sel:
        try:
            if any(d.soup.select_one(sel) is not None for d in html_docs):  # type: ignore[union-attr]
                return "all_excluded+container", ""
        except ValueError:
            pass   # 不正なセレクタは証拠なし扱い
        reasons.append(f"全行除外だがコンテナ {sel} が無い")
    else:
        reasons.append("コンテナの証拠も使えない（rows が単一段で empty_container 未指定）")
    return None, "。".join(reasons)


def build(source: Source, recipe: Recipe, docs: list[Doc], visited: list[Doc] | None = None) -> Result:
    """docs: rows を適用する文書。visited: 入口から辿った全文書（empty_text の照合にも使う）。"""
    res = Result(docs=len(docs))
    seen_ids: set[str] = set()
    # row_filter.field_lacks: {name: ["探しています"]} — 取った項目にこの語があれば捨てる（rows: body のように
    # 行の全文にサイトのメニュー文言が混ざるとき、text_lacks の代わりに使う）。これで全部捨てた日は「該当なし」とみなす
    field_lacks: dict[str, list[str]] = (recipe.row_filter or {}).get("field_lacks") or {}
    # row_filter.field_has_any: {name: ["探しています"]} — field_lacks の逆。取った項目にこの語が 1 つも無い行は捨てる
    # （同じ一覧から「探しています」だけを 4 区分目 lost の別 slug で拾う。旭川市あにまある）
    field_has_any: dict[str, list[str]] = (recipe.row_filter or {}).get("field_has_any") or {}
    excluded = 0
    for doc in docs:
        rows = extract_rows(recipe, doc)
        res.rows += len(rows)
        for row in rows:
            f: dict[str, str | None] = {}
            for name, spec in recipe.fields.items():
                f[name] = field_value(spec, row)
            hit = next((f"{k}: {w}" for k, ws in field_lacks.items() for w in ws if w in (f.get(k) or "")), None)
            if hit:
                res.dropped.append(Dropped(f"除外語（{hit}）", row.text()[:80]))
                excluded += 1
                continue
            miss = next((k for k, ws in field_has_any.items() if not any(w in (f.get(k) or "") for w in ws)), None)
            if miss:
                res.dropped.append(Dropped(f"対象語なし（{miss}）", row.text()[:80]))
                excluded += 1
                continue
            img_abs, img_raw = image_url(recipe, row, f)   # f: image.match_field（行の管理番号を含む写真を文書全体から探す）用
            dv = f.pop("detail", None)   # 個体ページの URL（相対可）。写真の無い子でも個体ページがあれば動物とみなす
            has_key = looks_like_mgmt(f.get("management_no")) or looks_like_date(f.get("shelter_date")) or bool(dv)
            if not img_abs and not has_key:
                res.dropped.append(Dropped("写真も管理番号も収容日も個体ページも無い", row.text()[:80]))
                continue
            species = resolve_species(source, recipe, row, f)
            # 決まらない子は捨てずに種別なし（None）で載せる（T518。2026-10-05 おまえさん判断:「犬猫が判断できなければ
            # フィルターやデータに格納する必要はない」）。allow_other のレシピは「map に当たらない＝犬猫以外」と言い切れる一覧なので other
            if species is None and recipe.species.get("allow_other"):
                species = "other"
            if species is None and _empty_or_closed(row, f, img_abs):
                res.dropped.append(Dropped("種別が決まらず、掲載が終わった行か中身の無い行", row.text()[:80]))
                continue
            # 元ページのリンク。PDF は日次で差し替わってファイル名が変わる（香川 r8-9-28.pdf、茨城 inu0924.pdf）ので
            # 既定では入口ページを指す。レシピに source_url: doc があれば PDF そのもの
            source_url = doc.url
            if doc.is_pdf and recipe.source_url != "doc":
                source_url = recipe.url or source.url
            if dv:
                source_url = urljoin(recipe.base_url or doc.url, dv)
            aid = make_id(source, img_raw, f, detail=source_url if dv else None)
            if aid in seen_ids:
                res.dropped.append(Dropped("同じ ID の行が既にある", row.text()[:80]))
                continue
            seen_ids.add(aid)
            animal = {
                "id": aid,
                "source": source.slug,
                "municipality": source.municipality,
                "prefecture": source.prefecture,
                "phone": source.phone,
                "address": source.address,
                "kind": source.kind,
                "species": species,
                "image_url": img_abs,
                "source_url": source_url,
            }
            for k in FIELD_NAMES:
                animal[k] = f.get(k)
            res.animals.append(animal)
    pool = list(docs) + [d for d in (visited or []) if d not in docs]
    if not res.animals and recipe.empty_selector:
        res.empty_confirmed = any(_blank_container(d, recipe.empty_selector) for d in pool)
        if res.empty_confirmed:
            res.empty_evidence = "empty_selector"
    if not res.animals and recipe.empty_absent and not res.empty_confirmed:
        res.empty_confirmed = any(_absent_list(d, recipe.empty_absent) for d in pool)
        if res.empty_confirmed:
            res.empty_evidence = "empty_absent"
    if not res.animals and recipe.empty_text and not res.empty_confirmed:
        alltext = " ".join(d.text() for d in pool)
        # 0 頭のときだけ「現在、掲載する情報はありません」の画像を出すサイトがある（豊中市）ので img の alt も照合する
        alts = " ".join(str(img.get("alt") or "") for d in pool if getattr(d, "soup", None) is not None
                        for img in d.soup.find_all("img"))
        res.empty_confirmed = any(t in f"{alltext} {alts}" for t in recipe.empty_text)
        if res.empty_confirmed:
            res.empty_evidence = "empty_text"
    if not res.animals and res.rows and excluded == res.rows and not res.empty_confirmed:
        # 載っている子が全部「除外語」の子（飼い主が探している告知だけ等）。ただし構造が変わって全行が除外語に
        # 当たる日と区別するため、見出しの項目名一致かコンテナ存在の肯定的な証拠が要る（W006 T605）
        evidence, reason = _all_excluded_evidence(recipe, docs)
        if evidence:
            res.empty_confirmed = True
            res.empty_evidence = evidence
        else:
            res.ambiguous_empty = True
            res.ambiguous_reason = reason
    return res
