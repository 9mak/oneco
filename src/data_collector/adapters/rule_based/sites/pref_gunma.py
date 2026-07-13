"""群馬県動物愛護センター rule-based adapter

対象ドメイン: https://www.pref.gunma.jp/

特徴:
- 同一ドメイン (pref.gunma.jp) 上で 3 サイトが共通テンプレートを使用する:
    - https://www.pref.gunma.jp/page/167499.html  (本所 保護犬)
    - https://www.pref.gunma.jp/page/179441.html  (東部支所 保護犬)
    - https://www.pref.gunma.jp/page/167523.html  (本所 保護猫)
- 2026-07 のサイト構造変更で、一覧ページはインラインの動物テーブルから
  **個別詳細ページへのリンク並び**に変わった:
    <div class="detail_free">
      <h3>収容情報</h3>
      <p><a href="/page/766184.html">管理番号：26-049（館林市岡野町）</a></p>
      ... (収容が無い地域は「現在、保管期間中の犬はおりません」<p> のみ)
    </div>
- 詳細ページは `div#main_body div.detail_free` 配下に th/td の
  ラベル/値テーブル 1 つ (管理番号/収容日/保管終了期日/収容場所/
  保管事務所/種類/性別/推定年齢/毛色/体格/首輪/備考) と動物写真
  (`/uploaded/image/...`) を持つ。ページ下部にバナー広告
  (`/uploaded/banner/...`) が並ぶため写真抽出時に除外が必要。
- 動物種別 (犬/猫) はサイト名から推定する (本文には明示されないため)。
- 0 件状態 (「現在、保管期間中の犬はおりません」等) は ParsingError では
  なく正常系として空リストを返す。
"""

from __future__ import annotations

import re
from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from ....domain.models import AnimalData, RawAnimalData
from ...municipality_adapter import ParsingError
from ..base import RuleBasedAdapter
from ..registry import SiteAdapterRegistry

# 「現在、保管期間中の犬はおりません」「保管期間中の負傷猫はいません」など
# 0 件告知パターン。表記揺れ (おりません/ありません/いません、犬/猫) を吸収。
_EMPTY_STATE_PATTERN = re.compile(
    r"(?:保管期間中|保護している|収容している|現在)[^。]*?"
    r"(?:犬|猫|動物|ペット)[^。]*?"
    r"(?:おりません|ありません|いません)"
)

# 一覧ページの動物詳細リンクのテキスト (例: "管理番号：26-049（館林市岡野町）")
_DETAIL_LINK_TEXT_PATTERN = re.compile(r"管理番号")

# 詳細ページの「東部出張所（…） Tel：0276-55-0731」から担当事務所の電話番号を
# 拾う。県庁代表 (「電話番号(代表): 027-223-1111」) を誤って拾わないよう
# "Tel" 表記に限定する。
_OFFICE_TEL_PATTERN = re.compile(r"Tel[：:]\s*(0\d[\d\-]{8,11})")


