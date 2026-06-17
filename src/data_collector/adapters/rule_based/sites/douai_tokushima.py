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

import re
import unicodedata
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
    # 譲渡カード (f_a3) のみ存在する自由記述フィールド。
    # color / size を直接持たないため、ここから体重・色キーワードを推定する。
    "etcs": ("その他の情報",),
}


# その他の情報 (etcs) から色を推定するためのキーワードと採用色。
# 順序が結果を決めるので、複合色 (黒白 / キジ白 等) を単色より先に並べる。
# 各タプルは (検索キーワード, RawAnimalData.color に格納する値)。
_ETCS_COLOR_PATTERNS: tuple[tuple[str, str], ...] = (
    ("キジトラ", "キジトラ"),
    ("キジ白", "キジ白"),
    ("サビ", "サビ"),
    ("三毛", "三毛"),
    # 白黒 / 黒白 はどちらも「黒白」に正規化 (順序: 複合 → 単色)
    ("白黒", "黒白"),
    ("黒白", "黒白"),
    ("茶白", "茶白"),
    ("黒茶", "黒茶"),
    # 単色 (語尾を伴う表現のみマッチ。例: 「白い」「白色」)
    ("白い", "白"),
    ("白色", "白"),
    ("黒い", "黒"),
    ("黒色", "黒"),
    ("茶色", "茶"),
    ("茶系", "茶"),
    # 柴犬風の表現は茶系として扱う (実写真の傾向)
    ("柴犬風", "茶"),
    ("柴風", "茶"),
    ("クリーム", "クリーム"),
    ("グレー", "グレー"),
)


# 「推定年齢」セルが「成犬/若犬/若猫」などの語彙のとき、
# normalizer (`DataNormalizer._normalize_age`) は数値パターンしか拾えず
# age_months が None になる。kochi_adapter._KOCHI_AGE_ESTIMATES と同基準で
# adapter 層で目安月齢 (Nヶ月) に置換し、normalizer が拾える形に整える。
# 値の意図:
#   高齢/老齢/老犬/老猫 = 10歳 (120ヶ月)
#   成犬/成猫/成熟      = 3歳  (36ヶ月)
#   中齢                = 5歳  (60ヶ月)
#   若犬/若猫/若齢      = 1.5歳 (18ヶ月)
#   子犬/子猫/仔犬/仔猫/幼犬/幼猫/幼齢 = 3ヶ月
#   乳飲み子            = 1ヶ月
_AGE_WORD_TO_MONTHS: dict[str, int] = {
    "高齢": 120,
    "老齢": 120,
    "老犬": 120,
    "老猫": 120,
    "成犬": 36,
    "成猫": 36,
    "成熟": 36,
    "中齢": 60,
    "若犬": 18,
    "若猫": 18,
    "若齢": 18,
    "子犬": 3,
    "仔犬": 3,
    "子猫": 3,
    "仔猫": 3,
    "幼犬": 3,
    "幼猫": 3,
    "幼齢": 3,
    "乳飲み子": 1,
}


