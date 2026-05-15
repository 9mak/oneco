"""徳島県動物愛護管理センター (douai-tokushima.com) rule-based adapter

対象ドメイン: https://douai-tokushima.com/

特徴:
- baserCMS で構築された自治体サイト。動物データは外部 iframe に
  EUC-JP エンコードの HTML として埋め込まれる動的構造。
- ラッパページ (sites.yaml の `list_url`) と実データ用 iframe URL の
  対応関係:
      /stray/             → /animalinfo/list1/   (収容中 = 1ページ)
      /transfer/doglist   → /animalinfo/list4_1  (譲渡犬)
      /transfer/catlist   → /animalinfo/list4_2  (譲渡猫)
- iframe の HTML は `<ul class="news">` 配下に動物ごとの `<li>` が並び、
  各 `<li>` 内の `<table class="f_a">` (収容中) / `<table class="f_a3">`
  (譲渡) で動物情報が表現される。
- すべてのデータセルは `aria-label` 属性で意味づけされており、
  この属性をキーにフィールドを抽出するのが最も堅牢。
- 個別 detail ページは存在しないため `SinglePageTableAdapter` を基底に採用し、
  各 `<li>` 行に対して仮想 URL (`#row=N`) を発行する。
- 写真は `photo/photoN-XXXX.JPG` の相対パスで、iframe URL を base として
  絶対化する。

カバーサイト (3):
- 徳島県動物愛護管理センター（収容中）
- 徳島県動物愛護管理センター（譲渡犬）
- 徳島県動物愛護管理センター（譲渡猫）
"""

from __future__ import annotations

from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..playwright import PlaywrightFetchMixin
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter

# ラッパページ URL → 実データ iframe URL のマッピング。
# 各サイトの list_url (sites.yaml) と対応する iframe ソースの組。
_IFRAME_URL_MAP: dict[str, str] = {
    "https://douai-tokushima.com/stray/": ("https://douai-tokushima.com/animalinfo/list1/"),
    "https://douai-tokushima.com/transfer/doglist": (
        "https://douai-tokushima.com/animalinfo/list4_1"
    ),
    "https://douai-tokushima.com/transfer/catlist": (
        "https://douai-tokushima.com/animalinfo/list4_2"
    ),
}


# サイト名 → species のヒント (収容中ページは犬猫混在のため空文字、
# 譲渡犬/譲渡猫は iframe テーブル内に種類セルが無いため adapter 側で補完)。
_SPECIES_HINT: dict[str, str] = {
    "徳島県動物愛護管理センター（収容中）": "",
    "徳島県動物愛護管理センター（譲渡犬）": "犬",
    "徳島県動物愛護管理センター（譲渡猫）": "猫",
}


# アダプターがアクセスする aria-label の候補リスト。
# 同一意味の field に対して収容中 / 譲渡で異なるラベルを使うため
# 候補順にマッチを試行する (最初に見つかった非空セルを採用)。
_LABEL_CANDIDATES: dict[str, tuple[str, ...]] = {
    "species": ("種類",),
    "sex": ("性別",),
    # 譲渡側は推定生年月日、収容中は推定年齢
    "age": ("推定生年月日", "推定年齢"),
    "color": ("毛色",),
    # 譲渡側は table に体格列が無いが、収容中側は体格列がある
    "size": ("体格",),
    "shelter_date": ("発見日",),
}


