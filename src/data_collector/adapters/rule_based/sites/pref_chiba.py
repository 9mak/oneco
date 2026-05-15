"""千葉県動物愛護センター rule-based adapter

対象ドメイン: https://www.pref.chiba.lg.jp/aigo/pet/

特徴:
- 同一テンプレート上で 5 サイト
  (本所収容犬/猫/犬猫以外、東葛飾支所収容犬/猫) を運用しており、
  URL パスのみが異なる single_page 形式:
    .../inu-neko/shuuyou/shuu-inu.html       (本所 収容犬)
    .../inu-neko/shuuyou/shuu-neko.html      (本所 収容猫)
    .../sonohoka/inu-nekoigai/index.html     (本所 収容犬猫以外)
    .../inu-neko/shuuyou/shuu-inu-tou.html   (東葛飾 収容犬)
    .../inu-neko/shuuyou/shuu-neko-tou.html  (東葛飾 収容猫)
- 1 ページに複数動物がブロック形式で並ぶ。個別 detail ページは存在しない。
- 各動物は次のような並びで表現される:
    <h2><strong>【収容日】2026年5月12日</strong></h2>
    <div class="col2">
      <div class="col2L">
        <p style="text-align: center;"><img alt="..." src="..."></p>
        <p style="text-align: center;">【管理番号】<a>kt260512-01</a></p>
        <p style="text-align: center;">【収容場所】香取市本矢作</p>
        <p style="text-align: center;">雑種・白黒茶・オス・中・成犬</p>
        <p style="text-align: center;">首輪無・鑑札無</p>
        <p style="text-align: center;">【掲載期限】2026年5月18日</p>
      </div>
      <div class="col2R"> ... </div>
    </div>
- ページ末尾に「テンプレート【収容日】2026年月日」というダミーブロックが
  含まれており、これは実データではないので除外する。
- 千葉県の HTML レスポンスは fixture 上で UTF-8 バイト列を Latin-1 と誤認して
  再 UTF-8 化された二重エンコーディング (mojibake) になっているケースがある。
  `_load_rows` で「千葉」が含まれていないときに限り逆変換を試みる。
- 動物種別 (犬/猫/その他) はサイト名から推定する (HTML の「種類」は
  "雑種"/"柴犬" 等の品種名のため)。
- 在庫 0 件 (動物データの h2 が無い) のページでもパース成功させる必要がある
  (例: 収容犬猫以外サイト等で空の場合)。テンプレート h2 だけは存在し得るが、
  それを除外した結果 0 件であっても ParsingError を出さない。
"""

from __future__ import annotations

import re
from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter

# 「【収容日】YYYY年MM月DD日」を抽出する正規表現 (全角/半角数字どちらでも)
_SHELTER_DATE_RE = re.compile(
    r"【\s*収容日\s*】\s*"
    r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日"
)


