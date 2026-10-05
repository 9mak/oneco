"""行 → 動物。動物とみなす条件、種別、ID。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin

from bs4 import Tag

from .recipe import Doc, Recipe, Row, extract_rows, field_value, image_url, looks_like_date, looks_like_mgmt, nearest_heading
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


def resolve_species(source: Source, recipe: Recipe, row: Row, fields: dict[str, str | None]) -> str:
    if source.species in ("dog", "cat"):
        return source.species
    spec = recipe.species or {}
    mapping = spec.get("map") or _SPECIES_DEFAULT_MAP
    src = spec.get("from", "text")
    text: str | None
    if src == "field":
        text = fields.get("species")
    elif src == "heading" and row.el is not None:
        text = nearest_heading(row.el, spec.get("selector", "h2, h3, h4"))
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
    return "other"


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
            img_abs, img_raw = image_url(recipe, row)
            dv = f.pop("detail", None)   # 個体ページの URL（相対可）。写真の無い子でも個体ページがあれば動物とみなす
            has_key = looks_like_mgmt(f.get("management_no")) or looks_like_date(f.get("shelter_date")) or bool(dv)
            if not img_abs and not has_key:
                res.dropped.append(Dropped("写真も管理番号も収容日も個体ページも無い", row.text()[:80]))
                continue
            species = resolve_species(source, recipe, row, f)
            if species == "other" and source.species == "mixed" and not recipe.species.get("allow_other"):
                res.dropped.append(Dropped("犬か猫か分からない", row.text()[:80]))
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
    if not res.animals and recipe.empty_text and not res.empty_confirmed:
        alltext = " ".join(d.text() for d in pool)
        # 0 頭のときだけ「現在、掲載する情報はありません」の画像を出すサイトがある（豊中市）ので img の alt も照合する
        alts = " ".join(str(img.get("alt") or "") for d in pool if getattr(d, "soup", None) is not None
                        for img in d.soup.find_all("img"))
        res.empty_confirmed = any(t in f"{alltext} {alts}" for t in recipe.empty_text)
    if not res.animals and res.rows and excluded == res.rows:
        res.empty_confirmed = True   # 載っている子が全部「除外語」の子（飼い主が探している告知だけ等）
    return res
