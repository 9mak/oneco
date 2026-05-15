"""広島県動物愛護センター rule-based adapter

対象ドメイン:
- https://www.pref.hiroshima.lg.jp/site/apc/jouto-stray-{dog,cat}-list.html

特徴:
- 同一テンプレート上で迷い犬/迷い猫の 2 サイトを運用する single_page 形式
  (`<div class="detail_free">` 配下に動物ブロックが並ぶ)。
- 広島市 (`city.hiroshima.lg.jp`) は別テンプレートのため別 adapter
  (`city_hiroshima.CityHiroshimaAdapter`) で対応済み。
- 各動物は `<h2>管理番号：XXX</h2>` で開始され、続く `<p>` ブロックに
  画像と属性テキストが含まれる。テーブルや明示的なラベル/値構造は無く、
  自由記述に近いフリーテキスト中から正規表現で抽出する必要がある。
- 典型的な属性 `<p>` の中身 (`<br>` 区切り):
    雑種（柴犬風）、推定7歳、雄
    センターに収容された日：令和8年5月12日
    保護された状況：令和8年5月11日に安芸郡熊野町城之堀付近で保護されました。
- フィクスチャは二重 UTF-8 mojibake 状態で保存されている可能性があるため、
  `_load_rows` で latin-1 → utf-8 の逆変換を試みる。
- 動物種別 (犬/猫) はサイト名に含まれる ("迷い犬"/"迷子犬"/"迷い猫"/"迷子猫") から
  推定する。HTML 内には明示されないため。
- 在庫 0 件の HTML (本文に動物ブロックが無い) でも `ParsingError` を出さず、
  `fetch_animal_list` は空リストを返す。
"""

from __future__ import annotations

import re
from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter


