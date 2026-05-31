"""町田市保健所 rule-based adapter (h3+ul li 形式)

対象 5 サイト（同一 CMS テンプレート）:
- syuyou.html                       (収容動物のお知らせ)
- hogo.html                         (保護情報)
- pet_fumei/search_dog.html         (迷子犬・捜索)
- pet_fumei/search_cat.html         (迷子猫・捜索)
- pet_fumei/search_sonota.html      (迷子その他・捜索)

HTML 構造（共通）:
    <article>
      <h1>...</h1>
      ...
      <h2>現在のXX情報</h2>      ← セクションアンカー
        <div class="h3bg"><h3>猫（おす）</h3></div>   ← 1 動物の見出し
        <div class="img-area-r">
          <ul>
            <li>種類：雑種</li>
            <li>性別：おす</li>
            <li>毛色：キジトラ</li>
            <li>保護場所：町田市XXX</li>
            <li>保護日：YYYY 年 M 月 D 日</li>
            <li>失踪場所：XXX</li>        ← 捜索系
            <li>失踪日時：XXX</li>        ← 捜索系
            <li>特徴：XXX</li>
            ...
          </ul>
        </div>
        <div class="h3bg"><h3>猫（めす）</h3></div>
        ...

旧実装は `<table>` 前提だったが、町田市の動物データは表ではなく見出し +
リスト構造で書かれている。本実装ではセクションアンカー h2 を探し、その後
ろの h3 を 1 動物として扱う。次の h2 までを 1 セクションとみなす。

0 件と adapter 破損の区別:
- セクション h2 が見つかる + h3 が 0 件 → 「動物がいない」正常 0 件
- セクション h2 が **見つからない** → サイト構造変更 (adapter 破損) で
  `ParsingError` を投げる。これにより構造変化を broken_tracker に拾わせる。
"""

from __future__ import annotations

import re
from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..base import RuleBasedAdapter
from ..registry import SiteAdapterRegistry

# 体重 → size 推定の境界 (kg)。oita_aigo / kumamoto_doubutuaigo._weight_to_size と同基準。
_SIZE_BOUNDARY_SMALL_KG: float = 5.0
_SIZE_BOUNDARY_LARGE_KG: float = 15.0

# 「特徴」フィールドの自由記述から体重を抽出する正規表現。
# 「体重4キロ」「体重約7キロ」「3キログラム」「7キロ越え」「5キロくらい」など。
# 範囲表記「3〜4キログラム」は最小値を採用 (軽い方を採って小判定を残す)。
_WEIGHT_KG_RE = re.compile(
    r"(\d+(?:\.\d+)?)"
    r"(?:\s*[〜~\-ー]\s*\d+(?:\.\d+)?)?"
    r"\s*(?:キロ(?:グラム)?|キログラム|kg|ｋｇ|Kg|KG)"
)

# 体格を明示する強キーワード。誤推定を避けるため「ぽっちゃり」「ふっくら」等の
# 曖昧表現は意図的に含めない。
_SIZE_SMALL_WORDS_RE = re.compile(r"小柄|小さめ|小型|子犬|子猫|小さい")
_SIZE_LARGE_WORDS_RE = re.compile(r"大柄|大型|大きい(?!が)")

# セクションアンカーとなる h2 テキストパターン。
# 完全一致ではなく substring match で、表記揺れを吸収する。
_SECTION_ANCHORS: tuple[str, ...] = (
    "現在の収容状況",
    "現在のペットの保護情報",
    "現在の迷子の犬情報",
    "現在の迷子の猫情報",
    "現在の迷子のその他",
    "現在の迷子のペット",
)

# 「ラベル：値」「ラベル: 値」両方を許容する区切り
_FIELD_SEP_RE = re.compile(r"[：:]")

