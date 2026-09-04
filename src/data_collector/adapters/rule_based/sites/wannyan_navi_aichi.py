"""愛知県わんにゃんナビ (wannyan-navi.pref.aichi.jp) rule-based adapter

対象ドメイン: https://wannyan-navi.pref.aichi.jp/

【T123 (2026-09-03) 再設計】
初版実装 (Phase A3, 2026 年前半) は「Playwright で JS 実行後 HTML を取得すれば
`<a href>` から詳細リンクを拾える」という他サイトと同じ前提で書かれていたが、
実サイトを Playwright で実際にレンダリングして検証した結果、この前提が
根本的に成り立たないことが判明した:

- サイト全体が Bubble.io 製 SPA で、一覧カードは `<a>` ではなく
  `onclick` ハンドラを持つ `<div class="clickable-element">` で構成される。
  JS 実行後の DOM に `<a>` タグは **1 つも存在しない** (実測)。
- カードをクリックすると `history.pushState` で URL が
  `?page=list_dc_m&no=<record_id>` に書き換わり、詳細内容が同一ページ内に
  描画される。この `record_id` は静的 HTML のどこにも埋め込まれておらず、
  一覧ページ読み込み時に発行される `/elasticsearch/search` /
  `/elasticsearch/msearch` への内部検索リクエストのレスポンス JSON にのみ
  含まれる (Bubble Data API の生の値ではなく、検索インデックスへの問い合わせ)。
  レスポンス本文の各フィールド値 (品種/毛色/年齢等) は Bubble の
  プライベートデータ保護によりキー名・一部値 (Option Set 等) が難読化されて
  おり抽出に使えないが、`_id` 自体は難読化されておらず detail URL の `no=`
  パラメータとしてそのまま利用できる (`_collect_record_ids_via_network`)。
- 上記の URL パターンは deep link として単独ロード可能 (fresh page で
  直接 goto しても同じ内容が描画される) ことを確認済みのため、detail
  ページ取得自体は他サイトと同じ `PlaywrightFetchMixin._http_get` に乗せる。
- detail ページにもラベル付き `<dt>/<dd>` や `<th>/<td>` は存在しない
  (Bubble はフラットな `<div class="bubble-element Text ...">` の羅列で
  UI を描画する)。個別の class 名は Bubble エディタでの再配置により
  再生成されうるため信頼できないが、「基本情報」「特徴」という見出し
  テキスト自体は編集者が書いた文言でありクラス名より安定していると判断し、
  これをアンカーにして周辺のテキストを構造的に分類する
  (`_extract_basic_info` / `_classify_basic_info`)。
- 動物種別 (犬/猫) はどのラベルにも出現しないが、詳細ページ本文に
  必ず「(犬|猫)の飼い方講習会へ」というリンク文言が現れる。これは
  サイト側が個体の種別に応じて出し分けている一次情報であり、
  最も信頼できる犬/猫判定シグナルとして採用する
  (`_infer_species_from_guide_link`)。実データ (犬 3 件・猫 26 件) で
  「犬の飼い方講習会へ」「猫の飼い方講習会へ」双方とも動作確認済み。

- 実測 (2026-09-03): 掲載頭数 29 頭 (犬 3 頭・猫 26 頭)。全 29 件を
  `fetch_animal_list` → `extract_animal_details` → `normalize` まで実行し、
  致命フィールド (species/phone/location/image_urls) の欠損 0 件・
  ParsingError 0 件を確認済み (dry-run、DB 書き込みは行っていない)。
  `?page=list_dc` の一覧ページ 1 回のロードで `/elasticsearch/search`
  レスポンスに `total: 29, hits: 29` が返り、ページネーション UI を
  クリックせずに全件の record id を取得できることを確認済み。
  (ページネーション UI 自体は `ul.pl_pagenation_all108976` という
  jQuery 系プラグインで実装されているが、フルページ再読み込み後の
  再初期化が不安定で `wait_for_selector` がタイムアウトすることがあった
  ため、クリック操作に依存しないこの方式を採用した。)
"""

