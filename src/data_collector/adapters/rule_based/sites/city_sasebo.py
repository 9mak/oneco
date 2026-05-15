"""佐世保市動物愛護センター rule-based adapter

対象ドメイン: https://www.city.sasebo.lg.jp/hokenhukusi/seikat/

特徴:
- 同一テンプレートで 2 サイト (保護犬 / 保護猫) を運用しており、
  list_url とリンク URL の `_dog` / `_cat` の差分のみ:
    - https://www.city.sasebo.lg.jp/hokenhukusi/seikat/hogodoubutsu.html
    - https://www.city.sasebo.lg.jp/hokenhukusi/seikat/mayoinekohogo.html
- 一覧ページに動物 1 頭ごとの情報がインラインで掲載される。
  detail ページ (`/YYYYMMDD_{dog,cat}NN.html`) は存在するが、
  一覧時点で必要な情報 (収容日、場所、犬種、性別、サムネイル) が
  全て `<a>` タグの中に揃っているため、本 adapter は detail への
  追加 HTTP は行わず一覧から抽出する。
- 動物カードの構造:
    <a href="/hokenhukusi/seikat/20260313_dog01.html">
      <img src="/images/.../img_xxxx.jpg" ...>
      <span class="space_lft1">令</span>和8年3月13日（金曜日）山祇町（雑種、オス）
    </a>
- 在庫 0 件のセクションは "～現在、情報はありません～" と表示される
  (リンクが無いため自然と 0 件になる)。
- 収容日は和暦 (令和N年M月D日) で記載される。文字列のまま保持し、
  正規化は DataNormalizer 側に委ねる。
"""

from __future__ import annotations

import re
from typing import ClassVar
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter


