"""徳島県動物愛護管理センター (douai-tokushima.com) rule-based adapter

対象ドメイン: https://douai-tokushima.com/

特徴:
- baserCMS で構築された自治体サイト。動物データは外部 iframe に
  EUC-JP エンコードの HTML として埋め込まれる構造 (ラッパページ側で iframe
  を JS 無しで読み込んでいるだけで、iframe 先の実データページ自体は
  静的 HTML)。T108 (2026-08-31) で iframe URL への直接静的 HTTP GET のみで
  一覧・詳細相当のデータが取得できることを確認し、sites.yaml の
  `requires_js` を全 3 サイトで false に修正した (旧実装は
  `PlaywrightFetchMixin` を保持したまま誤って true 設定されていた)。
- ラッパページ (sites.yaml の `list_url`) と実データ用 iframe URL の
  対応関係:
      /stray/             → /animalinfo/list1_1/ (収容中・犬)
                            /animalinfo/list1_2/ (収容中・猫)
                            /animalinfo/list1_3/ (収容中・その他)
      /transfer/doglist   → /animalinfo/list4_1  (譲渡犬)
      /transfer/catlist   → /animalinfo/list4_2  (譲渡猫)
- 収容中は当初 `/animalinfo/list1/` 1 ページだけを見ていたが、これは
  ページ自身に `最新の情報を3件表示しています。さらにご覧になる場合は
  一覧ページをご確認ください。` と書かれた **サマリーページ** で、
  種別ごとの全件は上記 3 つの iframe 側にある。2026-09-04 の実測で
  収容中・犬は 8 ページ 71 件あり、oneco は 3 件しか取れていなかった
  (68 件の掲載漏れ)。全件一覧は `<div class="pagination"><div class="next">
  <a href="index.cgi?Start=10">` でページ送りされる (T135)。
- 仮想 URL は当初 `#row=N` だったが、新しい個体が先頭に入るたび既存個体の
  URL がずれるため、件数が増えると T057 (山梨)・T066 (香川) と同じ
  identity 不安定による shelter_date 破壊と SNS 再投稿を引き起こす。
  写真ファイル名 (`photo2-17878928180.JPG`) が個体ごとに一意なので、
  T066 と同じ `#animal=<安定キー>` 方式に切り替えた (T135)。
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

import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import ClassVar
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..playwright import PlaywrightFetchMixin
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _RowEntry:
    """1 個体分の `<li>` と、その行がどの iframe / ページ由来かの情報。

    Attributes:
        row: 動物 1 件を表す `<li>` 要素。
        iframe_url: 由来する iframe のトップ URL。仮想 URL の base と
            画像の相対パス解決に使う。
        species_hint: その iframe に載る動物の species (判別不能なら空文字)。
        key: 仮想 URL に載せる安定キー。
    """

    row: Tag
    iframe_url: str
    species_hint: str
    key: str

# ラッパページ URL → 実データ iframe URL のマッピング。
# 収容中は種別ごとに 3 つの iframe に分かれるため、値は常にタプルで持つ。
_IFRAME_URL_MAP: dict[str, tuple[str, ...]] = {
    "https://douai-tokushima.com/stray/": (
        "https://douai-tokushima.com/animalinfo/list1_1/",
        "https://douai-tokushima.com/animalinfo/list1_2/",
        "https://douai-tokushima.com/animalinfo/list1_3/",
    ),
    "https://douai-tokushima.com/transfer/doglist": (
        "https://douai-tokushima.com/animalinfo/list4_1",
    ),
    "https://douai-tokushima.com/transfer/catlist": (
        "https://douai-tokushima.com/animalinfo/list4_2",
    ),
}

# iframe URL のパス断片 → その iframe に載る動物の species。
# 収容中の「種類」セルは「雑種」固定で犬猫が判別できないため、
# どの iframe から取れた行かで確定させる (空文字 = 判別不能)。
_IFRAME_SPECIES: tuple[tuple[str, str], ...] = (
    ("list1_1", "犬"),
    ("list1_2", "猫"),
    ("list1_3", ""),
    ("list4_1", "犬"),
    ("list4_2", "猫"),
)


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
    # 収容中ページの実表記は「収容日」。adapter 実装時に想定していた「発見日」は
    # 実サイトに存在せず、shelter_date が常に空 → normalizer が収集日に
    # フォールバックしていた (T135 で実 HTML を確認して発覚。T131 と同型)。
    "shelter_date": ("収容日", "発見日"),
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

    # 全件一覧のページ送り。`<div class="pagination"><div class="next">
    # <a href="index.cgi?Start=10">` 形式 (2026-09-04 実査)。
    NEXT_PAGE_SELECTOR: ClassVar[str] = ".pagination .next a"
    # 収容中・犬は実測 8 ページ。増加に余裕を持たせて 20 で打ち切る。
    MAX_LIST_PAGES: ClassVar[int] = 20

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._entries_cache: list[_RowEntry] | None = None

    # ─────────────────── 抽出ロジック ───────────────────

    def _load_entries(self) -> list[_RowEntry]:
        """対応する全 iframe を、ページ送りを辿りながら読み込む

        site_config.list_url はラッパページを指すが、実データは iframe 内の
        別ドキュメント。収容中は種別ごとに 3 つの iframe に分かれ、かつ犬は
        `index.cgi?Start=N` で複数ページに分割されている。

        上限到達・循環検知いずれで打ち切った場合も `self.list_truncated` を
        立てる。CollectorService はこれを見て prune_disappeared をスキップする
        (T059)。部分集合のまま消滅判定すると、未取得ページに載っている実在個体を
        誤って公開から削除してしまうため。
        """
        if self._entries_cache is not None:
            return self._entries_cache

        entries: list[_RowEntry] = []
        truncated = False
        used_keys: set[str] = set()

        for iframe_url in self._iframe_urls():
            species_hint = self._species_for_iframe(iframe_url)
            visited: set[str] = set()
            page_url = iframe_url
            for _ in range(self.MAX_LIST_PAGES):
                if page_url in visited:
                    truncated = True
                    logger.warning(
                        "[%s] 一覧のページ送りで循環を検知しました "
                        "(既訪問ページへの再遷移: %s)",
                        self.site_config.name,
                        page_url,
                    )
                    break
                visited.add(page_url)

                html = self._http_get(page_url)
                soup = BeautifulSoup(html, "html.parser")
                for row in soup.select(self.ROW_SELECTOR):
                    if not isinstance(row, Tag):
                        continue
                    key = self._stable_key(row, used_keys, len(entries))
                    used_keys.add(key)
                    entries.append(
                        _RowEntry(
                            row=row,
                            iframe_url=iframe_url,
                            species_hint=species_hint,
                            key=key,
                        )
                    )

                next_link = soup.select_one(self.NEXT_PAGE_SELECTOR)
                next_href = next_link.get("href") if isinstance(next_link, Tag) else None
                if not next_href or not isinstance(next_href, str):
                    break
                page_url = self._absolute_url(next_href, base=page_url)
            else:
                truncated = True
                logger.warning(
                    "[%s] 一覧のページ送りが上限 %d ページに達しました: %s",
                    self.site_config.name,
                    self.MAX_LIST_PAGES,
                    page_url,
                )

        self.list_truncated = truncated
        self._entries_cache = entries
        return entries

    def _load_rows(self) -> list[Tag]:
        """基底 (`SinglePageTableAdapter`) 互換の行リスト"""
        return [e.row for e in self._load_entries()]

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """動物一覧 (在庫 0 件でも ParsingError を出さず空リストを返す)

        仮想 URL は `<iframe URL>#animal=<安定キー>`。`#row=N` は掲載順が
        変わるたびに既存個体の URL がずれ、diff_detector が別個体の新規登録と
        みなして delete+insert する (= shelter_date 破壊・SNS 再投稿) ため
        使わない (T057 山梨・T066 香川と同型・T135)。
        """
        category = self.site_config.category
        return [(f"{e.iframe_url}#animal={e.key}", category) for e in self._load_entries()]

    def extract_animal_details(self, virtual_url: str, category: str = "adoption") -> RawAnimalData:
        """`#animal=<キー>` に対応する `<li>` から aria-label でフィールドを抽出"""
        entries = self._load_entries()
        key = self._parse_animal_key(virtual_url)
        entry = next((e for e in entries if e.key == key), None)
        if entry is None:
            raise ParsingError(
                f"animal key が一覧に見つかりません: {key} (total {len(entries)})",
                url=virtual_url,
            )
        row = entry.row

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
            elif entry.species_hint:
                # 収容中は iframe が種別ごとに分かれている (list1_1=犬 / list1_2=猫)
                # ため、どの iframe から取れた行かで確定する。
                fields["species"] = entry.species_hint
            elif inferred := self._infer_sheltered_species(row, fields.get("age", "")):
                fields["species"] = inferred

        # 収容中カードは個体ごとの「収容場所」を持つ (例: 吉野川市山川町井上)。
        # 譲渡カード (`f_a3`) は所在地セルを持たないため、その場合のみ
        # センター施設名にフォールバックする。
        location = self._extract_location(row)
        if not location:
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
                # 収容中カードの「種類」(雑種)は species 上書き(画像パス/年齢で犬猫確定)で
                # 失われていた。上書き前に退避した原値(species_val)を犬種=breed として保存。
                breed=species_val,
                sex=fields.get("sex", ""),
                age=age,
                color=color,
                size=size,
                shelter_date=fields.get("shelter_date", ""),
                location=location,
                phone=phone,
                image_urls=self._extract_row_images(row, entry.iframe_url),
                source_url=virtual_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(f"RawAnimalData バリデーション失敗: {e}", url=virtual_url) from e

    # ─────────────────── ヘルパー ───────────────────

    def _iframe_urls(self) -> tuple[str, ...]:
        """site_config.list_url に対応する iframe URL 群を返す

        収容中は種別ごとに 3 つ、譲渡は 1 つ。

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

    def _extract_location(self, row: Tag) -> str:
        """`<td aria-label="収容場所">` の先頭行だけを location として返す

        このセルは `吉野川市山川町井上<br>近隣住民の方からご連絡を受け、28日
        当センターに収容いたしました。` のように、地名のあとに `<br>` 区切りで
        経緯の説明文が続く。セル全体を取ると location に長い説明が混ざるため、
        最初の `<br>` より前だけを採用する。
        """
        td = row.find("td", attrs={"aria-label": "収容場所"})
        if not isinstance(td, Tag):
            return ""
        parts: list[str] = []
        for node in td.children:
            if isinstance(node, Tag) and node.name == "br":
                break
            text = node.get_text(strip=True) if isinstance(node, Tag) else str(node).strip()
            if text:
                parts.append(text)
        return " ".join(parts).strip()

    @staticmethod
    def _species_for_iframe(iframe_url: str) -> str:
        """iframe URL のパス断片から、そこに載る動物の species を返す"""
        for marker, species in _IFRAME_SPECIES:
            if marker in iframe_url:
                return species
        return ""

    @staticmethod
    def _stable_key(row: Tag, used: set[str], fallback_index: int) -> str:
        """掲載順が変わっても不変な個体キーを返す

        写真ファイル名 (`photo/photo2-17878928180.JPG`) は個体ごとに一意で、
        掲載順にも PDF 差し替えにも影響されないため安定キーに使える
        (T066 香川の個体管理番号と同じ役割)。写真が無い個体や、万一同じ
        ファイル名が複数行に現れた場合は通し番号にフォールバックする
        (このフォールバックは従来どおり不安定)。
        """
        for img in row.find_all("img"):
            src = img.get("src")
            if not isinstance(src, str) or not src:
                continue
            stem = src.rsplit("/", 1)[-1].rsplit(".", 1)[0]
            if stem and stem not in used:
                return stem
        return f"row{fallback_index}"

    @staticmethod
    def _parse_animal_key(virtual_url: str) -> str:
        """`<iframe URL>#animal=<キー>` からキーを取り出す"""
        fragment = urlparse(virtual_url).fragment
        if not fragment.startswith("animal="):
            raise ParsingError(f"無効な仮想 URL: {virtual_url} (#animal=<キー> 形式が必要)")
        return fragment.split("=", 1)[1]

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