from __future__ import annotations

import logging
import re
from typing import ClassVar

from bs4 import BeautifulSoup, Tag
from playwright.sync_api import sync_playwright

from ....domain.models import RawAnimalData
from ...municipality_adapter import NetworkError, ParsingError
from ...politeness import ONECO_USER_AGENT
from ..playwright import PlaywrightFetchMixin
from ..registry import SiteAdapterRegistry
from ..wordpress_list import WordPressListAdapter

# 一覧ページの「基本情報」ブロック内、見出しの直後に並ぶ値のうち
# 明確なキーワード/パターンで分類できないもの (品種・毛色) を割り当てる順序。
# サイト実測 (2026-09-03) の表示順: 管理番号 → 場所 → 品種 → 毛色 → 性別 → 年齢。
_BASIC_INFO_HEADING = "基本情報"
_FEATURE_HEADING = "特徴"

_LOCATION_KEYWORDS = ("本所", "支所")
_SEX_VALUES = {"オス", "メス", "不明"}
_AGE_PATTERN = re.compile(r"\d+\s*歳|\d+\s*ヶ月|\d+\s*ヵ月|\d+\s*か月")
_MANAGEMENT_NO_PREFIX = re.compile(r"^No\s*[.．]?\s*")
_POSTED_DATE_PATTERN = re.compile(r"掲載日[：:]\s*(\d{4}/\d{1,2}/\d{1,2})")
_GUIDE_LINK_PATTERN = re.compile(r"(犬|猫)の飼い方講習会へ")
_BUBBLE_FILE_ID_PATTERN = re.compile(r"/(f\d+x\d+)/")

# detail URL の `page` クエリパラメータ値 (一覧カードクリック時の実測値)。
_DETAIL_PAGE_PARAM = "list_dc_m"

# elasticsearch レスポンス判定用の URL 部分文字列。
_ELASTICSEARCH_URL_HINT = "elasticsearch"

logger = logging.getLogger(__name__)


