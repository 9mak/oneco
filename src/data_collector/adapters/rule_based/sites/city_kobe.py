"""神戸市動物管理センター rule-based adapter

対象ドメイン: https://www.city.kobe.lg.jp/a84140/kenko/health/hygiene/animal/zmenu/

特徴:
- 単一サイト ("神戸市動物管理センター（収容動物）") 1 つのみ運用される
  single_page 形式。1 ページ内に「収容犬一覧」「収容猫一覧」の 2 セクションが
  並び、それぞれに動物テーブルが配置される (もしくは在庫 0 件時は
  「現在、収容した犬はいません。」等の告知文のみが表示される)。
- 本文コンテナは `#tmp_contents`。
- 在庫 0 件状態 (現在のフィクスチャがこのケース):
    <h2>収容犬一覧</h2>
    <p>現在、収容した犬はいません。</p>
    <h2>収容猫一覧</h2>
    <p>現在、収容した猫はいません。</p>
  この状態は ParsingError ではなく "0 件" として扱い、
  `fetch_animal_list` は空リストを返す。
- 動物が居る場合の典型構造 (akashi/otsu と同じ汎用テーブル想定):
    <h2>収容犬一覧</h2>
    <table>
      <tr><th>収容日</th><th>写真</th><th>性別</th>...</tr>
      <tr><td>令和8年5月10日</td><td><img></td><td>オス</td>...</tr>
    </table>
    <h2>収容猫一覧</h2>
    <table>...</table>
  各テーブル行が直前の `<h2>` の見出しに属するため、行ごとに
  「収容犬一覧」配下なら "犬"、「収容猫一覧」配下なら "猫" と推定する。
- 神戸市ページは fixture 化される際に二重 UTF-8 mojibake
  (本来 UTF-8 のバイト列を Latin-1 として解釈してから再度 UTF-8 として
  保存) になるため、HTML キャッシュ取得時に逆変換を試みる。
- category は sites.yaml で "sheltered" (収容動物) と指定される。
"""

from __future__ import annotations

import re
from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter


# 「現在、収容した犬はいません。」「現在、収容している猫はいません。」等の
# 0 件告知パターン。「現在」+「(収容|保護)」+「いません」程度の表記揺れを
# 緩く吸収する。
_EMPTY_STATE_PATTERN = re.compile(
    r"現在[^。]*?(?:収容|保護)[^。]*?いません"
)

# 「収容犬一覧」「収容猫一覧」等の犬/猫セクション見出し検出パターン。
_DOG_SECTION_RE = re.compile(r"犬")
_CAT_SECTION_RE = re.compile(r"猫")