# li のラベル → RawAnimalData フィールドのマッピング。
# 同義語を網羅し、町田市内の 5 サイトで共通利用できるようにする。
_LABEL_TO_FIELD: dict[str, str] = {
    "種類": "species_detail",
    "種別": "species_detail",
    "犬種": "species_detail",
    "猫種": "species_detail",
    "性別": "sex",
    "毛色": "color",
    "毛の色": "color",
    "色": "color",
    "体格": "size",
    "大きさ": "size",
    "体重": "_weight",  # 後段で kg → size 語彙 (小/中/大) に変換
    "特徴": "_feature",  # 後段で体重数値・体格語を抽出して size 推定に使用
    "年齢": "age",
    "推定年齢": "age",
    "収容日": "shelter_date",
    "保護日": "shelter_date",
    "発見日": "shelter_date",
    "発見日時": "shelter_date",
    "失踪日": "shelter_date",
    "失踪日時": "shelter_date",
    "収容場所": "location",
    "保護場所": "location",
    "発見場所": "location",
    "失踪場所": "location",
    "場所": "location",
}

# 動物種別判定（h3 / li 値の中から「犬」「猫」を抜く）
_SPECIES_DOG_RE = re.compile(r"犬|子犬|成犬")
_SPECIES_CAT_RE = re.compile(r"猫|子猫|成猫")

# 性別判定（h3 の括弧内など）
_SEX_MALE_RE = re.compile(r"おす|オス|♂|雄")
_SEX_FEMALE_RE = re.compile(r"めす|メス|♀|雌")