class DouaiTokushimaAdapter(PlaywrightFetchMixin, SinglePageTableAdapter):
    """徳島県動物愛護管理センター 共通アダプター

    3 サイト (収容中 / 譲渡犬 / 譲渡猫) で同一テンプレート (`ul.news > li`
    に各動物 table を含む構造) を共有するため、1 クラスで全 site_name を
    束ねて registry に登録する。
    """

    # ─────────────────── Playwright 設定 ───────────────────
    # iframe 内の `<ul class="news">` が描画されたら抽出可能。
    # baserCMS は jQuery で読み込むため networkidle 待機 + selector 待機の
    # 二段構えにする (基底 PlaywrightFetcher 側で wait_until=networkidle)。
    WAIT_SELECTOR: ClassVar[str | None] = "ul.news"

    # ─────────────────── SinglePageTable 設定 ───────────────────
    # 各動物に対応するカード要素。
    ROW_SELECTOR: ClassVar[str] = "ul.news > li"
    # 行ヘッダ ↔ データ の縦配置 table なので COLUMN_FIELDS は使わず、
    # aria-label ベースで extract_animal_details を独自実装する。
    # 契約として宣言だけしておく (基底のチェックは ROW_SELECTOR のみ)。
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {}

    # ─────────────────── 抽出ロジック ───────────────────

    def _load_rows(self) -> list[Tag]:
        """iframe URL を直接 fetch して `<li>` 行をキャッシュ

        site_config.list_url はラッパページを指すが、実データは iframe
        内の別ドキュメント。Playwright で iframe URL に直接アクセスし
        JS 実行後の HTML を取り出す。

        基底 (`SinglePageTableAdapter._load_rows`) の `list_url` 取得を
        iframe URL に差し替える点だけが異なる。
        """
        if self._rows_cache is not None:
            return self._rows_cache

        iframe_url = self._iframe_url()
        if self._html_cache is None:
            self._html_cache = self._http_get(iframe_url)

        soup = BeautifulSoup(self._html_cache, "html.parser")
        rows = soup.select(self.ROW_SELECTOR)
        rows = [r for r in rows if isinstance(r, Tag)]
        self._rows_cache = rows
        return rows

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """動物一覧 (在庫 0 件でも ParsingError を出さず空リストを返す)"""
        rows = self._load_rows()
        category = self.site_config.category
        # 仮想 URL の base は iframe URL にして source_url を実データ側に揃える。
        base = self._iframe_url()
        return [(f"{base}#row={i}", category) for i in range(len(rows))]

    def extract_animal_details(self, virtual_url: str, category: str = "adoption") -> RawAnimalData:
        """`#row=N` に対応する `<li>` から aria-label でフィールドを抽出"""
        rows = self._load_rows()
        idx = self._parse_row_index(virtual_url)
        if idx >= len(rows):
            raise ParsingError(
                f"row index {idx} out of range (total {len(rows)})",
                url=virtual_url,
            )
        row = rows[idx]

        fields: dict[str, str] = {}
        for name, labels in _LABEL_CANDIDATES.items():
            fields[name] = self._extract_by_aria_labels(row, labels)

        # species の補完: サイト名から犬/猫を確定できる場合は使う。
        if not fields.get("species"):
            hint = _SPECIES_HINT.get(self.site_config.name, "")
            if hint:
                fields["species"] = hint

        # 譲渡カード (`f_a3`) は所在地セルを持たない。
        # その他センターからの動物はセンター施設に収容されているため、
        # location は固定で「徳島県動物愛護管理センター」を使う。
        location = "徳島県動物愛護管理センター"

        # 全フィールド空 = HTML 構造が想定外
        if not any(fields.values()):
            raise ParsingError(
                "detail 行から 1 フィールドも抽出できませんでした",
                url=virtual_url,
            )

        try:
            return RawAnimalData(
                species=fields.get("species", ""),
                sex=fields.get("sex", ""),
                age=fields.get("age", ""),
                color=fields.get("color", ""),
                size=fields.get("size", ""),
                shelter_date=fields.get("shelter_date", ""),
                location=location,
                phone=self._normalize_phone(fields.get("phone", "")),
                image_urls=self._extract_row_images(row, virtual_url),
                source_url=virtual_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(f"RawAnimalData バリデーション失敗: {e}", url=virtual_url) from e

    # ─────────────────── ヘルパー ───────────────────

    def _iframe_url(self) -> str:
        """site_config.list_url に対応する iframe URL を返す

        Raises:
            ParsingError: 未知の list_url に対しては明示的に失敗させる
        """
        url = self.site_config.list_url
        # 末尾スラッシュの差異を許容して照合
        candidates = (url, url.rstrip("/"), url.rstrip("/") + "/")
        for cand in candidates:
            if cand in _IFRAME_URL_MAP:
                return _IFRAME_URL_MAP[cand]
        raise ParsingError(
            f"未対応の list_url: {url} (iframe URL マッピングなし)",
            url=url,
        )

    def _extract_by_aria_labels(self, row: Tag, labels: tuple[str, ...]) -> str:
        """`<td aria-label="...">値</td>` から値を抽出

        labels の順に試して最初にマッチした td のテキストを返す。
        コメントノード (`<!--:##!...##:-->`) は get_text() で除外される。
        """
        for label in labels:
            td = row.find("td", attrs={"aria-label": label})
            if isinstance(td, Tag):
                text = td.get_text(separator=" ", strip=True)
                if text:
                    return text
        return ""


# ─────────────────── サイト登録 ───────────────────
_SITE_NAMES = (
    "徳島県動物愛護管理センター（収容中）",
    "徳島県動物愛護管理センター（譲渡犬）",
    "徳島県動物愛護管理センター（譲渡猫）",
)

for _name in _SITE_NAMES:
    SiteAdapterRegistry.register(_name, DouaiTokushimaAdapter)
