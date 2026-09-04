"""福岡市犬猫譲渡ポータル「ずっといっしょ」(zuttoissho.com) rule-based adapter

対象ドメイン: https://zuttoissho.com/

背景 (T124/W001):
- wannyan.city.fukuoka.lg.jp の犬譲渡/猫譲渡 (旧 `sorting_id=5`) は
  「5秒後に https://zuttoissho.com/mukaeru/ へ自動遷移」という JS
  リダイレクト通知のみで、譲渡動物データ自体はこのドメインに存在しない
  (T046/T108 で既知、`wannyan_fukuoka.py` docstring 参照)。実データは
  `https://zuttoissho.com/omukae/animal/{dog,cat}/` へ完全移行済みと
  2026-09-03 に実査で確認した (bot UA `oneco-collector/1.0` でも静的
  HTTP GET のみで一覧・詳細とも取得可能・200 応答を確認済み)。
- zuttoissho.com は `og:site_name`/Organization schema/footer copyright
  いずれも「福岡市」表記のみで、他自治体を含む共用プラットフォームでは
  ない (福岡市専用の custom domain WordPress サイト)。よって sites.yaml
  上は本アダプタが福岡市の犬譲渡/猫譲渡 2 サイトのみを担当する。
- 一覧は `/omukae/animal/{dog,cat}/` に WordPress 標準の wp-pagenavi
  ページネーション (実測 10 件/ページ) があり、2026-09-03 実査では
  猫 13 件 (2 ページ) ・犬 1 件 (1 ページ、pagenavi 自体が非表示) だった。
  1 ページ目しか読まないと 2 ページ目以降が掲載漏れになるため、
  `kumamoto_doubutuaigo.py` と同じ next リンク追従パターンを踏襲する。
- 一覧ページには動物カード一覧 (`ul.omukae_list`) の他に、犬/猫タブ切替
  ナビ (`ul.animal_list`、`/omukae/animal/cat/`・`/omukae/animal/dog/`
  への自己リンクを含む) が同居する。detail リンクの CSS セレクタは
  `ul.omukae_list` 配下に限定し、タブナビ自己リンクを拾わないようにする。
- detail ページは `<dl class="data_list"><dt>ラベル</dt><dd>値</dd></dl>`
  の定義リストで「登録日/動物種/品種/毛色/性別/体格/年齢/その他特徴/
  申込状況」が並ぶ (`WordPressListAdapter` 標準の label 抽出に乗る)。
  電話番号・所在地は dl の外、`section.takeover ul.place_list li` の
  `p.name`/`p.address`/`p.tel` にあるため `extract_animal_details` を
  オーバーライドして補完する (URL 由来の species 推定は「HTML から
  1 フィールドも取れない」判定より後段で行う必要があるため、`_postprocess_fields`
  フックではなく完全オーバーライドで順序を明示的に制御する)。
- 個体写真は `div.gallery` (swiper) 配下の `<img src>` のみを対象とする。
  既定の IMAGE_SELECTOR (`img` 全体 + `/wp-content/uploads/` フィルタ) の
  ままだと、footer の「トピックス」記事サムネイル
  (`/wp-content/uploads/2019/...`) まで全個体の image_urls に混入する
  (熊本 recommend-area 個体混入バグと同型の危険があるため、gallery に
  scope した専用 IMAGE_SELECTOR で防ぐ)。
- 個体識別: `p.no`「お問い合わせ番号【C4901】」を management_number、
  `p.title`「c4901【仮名：フミ】...」の仮名部分を name として抽出する
  (未登録だと個体識別フィールドがサイレントドロップする、既知の同型注意点)。
"""

from __future__ import annotations

import logging
import re
from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..wordpress_list import FieldSpec, WordPressListAdapter

logger = logging.getLogger(__name__)

# `p.address` の先頭に付く「住所：」ラベルを取り除くための正規表現。
_ADDRESS_LABEL_RE = re.compile(r"^住所[:：]\s*")
# `p.no`「お問い合わせ番号【C4901】」から管理番号を取り出す。
_INQUIRY_NO_RE = re.compile(r"【([^】]+)】")
# `p.title`「c4901【仮名：フミ】中央区）...」から仮名部分を取り出す。
_NICKNAME_RE = re.compile(r"仮名[：:]\s*([^】]+)】")