class PrefHiroshimaAdapter(SinglePageTableAdapter):
    """広島県・広島市の迷い犬/猫一覧用 rule-based adapter

    `<div class="detail_free">` 配下に「管理番号 h2 + 詳細 p」のブロックが
    繰り返し並ぶ single_page 形式。テーブル形式ではないため、
    `_load_rows` と `extract_animal_details` をオーバーライドし、
    管理番号 h2 ごとに「その h2 から次の管理番号 h2 までの兄弟要素群」を
    1 行 (= 1 動物ブロック) として束ねる。
    """

    # ROW_SELECTOR は `_load_rows` をオーバーライドするので実際には未使用だが、
    # 基底クラスの契約 (空文字禁止) を満たすために宣言する。
    ROW_SELECTOR: ClassVar[str] = "div.detail_free h2"
    SKIP_FIRST_ROW: ClassVar[bool] = False
    # 値の取り出しは `extract_animal_details` のオーバーライドが行うため
    # COLUMN_FIELDS / LOCATION_COLUMN は契約宣言のみ。
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {}
    LOCATION_COLUMN: ClassVar[int | None] = None
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    # 「管理番号：」の見出しを判定する regex (全角/半角コロン両対応)
    _MGMT_HEAD_RE: ClassVar[re.Pattern[str]] = re.compile(
        r"管理番号\s*[：:]"
    )

    def __init__(self, site_config) -> None:
        super().__init__(site_config)
        # 管理番号 h2 とそれに続く属性 <p> 群を保持するブロックリスト。
        # `_rows_cache` (基底) は Tag のリストとして使う必要があるため、
        # 別キャッシュとしてブロック化済みの (header, body_tags) を保持する。
        self._blocks_cache: list[tuple[Tag, list[Tag]]] | None = None

    # ─────────────────── オーバーライド ───────────────────

    def _load_rows(self) -> list[Tag]:
        """list_url の HTML を取得し、管理番号 h2 をキャッシュする

        - 二重 UTF-8 mojibake (latin-1 解釈 → utf-8 再エンコード) を補正
        - 「管理番号：」を含む h2 を「動物ブロックの先頭」として検出
        - 0 件状態でも例外を出さず空配列を返す
        - 同時に `_blocks_cache` に (h2, 属性 <p> のリスト) のタプルを
          並びで格納し、`extract_animal_details` が再走査せずに済むようにする
        """
        if self._rows_cache is not None:
            return self._rows_cache

        if self._html_cache is None:
            self._html_cache = self._http_get(self.site_config.list_url)

        html = self._html_cache
        # mojibake 検出: 復元後にしか出てこない「広島」が無ければ逆変換を試みる
        if "広島" not in html:
            try:
                html = html.encode("latin-1").decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
        self._html_cache = html

        soup = BeautifulSoup(html, "html.parser")
        # 動物ブロックは原則 `div.detail_free` 配下に置かれる。
        # 念のため見つからない場合は body 全体から探索するフォールバックも持つ。
        scope = soup.select_one("div.detail_free") or soup.body or soup

        headers: list[Tag] = []
        blocks: list[tuple[Tag, list[Tag]]] = []
        # scope 直下の要素を順に走査し、管理番号 h2 ごとにグルーピングする
        current_header: Tag | None = None
        current_body: list[Tag] = []
        for child in scope.children:
            if not isinstance(child, Tag):
                continue
            if child.name and child.name.lower() == "h2" and self._is_mgmt_header(child):
                # 直前のブロックを確定
                if current_header is not None:
                    blocks.append((current_header, current_body))
                    headers.append(current_header)
                current_header = child
                current_body = []
            else:
                if current_header is not None:
                    current_body.append(child)
        if current_header is not None:
            blocks.append((current_header, current_body))
            headers.append(current_header)

        self._rows_cache = headers
        self._blocks_cache = blocks
        return headers

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """動物リスト取得 (在庫 0 件でも ParsingError を出さない)

        基底実装は rows が空のとき例外を出すが、広島県 / 広島市のページは
        収容ゼロの状態が正常運用としてあり得るため、空リストを許容する。
        """
        rows = self._load_rows()
        category = self.site_config.category
        return [
            (f"{self.site_config.list_url}#row={i}", category)
            for i in range(len(rows))
        ]

    def extract_animal_details(
        self, virtual_url: str, category: str = "lost"
    ) -> RawAnimalData:
        """管理番号ブロック (h2 + 後続 p 群) から RawAnimalData を構築する"""
        rows = self._load_rows()
        idx = self._parse_row_index(virtual_url)
        if idx >= len(rows):
            raise ParsingError(
                f"row index {idx} out of range (total {len(rows)})",
                url=virtual_url,
            )
        assert self._blocks_cache is not None  # _load_rows で必ずセットされる
        header, body_tags = self._blocks_cache[idx]

        # 属性テキストは body_tags 内の <p> を結合して扱う
        # (<br> は改行に置換することで「収容された日：…」等の行頭ラベルを保つ)
        text_parts: list[str] = []
        for tag in body_tags:
            if not isinstance(tag, Tag):
                continue
            # <br> を改行に変換した上で行ごとに strip
            for br in tag.find_all("br"):
                br.replace_with("\n")
            raw_text = tag.get_text(separator="\n", strip=False)
            for line in raw_text.splitlines():
                line = line.strip()
                if line:
                    text_parts.append(line)
        full_text = "\n".join(text_parts)

        # 種別 (犬/猫) はサイト名から推定する (HTML 上に明示されないため)
        species = self._infer_species_from_site_name(self.site_config.name)

        # 1 行目 (画像 <p> がある場合は次の最初の本文行) は典型的に
        # 「{種別補足}、推定N歳、雄/雌」形式。これを , / 、 / ， で分割して
        # age と sex を抽出する。
        sex = ""
        age = ""
        color = ""
        first_attr_line = self._first_attribute_line(text_parts)
        if first_attr_line:
            tokens = re.split(r"[、,，]", first_attr_line)
            tokens = [t.strip() for t in tokens if t.strip()]
            for tok in tokens:
                if not sex and self._looks_like_sex(tok):
                    sex = self._normalize_sex_token(tok)
                    continue
                if not age and self._looks_like_age(tok):
                    age = tok
                    continue
                if not color and self._looks_like_color(tok):
                    color = tok

        # 収容日 ("センターに収容された日：…") を行頭ラベルから抽出
        shelter_date = self._extract_labeled(
            full_text,
            (
                "センターに収容された日",
                "収容された日",
                "収容日",
                "保護日",
            ),
        )

        # 場所 ("保護された状況：…で保護されました。") から地名相当を抽出
        location = self._extract_location(full_text)

        # 画像 URL は header 直後の <p> 内 <img>、加えて body_tags 全体からも収集
        image_urls = self._collect_image_urls(body_tags, virtual_url)

        try:
            return RawAnimalData(
                species=species,
                sex=sex,
                age=age,
                color=color,
                size="",
                shelter_date=shelter_date or self.SHELTER_DATE_DEFAULT,
                location=location,
                phone="",
                image_urls=image_urls,
                source_url=virtual_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(
                f"RawAnimalData バリデーション失敗: {e}", url=virtual_url
            ) from e

    # ─────────────────── ヘルパー ───────────────────

    @classmethod
    def _is_mgmt_header(cls, h2: Tag) -> bool:
        """h2 が「管理番号：…」形式か判定"""
        text = h2.get_text(separator="", strip=True)
        return bool(cls._MGMT_HEAD_RE.search(text))

    @staticmethod
    def _first_attribute_line(lines: list[str]) -> str:
        """属性 1 行目 (種別/年齢/性別の CSV 風行) を返す

        画像 <p> しか無い行や「収容された日」「保護された状況」のラベル行は
        スキップして最初の属性 CSV 行を選ぶ。
        """
        skip_prefixes = (
            "センターに収容された日",
            "収容された日",
            "収容日",
            "保護日",
            "保護された状況",
        )
        for line in lines:
            if not line:
                continue
            if any(line.startswith(p) for p in skip_prefixes):
                continue
            # ラベル付き行 ("ラベル：値") は属性 CSV 行ではない
            if "：" in line or ":" in line:
                # ただし末尾にしか含まない短い行は CSV と区別しづらいので
                # ラベル行とみなしてスキップする
                continue
            return line
        return ""

    @staticmethod
    def _looks_like_sex(token: str) -> bool:
        return token in ("雄", "雌", "オス", "メス", "おす", "めす", "♂", "♀") or (
            "性" not in token and (
                "雄" == token or "雌" == token
            )
        )

    @staticmethod
    def _normalize_sex_token(token: str) -> str:
        """「雄/雌」表記を「オス/メス」に統一 (上流 normalizer の入力候補)"""
        if token in ("雄", "オス", "おす", "♂"):
            return "オス"
        if token in ("雌", "メス", "めす", "♀"):
            return "メス"
        return token

    @staticmethod
    def _looks_like_age(token: str) -> bool:
        # 「推定7歳」「成犬」「7歳」「2か月」など
        return bool(
            re.search(r"\d+\s*(歳|か月|ヶ月|ケ月|カ月|か月齢)", token)
            or "推定" in token
            or "成犬" in token
            or "成猫" in token
            or "幼犬" in token
            or "幼猫" in token
            or "子犬" in token
            or "子猫" in token
        )

    @staticmethod
    def _looks_like_color(token: str) -> bool:
        # 性別/年齢でない残りはヒューリスティックに「色」候補とみなす。
        # 雑種（柴犬風）のような括弧付き種別補足は色ではないので除外。
        if not token:
            return False
        if "（" in token or "(" in token:
            # 種別補足 ("雑種（柴犬風）" 等) は色ではない
            return False
        return any(c in token for c in ("茶", "黒", "白", "灰", "赤", "黄", "クリーム", "三毛", "ブチ", "キジ", "縞"))

    @staticmethod
    def _extract_labeled(full_text: str, labels: tuple[str, ...]) -> str:
        """行頭ラベル ("ラベル：値") から値部分を取り出す"""
        for line in full_text.splitlines():
            line = line.strip()
            for label in labels:
                # 全角/半角コロン両対応
                for sep in ("：", ":"):
                    prefix = f"{label}{sep}"
                    if line.startswith(prefix):
                        return line[len(prefix):].strip()
        return ""

    @staticmethod
    def _extract_location(full_text: str) -> str:
        """「保護された状況：YYYY年M月D日に{場所}で保護されました。」から場所を抽出

        日付らしき先頭部分 ("令和N年M月D日に" / "YYYY年M月D日に") を除去して
        「で保護されました」直前までを場所として返す。抽出に失敗したら
        フォールバックとして「保護された状況」全文を返す。
        """
        labels = ("保護された状況", "発見場所", "保護場所", "収容場所")
        raw = ""
        for line in full_text.splitlines():
            line = line.strip()
            for label in labels:
                for sep in ("：", ":"):
                    prefix = f"{label}{sep}"
                    if line.startswith(prefix):
                        raw = line[len(prefix):].strip()
                        break
                if raw:
                    break
            if raw:
                break
        if not raw:
            return ""

        # 「令和N年M月D日に / YYYY年M月D日に / N月D日に」までを除去
        date_re = re.compile(
            r"^(令和|平成|昭和)?\s*\d+\s*年\s*\d+\s*月\s*\d+\s*日\s*に"
        )
        without_date = date_re.sub("", raw, count=1).strip()

        # 「で保護されました」「で発見されました」より前を場所候補とする
        for tail in (
            "で保護されました",
            "で保護され",
            "にて保護されました",
            "にて保護され",
            "で発見されました",
            "で発見され",
        ):
            if tail in without_date:
                return without_date.split(tail, 1)[0].rstrip("、,，").strip()
        # 句点で切る
        return without_date.split("。", 1)[0].strip()

    def _collect_image_urls(self, body_tags: list[Tag], base_url: str) -> list[str]:
        """body_tags の全 <img> から画像 URL を絶対 URL 化して返す"""
        urls: list[str] = []
        for tag in body_tags:
            if not isinstance(tag, Tag):
                continue
            for img in tag.find_all("img"):
                src = img.get("src")
                if src and isinstance(src, str):
                    urls.append(self._absolute_url(src, base=base_url))
        return self._filter_image_urls(urls, base_url)

    @staticmethod
    def _infer_species_from_site_name(name: str) -> str:
        """サイト名から動物種別 (犬/猫) を推定する

        - "犬" を含む → "犬"
        - "猫" を含む → "猫"
        - いずれにも該当しない → "" (空文字: 上流 normalizer 側で処理)
        """
        if "犬" in name:
            return "犬"
        if "猫" in name:
            return "猫"
        return ""


# ─────────────────── サイト登録 ───────────────────
# sites.yaml の `pref.hiroshima.lg.jp` ドメイン 2 件を同一 adapter にマップする。
# 広島市 (`city.hiroshima.lg.jp`) は別 adapter (`city_hiroshima.CityHiroshimaAdapter`)
# が既に登録済みなので対象外。福山市 (`city.fukuyama.hiroshima.jp`) もテンプレートが
# 異なる (片方は detail ページあり) ため対象外。
for _site_name in (
    "広島県動物愛護センター（迷い犬）",
    "広島県動物愛護センター（迷い猫）",
):
    if SiteAdapterRegistry.get(_site_name) is None:
        SiteAdapterRegistry.register(_site_name, PrefHiroshimaAdapter)