class WannyanNaviAichiAdapter(PlaywrightFetchMixin, WordPressListAdapter):
    """愛知県わんにゃんナビ rule-based adapter (T123 再設計版)

    一覧: `_collect_record_ids_via_network` で elasticsearch レスポンスから
    record id を収集し、detail URL を組み立てる (`fetch_animal_list` は
    `WordPressListAdapter` の `<a href>` 前提実装を使わず完全に上書きする)。
    詳細: `PlaywrightFetchMixin` 経由で deep link を単独ロードし、見出し
    テキストをアンカーにした構造的パースでフィールドを抽出する。
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # elasticsearch が報告する総件数 (`hits.total`)。収集した record id が
        # これより少なければ打ち切りとみなす (T123 reviewer F-01)。
        self._observed_total: int | None = None

    # `wait_until="networkidle"` (既定) だけで detail ページの描画完了後
    # HTML (実測 80KB 前後、bubble-element 100+ 個) を取得できることを実サイトで
    # 確認済み。photo carousel 等の存在に依存する selector にすると写真 0 枚の
    # 個体で wait_for_selector がタイムアウトし detail 取得ごと失敗するため、
    # ページ全体で必ず出現する `.bubble-element` を保険として待つ。
    WAIT_SELECTOR: ClassVar[str | None] = ".bubble-element"

    # 基底クラス (`WordPressListAdapter.__init_subclass__`) が
    # 空文字を拒否するため形式上定義するが、`fetch_animal_list` を
    # 完全にオーバーライドしているため実際には参照されない。
    LIST_LINK_SELECTOR: ClassVar[str] = "a[href]"

    # 動物本人の写真は slick カルーセル (`slickcarousel-Carousel`、Bubble
    # プラグインの固定クラス名で内部 id ハッシュより安定) 配下の img のみ。
    # ヘッダーロゴ / サイト共通アイコンはこの外側にあるため自然に除外される。
    IMAGE_SELECTOR: ClassVar[str] = ".slickcarousel-Carousel img"

    # ─────────────────── 一覧: record id 収集 ───────────────────

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """elasticsearch レスポンスから収集した record id で detail URL を組み立てる

        0 件 (record id が 1 つも観測できない) は「現在譲渡対象の個体がいない」
        真のゼロとして扱い、ParsingError にはしない。

        elasticsearch レスポンスの `hits.total` が実際に拾えた id 件数より多い
        場合は `self.list_truncated` を立てる。Bubble のクライアント側検索が
        隠れた size 上限で結果を打ち切ると、無警告で収集漏れが起きたうえに
        「全件取れた」と誤認されて prune_disappeared が実在個体を削除しうる
        (T059 の安全弁と同じ扱い・T123 reviewer F-01)。
        """
        self._observed_total = None
        ids = self._collect_record_ids_via_network()
        category = self.site_config.category
        base = self.site_config.list_url
        urls: list[tuple[str, str]] = []
        seen: set[str] = set()
        for record_id in ids:
            detail_url = self._absolute_url(f"?page={_DETAIL_PAGE_PARAM}&no={record_id}", base=base)
            if detail_url in seen:
                continue
            seen.add(detail_url)
            urls.append((detail_url, category))

        total = self._observed_total
        if total is not None and total > len(urls):
            self.list_truncated = True
            logger.warning(
                "[%s] elasticsearch は %d 件と報告しているが record id は %d 件しか"
                "拾えませんでした。未取得の個体が残っている可能性があります",
                self.site_config.name,
                total,
                len(urls),
            )
        return urls

    def _collect_record_ids_via_network(self) -> list[str]:
        """一覧ページ読み込み時の elasticsearch レスポンスから `_id` を収集する

        Bubble.io は一覧カードに `<a href>` を持たないため、静的/JS 実行後
        いずれの HTML パースでも record id を取得できない。一覧ページの
        検索ウィジェットが発行する `/elasticsearch/search` (単数検索) と
        `/elasticsearch/msearch` (複数検索まとめ) のレスポンス JSON には
        `hits.hits[]._id` (msearch は `responses[].hits.hits[]._id`) として
        非難読化の record id が含まれるため、ここから収集する。
        """
        ids: set[str] = set()

        def _harvest(data: object) -> None:
            if not isinstance(data, dict):
                return
            hits = data.get("hits")
            if isinstance(hits, dict):
                for hit in hits.get("hits", []) or []:
                    if isinstance(hit, dict):
                        record_id = hit.get("_id")
                        if isinstance(record_id, str) and record_id:
                            ids.add(record_id)
                total = self._parse_hits_total(hits.get("total"))
                if total is not None:
                    # 複数の検索が飛ぶため、報告された最大件数を母数とみなす。
                    current = self._observed_total
                    self._observed_total = total if current is None else max(current, total)
            responses = data.get("responses")
            if isinstance(responses, list):
                for sub in responses:
                    _harvest(sub)

        def _on_response(response) -> None:  # type: ignore[no-untyped-def]
            if _ELASTICSEARCH_URL_HINT not in response.url:
                return
            try:
                data = response.json()
            except Exception:
                return
            _harvest(data)

        self._polite_wait(getattr(self.site_config, "request_interval", None))
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                try:
                    context = browser.new_context(user_agent=ONECO_USER_AGENT)
                    page = context.new_page()
                    page.on("response", _on_response)
                    page.goto(
                        self.site_config.list_url,
                        wait_until="networkidle",
                        timeout=self.PLAYWRIGHT_TIMEOUT_MS,
                    )
                    page.wait_for_timeout(2000)
                finally:
                    browser.close()
        except NetworkError:
            raise
        except Exception as e:
            raise NetworkError(
                f"Playwright 一覧取得失敗: {e}", url=self.site_config.list_url
            ) from e

        return sorted(ids)

    @staticmethod
    def _parse_hits_total(total: object) -> int | None:
        """`hits.total` を件数に正規化する

        elasticsearch は版によって `total: 29` と
        `total: {"value": 29, "relation": "eq"}` の両形式を返す。
        `relation` が `gte` (概算) の場合は母数として信用できないため無視する。
        """
        if isinstance(total, bool):
            return None
        if isinstance(total, int):
            return total
        if isinstance(total, dict):
            if total.get("relation") not in (None, "eq"):
                return None
            value = total.get("value")
            if isinstance(value, int) and not isinstance(value, bool):
                return value
        return None

    # ─────────────────── 詳細: フィールド抽出 ───────────────────

    def extract_animal_details(self, detail_url: str, category: str = "adoption") -> RawAnimalData:
        """detail ページ (deep link 単独ロード) から RawAnimalData を構築する"""
        html = self._http_get(detail_url)
        soup = BeautifulSoup(html, "html.parser")

        basic = self._extract_basic_info(soup)
        description = self._extract_description(soup)
        species = self._infer_species_from_guide_link(soup)
        shelter_date = self._extract_posted_date(soup)
        phone = self._normalize_phone(soup.get_text())
        image_urls = self._extract_images(soup, detail_url)

        has_any_field = any(
            [
                basic.get("management_number"),
                basic.get("location"),
                basic.get("breed"),
                basic.get("color"),
                basic.get("sex"),
                basic.get("age"),
                description,
                species,
                phone,
            ]
        )
        if not has_any_field and not image_urls:
            raise ParsingError(
                "detail ページから 1 フィールドも抽出できませんでした",
                url=detail_url,
            )

        try:
            return RawAnimalData(
                species=species,
                sex=basic.get("sex", ""),
                age=basic.get("age", ""),
                color=basic.get("color", ""),
                size="",
                shelter_date=shelter_date,
                location=basic.get("location", ""),
                phone=phone,
                image_urls=image_urls,
                source_url=detail_url,
                category=category,
                breed=basic.get("breed", ""),
                description=description,
                management_number=basic.get("management_number", ""),
            )
        except Exception as e:
            raise ParsingError(f"RawAnimalData バリデーション失敗: {e}", url=detail_url) from e

    # ─────────────────── 構造的抽出ヘルパー ───────────────────

    @staticmethod
    def _iter_leaf_texts(soup: BeautifulSoup):
        """`.bubble-element.Text` / `.bubble-element.HTML` の葉要素テキストを

        文書順に yield する。Bubble.io の内部クラス名 (ハッシュ) には依存せず、
        「他の bubble-element を子孫に持たない」という構造的性質だけで
        葉要素を判定する (エディタでの再配置によるクラス名変化に強い)。
        """
        for el in soup.select(".bubble-element.Text, .bubble-element.HTML"):
            if not isinstance(el, Tag):
                continue
            if el.find(class_="bubble-element") is not None:
                continue
            text = el.get_text(strip=True)
            if text:
                yield text

    def _extract_basic_info(self, soup: BeautifulSoup) -> dict[str, str]:
        """「基本情報」〜「特徴」見出しの間のテキスト群を各フィールドに分類する"""
        texts = list(self._iter_leaf_texts(soup))
        try:
            start = texts.index(_BASIC_INFO_HEADING)
        except ValueError:
            return {}
        try:
            end = texts.index(_FEATURE_HEADING, start + 1)
        except ValueError:
            end = len(texts)
        segment = texts[start + 1 : end]
        return self._classify_basic_info(segment)

    @staticmethod
    def _classify_basic_info(segment: list[str]) -> dict[str, str]:
        """基本情報ブロックの値を意味カテゴリへ分類する

        管理番号 ("No . xxx" 表記) / 場所 ("本所"/"支所" を含む) / 性別
        (オス・メス・不明の完全一致) / 年齢 (歳・ヶ月パターン) は
        キーワード/正規表現で確実に判定できるため、あいまいさを避けて
        個別に拾う。残った値 (品種・毛色はいずれも自由記述で区別する
        確実な手がかりが無い) は実測順 (品種 → 毛色) で割り当てる。
        品種/毛色の順序が入れ替わっても影響は両フィールドの取り違えに
        留まり、致命8フィールド (species/location/phone 等) には波及しない。
        """
        fields = {
            "management_number": "",
            "location": "",
            "sex": "",
            "age": "",
            "breed": "",
            "color": "",
        }
        remaining: list[str] = []
        for text in segment:
            if not fields["management_number"] and _MANAGEMENT_NO_PREFIX.match(text):
                fields["management_number"] = _MANAGEMENT_NO_PREFIX.sub("", text).strip()
            elif not fields["location"] and any(kw in text for kw in _LOCATION_KEYWORDS):
                fields["location"] = text
            elif not fields["sex"] and text in _SEX_VALUES:
                fields["sex"] = text
            elif not fields["age"] and _AGE_PATTERN.search(text):
                fields["age"] = text
            else:
                remaining.append(text)

        if remaining:
            fields["breed"] = remaining[0]
        if len(remaining) > 1:
            fields["color"] = remaining[1]
        return fields

    def _extract_description(self, soup: BeautifulSoup) -> str:
        """「特徴」見出し直後のテキストを性格・特徴の自由記述として取得する"""
        texts = list(self._iter_leaf_texts(soup))
        try:
            idx = texts.index(_FEATURE_HEADING)
        except ValueError:
            return ""
        if idx + 1 < len(texts):
            return texts[idx + 1]
        return ""

    @staticmethod
    def _infer_species_from_guide_link(soup: BeautifulSoup) -> str:
        """「(犬|猫)の飼い方講習会へ」リンク文言から動物種別を判定する

        サイトのラベルには「種類」欄が無く、品種テキスト ("雑種" 等) も
        犬/猫どちらの表記か判別できないため、個体の種別に応じて
        出し分けられるこのリンク文言を一次情報として採用する。
        マッチしない場合は空文字 (normalize 側で "その他" 扱い)。
        """
        m = _GUIDE_LINK_PATTERN.search(soup.get_text())
        return m.group(1) if m else ""

    @staticmethod
    def _extract_posted_date(soup: BeautifulSoup) -> str:
        """「掲載日：YYYY/MM/DD」から日付部分のみを取り出す

        サイトには「収容日」に相当する項目が存在しないため、掲載日を
        shelter_date の代替値として使う。取得できない場合は空文字を返し、
        DataNormalizer 側の「データ取得日」フォールバックに委ねる。
        """
        m = _POSTED_DATE_PATTERN.search(soup.get_text())
        return m.group(1) if m else ""

    def _filter_image_urls(self, urls: list[str], base_url: str) -> list[str]:
        """cdn-cgi リサイズ違いの同一画像を Bubble ファイル id で重複除去する

        同一写真が異なる解像度パラメータ (`cdn-cgi/image/w=...`) で
        カルーセル本体・サムネイルナビの双方に出現するため、
        `/f<数字>x<数字>/` というファイル id 部分をキーに最初の 1 件
        (実測では最大解像度版が先に現れる) だけを残す。
        """
        seen_ids: set[str] = set()
        filtered: list[str] = []
        for u in urls:
            if u.startswith("data:"):
                continue
            m = _BUBBLE_FILE_ID_PATTERN.search(u)
            key = m.group(1) if m else u
            if key in seen_ids:
                continue
            seen_ids.add(key)
            filtered.append(u)
        return filtered if filtered else urls


# ─────────────────── サイト登録 ───────────────────
# sites.yaml の `name` フィールドと完全一致する 1 サイト名で登録する。
_SITE_NAME = "愛知県わんにゃんナビ"
if SiteAdapterRegistry.get(_SITE_NAME) is None:
    SiteAdapterRegistry.register(_SITE_NAME, WannyanNaviAichiAdapter)