class CityMachidaAdapter(RuleBasedAdapter):
    """町田市保健所用 rule-based adapter (h3+ul li 形式)

    `article > h2 (セクションアンカー) > h3 (動物見出し) > ul li (フィールド)`
    という DOM 構造を前提に動物リストを抽出する。

    本 adapter は 5 サイト共通で使われる（syuyou / hogo / search_{dog,cat,sonota}）。
    """

    SECTION_ANCHORS: ClassVar[tuple[str, ...]] = _SECTION_ANCHORS

    def __init__(self, site_config) -> None:
        super().__init__(site_config)
        self._html_cache: str | None = None
        self._h3_cache: list[Tag] | None = None
        self._phone_cache: str | None = None

    # ─────────────────── 公開 API ───────────────────

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """h3 アンカー単位で仮想 URL を返す

        Raises:
            ParsingError: セクションアンカー h2 自体が見つからない（adapter 破損）
        """
        h3_list = self._load_h3_list()
        category = self.site_config.category
        return [(f"{self.site_config.list_url}#h3={i}", category) for i in range(len(h3_list))]

    def extract_animal_details(
        self, virtual_url: str, category: str = "sheltered"
    ) -> RawAnimalData:
        """1 個の h3 + 後続 ul li から RawAnimalData を構築する"""
        h3_list = self._load_h3_list()
        idx = self._parse_h3_index(virtual_url)
        if idx >= len(h3_list):
            raise ParsingError(
                f"h3 index {idx} out of range (total {len(h3_list)})",
                url=virtual_url,
            )
        h3 = h3_list[idx]

        # h3 のテキスト（「猫（おす）」「猫(おす)」等）から species / sex を推定
        h3_text = h3.get_text(separator=" ", strip=True)
        species_from_h3 = self._infer_species(h3_text)
        sex_from_h3 = self._infer_sex(h3_text)

        # h3 直後から次の h3/h2 までのレンジで ul li を集める
        fields = self._extract_fields_after_h3(h3)

        # species は「犬/猫/その他」に正規化（species_detail は柴犬/雑種等の具体名）
        species_detail = fields.get("species_detail", "")
        species_from_detail = self._infer_species(species_detail) if species_detail else ""
        species = species_from_detail or species_from_h3 or self._species_from_site_name()

        # sex は「オス/メス」に正規化（li の生値は「おす（去勢済み）」等の自由記述）
        sex_raw = fields.get("sex", "") or sex_from_h3
        sex = self._normalize_sex(sex_raw)

        # 画像 URL は h3 直後の div.img-area-r 内の img から取得
        image_urls = self._extract_images_after_h3(h3, virtual_url)

        # 電話番号はページ末尾の `<aside class="contact">` 内
        # `<p class="contact__tel">電話：042-722-6727</p>` から取得 (ページ共通)
        phone = self._extract_contact_phone()

        # size: 「大きさ」「体格」明示ラベルが最優先。空のときは「体重」ラベル、
        # それでも空なら「特徴」フィールド内の自由記述から体重数値・体格語で推定。
        # 町田市 CMS は「大きさ」欄を実質的に持たず (59件全件で size 欠損)、
        # 動物の体重・体格はもっぱら「特徴」自由記述に書かれている。
        size = (
            fields.get("size", "")
            or self._weight_to_size(fields.get("_weight", ""))
            or self._infer_size_from_feature(fields.get("_feature", ""))
        )

        try:
            return RawAnimalData(
                species=species,
                sex=sex,
                age=fields.get("age", ""),
                color=fields.get("color", ""),
                size=size,
                shelter_date=fields.get("shelter_date", ""),
                location=fields.get("location", ""),
                phone=phone,
                image_urls=image_urls,
                source_url=virtual_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(f"RawAnimalData バリデーション失敗: {e}", url=virtual_url) from e

    def normalize(self, raw_data: RawAnimalData):
        return self._default_normalize(raw_data)

    # ─────────────────── ヘルパー ───────────────────

    def _load_h3_list(self) -> list[Tag]:
        """list_url の HTML を 1 回だけ取得し、セクション内の h3 を抽出してキャッシュ"""
        if self._h3_cache is not None:
            return self._h3_cache

        if self._html_cache is None:
            raw = self._http_get(self.site_config.list_url)
            # 町田市 CMS は Content-Type charset 不正で requests.text が
            # Latin-1 → UTF-8 二重エンコードとして返るケースがあるため、
            # サイト名や見出しに含まれるはずの日本語が無ければ補正する
            # (Koshigaya/Aomori adapter と同様の防御策)
            if "町田市" not in raw and "現在" not in raw:
                try:
                    raw = raw.encode("latin-1").decode("utf-8")
                except (UnicodeEncodeError, UnicodeDecodeError):
                    pass
            self._html_cache = raw

        soup = BeautifulSoup(self._html_cache, "html.parser")
        article = soup.find("article")
        if article is None:
            # 町田市 CMS の構造前提が崩れているケース（典型的には search_*.html
            # 等で <article> が無いテンプレート派生があり得る）。フォールバックで
            # body 全体から探す。
            article = soup.find("body")
        if article is None:
            raise ParsingError(
                "article/body 要素が見つかりません",
                url=self.site_config.list_url,
            )

        section_h2 = self._find_section_anchor(article)
        if section_h2 is None:
            # アンカーが無い = サイト構造変更 (adapter 破損)。
            # broken_tracker でスキップ対象に乗せたいので例外を投げる。
            raise ParsingError(
                "動物情報セクションの h2 アンカーが見つかりません",
                url=self.site_config.list_url,
            )

        # section_h2 以降、動物見出し (性別マーカーを含む h2/h3) を順に集める。
        # search_cat.html の CMS では「猫（めす）」が h2 で書かれているケース
        # (作成ミス) があり、単純に「次の h2 までの h3」では拾い切れない。
        # → 性別マーカーを含む見出しはすべて 1 動物として扱う。
        # → 性別マーカーを含まない h2 が来たらセクション終了。
        h3_list: list[Tag] = []
        for sib in section_h2.find_all_next(["h2", "h3"]):
            if sib is section_h2:
                continue
            text = sib.get_text(separator=" ", strip=True)
            if self._is_animal_heading(text):
                h3_list.append(sib)
            elif sib.name == "h2":
                # 動物見出しでない h2 = セクション終了 (お問い合わせ等)
                break
            # 動物見出しでない h3 はスキップ (ナビゲーション等の可能性)

        self._h3_cache = h3_list
        return h3_list

    def _find_section_anchor(self, root: Tag) -> Tag | None:
        for h2 in root.find_all("h2"):
            text = h2.get_text(separator=" ", strip=True)
            if any(anchor in text for anchor in self.SECTION_ANCHORS):
                return h2
        return None

    def _parse_h3_index(self, virtual_url: str) -> int:
        """`<list_url>#h3=N` から N を取り出す"""
        m = re.search(r"#h3=(\d+)", virtual_url)
        if not m:
            raise ParsingError(f"無効な仮想 URL: {virtual_url} (#h3=N 形式が必要)")
        return int(m.group(1))

    def _extract_fields_after_h3(self, h3: Tag) -> dict[str, str]:
        """h3 直後（次の h3/h2 まで）の ul li を「ラベル：値」形式で抽出"""
        fields: dict[str, str] = {}
        for sib in h3.find_all_next(["h3", "h2", "ul"]):
            if sib.name in ("h2", "h3"):
                break
            if sib.name == "ul":
                for li in sib.find_all("li"):
                    text = li.get_text(separator=" ", strip=True)
                    parts = _FIELD_SEP_RE.split(text, maxsplit=1)
                    if len(parts) != 2:
                        continue
                    label = parts[0].strip()
                    value = parts[1].strip()
                    if not value:
                        continue
                    field = _LABEL_TO_FIELD.get(label)
                    if field is None:
                        continue
                    # 既に値が入っているフィールドは上書きしない
                    fields.setdefault(field, value)
                # 最初の ul で抽出完了。捜索ページのような複数 ul もありうるが、
                # 1 動物 1 ul を前提とする（CMS テンプレ通り）。
                break
        return fields

    def _extract_images_after_h3(self, h3: Tag, base_url: str) -> list[str]:
        """h3 直後の div.img-area-r 内の img src を絶対 URL リストとして返す"""
        urls: list[str] = []
        for sib in h3.find_all_next(["h3", "h2", "div"]):
            if sib.name in ("h2", "h3"):
                break
            if sib.name == "div":
                classes = sib.get("class") or []
                if any("img-area" in c for c in classes):
                    for img in sib.find_all("img"):
                        src = img.get("src")
                        if src and isinstance(src, str):
                            urls.append(self._absolute_url(src, base=base_url))
                    break
        return self._filter_image_urls(urls, base_url)

    def _extract_contact_phone(self) -> str:
        """ページ末尾の `<aside class="contact">` 内 `<p class="contact__tel">` から
        ページ共通の問い合わせ先電話番号を取得する

        町田市 CMS は動物カード内に個別電話番号を持たず、ページ末尾の
        担当課お問い合わせ aside に 1 つだけ電話番号が表示される。
        全動物カードでこの電話番号を共通利用する (同 list_url 内の全件で同じ)。
        """
        if self._phone_cache is not None:
            return self._phone_cache
        if self._html_cache is None:
            # _load_h3_list 経由で _html_cache が埋まる前提だが、フェイルセーフ
            self._phone_cache = ""
            return ""
        soup = BeautifulSoup(self._html_cache, "html.parser")
        # aside.contact > .contact__inner > .contact__content > p.contact__tel
        tel_p = soup.select_one("aside.contact .contact__tel")
        if tel_p is None:
            self._phone_cache = ""
            return ""
        # 「電話：042-722-6727」のような表記から番号部分のみ抽出
        text = tel_p.get_text(separator=" ", strip=True)
        m = re.search(r"(\d{2,4}[-ー]\d{2,4}[-ー]\d{3,4})", text)
        phone = m.group(1).replace("ー", "-") if m else ""
        self._phone_cache = phone
        return phone

    @staticmethod
    def _weight_to_size(weight_text: str) -> str:
        """「4kg」「4キロ」「3〜4キログラム」を「小/中/大」に変換

        - 5kg 未満: 小
        - 5kg 以上 15kg 未満: 中
        - 15kg 以上: 大
        - 数値が拾えない/空: 空文字

        範囲表記「3〜4」は最小値を採用する。oita_aigo._weight_to_size と同基準。
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
        if kg < _SIZE_BOUNDARY_SMALL_KG:
            return "小"
        if kg < _SIZE_BOUNDARY_LARGE_KG:
            return "中"
        return "大"

    @classmethod
    def _infer_size_from_feature(cls, feature_text: str) -> str:
        """「特徴」自由記述から size を推定する

        優先度:
        1. 体重数値 (「体重4キロ」「3キログラム程度」等) → _weight_to_size
        2. 体格語 (「小柄」「大柄」等) → 小/大
        3. それ以外: 空文字 (誤推定を避ける)

        町田市 CMS は「大きさ」明示欄が無いため、自由記述からの推定が
        サイズフィールドの実質的な抽出経路になる。
        """
        if not feature_text:
            return ""

        # 体重数値があれば最優先 (範囲表記は最小値が拾われる)
        m = _WEIGHT_KG_RE.search(feature_text)
        if m:
            return cls._weight_to_size(m.group(0))

        # 体格語 (強キーワードのみ。「ぽっちゃり」等の曖昧表現は意図的に除外)
        if _SIZE_SMALL_WORDS_RE.search(feature_text):
            return "小"
        if _SIZE_LARGE_WORDS_RE.search(feature_text):
            return "大"
        return ""

    def _infer_species(self, text: str) -> str:
        """テキストから「犬」「猫」を判定する（猫を先にチェック）"""
        if _SPECIES_CAT_RE.search(text):
            return "猫"
        if _SPECIES_DOG_RE.search(text):
            return "犬"
        return ""

    def _is_animal_heading(self, text: str) -> bool:
        """見出しテキストが「動物見出し」(性別マーカーを含む) か判定

        町田市 CMS の不規則な HTML で h2 と h3 が混在することがあるため、
        性別マーカーで動物見出しを識別する。
        例: 「猫（おす）」「犬(めす)」「成猫♂」 → True
            「お問い合わせ」「現在の収容状況」 → False
        """
        return bool(_SEX_MALE_RE.search(text) or _SEX_FEMALE_RE.search(text))

    def _infer_sex(self, text: str) -> str:
        """テキストから「オス」「メス」を判定する"""
        if _SEX_MALE_RE.search(text):
            return "オス"
        if _SEX_FEMALE_RE.search(text):
            return "メス"
        return ""

    def _normalize_sex(self, raw: str) -> str:
        """li 値「おす（去勢済みを確認）」等を「オス」「メス」に正規化

        判定不能なときは空文字を返す（RawAnimalData 側で空許容）。
        """
        if not raw:
            return ""
        return self._infer_sex(raw)

    def _species_from_site_name(self) -> str:
        """サイト名から species を推定する fallback"""
        name = self.site_config.name
        if "犬" in name and "猫" not in name:
            return "犬"
        if "猫" in name and "犬" not in name:
            return "猫"
        return ""


# ─────────────────── サイト登録 ───────────────────
# 町田市の 5 サイト（収容/保護/捜索犬/捜索猫/捜索その他）が同一 adapter を共有する。
# sites.yaml に登録される全名称を列挙する。
_MACHIDA_SITE_NAMES: tuple[str, ...] = (
    "町田市（収容動物のお知らせ）",
    "町田市（保護情報）",
    "町田市（捜索：飼い主が探している）",
    "町田市（迷子犬・捜索）",
    "町田市（迷子猫・捜索）",
    "町田市（迷子その他・捜索）",
)

for _name in _MACHIDA_SITE_NAMES:
    if SiteAdapterRegistry.get(_name) is None:
        SiteAdapterRegistry.register(_name, CityMachidaAdapter)