class CitySaseboAdapter(SinglePageTableAdapter):
    """佐世保市 (city.sasebo.lg.jp) 用 rule-based adapter

    一覧ページに掲載された各 `<a href="*_dog*.html">` / `<a href="*_cat*.html">`
    リンクを 1 頭分のレコードとみなし、リンク内の img と
    インラインテキストから RawAnimalData を構築する。
    """

    # 動物 1 頭分に対応するリンク。実体としてのセレクタは派生先サイト名から
    # 動的に決まる (_dog vs _cat) が、基底契約のため代表値として _dog を置く。
    # `_load_rows` 経由で参照される際はサイト名から動的に決定し直す。
    ROW_SELECTOR: ClassVar[str] = (
        "div#tmp_contents a[href*='_dog'], div#tmp_contents a[href*='_cat']"
    )
    SKIP_FIRST_ROW: ClassVar[bool] = False
    # cells ベースの基底既定実装は使わない (列構造ではなく自由テキスト)
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {}
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    # detail URL から row index を引き戻すために、検出順を記憶しておく
    # (基底の `<list_url>#row=N` では fragment しか拾えないが、本 adapter は
    # 実 URL を返すため別ルートでマッピングを保持する)
    _detail_url_to_index: dict[str, int]

    def __init__(self, site_config) -> None:  # type: ignore[no-untyped-def]
        super().__init__(site_config)
        self._detail_url_to_index = {}

    # ─────────────────── オーバーライド ───────────────────

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """一覧ページから検出した detail link を `(absolute_url, category)` で返す

        基底の `<list_url>#row=N` 仮想 URL ではなく、実 detail URL を返す。
        後続の `extract_animal_details` ではこの URL から内部 index に
        引き戻して、キャッシュ済みの list HTML から抽出する。
        """
        rows = self._load_rows()
        if not rows:
            # 在庫 0 件でも例外にはしない: 一覧ページ自体が取得できているなら
            # "現在、情報はありません" の正常系として扱う。
            # ただし HTML 構造そのものが見当たらない場合は例外。
            container = self._load_container()
            if container is None:
                raise ParsingError(
                    "一覧コンテナ (#tmp_contents) が見つかりません",
                    selector="div#tmp_contents",
                    url=self.site_config.list_url,
                )
            return []

        category = self.site_config.category
        result: list[tuple[str, str]] = []
        self._detail_url_to_index = {}
        seen: set[str] = set()
        for i, link in enumerate(rows):
            href = link.get("href")
            if not href or not isinstance(href, str):
                continue
            absolute = self._absolute_url(href)
            if absolute in seen:
                continue
            seen.add(absolute)
            self._detail_url_to_index[absolute] = i
            result.append((absolute, category))
        return result

    def extract_animal_details(
        self, detail_url: str, category: str = "adoption"
    ) -> RawAnimalData:
        """`detail_url` に対応する `<a>` 要素から RawAnimalData を構築する

        detail ページへの追加 HTTP は行わず、一覧 HTML キャッシュ内の
        `<a>` 要素のインラインテキストと img から各フィールドを推定する。
        """
        rows = self._load_rows()
        # 一覧キャッシュの再評価で URL → index マッピングを準備しておく
        if not self._detail_url_to_index:
            for i, link in enumerate(rows):
                href = link.get("href")
                if isinstance(href, str):
                    self._detail_url_to_index.setdefault(
                        self._absolute_url(href), i
                    )

        # 仮想 URL (`<list_url>#row=N`) で渡された場合のフォールバック
        idx: int | None = None
        if detail_url in self._detail_url_to_index:
            idx = self._detail_url_to_index[detail_url]
        else:
            fragment = urlparse(detail_url).fragment
            if fragment.startswith("row="):
                try:
                    idx = int(fragment.split("=", 1)[1])
                except ValueError:
                    idx = None

        if idx is None or idx >= len(rows):
            raise ParsingError(
                f"detail URL に対応する一覧リンクが見つかりません: {detail_url}",
                url=detail_url,
            )

        link = rows[idx]
        text = link.get_text(separator=" ", strip=True)

        species, sex = self._parse_species_and_sex(text)
        if not species:
            # サイト名から動物種別をフォールバック推定
            species = self._infer_species_from_site_name(self.site_config.name)

        location = self._parse_location(text)
        shelter_date = self._parse_shelter_date(text)
        image_urls = self._extract_row_images(link, detail_url)

        try:
            return RawAnimalData(
                species=species,
                sex=sex,
                age="",
                color="",
                size="",
                shelter_date=shelter_date,
                location=location,
                phone="",
                image_urls=image_urls,
                source_url=detail_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(
                f"RawAnimalData バリデーション失敗: {e}", url=detail_url
            ) from e

    # ─────────────────── 行ロード ───────────────────

    def _load_rows(self) -> list[Tag]:
        """list_url の HTML を 1 回だけ取得して `<a>` 要素をキャッシュ

        サイト名 (保護犬 / 保護猫) に応じて `_dog` か `_cat` を含むリンクのみ
        を行とみなす。これにより、関連リンク欄に紛れた他の `<a>` (例: 長崎県
        のサイトリンク等) を誤って動物として拾わない。
        """
        if self._rows_cache is not None:
            return self._rows_cache

        if self._html_cache is None:
            self._html_cache = self._http_get(self.site_config.list_url)

        soup = BeautifulSoup(self._html_cache, "html.parser")
        # 本文コンテナに限定して動物リンクを抽出
        container = soup.select_one("div#tmp_contents")
        scope: BeautifulSoup | Tag = container if isinstance(container, Tag) else soup

        keyword = self._link_keyword_for_site()
        rows: list[Tag] = []
        for a in scope.find_all("a"):
            if not isinstance(a, Tag):
                continue
            href = a.get("href")
            if not isinstance(href, str):
                continue
            if keyword in href and href.endswith(".html"):
                rows.append(a)
        self._rows_cache = rows
        return rows

    def _load_container(self) -> Tag | None:
        """`<div id="tmp_contents">` 要素を取得 (構造妥当性チェック用)"""
        if self._html_cache is None:
            self._html_cache = self._http_get(self.site_config.list_url)
        soup = BeautifulSoup(self._html_cache, "html.parser")
        container = soup.select_one("div#tmp_contents")
        return container if isinstance(container, Tag) else None

    def _link_keyword_for_site(self) -> str:
        """サイト名から `_dog` / `_cat` のキーワードを決定する"""
        name = self.site_config.name or ""
        if "猫" in name:
            return "_cat"
        # 既定 (犬サイトおよび不明) は `_dog`
        return "_dog"

    # ─────────────────── 画像 URL フィルタ ───────────────────

    def _filter_image_urls(self, urls: list[str], base_url: str) -> list[str]:
        """佐世保市 CMS 上の動物写真のみを残す

        本サイトでは `/images/<記事ID>/` 配下のファイルが本文画像で、
        `/shared/` 配下のロゴ・テンプレ画像と区別する。フィルタ後 0 件
        になる場合は元リストを返すフェイルセーフ。
        """
        filtered = [u for u in urls if "/images/" in u and "/shared/" not in u]
        return filtered if filtered else urls

    # ─────────────────── テキスト解析 ───────────────────

    # 例: "令和8年3月13日（金曜日）山祇町（雑種、オス）"
    # 解析戦略: 末尾の括弧 `（雑種、オス）` から犬種と性別を取り出し、
    # それより前の "曜日)" 以降の文字列から場所、先頭の和暦から日付を取る。
    _PAREN_RE: ClassVar[re.Pattern[str]] = re.compile(
        r"[（(]([^（）()]+)[）)]\s*$"
    )
    # 元号の文字間にも空白が混ざりうる (例: `<span>令</span>和8年` を
    # get_text(separator=" ") で取り出すと "令 和8年..." になる)
    _DATE_RE: ClassVar[re.Pattern[str]] = re.compile(
        r"(令\s*和|平\s*成|昭\s*和)\s*\d+\s*年\s*\d+\s*月\s*\d+\s*日"
    )

    @classmethod
    def _parse_species_and_sex(cls, text: str) -> tuple[str, str]:
        """末尾の `（種別、性別）` から (species, sex) を取り出す

        例: "雑種、オス" → ("雑種", "オス"), "オス" のみなら ("", "オス")
        性別キーワードが含まれない場合は species 側に丸ごと寄せる。
        """
        m = cls._PAREN_RE.search(text)
        if not m:
            return "", ""
        inner = m.group(1)
        # 全角/半角カンマ・読点で分割
        parts = [p.strip() for p in re.split(r"[、,，]", inner) if p.strip()]
        species = ""
        sex = ""
        for p in parts:
            if any(k in p for k in ("オス", "メス", "雄", "雌")):
                # 性別単独 or "オス・メス" 等の混合表記
                sex = cls._normalize_sex(p)
            else:
                # 性別キーワードを含まない部分は犬種/猫種扱い
                if not species:
                    species = p
                else:
                    species = f"{species}、{p}"
        # 性別単独で species が空の場合はそのまま (species は空)
        return species, sex

    @staticmethod
    def _normalize_sex(text: str) -> str:
        """性別表記を "オス" / "メス" / 元文字列 のいずれかに正規化する"""
        if "オス" in text or "雄" in text:
            if "メス" in text or "雌" in text:
                # "オス・メス" 等の混合 → 原文を保持 (情報量損失防止)
                return text
            return "オス"
        if "メス" in text or "雌" in text:
            return "メス"
        return text

    @classmethod
    def _parse_location(cls, text: str) -> str:
        """日付の末尾 ")" 以降、性別括弧の手前までを場所として抽出する

        例: "令和8年3月13日（金曜日）山祇町（雑種、オス）" → "山祇町"
        曜日括弧が無い場合は日付直後から末尾括弧手前までを採用する。
        """
        # 末尾の `（…）` (種別/性別) を除去
        body = cls._PAREN_RE.sub("", text).strip()
        # 日付 + 曜日括弧 (`（金曜日）` 等) を除去
        # まず日付パターンを検出
        m = cls._DATE_RE.search(body)
        if m:
            after = body[m.end():]
            # 曜日括弧 (`（金曜日）` / `(金)` 等) を先頭から剥がす
            after = re.sub(r"^[（(][^）)]*[）)]", "", after).strip()
            return after
        return body

    @classmethod
    def _parse_shelter_date(cls, text: str) -> str:
        """テキスト内の和暦日付 (例: 令和8年3月13日) を抽出して返す

        和暦のまま保持し、西暦化や ISO 化は DataNormalizer 側に委ねる。
        見つからない場合は空文字。
        """
        m = cls._DATE_RE.search(text)
        if not m:
            return ""
        # 全角/半角混在の空白を除去して整える
        return re.sub(r"\s+", "", m.group(0))

    @staticmethod
    def _infer_species_from_site_name(name: str) -> str:
        """サイト名から動物種別 (犬/猫) を推定する"""
        if "猫" in name:
            return "猫"
        if "犬" in name:
            return "犬"
        return "その他"


# ─────────────────── サイト登録 ───────────────────
# 同一テンプレート上で運用される 2 サイトを同一 adapter にマップする。
for _site_name in (
    "佐世保市（保護犬）",
    "佐世保市（保護猫）",
):
    SiteAdapterRegistry.register(_site_name, CitySaseboAdapter)
