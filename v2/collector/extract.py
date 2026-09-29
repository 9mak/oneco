"""行 → 動物。動物とみなす条件、種別、ID。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin

from bs4 import Tag

from .recipe import Doc, Recipe, Row, extract_rows, field_value, image_url, looks_like_date, looks_like_mgmt
from .registry import Source

FIELD_NAMES = ["name", "sex", "age", "breed", "color", "size", "management_no", "shelter_date", "note", "location"]
_SPECIES_DEFAULT_MAP = {"犬": "dog", "いぬ": "dog", "イヌ": "dog", "猫": "cat", "ねこ": "cat", "ネコ": "cat", "仔猫": "cat", "子猫": "cat", "子犬": "dog", "仔犬": "dog"}


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


def _nearest_heading(el: Tag, selector: str) -> str | None:
    """行より前にある、selector に合う直近の要素（見出し）のテキスト。"""
    root = el
    while root.parent is not None and root.parent.name != "[document]":
        root = root.parent
    candidates = root.select(selector)
    best = None
    for c in candidates:
        if c is el or el in c.descendants:
            continue
        # c が el より前にあるか（文書順）
        if c.sourceline is not None and el.sourceline is not None:
            if (c.sourceline, c.sourcepos or 0) < (el.sourceline, el.sourcepos or 0):
                best = c
        elif el in c.find_all_next():
            best = c
    return best.get_text(" ", strip=True) if best is not None else None


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
        text = _nearest_heading(row.el, spec.get("selector", "h2, h3, h4"))
    else:
        text = row.text()
    if text:
        for k, v in mapping.items():
            if k in text:
                return v
    return "other"


def make_id(source: Source, image_raw: str | None, f: dict[str, str | None]) -> str:
    if image_raw:
        key = f"{source.slug}|{image_raw}"
    elif f.get("management_no"):
        key = f"{source.slug}|{f['management_no']}"
    else:
        key = f"{source.slug}|{f.get('name')}|{f.get('shelter_date')}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def build(source: Source, recipe: Recipe, docs: list[Doc], visited: list[Doc] | None = None) -> Result:
    """docs: rows を適用する文書。visited: 入口から辿った全文書（empty_text の照合にも使う）。"""
    res = Result(docs=len(docs))
    seen_ids: set[str] = set()
    for doc in docs:
        rows = extract_rows(recipe, doc)
        res.rows += len(rows)
        for row in rows:
            f: dict[str, str | None] = {}
            for name, spec in recipe.fields.items():
                f[name] = field_value(spec, row)
            img_abs, img_raw = image_url(recipe, row)
            has_key = looks_like_mgmt(f.get("management_no")) or looks_like_date(f.get("shelter_date"))
            if not img_abs and not has_key:
                res.dropped.append(Dropped("写真も管理番号も収容日も無い", row.text()[:80]))
                continue
            species = resolve_species(source, recipe, row, f)
            if species == "other" and source.species == "mixed" and not recipe.species.get("allow_other"):
                res.dropped.append(Dropped("犬か猫か分からない", row.text()[:80]))
                continue
            source_url = doc.url
            dv = f.pop("detail", None)
            if dv:
                source_url = urljoin(recipe.base_url or doc.url, dv)
            aid = make_id(source, img_raw, f)
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
    if not res.animals and recipe.empty_text:
        pool = list(docs) + [d for d in (visited or []) if d not in docs]
        alltext = " ".join(d.text() for d in pool)
        res.empty_confirmed = any(t in alltext for t in recipe.empty_text)
    return res