class DouaiTokushimaAdapter(PlaywrightFetchMixin, SinglePageTableAdapter):
    """徳島県動物愛護管理センター 共通アダプター

    3 サイト (収容中 / 譲渡犬 / 譲渡猫) で同一テンプレート (`ul.news > li`
    に各動物 table を含む構造) を共有するため、1 クラスで全 site_name を
    束ねて registry に登録する。
    """

    # ページ末尾に載るセンター代表電話。aria-label に「電話」「連絡先」が
    # 無く各カード個別の phone が取れないため、全動物カード共通で割り当てる。
    # (個別 li に phone aria-label があれば優先採用)
    _CENTER_TEL: ClassVar[str] = "088-636-6122"

    # 体重 → size 推定の境界 (kg)。kumamoto_doubutuaigo と同基準で揃える。
    # - 5kg 未満: 小
    # - 5kg 以上 15kg 未満: 中
    # - 15kg 以上: 大
    _SIZE_BOUNDARY_SMALL_KG: ClassVar[float] = 5.0
    _SIZE_BOUNDARY_LARGE_KG: ClassVar[float] = 15.0

    # 収容中 iframe (list1) の photo パスに含まれる種別コード。
    # ../list1_1/photo/=犬 / ../list1_2/photo/=猫 (譲渡の list4_1/list4_2 と同規約)。
    _SHELTERED_SPECIES_BY_PATH: ClassVar[tuple[tuple[str, str], ...]] = (
        ("list1_1", "犬"),
        ("list1_2", "猫"),
    )

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

        # species の補完。種類セルが犬/猫キーワードを含まない場合 (譲渡カードは
        # 種類セル自体が無く空、収容中カードは「雑種」固定) に補完する。
        species_val = fields.get("species", "")
        if not any(kw in species_val for kw in ("犬", "猫", "いぬ", "ねこ", "イヌ", "ネコ")):
            hint = _SPECIES_HINT.get(self.site_config.name, "")
            if hint:
                # 譲渡犬/譲渡猫はサイト名で犬猫が確定する。
                fields["species"] = hint
            # 収容中ページ (hint="") は種類セルが「雑種」で犬猫不明。ソースは
            # 犬/猫を画像パス (list1_1=犬 / list1_2=猫) と推定年齢 (若犬/若猫)
            # で明示分類しているため、これを拾って確定する (色推測ではない)。
            elif inferred := self._infer_sheltered_species(row, fields.get("age", "")):
                fields["species"] = inferred

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

        # phone はカードの aria-label から取れないため、ページ末尾に載っている
        # センター代表電話を全動物カード共通で割り当てる (2026-05 観測)。
        # 個別 li に phone aria-label があれば優先採用。
        phone = self._normalize_phone(fields.get("phone", "")) or self._CENTER_TEL

        # size の決定ロジック:
        # 1. 「体格」セルの値が「小型 / 中型 / 大型」のような語であればそのまま採用。
        # 2. 「体格」セルが「0.3kg」のように数値混じりの場合は _weight_to_size で
        #    小/中/大 に変換する (後段 normalize で kg 表記が落ちる救済)。
        # 3. 「体格」セルが空 (譲渡カード) であれば、その他の情報の体重表記を
        #    探して同様に推定する。
        raw_size = fields.get("size", "")
        size = raw_size if raw_size else ""
        if size and self._contains_kg_value(size):
            size = self._weight_to_size(size)
        if not size:
            size = self._weight_to_size(fields.get("etcs", ""))

        # color の決定ロジック: 「毛色」セルを優先採用し、空の場合のみ
        # その他の情報からキーワードベースで推定する。
        color = fields.get("color", "")
        if not color:
            color = self._color_from_etcs(fields.get("etcs", ""))

        # age の決定ロジック:
        # 収容中テーブルの「推定年齢」が「成犬/若犬/若猫」などの語彙のとき、
        # normalizer は数値パターンしか拾えず age_months が None になる。
        # adapter 層で目安月齢 (Nヶ月) に置換し、normalizer が拾える形に整える。
        # 数値表記 (「2歳」「3ヶ月」「２０２５年８月８日」) はそのまま保持する。
        age = self._age_word_to_months(fields.get("age", ""))

        try:
            return RawAnimalData(
                species=fields.get("species", ""),
                sex=fields.get("sex", ""),
                age=age,
                color=color,
                size=size,
                shelter_date=fields.get("shelter_date", ""),
                location=location,
                phone=phone,
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

    @staticmethod
    def _contains_kg_value(text: str) -> bool:
        """テキストに「N kg」「Ｎ kg」など体重を表す数値+kg が含まれるか"""
        norm = unicodedata.normalize("NFKC", text).replace("．", ".")
        return bool(re.search(r"\d+(?:\.\d+)?\s*kg", norm, flags=re.IGNORECASE))

    @classmethod
    def _weight_to_size(cls, text: str) -> str:
        """体重表記 (例: 「４．９kg」「12kg」) から size 語 (小/中/大) を推定

        - 5kg 未満: 小
        - 5kg 以上 15kg 未満: 中
        - 15kg 以上: 大
        - 数値 + kg が見つからない場合: 空文字

        全角数字 / 全角小数点 (．) も正規化して扱う。
        """
        if not text:
            return ""
        norm = unicodedata.normalize("NFKC", text).replace("．", ".")
        m = re.search(r"(\d+(?:\.\d+)?)\s*kg", norm, flags=re.IGNORECASE)
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

    @staticmethod
    def _age_word_to_months(text: str) -> str:
        """「成犬/若犬/若猫」などの語彙を「Nヶ月」表記に変換

        - 辞書 `_AGE_WORD_TO_MONTHS` に完全一致 (前後 strip 後) する語のみ
          目安月齢に置換する。
        - 既に数値表記 (「2歳」「3ヶ月」) や日付表記 (「２０２５年８月８日」) は
          そのまま返す。normalizer 側で正しく処理される。
        - 「不明」「--」「空文字」もそのまま返す (normalizer 側で None になる)。
        """
        stripped = text.strip()
        if stripped in _AGE_WORD_TO_MONTHS:
            return f"{_AGE_WORD_TO_MONTHS[stripped]}ヶ月"
        return text

    def _infer_sheltered_species(self, row: Tag, age_text: str) -> str:
        """収容中カードの犬/猫を画像パス → 推定年齢の順で確定する。

        収容中 iframe (list1) の種類セルは「雑種」固定で犬猫不明だが、ソースは
        犬/猫を (a) 画像パス (../list1_1/photo=犬 / ../list1_2/photo=猫)、
        (b) 推定年齢の語 (若犬/成犬=犬, 若猫/幼猫=猫) で明示分類している。
        いずれも取れなければ空文字を返し、その他 のままにする (誤分類より未分類)。
        """
        for img in row.find_all("img"):
            src = img.get("src")
            if not isinstance(src, str):
                continue
            for marker, species in self._SHELTERED_SPECIES_BY_PATH:
                if marker in src:
                    return species
        # 画像が無い個体の fallback: 推定年齢の語に犬/猫が含まれれば確定する。
        if "犬" in age_text:
            return "犬"
        if "猫" in age_text:
            return "猫"
        return ""

    @staticmethod
    def _color_from_etcs(text: str) -> str:
        """その他の情報の自由記述から色キーワードを抽出

        `_ETCS_COLOR_PATTERNS` の順 (複合色 → 単色) で最初にヒットした
        キーワードに対応する色を返す。該当無しなら空文字。
        """
        if not text:
            return ""
        for keyword, color in _ETCS_COLOR_PATTERNS:
            if keyword in text:
                return color
        return ""


# ─────────────────── サイト登録 ───────────────────
_SITE_NAMES = (
    "徳島県動物愛護管理センター（収容中）",
    "徳島県動物愛護管理センター（譲渡犬）",
    "徳島県動物愛護管理センター（譲渡猫）",
)

for _name in _SITE_NAMES:
    SiteAdapterRegistry.register(_name, DouaiTokushimaAdapter)