class PrefChibaAdapter(SinglePageTableAdapter):
    """千葉県動物愛護センター用 rule-based adapter

    本所 (収容犬/猫/犬猫以外) と東葛飾支所 (収容犬/猫) の計 5 サイトで
    共通テンプレートを使用する single_page 形式。
    各動物は `<h2>【収容日】...</h2>` を起点としたブロックで表現される。
    """

    # 各動物の起点となる `<h2>`。テンプレート行 ("テンプレート【収容日】") は
    # `_load_rows` 側で除外する。
    ROW_SELECTOR: ClassVar[str] = "h2"
    SKIP_FIRST_ROW: ClassVar[bool] = False
    # 基底の cells ベース既定実装は使わない (col2L 内 <p> のフリーテキスト
    # ベースで属性を抽出するため)。契約として明示する。
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {}
    LOCATION_COLUMN: ClassVar[int | None] = None
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    # 属性段落のラベル -> RawAnimalData フィールド名
    _LABEL_TO_FIELD: ClassVar[dict[str, str]] = {
        "管理番号": "management_number",
        "収容場所": "location",
        "掲載期限": "deadline",
    }

    # ─────────────────── オーバーライド ───────────────────

    def _load_rows(self) -> list[Tag]:
        """list_url の HTML を取得し、動物ブロックの起点 h2 をキャッシュ

        - 二重 UTF-8 mojibake (latin-1 解釈 → utf-8 再エンコード) を補正
        - "テンプレート【収容日】..." のダミー h2 を除外
        - 「【収容日】」を含まない h2 (ページ見出し等) も除外
        """
        if self._rows_cache is not None:
            return self._rows_cache

        if self._html_cache is None:
            self._html_cache = self._http_get(self.site_config.list_url)

        html = self._html_cache
        # mojibake 検出: ページタイトルや本文に「千葉」が含まれない場合は
        # latin-1 → utf-8 の逆変換を試みる。失敗したら元のまま。
        if "千葉" not in html:
            try:
                html = html.encode("latin-1").decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass

        soup = BeautifulSoup(html, "html.parser")
        rows: list[Tag] = []
        for h2 in soup.select(self.ROW_SELECTOR):
            if not isinstance(h2, Tag):
                continue
            text = h2.get_text(strip=True)
            # テンプレート行除外 ("テンプレート【収容日】...")
            if text.startswith("テンプレート"):
                continue
            # 動物データの h2 は必ず「【収容日】」を含む
            if "【収容日】" not in text and "収容日" not in text:
                continue
            rows.append(h2)

        self._rows_cache = rows
        return rows

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """動物リスト取得 (在庫 0 件でも ParsingError を出さない)

        基底実装は rows が空のとき例外を出すが、千葉県のサイトは
        収容動物が居ない期間でもページ自体は存在するため、空リストを返す。
        """
        rows = self._load_rows()
        category = self.site_config.category
        return [(f"{self.site_config.list_url}#row={i}", category) for i in range(len(rows))]

    def extract_animal_details(
        self, virtual_url: str, category: str = "sheltered"
    ) -> RawAnimalData:
        """`<h2>【収容日】...</h2>` を起点とした動物ブロックから抽出する

        基底の `td/th` 既定実装は使わず、col2L 内の `<p>` 群を解析する。
        """
        rows = self._load_rows()
        idx = self._parse_row_index(virtual_url)
        if idx >= len(rows):
            raise ParsingError(
                f"row index {idx} out of range (total {len(rows)})",
                url=virtual_url,
            )
        h2 = rows[idx]

        # 1) h2 から収容日を抽出 (例: "【収容日】2026年5月12日" -> "2026-05-12")
        shelter_date = self._parse_shelter_date(h2.get_text(strip=True))

        # 2) h2 直後の <div class="col2"> -> <div class="col2L"> を取得
        col2L = self._find_col2L_after(h2)

        location = ""
        breed = ""  # 「種類」(雑種/柴犬 等) ※species 判定は site 名で行う
        color = ""
        sex = ""
        size = ""
        age = ""
        image_urls: list[str] = []

        if col2L is not None:
            # 直下 <p> を順に処理
            paragraphs = [p for p in col2L.find_all("p", recursive=False) if isinstance(p, Tag)]
            for p in paragraphs:
                # 画像段落
                imgs = p.find_all("img")
                if imgs:
                    for img in imgs:
                        src = img.get("src")
                        if src and isinstance(src, str):
                            image_urls.append(self._absolute_url(src, base=virtual_url))
                    continue

                text = p.get_text(separator="", strip=True)
                if not text:
                    continue

                # ラベル付き段落 ("【管理番号】xxx" / "【収容場所】xxx" / "【掲載期限】xxx")
                label_match = re.match(r"【\s*([^】]+?)\s*】\s*(.*)", text)
                if label_match:
                    label = label_match.group(1)
                    value = label_match.group(2).strip()
                    if label == "管理番号":
                        pass
                    elif label == "収容場所":
                        location = value
                    elif label == "掲載期限":
                        # 掲載期限は AnimalData モデルに該当フィールド無し、
                        # 抽出はするが格納はしない (将来拡張用に変数だけ確保)
                        pass
                    continue

                # 属性段落: "種類・毛色・性別・体格・年齢" を「・」区切りで分解
                # 例: "雑種・白黒茶・オス・中・成犬"
                #     "首輪無・鑑札無" のような付帯情報段落も同形式で来る
                if "・" in text and not breed:
                    parts = [s.strip() for s in text.split("・")]
                    breed, color, sex, size, age = self._parse_attribute_parts(parts)

        # 種別はサイト名から推定 (HTML の breed は品種名のため)
        species = self._infer_species_from_site_name(self.site_config.name)

        try:
            return RawAnimalData(
                species=species,
                sex=sex,
                age=age,
                color=color,
                size=size,
                shelter_date=shelter_date or self.SHELTER_DATE_DEFAULT,
                location=location,
                phone="",
                image_urls=image_urls,
                source_url=virtual_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(f"RawAnimalData バリデーション失敗: {e}", url=virtual_url) from e

    # ─────────────────── ヘルパー ───────────────────

    @staticmethod
    def _parse_shelter_date(text: str) -> str:
        """「【収容日】2026年5月12日」から ISO 形式 "2026-05-12" を返す"""
        m = _SHELTER_DATE_RE.search(text)
        if not m:
            return ""
        y, mo, d = m.group(1), m.group(2), m.group(3)
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"

    @staticmethod
    def _find_col2L_after(h2: Tag) -> Tag | None:
        """h2 以降で最初に出現する `div.col2 > div.col2L` を返す"""
        for sib in h2.find_next_siblings():
            if not isinstance(sib, Tag):
                continue
            if sib.name in ("h1", "h2", "h3"):
                # 次の動物 h2 や別セクションに到達したら打ち切り
                break
            if sib.name == "div":
                col2L = sib.find("div", class_="col2L")
                if isinstance(col2L, Tag):
                    return col2L
        return None

    @staticmethod
    def _parse_attribute_parts(parts: list[str]) -> tuple[str, str, str, str, str]:
        """「・」区切り属性リストから (breed, color, sex, size, age) を返す

        典型例: ["雑種", "白黒茶", "オス", "中", "成犬"]
        要素数が足りない場合は空文字で埋める。
        """
        breed = parts[0] if len(parts) > 0 else ""
        color = parts[1] if len(parts) > 1 else ""
        sex = parts[2] if len(parts) > 2 else ""
        size = parts[3] if len(parts) > 3 else ""
        age = parts[4] if len(parts) > 4 else ""
        return breed, color, sex, size, age

    @staticmethod
    def _infer_species_from_site_name(name: str) -> str:
        """サイト名から動物種別 (犬/猫/その他) を推定する

        「収容犬猫以外」のように両方含むケースを先に判定する。
        """
        if "犬猫以外" in name or "以外" in name:
            return "その他"
        if "犬" in name:
            return "犬"
        if "猫" in name:
            return "猫"
        return "その他"


# ─────────────────── サイト登録 ───────────────────
# 同一テンプレート上で運用される 5 サイトを同一 adapter にマップする。
for _site_name in (
    "千葉県動愛センター本所（収容犬）",
    "千葉県動愛センター本所（収容猫）",
    "千葉県動愛センター本所（収容犬猫以外）",
    "千葉県動愛センター東葛飾支所（収容犬）",
    "千葉県動愛センター東葛飾支所（収容猫）",
):
    SiteAdapterRegistry.register(_site_name, PrefChibaAdapter)
