"""東京都収容動物情報 rule-based adapter

対象ドメイン: https://shuyojoho.metro.tokyo.lg.jp/

特徴:
- 東京都動物愛護相談センターの専用検索 DB。一覧 / 詳細とも JavaScript
  により描画されるため (sites.yaml で `requires_js: true`)、
  `PlaywrightFetchMixin` を多重継承して `_http_get` を Playwright
  実装に差し替える。
- 2 サイトを単一 adapter で扱う:

  * `https://shuyojoho.metro.tokyo.lg.jp/`     東京都収容動物情報（犬）
  * `https://shuyojoho.metro.tokyo.lg.jp/cat`  東京都収容動物情報（猫等）

  両者ともトップ一覧と address/datein/office 等の絞り込み一覧から
  `/animals/detail/{id}` 形式の詳細ページにリンクされる構造を共有する。

- 詳細ページは `<dl id="dataGroup0X">` 配下の `<dt>/<dd>` 定義リスト
  形式で各フィールドが格納されており、`WordPressListAdapter` の
  標準ラベル抽出に乗る:

  * 種類 (species), 性別 (sex), 大きさ (size), 毛色 (color),
    収容日 (shelter_date), 収容場所 (location)
  * 連絡先 (phone) は `.contact_box .tel` から抽出 (定義リストには無いため
    selector 直接指定)
  * 「動物名」フィールド (例: "イヌ", "ネコ") を species のフォールバック
    として利用する。

- メイン画像は `#mainPhoto img` 配下のみを対象 (banner 等を除外する)。
- 在庫 0 件 (「現在、収容動物情報はありません。」) の状態が日常的に発生
  し得るため、一覧から 1 件も detail リンクが拾えなかった場合は
  ParsingError ではなく空リストを返す。
"""

from __future__ import annotations

import re
from typing import ClassVar

from bs4 import BeautifulSoup

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..playwright import PlaywrightFetchMixin
from ..registry import SiteAdapterRegistry
from ..wordpress_list import FieldSpec, WordPressListAdapter