class ZuttoisshoFukuokaAdapter(WordPressListAdapter):
    """福岡市「ずっといっしょ」(zuttoissho.com) 犬猫譲渡 rule-based adapter

    犬譲渡 (`/omukae/animal/dog/`) / 猫譲渡 (`/omukae/animal/cat/`) の
    2 サイトを共通テンプレートで扱う。静的 HTTP GET のみで取得可能な
    ため PlaywrightFetchMixin は使わない (requires_js: false)。
    """

    # 動物カード一覧 (`ul.omukae_list`) 配下の detail リンクだけを狙う。
    # `ul.animal_list` (犬/猫タブ切替ナビ、list_url 自身への自己リンクを
    # 含む) を誤って拾わないよう scope する。
    LIST_LINK_SELECTOR: ClassVar[str] = "ul.omukae_list a[href*='/omukae/']"

    # wp-pagenavi の「次のページ」リンク。犬 (1 件・1 ページ) のように
    # wp-pagenavi 自体が出ないケースもあるため無ければ単に打ち切る。
    NEXT_PAGE_SELECTOR: ClassVar[str] = "div.wp-pagenavi a[rel='next']"
    # 一覧ページ送りの追跡上限 (無限ループ・暴走の保険)。
    # 2026-09-03 実査で猫 13 件/2 ページのため、増加余地を持たせつつ
    # oita_aigo/kumamoto と同じ 20 ページを採用する。
    MAX_LIST_PAGES: ClassVar[int] = 20

    # detail ページの `<dl class="data_list"><dt>/<dd>` ラベル
    # (2026-09-03 実ページ確認: https://zuttoissho.com/omukae/6279/ 等)。
    FIELD_SELECTORS: ClassVar[dict[str, FieldSpec]] = {
        "shelter_date": FieldSpec(label="登録日"),
        "species": FieldSpec(label="動物種"),
        "breed": FieldSpec(label="品種"),
        "color": FieldSpec(label="毛色"),
        "sex": FieldSpec(label="性別"),
        "size": FieldSpec(label="体格"),
        "age": FieldSpec(label="年齢"),
        "description": FieldSpec(label="その他特徴"),
    }

    # 個体写真は `div.gallery` (swiper) 配下の `<img>` のみ。
    # footer の「トピックス」記事サムネイルやヘッダーロゴが
    # `/wp-content/uploads/` フィルタだけでは除外できないため scope する。
    IMAGE_SELECTOR: ClassVar[str] = "div.gallery img"

    # ─────────────────── オーバーライド ───────────────────

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """一覧のページ送り (wp-pagenavi `rel="next"`) を最後まで辿って
        全 detail URL を集める (0 件は正常系として許容)

        `kumamoto_doubutuaigo.py` と同じ「訪問済みページへの循環検知」
        「上限到達時の打ち切り」パターンを踏襲する。打ち切り時は
        `self.list_truncated` を立て、CollectorService の
        prune_disappeared (消滅同期削除) をスキップさせる。
        """
        urls: list[tuple[str, str]] = []
        seen: set[str] = set()
        visited_pages: set[str] = set()
        category = self.site_config.category
        page_url = self.site_config.list_url
        truncated = False
        for _ in range(self.MAX_LIST_PAGES):
            if page_url in visited_pages:
                truncated = True
                logger.warning(
                    "[%s] 一覧のページ送りで循環を検知しました (既訪問ページへの"
                    "再遷移: %s)。未取得のページが残っている可能性があります",
                    self.site_config.name,
                    page_url,
                )
                break
            visited_pages.add(page_url)
            html = self._http_get(page_url)
            soup = BeautifulSoup(html, "html.parser")

            for link in soup.select(self.LIST_LINK_SELECTOR):
                href = link.get("href")
                if not href or not isinstance(href, str):
                    continue
                absolute = self._absolute_url(href, base=page_url)
                if absolute in seen:
                    continue
                seen.add(absolute)
                urls.append((absolute, category))

            next_link = soup.select_one(self.NEXT_PAGE_SELECTOR)
            next_href = next_link.get("href") if isinstance(next_link, Tag) else None
            if not next_href or not isinstance(next_href, str):
                break
            page_url = self._absolute_url(next_href, base=page_url)
        else:
            truncated = True
            logger.warning(
                "[%s] 一覧のページ送りが上限 %d ページに達しました。"
                "未取得のページが残っている可能性があります: %s",
                self.site_config.name,
                self.MAX_LIST_PAGES,
                page_url,
            )

        self.list_truncated = truncated
        return urls

    def extract_animal_details(self, detail_url: str, category: str = "adoption") -> RawAnimalData:
        """detail ページから RawAnimalData を構築する

        基底実装 (`FIELD_SELECTORS` の dt/dd 抽出) に加え、以下の
        zuttoissho.com 固有処理を行う:
        - location/phone: dl.data_list の外、`section.takeover
          ul.place_list li` の `p.name`/`p.address`/`p.tel` から組み立てる。
        - management_number/name: `p.no`「お問い合わせ番号【C4901】」/
          `p.title`「c4901【仮名：フミ】...」から抽出する。
        - species: `動物種` ラベルが空のとき list URL (`/dog/` or `/cat/`)
          から補完する。ただし「HTML から 1 フィールドも取れない」判定
          (ParsingError) より後段で行う。ここを `_postprocess_fields`
          フックに乗せると URL 由来の値だけで完全に空の HTML でも
          常に非空判定されてしまい、構造崩壊の検知が効かなくなるため。
        """
        html = self._http_get(detail_url)
        soup = BeautifulSoup(html, "html.parser")

        fields: dict[str, str] = {}
        for name, spec in self.FIELD_SELECTORS.items():
            fields[name] = self._extract_field(soup, spec)

        if not any(fields.values()):
            raise ParsingError(
                "detail ページから 1 フィールドも抽出できませんでした",
                url=detail_url,
            )

        if not fields.get("species"):
            fields["species"] = self._infer_species_from_url()

        place = soup.select_one("ul.place_list li")
        if isinstance(place, Tag):
            name_el = place.select_one("p.name")
            address_el = place.select_one("p.address")
            tel_el = place.select_one("p.tel")

            name_text = name_el.get_text(strip=True) if isinstance(name_el, Tag) else ""
            address_text = address_el.get_text(strip=True) if isinstance(address_el, Tag) else ""
            address_text = _ADDRESS_LABEL_RE.sub("", address_text).strip()

            if name_text and name_text not in address_text:
                location = f"{name_text}　{address_text}" if address_text else name_text
            else:
                location = address_text or name_text
            if location:
                fields["location"] = location

            if isinstance(tel_el, Tag):
                tel_text = tel_el.get_text(strip=True)
                if tel_text:
                    fields["phone"] = tel_text

        no_el = soup.select_one("p.no")
        if isinstance(no_el, Tag):
            m = _INQUIRY_NO_RE.search(no_el.get_text(strip=True))
            if m:
                fields["management_number"] = m.group(1)

        title_el = soup.select_one("p.title")
        if isinstance(title_el, Tag):
            m = _NICKNAME_RE.search(title_el.get_text(strip=True))
            if m:
                fields["name"] = m.group(1).strip()

        image_urls = self._extract_images(soup, detail_url)

        try:
            return RawAnimalData(
                species=fields.get("species", ""),
                breed=fields.get("breed", ""),
                sex=fields.get("sex", ""),
                age=fields.get("age", ""),
                color=fields.get("color", ""),
                size=fields.get("size", ""),
                shelter_date=fields.get("shelter_date", ""),
                location=fields.get("location", ""),
                phone=self._normalize_phone(fields.get("phone", "")),
                description=fields.get("description", ""),
                name=fields.get("name", ""),
                management_number=fields.get("management_number", ""),
                image_urls=image_urls,
                source_url=detail_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(f"RawAnimalData バリデーション失敗: {e}", url=detail_url) from e


# ─────────────────── サイト登録 ───────────────────
# sites.yaml の `name` フィールド (旧 wannyan.city.fukuoka.lg.jp 時代の
# 名称を維持、list_url のみ zuttoissho.com へ差し替え済み・T124) と
# 完全一致する 2 サイト名で登録する。
for _site_name in (
    "福岡市わんにゃん（犬譲渡）",
    "福岡市わんにゃん（猫譲渡）",
):
    if SiteAdapterRegistry.get(_site_name) is None:
        SiteAdapterRegistry.register(_site_name, ZuttoisshoFukuokaAdapter)
