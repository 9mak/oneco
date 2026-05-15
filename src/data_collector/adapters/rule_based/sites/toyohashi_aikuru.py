"""豊橋市あいくる (toyohashi-aikuru.jp) rule-based adapter

WordPress 系の動物個別投稿型サイト。一覧ページ
`/animal_category/lost-found?animal_type=dog|cat` から個別投稿リンクを抽出。
個別ページに動物情報が掲載される。

カバーサイト (2):
- 豊橋市あいくる（迷い犬）
- 豊橋市あいくる（迷い猫）
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..wordpress_list import FieldSpec, WordPressListAdapter


class ToyohashiAikuruAdapter(WordPressListAdapter):
    """豊橋市あいくる adapter (animal_type クエリで犬/猫識別)"""

    LIST_LINK_SELECTOR = "article a[href*='/animal/'], a.post-link[href*='/animal/']"
    FIELD_SELECTORS = {
        "species": FieldSpec(label="種別"),
        "sex": FieldSpec(label="性別"),
        "age": FieldSpec(label="年齢"),
        "color": FieldSpec(label="毛色"),
        "size": FieldSpec(label="体格"),
        "shelter_date": FieldSpec(label="収容日"),
        "location": FieldSpec(label="保護場所"),
    }
    IMAGE_SELECTOR = "article img, .animal-photos img"

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        try:
            html = self._http_get(self.site_config.list_url)
        except Exception:
            return []
        soup = BeautifulSoup(html, "html.parser")
        links = soup.select(self.LIST_LINK_SELECTOR)
        category = self.site_config.category
        urls: list[tuple[str, str]] = []
        seen: set[str] = set()
        for link in links:
            href = link.get("href")
            if not href or not isinstance(href, str):
                continue
            absolute = self._absolute_url(href)
            if absolute in seen:
                continue
            seen.add(absolute)
            urls.append((absolute, category))
        return urls

    def extract_animal_details(self, detail_url: str, category: str = "lost") -> RawAnimalData:
        html = self._http_get(detail_url)
        soup = BeautifulSoup(html, "html.parser")

        fields: dict[str, str] = {}
        for name, spec in self.FIELD_SELECTORS.items():
            fields[name] = self._extract_field(soup, spec)

        # species をクエリパラメータから補完
        species = fields.get("species", "")
        if not species or species in ("", "不明"):
            qs = parse_qs(urlparse(self.site_config.list_url).query)
            atype = qs.get("animal_type", [""])[0]
            species = "犬" if atype == "dog" else ("猫" if atype == "cat" else "")
        fields["species"] = species or ""

        if not any(fields.values()):
            raise ParsingError(
                "詳細ページから抽出できるフィールドが見つかりませんでした",
                url=detail_url,
            )

        return RawAnimalData(
            species=fields.get("species", ""),
            sex=fields.get("sex", ""),
            age=fields.get("age", ""),
            color=fields.get("color", ""),
            size=fields.get("size", ""),
            shelter_date=fields.get("shelter_date", ""),
            location=fields.get("location", ""),
            phone=self._normalize_phone(fields.get("phone", "")),
            image_urls=self._extract_images(soup, detail_url),
            source_url=detail_url,
            category=category,
        )


SiteAdapterRegistry.register("豊橋市あいくる（迷い犬）", ToyohashiAikuruAdapter)
SiteAdapterRegistry.register("豊橋市あいくる（迷い猫）", ToyohashiAikuruAdapter)
