"""おおいた動物愛護センター rule-based adapter

対象ドメイン: https://oita-aigo.com/

特徴:
- 同一ドメイン上で 3 サイト (迷子情報メイン / 譲渡犬 / 譲渡猫) が
  共通テンプレートを使用しているため 1 つの adapter で全サイトを賄う:
    - https://oita-aigo.com/lostchild/                       (迷子情報, sheltered)
    - https://oita-aigo.com/information_doglist/anytimedog/  (譲渡犬,   adoption)
    - https://oita-aigo.com/information_catlist/anytimecat/  (譲渡猫,   adoption)
- 1 ページに複数動物が `<div class="information_box">` カード形式で
  並ぶ single_page サイト。詳細ページへのリンクは存在するが、
  一覧ページに必要な情報 (保護地域 / 推定年齢 / 性別 / 体重 / 写真) が
  全て掲載されているため一覧から抽出する。
- 各カード内部は `<dl><dt>項目名</dt><dd>値</dd></dl>` の定義リスト + 先頭の
  `<dd class="lostchild_ttl">` (例: 令和8年5月1日) と末尾の
  `<div class="information_day"><time>更新日：YYYY.MM.DD</time></div>` で
  構成される。テーブルではなく label 一致で抽出するため、基底の
  `td/th` ベース既定 `extract_animal_details` をオーバーライドする。
- 動物種別 (犬/猫) は譲渡サイトでは URL/サイト名から決まるが、
  迷子情報メインは犬猫が混在し HTML 上にも明示が無いため、
  サイト名から推定し不明な場合は空文字とする。
"""

from __future__ import annotations

import logging
import re
from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import NetworkError, ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter

logger = logging.getLogger(__name__)