class PrefGunmaAdapter(RuleBasedAdapter):
    """群馬県動物愛護センター用 rule-based adapter

    本所 (保護犬/保護猫) と東部支所 (保護犬) の計 3 サイトで
    共通テンプレートを使用する。一覧ページの「管理番号：…」リンクを
    詳細ページ URL として辿り、詳細ページのラベル/値テーブルから抽出する。
    """

    # 一覧・詳細とも本文は `div#main_body div.detail_free` 配下
    _MAIN_SELECTOR: ClassVar[str] = "div#main_body div.detail_free"

    # 詳細ページのラベル → RawAnimalData フィールド名のマッピング
    _LABEL_TO_FIELD: ClassVar[dict[str, str]] = {
        "管理番号": "management_number",
        "種類": "breed",  # 値は「柴犬」等の品種。species はサイト名から推定
        "犬種": "breed",
        "猫種": "breed",
        "毛色": "color",
        "毛の色": "color",
        "性別": "sex",
        "体格": "size",
        "大きさ": "size",
        "体型": "size",
        "推定年齢": "age",
        "年齢": "age",
        "収容日": "shelter_date",
        "保護日": "shelter_date",
        "保管日": "shelter_date",
        "収容場所": "location",
        "保護場所": "location",
        "発見場所": "location",
        "保管場所": "location",
    }

    # 個体識別の自由記述として description に残すラベル (「首輪：赤色」等)
    _DESCRIPTION_LABELS: ClassVar[tuple[str, ...]] = ("首輪", "特徴", "備考")

    def __init__(self, site_config) -> None:
        super().__init__(site_config)
        self._list_html_cache: str | None = None
        self._detail_html_cache: dict[str, str] = {}

    # ─────────────────── MunicipalityAdapter 実装 ───────────────────

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """一覧ページの「管理番号：…」リンクから詳細ページ URL を抽出する

        リンクが 1 件も無い場合、「現在、保管期間中の犬はおりません」等の
        0 件告知テキストがあれば正常な 0 件として空リストを返す。
        どちらも無い場合のみ ParsingError (構造変化の疑い)。
        """
        if self._list_html_cache is None:
            self._list_html_cache = self._http_get(self.site_config.list_url)
        html = self._list_html_cache

        soup = BeautifulSoup(html, "html.parser")
        main = soup.select_one(self._MAIN_SELECTOR)
        scope = main if isinstance(main, Tag) else soup

        category = self.site_config.category
        results: list[tuple[str, str]] = []
        seen: set[str] = set()
        for a in scope.find_all("a"):
            if not isinstance(a, Tag):
                continue
            href = a.get("href")
            if not href or not isinstance(href, str):
                continue
            if not _DETAIL_LINK_TEXT_PATTERN.search(a.get_text(strip=True)):
                continue
            url = self._absolute_url(href, base=self.site_config.list_url)
            if url not in seen:
                seen.add(url)
                results.append((url, category))

        if results:
            return results
        if _EMPTY_STATE_PATTERN.search(html):
            # 「現在、保管期間中の犬はおりません」等の正常な 0 件状態
            return []
        raise ParsingError(
            "動物詳細リンクが見つかりません (0 件告知も無し)",
            selector=self._MAIN_SELECTOR,
            url=self.site_config.list_url,
        )

    def extract_animal_details(self, detail_url: str, category: str = "sheltered") -> RawAnimalData:
        """詳細ページのラベル/値テーブル 1 つから RawAnimalData を構築する

        テーブルは <th>ラベル</th><td>値</td> の縦並び構造。
        「首輪」「備考」等の自由記述ラベルは「ラベル：値」形式で
        description に連結して個体識別情報として残す。
        """
        if detail_url not in self._detail_html_cache:
            self._detail_html_cache[detail_url] = self._http_get(detail_url)
        html = self._detail_html_cache[detail_url]

        soup = BeautifulSoup(html, "html.parser")
        # 詳細ページの本文は複数の div.detail_free ブロックに分かれる
        # (前置き / 写真+テーブル / 後置き)。全ブロックを走査対象にする。
        blocks = [b for b in soup.select(self._MAIN_SELECTOR) if isinstance(b, Tag)]
        scopes: list[Tag] = blocks or [soup]

        fields: dict[str, str] = {}
        description_parts: list[str] = []
        for tr in (tr for scope in scopes for tr in scope.find_all("tr")):
            if not isinstance(tr, Tag):
                continue
            th = tr.find("th")
            td = tr.find("td")
            if not isinstance(th, Tag) or not isinstance(td, Tag):
                continue
            label = th.get_text(strip=True)
            value = td.get_text(separator=" ", strip=True)
            value = re.sub(r"[ 　]+", " ", value).strip()
            if not value:
                continue
            field = self._LABEL_TO_FIELD.get(label)
            if field and field not in fields:
                fields[field] = value
            elif label in self._DESCRIPTION_LABELS:
                description_parts.append(f"{label}：{value}")

        if not fields:
            raise ParsingError(
                "詳細ページにラベル/値テーブルが見つかりません",
                selector=self._MAIN_SELECTOR,
                url=detail_url,
            )

        # species はサイト名 (保護犬/保護猫) から推定。テーブルの「種類」は
        # 「柴犬」等の品種情報なので breed に保持する (サイレントドロップ防止)。
        species = self._infer_species_from_site_name(self.site_config.name)

        try:
            return RawAnimalData(
                species=species,
                breed=fields.get("breed", ""),
                sex=fields.get("sex", ""),
                age=fields.get("age", ""),
                color=fields.get("color", ""),
                size=fields.get("size", ""),
                shelter_date=fields.get("shelter_date", ""),
                location=fields.get("location", ""),
                phone=self._extract_office_phone(html),
                image_urls=self._extract_detail_images(scopes, detail_url),
                source_url=detail_url,
                category=category,
                description="　".join(description_parts),
                management_number=fields.get("management_number", ""),
                name="",
            )
        except Exception as e:
            raise ParsingError(f"RawAnimalData バリデーション失敗: {e}", url=detail_url) from e

    def normalize(self, raw_data: RawAnimalData) -> AnimalData:
        return self._default_normalize(raw_data)

    # ─────────────────── ヘルパー ───────────────────

    def _extract_detail_images(self, scopes: list[Tag], base_url: str) -> list[str]:
        """詳細ページ本文から動物写真の絶対 URL を返す

        群馬県 CMS では動物写真が `/uploaded/image/NNNNNN.JPG`、
        バナー広告が `/uploaded/banner/...` に置かれる。banner 配下を
        除外し、それ以外の img src を採用する。
        """
        urls: list[str] = []
        for img in (img for scope in scopes for img in scope.find_all("img")):
            if not isinstance(img, Tag):
                continue
            src = img.get("src")
            if not src or not isinstance(src, str):
                continue
            if "/uploaded/banner/" in src:
                continue
            urls.append(self._absolute_url(src, base=base_url))
        return urls

    def _extract_office_phone(self, html: str) -> str:
        """詳細ページから担当事務所 (本所/東部出張所) の電話番号を抽出する

        ページ下部の「東部出張所（…） Tel：0276-55-0731」を拾う。
        見つからなければ空文字 (不明扱い)。
        """
        m = _OFFICE_TEL_PATTERN.search(html)
        if m:
            return self._normalize_phone(m.group(1))
        return ""

    @staticmethod
    def _infer_species_from_site_name(name: str) -> str:
        """サイト名から動物種別 (犬/猫) を推定する

        - "保護犬" / "犬" を含む → "犬"
        - "保護猫" / "猫" を含む → "猫"
        - それ以外 → "" (空文字)
        """
        if "犬" in name:
            return "犬"
        if "猫" in name:
            return "猫"
        return ""


# ─────────────────── サイト登録 ───────────────────
# 同一テンプレート上で運用される 3 サイトを同一 adapter にマップする。
# `sites.yaml` の `prefecture: 群馬県` かつ `pref.gunma.jp` ドメインのもの。
for _site_name in (
    "群馬県動物愛護センター（保護犬）",
    "群馬県動物愛護センター東部支所（保護犬）",
    "群馬県動物愛護センター（保護猫）",
):
    if SiteAdapterRegistry.get(_site_name) is None:
        SiteAdapterRegistry.register(_site_name, PrefGunmaAdapter)
