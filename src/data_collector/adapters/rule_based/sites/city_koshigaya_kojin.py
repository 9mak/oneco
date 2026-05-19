"""越谷市 個人保護犬猫 rule-based adapter (h2+h3+p 形式)

対象 URL:
- /kurashi_shisei/fukushi/hokenjo/pet/hogo/hogo_kojin.html

HTML 構造:
    <div id="tmp_honbun">
      <h2>犬の情報</h2>
        <p>現在、情報はありません。</p>
      <h2>猫の情報</h2>
        <h3>R8-001</h3>                ← 1 動物 (発見/管理ID)
          <p>発見場所：越谷市大沢４丁目付近</p>
          <p>発見時期：おおよそ２０２５年８月ごろ</p>
          <p>毛色：キジトラ</p>
          <p>特徴：ピンク色の首輪あり</p>
        <h3>R8-002</h3>
          ...

「犬の情報」「猫の情報」の h2 が species のスコープアンカーとなり、その中の
h3 が 1 動物に対応する。h3 直後の `<p>` がフィールド情報。

旧 CityKoshigayaAdapter は table 前提で書かれており、このページでは動物が
いても 0 件として記録される誤動作があった。本 adapter で専用処理する。

adapter 破損検出:
- `div#tmp_honbun` が無い → ParsingError
- 「犬の情報」「猫の情報」の h2 がどちらも無い → ParsingError
- 「犬の情報」「猫の情報」のいずれかが見つかり、その中に h3 が無い → 0 件正常
"""

from __future__ import annotations

import re
from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..base import RuleBasedAdapter
from ..registry import SiteAdapterRegistry

# 「ラベル：値」「ラベル: 値」両方を許容する区切り
_FIELD_SEP_RE = re.compile(r"[：:]")

# 性別判定
_SEX_MALE_RE = re.compile(r"おす|オス|♂|雄")
_SEX_FEMALE_RE = re.compile(r"めす|メス|♀|雌")

# 種別セクションの h2 テキスト → species
_SPECIES_SECTIONS: dict[str, str] = {
    "犬の情報": "犬",
    "猫の情報": "猫",
}

_LABEL_TO_FIELD: dict[str, str] = {
    "発見場所": "location",
    "発見時期": "shelter_date",
    "発見日時": "shelter_date",
    "発見日": "shelter_date",
    "保護場所": "location",
    "保護日": "shelter_date",
    "保護時期": "shelter_date",
    "毛色": "color",
    "毛の色": "color",
    "色": "color",
    "性別": "sex",
    "体格": "size",
    "大きさ": "size",
    "年齢": "age",
    "種類": "species_detail",
    "犬種": "species_detail",
    "猫種": "species_detail",
}


class CityKoshigayaKojinAdapter(RuleBasedAdapter):
    """越谷市 個人保護犬猫専用 adapter (h2「犬の情報/猫の情報」+ h3 + p 形式)"""

    SPECIES_SECTIONS: ClassVar[dict[str, str]] = _SPECIES_SECTIONS

    def __init__(self, site_config) -> None:
        super().__init__(site_config)
        self._html_cache: str | None = None
        # [(species, h3_tag)] のリスト
        self._animals_cache: list[tuple[str, Tag]] | None = None

    # ─────────────────── 公開 API ───────────────────

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        animals = self._load_animals()
        category = self.site_config.category
        return [(f"{self.site_config.list_url}#h3={i}", category) for i in range(len(animals))]

    def extract_animal_details(
        self, virtual_url: str, category: str = "sheltered"
    ) -> RawAnimalData:
        animals = self._load_animals()
        idx = self._parse_index(virtual_url)
        if idx >= len(animals):
            raise ParsingError(
                f"index {idx} out of range (total {len(animals)})",
                url=virtual_url,
            )
        species, h3 = animals[idx]

        fields = self._extract_fields_after_h3(h3)

        sex_raw = fields.get("sex", "")
        sex = self._normalize_sex(sex_raw)

        try:
            return RawAnimalData(
                species=species,
                sex=sex,
                age=fields.get("age", ""),
                color=fields.get("color", ""),
                size=fields.get("size", ""),
                shelter_date=fields.get("shelter_date", ""),
                location=fields.get("location", ""),
                phone="",
                image_urls=[],
                source_url=virtual_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(f"RawAnimalData バリデーション失敗: {e}", url=virtual_url) from e

    def normalize(self, raw_data: RawAnimalData):
        return self._default_normalize(raw_data)

    # ─────────────────── ヘルパー ───────────────────

    def _load_animals(self) -> list[tuple[str, Tag]]:
        if self._animals_cache is not None:
            return self._animals_cache

        if self._html_cache is None:
            raw = self._http_get(self.site_config.list_url)
            # 越谷市 CMS は Latin-1 → UTF-8 二重エンコードで返るケースがあるため補正
            if "越谷" not in raw:
                try:
                    raw = raw.encode("latin-1").decode("utf-8")
                except (UnicodeEncodeError, UnicodeDecodeError):
                    pass
            self._html_cache = raw

        soup = BeautifulSoup(self._html_cache, "html.parser")
        honbun = soup.select_one("div#tmp_honbun")
        if honbun is None:
            raise ParsingError(
                "div#tmp_honbun が見つかりません",
                url=self.site_config.list_url,
            )

        animals: list[tuple[str, Tag]] = []
        sections_found = 0
        for h2 in honbun.find_all("h2"):
            h2_text = h2.get_text(separator=" ", strip=True)
            species = self.SPECIES_SECTIONS.get(h2_text)
            if species is None:
                continue
            sections_found += 1
            # 次の h2 までの h3 を集める
            for sib in h2.find_all_next(["h2", "h3"]):
                if sib.name == "h2":
                    break
                if sib.name == "h3":
                    animals.append((species, sib))

        if sections_found == 0:
            raise ParsingError(
                "「犬の情報」「猫の情報」のセクション h2 が見つかりません",
                url=self.site_config.list_url,
            )

        self._animals_cache = animals
        return animals

    def _parse_index(self, virtual_url: str) -> int:
        m = re.search(r"#h3=(\d+)", virtual_url)
        if not m:
            raise ParsingError(f"無効な仮想 URL: {virtual_url} (#h3=N 形式が必要)")
        return int(m.group(1))

    def _extract_fields_after_h3(self, h3: Tag) -> dict[str, str]:
        fields: dict[str, str] = {}
        for sib in h3.find_all_next(["h3", "h2", "p"]):
            if sib.name in ("h2", "h3"):
                break
            if sib.name == "p":
                text = sib.get_text(separator=" ", strip=True)
                parts = _FIELD_SEP_RE.split(text, maxsplit=1)
                if len(parts) != 2:
                    continue
                label = parts[0].strip()
                value = parts[1].strip()
                if not value:
                    continue
                field = _LABEL_TO_FIELD.get(label)
                if field is None:
                    continue
                fields.setdefault(field, value)
        return fields

    def _normalize_sex(self, raw: str) -> str:
        if not raw:
            return ""
        if _SEX_MALE_RE.search(raw):
            return "オス"
        if _SEX_FEMALE_RE.search(raw):
            return "メス"
        return ""


# ─────────────────── サイト登録 ───────────────────
_KOJIN_SITE_NAMES: tuple[str, ...] = ("越谷市（個人保護犬猫）",)
for _name in _KOJIN_SITE_NAMES:
    if SiteAdapterRegistry.get(_name) is None:
        SiteAdapterRegistry.register(_name, CityKoshigayaKojinAdapter)