class ShuyojohoTokyoAdapter(PlaywrightFetchMixin, WordPressListAdapter):
    """東京都収容動物情報 (shuyojoho.metro.tokyo.lg.jp) 共通 rule-based adapter

    2 サイト (犬 / 猫等) を同一 adapter で扱う。Playwright で JS 描画後の
    HTML を取得し、`<dl id="dataGroup...">` 配下の `<dt>/<dd>` 定義リスト
    から各フィールドを抽出する。
    """

    # JS 描画完了の目印。詳細ページのメインデータ領域 / トップの収容件数
    # ボックスのいずれかが現れれば描画完了とみなせるが、
    # `PlaywrightFetcher` は selector 不在でも timeout までに body が出れば
    # 返すため、ここでは body を待ち受けに使う緩い制約に留める。
    WAIT_SELECTOR: ClassVar[str | None] = "body"

    # 一覧ページ / 絞り込みページから詳細ページへのリンク。
    # `/animals/detail/{id}` のみを対象とする (犬/猫共通)。
    LIST_LINK_SELECTOR: ClassVar[str] = "a[href*='/animals/detail/']"

    # 詳細ページの定義リスト (dl id=dataGroup01..05) から抽出するラベル群。
    # phone のみ定義リスト外の `.contact_box .tel` を直接参照する。
    FIELD_SELECTORS: ClassVar[dict[str, FieldSpec]] = {
        # 種類 (例: "雑種")
        "species": FieldSpec(label="種類"),
        # 性別 (例: "オス(去勢含む)", "メス")
        "sex": FieldSpec(label="性別"),
        # 年齢: 東京都 DB には独立フィールドが無いため空文字のままとする
        "age": FieldSpec(label="年齢"),
        # 毛色 (例: "黒/白")
        "color": FieldSpec(label="毛色"),
        # 大きさ (例: "中")
        "size": FieldSpec(label="大きさ"),
        # 収容日 (例: "2026/05/15")
        "shelter_date": FieldSpec(label="収容日"),
        # 収容場所 (例: "練馬区 氷川台2丁目")
        "location": FieldSpec(label="収容場所"),
        # 連絡先電話番号: `.contact_box .tel` から抽出 (例: "TEL. 03-3790-0861")
        "phone": FieldSpec(selector=".contact_box .tel"),
    }

    # メイン写真のみを対象とする。`#mainPhoto img` の他に
    # banner / 福祉保健局リンク用の img が大量に含まれるため、
    # filter を厳しくしている。
    IMAGE_SELECTOR: ClassVar[str] = "#mainPhoto img"

    # ─────────────────── オーバーライド ───────────────────

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """一覧ページから detail URL を抽出する (0 件は正常系として許容)"""
        html = self._http_get(self.site_config.list_url)
        soup = BeautifulSoup(html, "html.parser")

        links = soup.select(self.LIST_LINK_SELECTOR)
        if not links:
            return []

        urls: list[tuple[str, str]] = []
        seen: set[str] = set()
        category = self.site_config.category
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

    def extract_animal_details(self, detail_url: str, category: str = "adoption") -> RawAnimalData:
        """detail ページから RawAnimalData を構築する

        基底実装に加え、以下の固有処理を行う:
        - phone は `.contact_box .tel` から取得した上で `TEL.` 等の
          ラベル文字を除去してから `_normalize_phone` に渡す。
        - species がラベル抽出で空の場合、`<dl id="dataGroup01">` の
          「動物名」(例: "イヌ", "ネコ") → site name (URL は
          `/cat` 以外区別が薄いため) の順に推定する。
        """
        html = self._http_get(detail_url)
        soup = BeautifulSoup(html, "html.parser")

        fields: dict[str, str] = {}
        for name, spec in self.FIELD_SELECTORS.items():
            value = self._extract_field(soup, spec)
            fields[name] = value

        if not any(fields.values()):
            raise ParsingError(
                "detail ページから 1 フィールドも抽出できませんでした",
                url=detail_url,
            )

        # species 補完: ラベル「種類」が空のとき
        # 1) 同じ詳細ページの「動物名」(イヌ/ネコ) → 犬/猫 にマップ
        # 2) site_config.list_url の `/cat` 有無でフォールバック
        # 3) site_config.name の "犬"/"猫" でフォールバック
        if not fields.get("species"):
            inferred = (
                self._infer_species_from_animal_name(soup)
                or self._infer_species_from_list_url(self.site_config.list_url)
                or self._infer_species_from_site_name(self.site_config.name)
            )
            if inferred:
                fields["species"] = inferred

        image_urls = self._extract_images(soup, detail_url)

        try:
            return RawAnimalData(
                species=fields.get("species", ""),
                sex=fields.get("sex", ""),
                age=fields.get("age", ""),
                color=fields.get("color", ""),
                size=fields.get("size", ""),
                shelter_date=fields.get("shelter_date", ""),
                location=fields.get("location", ""),
                phone=self._normalize_phone(fields.get("phone", "")),
                image_urls=image_urls,
                source_url=detail_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(f"RawAnimalData バリデーション失敗: {e}", url=detail_url) from e

    # ─────────────────── 種別推定 ───────────────────

    @staticmethod
    def _infer_species_from_animal_name(soup: BeautifulSoup) -> str:
        """詳細ページの `<dt>動物名</dt><dd>...</dd>` から動物種別を推定

        東京都 DB は「動物名」セルに "イヌ"/"ネコ" のカタカナで動物種を
        格納している。これを「犬"/"猫" にマップする。
        """
        for dt in soup.find_all("dt"):
            label = dt.get_text(strip=True)
            if "動物名" not in label:
                continue
            dd = dt.find_next_sibling("dd")
            if dd is None:
                continue
            text = dd.get_text(strip=True)
            if "イヌ" in text or "犬" in text:
                return "犬"
            if "ネコ" in text or "猫" in text:
                return "猫"
        return ""

    @staticmethod
    def _infer_species_from_list_url(url: str) -> str:
        """list URL のパス末尾 `/cat` で猫サイトを判定

        - 末尾が `/cat` (または `/cat/...`) の場合 → "猫"
        - それ以外は犬サイト扱いだが、断定情報が無いため "" を返す
          (site_name fallback に委ねる)
        """
        if not url:
            return ""
        # 末尾 `/cat` または `/cat/` 等
        if re.search(r"/cat(/|$)", url):
            return "猫"
        return ""

    @staticmethod
    def _infer_species_from_site_name(name: str) -> str:
        """サイト名 ("...犬", "...猫") から動物種別を推定する"""
        has_dog = bool(re.search(r"犬", name))
        has_cat = bool(re.search(r"猫", name))
        if has_dog and has_cat:
            # 「犬・猫」併記の場合は曖昧な「その他」よりも先に
            # 「猫等」表記との曖昧性回避のため猫を優先
            return "猫"
        if has_dog:
            return "犬"
        if has_cat:
            return "猫"
        return ""


# ─────────────────── サイト登録 ───────────────────
# sites.yaml の 2 サイトを同一 adapter にマップする。
for _site_name in (
    "東京都収容動物情報（犬）",
    "東京都収容動物情報（猫等）",
):
    if SiteAdapterRegistry.get(_site_name) is None:
        SiteAdapterRegistry.register(_site_name, ShuyojohoTokyoAdapter)
