"""長崎市動物愛護管理センター rule-based adapter

対象ドメイン: https://www.city.nagasaki.lg.jp/site/doubutsuaigo/

**このサイトからは個体を取得できない** (2026-08-05 確認・W001/T021)

犬里親募集 (list7-19.html) / 猫里親募集 (list7-18.html) の 2 ページは、
どちらも個体一覧を持たない。本文 `div#main_body` にあるのは新着情報
(`div.info_list_wrap > div.info_list > ul > li > div.list_pack`) という
**お知らせ記事へのリンク**だけで、リンク先も個体ではなく見学案内である:

- 犬 (2794.html): 「常時募集中ですのでご希望の方はご連絡のうえ随時見学に」。
  迷子情報は X (旧 Twitter) に掲載、引き取り犬は「公開準備中」
- 猫 (4368.html): 掲載写真に「動物愛護管理センターの猫たち
  （現在収容中の猫とは異なります）」と明記

旧実装はこの `list_pack` を 1 動物として扱い、記事タイトル
「引き取り犬（保護犬）の見学　受付中」「猫の里親　募集中　見学できます」を
location とする**実在しない個体**を公開していた。本番 DB の長崎市由来 2 件は
どちらもこの架空個体で、2026-08-05 の掲載監査 (W001/T004) で発見した。

記事タイトルが個体を指すか否かで判定する方式は採らない。「里親募集中の
ミックス犬」のようなタイトルでも実体は案内記事であり、性別・毛色・収容日を
持たないため個体として成立しないからである。

サイト側が個体を掲載し始めたら構造を見て書き直す。それまではページの生存
確認だけ行って 0 件を返し、ゼロ件監視 (W002) の対象として残す。名古屋市の
譲渡犬・譲渡猫 (W001/T017) と同じ「取得不能」の扱い。
"""

from __future__ import annotations

from typing import ClassVar

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter


class CityNagasakiLgAdapter(SinglePageTableAdapter):
    """長崎市動物愛護管理センター用 adapter (常に 0 件)

    個体一覧が存在しないため収集対象は無い。サイト定義を残しているのは、
    掲載が始まったときにゼロ件監視で気づけるようにするため。
    """

    # 基底が非空の ROW_SELECTOR を要求するため宣言は残すが、この adapter は
    # 行を読まない。旧実装がここで拾っていたのが新着情報の記事 (= 架空個体の
    # 発生源) で、値そのものが「何を個体と誤認していたか」の記録になっている。
    ROW_SELECTOR: ClassVar[str] = "div.info_list_wrap div.list_pack"
    SKIP_FIRST_ROW: ClassVar[bool] = False
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {}
    LOCATION_COLUMN: ClassVar[int | None] = None
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    # ─────────────────── オーバーライド ───────────────────

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """常に 0 件を返す (このサイトは個体を掲載していない)

        ページの取得自体は行う。URL 消滅やサイト障害はここで HTTP エラーに
        なり、収集ログと `broken_sites.yaml` に残る。
        """
        self._http_get(self.site_config.list_url)
        return []

    def extract_animal_details(self, virtual_url: str, category: str = "adoption") -> RawAnimalData:
        """呼ばれない経路 (`fetch_animal_list` が常に空を返すため)

        誤って呼ばれたときに架空個体を作らないよう、明示的に失敗させる。
        """
        raise ParsingError(
            "長崎市のサイトは個体を掲載していないため詳細取得は行わない",
            url=virtual_url,
        )

    # ─────────────────── ヘルパー ───────────────────

    @staticmethod
    def _infer_species_from_site_name(name: str) -> str:
        """サイト名から動物種別 (犬/猫/その他) を推定する

        現状は使われないが、サイトが個体を載せ始めたときに再利用する。
        HTML には種別が明示されないため、判別はサイト名に依存する。
        """
        if "犬" in name:
            return "犬"
        if "猫" in name:
            return "猫"
        return "その他"


# ─────────────────── サイト登録 ───────────────────
# 同一テンプレート上で運用される 2 サイトを同一 adapter にマップする。
# `sites.yaml` の `prefecture: 長崎県` かつ `city.nagasaki.lg.jp` ドメイン。
for _site_name in (
    "長崎市動物愛護管理センター（犬里親募集）",
    "長崎市動物愛護管理センター（猫里親募集）",
):
    if SiteAdapterRegistry.get(_site_name) is None:
        SiteAdapterRegistry.register(_site_name, CityNagasakiLgAdapter)