class CityKobeAdapter(SinglePageTableAdapter):
    """神戸市動物管理センター用 rule-based adapter

    収容犬・収容猫の単一サイト。`#tmp_contents` 配下の `<table>` 内
    `<tr>` を 1 動物として扱う single_page 形式。0 件状態は告知文のみで
    テーブルが存在しないため、`fetch_animal_list` 側で 0 件として扱う。
    """

    # `#tmp_contents` 配下のテーブル行のみを対象とする。
    # ページ内 (フッタ等) の他テーブルが追加された場合に備えてスコープを限定。
    ROW_SELECTOR: ClassVar[str] = "#tmp_contents table tr"
    # 1 行目はヘッダ行 (`<th>`) を想定し、データ行抽出時に除外する。
    SKIP_FIRST_ROW: ClassVar[bool] = False  # テーブル単位ではなくグローバル除外
    # 列インデックス → RawAnimalData フィールド名 のマッピング。
    # 想定列構成 (akashi 同等): [収容日 / 写真 / 種類 / 性別 / 毛色 / 体格 / 場所]
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {
        0: "shelter_date",
        3: "sex",
        4: "color",
        5: "size",
    }
    LOCATION_COLUMN: ClassVar[int | None] = 6
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    # ─────────────────── オーバーライド ───────────────────

    def _load_rows(self) -> list[Tag]:
        """list_url の HTML を取得し、二重 UTF-8 mojibake を補正してから行を抽出

        ヘッダ行 (全セルが `<th>` のみ) は除外する。各行は対応する
        `<h2>` セクション (収容犬一覧/収容猫一覧) の情報も含めてキャッシュ。
        """
        if self._rows_cache is not None:
            return self._rows_cache

        if self._html_cache is None:
            self._html_cache = self._http_get(self.site_config.list_url)

        html = self._html_cache
        # mojibake 検出: ページに「神戸」が含まれない場合は
        # latin-1 → utf-8 の逆変換を試みる。失敗したら元のまま。
        if "神戸" not in html:
            try:
                html = html.encode("latin-1").decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass

        # 復元後の HTML をキャッシュに反映 (extract_animal_details で
        # 同じ HTML を再利用できるようにするため)
        self._html_cache = html

        soup = BeautifulSoup(html, "html.parser")
        rows = soup.select(self.ROW_SELECTOR)
        # データ行のみを残す (全セルが `<th>` のヘッダ行を除外)
        rows = [
            r
            for r in rows
            if isinstance(r, Tag) and r.find("td") is not None
        ]
        self._rows_cache = rows
        return rows

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """テーブル行を仮想 URL に変換する

        0 件状態 (告知文のみ / テーブル不在) は空リストを返す。
        本文コンテナ (`#tmp_contents`) すら無い場合のみ ParsingError。
        """
        rows = self._load_rows()
        if not rows:
            # 本文コンテナの有無を確認 (テンプレート崩壊検知)
            html = self._html_cache or ""
            soup = BeautifulSoup(html, "html.parser")
            if soup.select_one("#tmp_contents") is None:
                raise ParsingError(
                    "本文コンテナ (#tmp_contents) が見つかりません",
                    selector="#tmp_contents",
                    url=self.site_config.list_url,
                )
            # 0 件告知 (現在、収容した犬/猫はいません) を許容
            if _EMPTY_STATE_PATTERN.search(html):
                return []
            # 告知も無いがテーブルも無い → 0 件として許容
            # (実サイトはセンター業務ページであり、保護動物が居ない期間も
            # 平常運用される)
            return []

        category = self.site_config.category
        return [
            (f"{self.site_config.list_url}#row={i}", category)
            for i in range(len(rows))
        ]

    def extract_animal_details(
        self, virtual_url: str, category: str = "sheltered"
    ) -> RawAnimalData:
        """テーブル行から RawAnimalData を構築する

        基底のセルベース既定実装に対し、行が属するセクション見出し
        (収容犬一覧 / 収容猫一覧) から species を推定する処理を加える。
        """
        rows = self._load_rows()
        idx = self._parse_row_index(virtual_url)
        if idx >= len(rows):
            raise ParsingError(
                f"row index {idx} out of range (total {len(rows)})",
                url=virtual_url,
            )
        row = rows[idx]
        cells = [c for c in row.find_all(["td", "th"]) if isinstance(c, Tag)]

        def _cell_text(i: int) -> str:
            if i >= len(cells):
                return ""
            return cells[i].get_text(separator=" ", strip=True)

        shelter_date = _cell_text(0) or self.SHELTER_DATE_DEFAULT
        sex = _cell_text(3)
        color = _cell_text(4)
        size = _cell_text(5)
        location = (
            _cell_text(self.LOCATION_COLUMN)
            if self.LOCATION_COLUMN is not None
            else ""
        )

        # 動物種別: 行が属するセクション見出し (h2) から推定する。
        # 「収容犬一覧」配下 → "犬"、「収容猫一覧」配下 → "猫"。
        # 推定不能ならサイト名にフォールバック。
        species = self._infer_species_from_row(row)

        try:
            return RawAnimalData(
                species=species,
                sex=sex,
                age="",
                color=color,
                size=size,
                shelter_date=shelter_date,
                location=location,
                phone="",
                image_urls=self._extract_row_images(row, virtual_url),
                source_url=virtual_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(
                f"RawAnimalData バリデーション失敗: {e}", url=virtual_url
            ) from e

    # ─────────────────── ヘルパー ───────────────────

    @classmethod
    def _infer_species_from_row(cls, row: Tag) -> str:
        """行の祖先テーブル直前の `<h2>` 見出しから種別を推定する

        神戸市は 1 ページ内に「収容犬一覧」「収容猫一覧」が並ぶ構造。
        各テーブルは対応する `<h2>` の直後に置かれるため、テーブル要素から
        直前 (前方) の `<h2>` を辿ってその文言で犬/猫を判定する。

        判定不能な場合は "その他" を返す。
        """
        # 1. 行 → 祖先テーブル
        table: Tag | None = None
        for ancestor in row.parents:
            if isinstance(ancestor, Tag) and ancestor.name == "table":
                table = ancestor
                break
        if table is None:
            return "その他"

        # 2. テーブルから前方兄弟 / 上位の前方兄弟を辿って最初の `<h2>` を探す
        heading = cls._find_preceding_h2(table)
        if heading is None:
            return "その他"

        text = heading.get_text(separator="", strip=True)
        # 「収容犬一覧」などは犬/猫いずれもヒットしうる文字 (例: "犬猫") を
        # 含む可能性があるため、両方含むケースは "その他" として扱う。
        has_dog = bool(_DOG_SECTION_RE.search(text))
        has_cat = bool(_CAT_SECTION_RE.search(text))
        if has_dog and has_cat:
            return "その他"
        if has_dog:
            return "犬"
        if has_cat:
            return "猫"
        return "その他"

    @staticmethod
    def _find_preceding_h2(start: Tag) -> Tag | None:
        """`start` から DOM を遡って最初の `<h2>` を返す (見つからなければ None)

        - まず `start` の前方兄弟を順に確認
        - 見つからなければ親に上がり、親の前方兄弟を確認
        - これを document root まで繰り返す
        """
        current: Tag | None = start
        while current is not None:
            for sib in current.find_previous_siblings():
                if not isinstance(sib, Tag):
                    continue
                if sib.name == "h2":
                    return sib
                # 兄弟内に h2 がネストされている場合 (div ラップ等) も拾う
                nested = sib.find_all("h2")
                if nested:
                    last = nested[-1]
                    if isinstance(last, Tag):
                        return last
            parent = current.parent
            if not isinstance(parent, Tag):
                return None
            current = parent
        return None


# ─────────────────── サイト登録 ───────────────────
# sites.yaml で定義される 1 サイトを登録する。
if SiteAdapterRegistry.get("神戸市動物管理センター（収容動物）") is None:
    SiteAdapterRegistry.register(
        "神戸市動物管理センター（収容動物）", CityKobeAdapter
    )