class OitaAigoAdapter(SinglePageTableAdapter):
    """おおいた動物愛護センター用 rule-based adapter

    迷子情報メイン / 譲渡犬 / 譲渡猫 の 3 サイトで共通テンプレート。
    各動物は `div.information_box` カードで表現される single_page 形式。
    """

    # 各動物カード
    ROW_SELECTOR: ClassVar[str] = "div.information_box"
    # ヘッダ相当の行は無いので除外しない
    SKIP_FIRST_ROW: ClassVar[bool] = False
    # `<dl><dt>...</dt><dd>...</dd></dl>` から label 一致で抽出するため、
    # 基底の col_index ベース実装は使わない。契約として空辞書を宣言する。
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {}
    LOCATION_COLUMN: ClassVar[int | None] = None
    # 収容日はカード上の「令和YYYY年M月D日」表記をそのまま採用するため
    # 既定値は不要 (空文字 = 不明扱い)。
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    # 定義リストの dt ラベル -> RawAnimalData フィールド名
    # 詳細ページのみに現れるラベル (「毛色・長さ」「大きさ」) もここに含める。
    # 一覧カードに無い項目は extract_animal_details が詳細ページから補完する。
    LABEL_FIELDS: ClassVar[dict[str, str]] = {
        "保護地域": "location",
        "推定年齢": "age",
        "性別": "sex",
        "体重": "_weight",  # 後段で kg → size 語彙 (小/中/大) に変換
        "毛色": "color",
        "毛色・長さ": "color",  # 迷子情報詳細ページの揺れ
        "大きさ": "size",  # 詳細ページの体格 (中型/大型)
        "体格": "size",  # 念のための揺れ
        "仮名": "name",  # 個体識別: 仮名 (例 ぐりこ)。未登録で全件ドロップしていた
    }

    # 体重 → size 推定の境界 (kg)。
    # - ~5kg: 小型 (例: 子犬, 猫の多くがここに入る)
    # - 5~15kg: 中型 (例: 柴犬, 雑種の中型犬)
    # - 15kg~: 大型 (例: ラブラドール, シェパード)
    _SIZE_BOUNDARY_SMALL_KG: ClassVar[float] = 5.0
    _SIZE_BOUNDARY_LARGE_KG: ClassVar[float] = 15.0

    # ページ末尾 (またはサイト共通) で表示される愛護センター本部の代表電話。
    # 個別の保健所電話番号も並ぶが、動物カードと特定の番号が紐付かないため
    # 本部代表を全動物カード共通の phone として割り当てる。
    _CENTER_TEL: ClassVar[str] = "097-588-1122"

    # 一覧ページ送りの追跡上限。譲渡猫は 12 件/ページ × 5 ページ (2026-08-19
    # 実査 52 頭) で、余裕を持たせつつ暴走を防ぐ。
    MAX_LIST_PAGES: ClassVar[int] = 20

    # ─────────────────── オーバーライド ───────────────────

    def __init__(self, site_config) -> None:
        super().__init__(site_config)
        # 詳細ページ HTML のキャッシュ。同一 URL を 1 回しか取得しない。
        self._detail_html_cache: dict[str, str] = {}

    def _load_rows(self) -> list[Tag]:
        """一覧のページ送り (`<a rel="next">`) を最後まで辿って全カードを集める

        WordPress のカテゴリ一覧は 12 件/ページで、譲渡猫は 5 ページ 52 頭に
        及ぶ (2026-08-19 実査)。基底 `SinglePageTableAdapter._load_rows` は
        list_url の 1 ページしか読まないため、1 ページ目の 12 頭以外が
        掲載漏れになっていた (T046 で検出・T052)。

        仮想 URL (list_url#row=N) は全ページ連結後の通し index を row 検索用の
        内部キーとして使うが、source_url には採用しない (T053)。掲載順の
        入れ替わりで row 番号と実個体の対応がズレるため、実際の source_url は
        `extract_animal_details` がカード固有の詳細 URL から決定する。

        上限到達・循環検知いずれで打ち切った場合も `self.list_truncated` を
        立てる。CollectorService はこのフラグを見て prune_disappeared
        (消滅同期削除) をスキップする (T059)。打ち切り区間に未取得の
        実在個体が残っている可能性があり、部分集合のまま消滅判定すると
        誤って公開から削除してしまうため。
        """
        if self._rows_cache is not None:
            return self._rows_cache

        rows: list[Tag] = []
        visited_pages: set[str] = set()
        page_url = self.site_config.list_url
        truncated = False
        for _ in range(self.MAX_LIST_PAGES):
            if page_url in visited_pages:
                # next リンクが既訪問ページを指す異常系 (循環)。この先に未取得の
                # ページが残っている可能性があるため、上限到達と同様の打ち切りと
                # みなす (従来は無警告のまま silent break していた)。
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
            page_rows = [r for r in soup.select(self.ROW_SELECTOR) if isinstance(r, Tag)]
            rows.extend(page_rows)

            next_link = soup.find("a", rel="next")
            next_href = next_link.get("href") if isinstance(next_link, Tag) else None
            if not next_href or not isinstance(next_href, str):
                break
            page_url = self._absolute_url(next_href, base=page_url)
        else:
            # 上限で打ち切った = まだ next が残っている可能性があり、
            # 静かな掲載漏れになるため必ずログに残す。
            truncated = True
            logger.warning(
                "[%s] 一覧のページ送りが上限 %d ページに達しました。"
                "未取得のページが残っている可能性があります: %s",
                self.site_config.name,
                self.MAX_LIST_PAGES,
                page_url,
            )

        self.list_truncated = truncated
        self._rows_cache = rows
        return rows

    def extract_animal_details(self, virtual_url: str, category: str = "adoption") -> RawAnimalData:
        """`<div class="information_box">` カードから RawAnimalData を構築する

        基底の `td/th` ベース実装ではなく、`<dl><dt>label</dt><dd>value</dd></dl>`
        の並びを LABEL_FIELDS のラベル一致で取り出す。
        """
        rows = self._load_rows()
        idx = self._parse_row_index(virtual_url)
        if idx >= len(rows):
            raise ParsingError(
                f"row index {idx} out of range (total {len(rows)})",
                url=virtual_url,
            )
        card = rows[idx]

        fields = self._extract_dl_fields(card)

        # source_url: カード固有の詳細URLを優先する (T053)。
        # 仮想URL (list_url#row=N) は一覧の並び順に依存するため、掲載順の
        # 入れ替わりで指す動物がズレる。詳細URLはカード固有で安定する。
        # 見つからない場合のみ仮想URLへフォールバックする (真の掲載漏れ防止)。
        detail_url = self._select_detail_url(card)
        source_url = detail_url or virtual_url

        # 一覧カードに無い項目 (毛色/大きさ) を詳細ページから補完する。
        # 譲渡犬 (anytimedog) / 迷子 (lostchild) の一覧カードには毛色が無く、
        # 詳細ページ (transferdoglist / lostchild/...) にのみ「毛色」または
        # 「毛色・長さ」「大きさ」の dt がある。猫サイトは詳細ページにも体重
        # ・大きさ情報は無いが、毛色は一覧から取れているので補完不要。
        # 詳細ページ取得が失敗した場合は一覧カードの情報のみで継続する。
        detail_fields = self._fetch_detail_fields(detail_url=detail_url)
        for key, value in detail_fields.items():
            if value and not fields.get(key):
                fields[key] = value

        # 収容日: `<dd class="lostchild_ttl">` (例: "令和8年5月1日") を採用。
        # 無い場合は SHELTER_DATE_DEFAULT (空文字) で不明扱い。
        shelter_date = ""
        ttl = card.select_one("dd.lostchild_ttl")
        if isinstance(ttl, Tag):
            shelter_date = ttl.get_text(strip=True)
        if not shelter_date:
            shelter_date = self.SHELTER_DATE_DEFAULT

        # 動物種別はサイト名/URL から推定 (HTML には明示されない)。
        species = self._infer_species(self.site_config.name, self.site_config.list_url)

        # location: 譲渡ページ (anytimedog/anytimecat) には「保護地域」欄が無く
        # location が空になる。譲渡動物は当該センターに収容されているため、
        # サイト名 (括弧内を除く) をシェルター名として補完する。
        location = fields.get("location", "") or self._shelter_location()

        # size: 詳細ページに「大きさ」(中型/大型) があればそれを優先。
        # 詳細にも体格語が無ければ「体重: 11.64kg」から小/中/大 を推定する。
        size = fields.get("size", "") or self._weight_to_size(fields.get("_weight", ""))

        try:
            return RawAnimalData(
                species=species,
                sex=fields.get("sex", ""),
                age=fields.get("age", ""),
                color=fields.get("color", ""),
                size=size,
                shelter_date=shelter_date,
                location=location,
                phone=self._CENTER_TEL,
                name=fields.get("name", ""),
                image_urls=self._extract_row_images(card, virtual_url),
                source_url=source_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(f"RawAnimalData バリデーション失敗: {e}", url=virtual_url) from e

    # ─────────────────── ヘルパー ───────────────────

    def _fetch_detail_fields(self, *, detail_url: str) -> dict[str, str]:
        """カードに紐づく詳細ページの dl から LABEL_FIELDS マッピング済み辞書を返す

        詳細ページ URL は呼び出し側 (`extract_animal_details`) が
        `_select_detail_url` で解決済みのものを受け取る (source_url と
        二重に解決しないため)。

        実 oita-aigo.com 観測 (2026-06):
          anytimedog / anytimecat ページではカード内最初の `<a>` が
          「随時」カテゴリの自リンク (list_url 自身) であり、単純な
          `card.find("a")` だと詳細フェッチが list URL に向かい毛色 dl が
          一切取れない。list_url と一致するリンクは必ずスキップする
          (`_select_detail_url` 側で対処済み)。

        詳細ページ取得失敗 (NetworkError) は致命ではない。
        一覧カードのみで取れる範囲を返したいため、空辞書を返して継続する。
        同一 URL は `_detail_html_cache` で 1 回しかフェッチしない。
        """
        if not detail_url:
            return {}

        if detail_url in self._detail_html_cache:
            html = self._detail_html_cache[detail_url]
        else:
            try:
                html = self._http_get(detail_url)
            except NetworkError:
                # 詳細ページが取れなくても一覧側の情報は返したいので空辞書で継続
                return {}
            self._detail_html_cache[detail_url] = html

        soup = BeautifulSoup(html, "html.parser")
        # 詳細ページは `<div class="information_box">` を持たないので
        # ページ全体の dl を走査する。ヘッダ/フッタにも dl はあるが
        # LABEL_FIELDS に登録されたラベルのみ採用するので衝突しない。
        return self._extract_dl_fields(soup)

    def _select_detail_url(self, card: Tag) -> str:
        """カード内の `<a href>` から詳細ページ URL を 1 つ選ぶ

        スキップ条件:
          - href 属性が空
          - 絶対 URL 化した結果が oita-aigo.com 以外 (外部リンク)
          - list_url 自身 (anytimedog/anytimecat の「随時」カテゴリ自リンク等)。
            末尾スラッシュの有無は正規化して比較する。

        見つからなければ空文字を返す。
        """
        list_url_normalized = self.site_config.list_url.rstrip("/")
        for href_tag in card.find_all("a", href=True):
            if not isinstance(href_tag, Tag):
                continue
            href = href_tag.get("href")
            if not isinstance(href, str) or not href.strip():
                continue
            candidate = self._absolute_url(href, base=self.site_config.list_url)
            if "oita-aigo.com" not in candidate:
                continue
            # list_url 自身 (カテゴリ自リンク) は詳細ではない
            if candidate.rstrip("/") == list_url_normalized:
                continue
            return candidate
        return ""

    def _extract_dl_fields(self, card: Tag) -> dict[str, str]:
        """カード配下の `<dl><dt>label</dt><dd>value</dd></dl>` を辞書化する

        同一 dl 内に dt が無く dd のみのもの (タイトル用 `lostchild_ttl`) は
        `LABEL_FIELDS` に登録されないため自然にスキップされる。
        """
        result: dict[str, str] = {}
        for dl in card.find_all("dl"):
            if not isinstance(dl, Tag):
                continue
            dt = dl.find("dt")
            dd = dl.find("dd")
            if not isinstance(dt, Tag) or not isinstance(dd, Tag):
                continue
            label = dt.get_text(strip=True)
            value = dd.get_text(strip=True)
            field = self.LABEL_FIELDS.get(label)
            if field and field not in result:
                result[field] = value
        return result

    @classmethod
    def _weight_to_size(cls, weight_text: str) -> str:
        """「11.64kg」のような体重テキストを normalizer 語彙 (小/中/大) に変換

        - 5kg 未満: 小
        - 5kg 以上 15kg 未満: 中
        - 15kg 以上: 大
        - 数値が拾えない場合 (空文字, 「不明」等): 空文字
        """
        if not weight_text:
            return ""
        m = re.search(r"(\d+(?:\.\d+)?)", weight_text)
        if not m:
            return ""
        try:
            kg = float(m.group(1))
        except ValueError:
            return ""
        if kg < cls._SIZE_BOUNDARY_SMALL_KG:
            return "小"
        if kg < cls._SIZE_BOUNDARY_LARGE_KG:
            return "中"
        return "大"

    def _shelter_location(self) -> str:
        """サイト名から括弧書き (例: 「（譲渡犬）」) を除いたシェルター名を返す。

        例: 「おおいた動物愛護センター（譲渡犬）」→「おおいた動物愛護センター」。
        保護地域が取れない譲渡カードの location フォールバックに使う。
        """
        return re.sub(r"[（(].*?[）)]", "", self.site_config.name).strip()

    @staticmethod
    def _infer_species(name: str, list_url: str) -> str:
        """サイト名 / URL から動物種別 (犬/猫) を推定する

        - 譲渡犬サイト: name に "犬" / URL に "doglist" を含む
        - 譲渡猫サイト: name に "猫" / URL に "catlist" を含む
        - 迷子情報メイン: 犬猫混在のため空文字 (不明) を返す
        """
        haystack = f"{name} {list_url}"
        if "doglist" in list_url or ("犬" in name and "猫" not in name):
            return "犬"
        if "catlist" in list_url or ("猫" in name and "犬" not in name):
            return "猫"
        # 迷子情報など犬猫混在のケースは空文字 (不明)
        del haystack
        return ""


# ─────────────────── サイト登録 ───────────────────
# 同一テンプレート上で運用される 3 サイトを同一 adapter にマップする。
_SITE_NAMES = (
    "おおいた動物愛護センター（迷子情報メイン）",
    "おおいた動物愛護センター（譲渡犬）",
    "おおいた動物愛護センター（譲渡猫）",
)

for _name in _SITE_NAMES:
    SiteAdapterRegistry.register(_name, OitaAigoAdapter)
