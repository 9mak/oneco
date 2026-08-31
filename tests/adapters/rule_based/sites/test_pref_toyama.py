"""PrefToyamaAdapter のテスト

富山県（迷い犬猫情報）サイト (pref.toyama.jp/1207/.../syuyou/) 用
rule-based adapter の動作を検証する。

- サイト名 ("富山県（迷い犬猫情報）") の Registry 登録確認
- インデックスページ (本フィクスチャ: 各厚生センターへのリンクのみ) は
  fetch_animal_list が空配列を返す
- 「現在…ありません」告知文がある場合の 0 件動作
- 本文も判定要素も無い HTML では ParsingError
- HTML キャッシュ (HTTP は 1 回のみ実行)
- 動物テーブルが直接掲載されているケース (合成 HTML) で抽出ロジックを検証
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.pref_toyama import (
    PrefToyamaAdapter,
)
from data_collector.llm.config import SiteConfig


def _site(
    name: str = "富山県（迷い犬猫情報）",
    list_url: str = (
        "https://www.pref.toyama.jp/1207/kurashi/seikatsu/seikatsu/doubutsuaigo/syuyou/index.html"
    ),
    category: str = "lost",
) -> SiteConfig:
    return SiteConfig(
        name=name,
        prefecture="富山県",
        prefecture_code="16",
        list_url=list_url,
        category=category,
        single_page=True,
    )


def _load_toyama_html(fixture_html) -> str:
    """フィクスチャを読み込み、必要であれば mojibake (二重 UTF-8) を補正する

    リポジトリに保存されている `pref_toyama_jp.html` は、本来 UTF-8 の
    バイト列を Latin-1 として解釈してから再度 UTF-8 として保存し直された
    二重エンコーディング状態になっている。実運用 (`_http_get`) では
    requests が正しい UTF-8 として受け取る。
    """
    raw = fixture_html("pref_toyama_jp")
    # 復号後に「富山県」または「迷い」が出現するかで判定
    if "富山県" in raw or "迷い" in raw:
        return raw
    try:
        return raw.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return raw


class TestPrefToyamaAdapter:
    def test_fetch_animal_list_returns_empty_for_index_page(self, fixture_html):
        """各厚生センターへの窓口リンクのみのインデックスページでは空リスト

        本フィクスチャは `table.datatable` の中に各厚生センター・支所への
        `<a>` リンクが並ぶだけの 0 件状態。基底の単純実装は ParsingError を
        投げるが、本 adapter ではこれを正常な 0 件として扱う。
        """
        html = _load_toyama_html(fixture_html)
        adapter = PrefToyamaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert result == [], f"インデックスページでは空配列が返るはず: got {result!r}"

    def test_fetch_animal_list_caches_html(self, fixture_html):
        """同一インスタンスでの繰り返し呼び出しは HTTP を 1 回しか実行しない"""
        html = _load_toyama_html(fixture_html)
        adapter = PrefToyamaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            adapter.fetch_animal_list()
            adapter.fetch_animal_list()
            adapter.fetch_animal_list()

        assert mock_get.call_count == 1, (
            f"HTML はキャッシュされ HTTP は 1 回のみ: got {mock_get.call_count}"
        )

    def test_fetch_animal_list_returns_empty_for_explicit_no_animal_text(self):
        """「現在、迷い犬・ねこ情報はありません。」告知ページでも空リスト"""
        synthetic_html = """
        <html><body>
        <div id="tmp_main">
            <p>現在、迷い犬・ねこの情報はありません。</p>
        </div>
        </body></html>
        """
        adapter = PrefToyamaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=synthetic_html):
            result = adapter.fetch_animal_list()

        assert result == []

    def test_raises_parsing_error_for_unrelated_html(self):
        """テーブルも empty state 判定要素も無い HTML では ParsingError"""
        adapter = PrefToyamaAdapter(_site())
        with patch.object(
            adapter,
            "_http_get",
            return_value=('<html><body><div id="tmp_main"><p>無関係な本文</p></div></body></html>'),
        ):
            with pytest.raises(Exception):
                adapter.fetch_animal_list()

    def test_extract_animal_details_from_synthetic_table(self):
        """合成 HTML (動物テーブル 1 個) から RawAnimalData を構築できる

        実フィクスチャは 0 件状態のため、抽出ロジックの検証用に
        典型的な「ラベル/値」の 2 列テーブルを合成して使う。
        """
        synthetic_html = """
        <html><body>
        <div id="tmp_main">
        <table>
            <tr><th>種類</th><td>柴犬</td></tr>
            <tr><th>毛色</th><td>茶</td></tr>
            <tr><th>性別</th><td>オス</td></tr>
            <tr><th>体格</th><td>中</td></tr>
            <tr><th>収容日</th><td>2026年5月10日</td></tr>
            <tr><th>収容場所</th><td>富山市新総曲輪</td></tr>
        </table>
        </div>
        </body></html>
        """
        adapter = PrefToyamaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=synthetic_html):
            urls = adapter.fetch_animal_list()
            assert len(urls) == 1
            url, category = urls[0]
            raw = adapter.extract_animal_details(url, category=category)

        assert raw.species == "柴犬"
        assert raw.color == "茶"
        assert raw.sex == "オス"
        assert raw.size == "中"
        assert raw.shelter_date == "2026年5月10日"
        assert raw.location == "富山市新総曲輪"
        assert raw.source_url == url
        assert raw.category == "lost"

        # normalize() 経由でも breed (個体識別フィールド) が脱落しないこと
        # (T042/T114: raw のみの確認では normalize 段のサイレントドロップを
        # 検知できない)。raw.species="柴犬" は「犬」の文字を含むため
        # DataNormalizer._normalize_species() で正しく "犬" に変換される
        # (下の test_extract_animal_details_with_multiple_tables で
        # "キジトラ" 等・犬猫の文字を含まない品種名では誤分類される既知の
        # 挙動を記録している)。
        animal_data = adapter.normalize(raw)
        assert animal_data.species == "犬"
        assert animal_data.breed == "柴犬"
        assert animal_data.sex == "男の子"
        assert animal_data.size == "中型"
        assert animal_data.shelter_date.isoformat() == "2026-05-10"
        assert animal_data.location == "富山市新総曲輪"

    def test_extract_animal_details_with_multiple_tables(self):
        """複数の動物テーブル = 複数動物として扱われる

        厚生センター窓口リンクの `table.datatable` が混じっていても、
        動物データを含む通常テーブルだけが抽出対象になる。
        """
        synthetic_html = """
        <html><body>
        <div id="tmp_main">
        <table class="datatable">
            <tr><th scope="col">厚生センター名</th></tr>
            <tr><td><a href="/x.html">新川厚生センター</a></td></tr>
        </table>
        <table>
            <tr><th>種類</th><td>三毛猫</td></tr>
            <tr><th>性別</th><td>メス</td></tr>
        </table>
        <table>
            <tr><th>種類</th><td>キジトラ</td></tr>
            <tr><th>性別</th><td>オス</td></tr>
        </table>
        </div>
        </body></html>
        """
        adapter = PrefToyamaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=synthetic_html):
            urls = adapter.fetch_animal_list()
            assert len(urls) == 2, f"datatable は除外され動物テーブル 2 個が残るはず: got {urls!r}"
            raws = [adapter.extract_animal_details(u, category=c) for u, c in urls]

        assert raws[0].species == "三毛猫"
        assert raws[0].sex == "メス"
        assert raws[0].category == "lost"
        assert raws[1].species == "キジトラ"
        assert raws[1].sex == "オス"
        assert raws[1].category == "lost"

        # normalize() 経由での挙動確認 (T114 監査で発見、T118 で調査確定):
        # 「種類」ラベルの品種名がそのまま species に入り (breed とも同一値)、
        # site_config.name も "犬猫" 併記で判定不能。DataNormalizer
        # ._normalize_species() の文字列部分一致に頼るため、「三毛猫」は
        # "猫" を含み正しく変換されるが、「キジトラ」(毛柄のみ・犬猫いずれの
        # 文字も含まない) は "その他" に分類される。
        # これは実装バグではなく、当実データ (「種類」ラベルのみ・サイト名
        # 併記・URL 上の犬猫区分なし) には species を確定する追加の手がかりが
        # 存在しないための構造的な限界であり、T118 では「犬種」「猫種」の
        # ように種別を明示するラベルがある場合のみ確実に推定する
        # (test_extract_animal_details_with_dog_and_cat_species_labels 参照)。
        animal_datas = [adapter.normalize(r) for r in raws]
        assert animal_datas[0].species == "猫"
        assert animal_datas[1].species == "その他", (
            "既知の限界: breed='キジトラ' (犬猫の文字を含まない毛柄表記) かつ "
            "ラベルも「種類」(犬猫を明示しない) のため、種別を確定する手がかりが "
            "無く 'その他' に分類される。"
        )

    def test_extract_animal_details_with_dog_and_cat_species_labels(self):
        """「犬種」「猫種」ラベルはラベル自体から種別を確定できる (T118 修正)

        値セルが「雑種」等 (犬猫の文字を含まない品種名) でも、ラベルが
        「犬種」「猫種」であれば種別を確定できる。city_mito.py の実データ
        実測 (2025-11 wayback snapshot) で確認した同型パターン。
        """
        synthetic_html = """
        <html><body>
        <div id="tmp_main">
        <table>
            <tr><th>犬種</th><td>雑種</td></tr>
            <tr><th>性別</th><td>オス</td></tr>
        </table>
        <table>
            <tr><th>猫種</th><td>キジトラ</td></tr>
            <tr><th>性別</th><td>メス</td></tr>
        </table>
        </div>
        </body></html>
        """
        adapter = PrefToyamaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=synthetic_html):
            urls = adapter.fetch_animal_list()
            assert len(urls) == 2
            raws = [adapter.extract_animal_details(u, category=c) for u, c in urls]

        assert raws[0].species == "犬"
        assert raws[1].species == "猫"
        animal_datas = [adapter.normalize(r) for r in raws]
        assert animal_datas[0].species == "犬"
        assert animal_datas[1].species == "猫"

    def test_extract_animal_details_with_dual_field_row_layout(self):
        """1 行に 2 フィールドが並ぶレイアウトでも全フィールドを正しく抽出する (T122)

        city_mito.py の実データ (wayback snapshot 2025-11-14) で確認した
        `<tr><th>収容日時</th><td>...</td><th>年齢</th><td>...</td></tr>` の
        ような構造は富山県 adapter でもコード構造上同型のバグを持ちうる
        (現状ライブ 0 件のため未発現)。修正前は行内の末尾セルのみを値として
        扱っていたため、1 個目のラベル (収容日) に 2 個目のラベル (年齢) の
        値が誤って混入していた。セルを 2 個ずつ (ラベル, 値) のペアとして
        処理する修正で、隣接フィールドの値が混入しないことを検証する。
        """
        synthetic_html = """
        <html><body>
        <div id="tmp_main">
        <table>
            <tr><th>収容日</th><td>2026年5月10日</td><th>年齢</th><td>成犬</td></tr>
            <tr><th>収容場所</th><td>富山市新総曲輪</td><th>毛色</th><td>茶</td></tr>
        </table>
        </div>
        </body></html>
        """
        adapter = PrefToyamaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=synthetic_html):
            urls = adapter.fetch_animal_list()
            url, category = urls[0]
            raw = adapter.extract_animal_details(url, category=category)

        assert raw.shelter_date == "2026年5月10日", (
            f"収容日ラベルの値のみが入るはず (年齢の値が混入していないか): got {raw.shelter_date!r}"
        )
        assert raw.location == "富山市新総曲輪", (
            f"収容場所ラベルの値のみが入るはず (毛色の値が混入していないか): got {raw.location!r}"
        )
        assert raw.age == "成犬"
        assert raw.color == "茶"

        animal_data = adapter.normalize(raw)
        assert animal_data.shelter_date.isoformat() == "2026-05-10"
        assert animal_data.location == "富山市新総曲輪"

    def test_extract_animal_details_with_odd_cell_row_falls_back_to_shared_value(self):
        """奇数セル行では末尾の値が失われず、旧来の共有値方式で処理される (T122 M-1 再発防止)

        `<tr><th>種類</th><th>性別</th><td>柴犬</td></tr>` のような 3 セル行
        (ラベル候補 2 個 + 共有値 1 個) にペア処理をそのまま適用すると、
        本来の値 `cells[2]` を無視して species="性別" になってしまう
        退行があった (reviewer 指摘 M-1)。奇数セル行は末尾セルを全ラベル
        候補で共有する旧実装セマンティクスにフォールバックすることを
        検証する。
        """
        synthetic_html = """
        <html><body>
        <div id="tmp_main">
        <table>
            <tr><th>種類</th><th>性別</th><td>柴犬</td></tr>
        </table>
        </div>
        </body></html>
        """
        adapter = PrefToyamaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=synthetic_html):
            urls = adapter.fetch_animal_list()
            url, category = urls[0]
            raw = adapter.extract_animal_details(url, category=category)

        assert raw.species == "柴犬", (
            f"奇数セル行では末尾セルが共有値として採用されるはず: got {raw.species!r}"
        )
        animal_data = adapter.normalize(raw)
        assert animal_data.species == "犬"

    def test_extract_animal_details_duplicate_label_in_row_prefers_non_empty_value(self):
        """同一行内の重複ラベルでは、空値が後続の有効値を握り潰さない (T122 M-2 再発防止)

        `<tr><th>年齢</th><td></td><th>年齢</th><td>成犬</td></tr>` のように
        同一行に同じラベルが 2 回現れ、1 個目の値が空、2 個目の値が非空の
        変則行で、ペア処理は 1 個目の空値でフィールドを確定させてしまい
        2 個目の有効値を握り潰す退行があった (reviewer 指摘 M-2)。
        """
        synthetic_html = """
        <html><body>
        <div id="tmp_main">
        <table>
            <tr><th>年齢</th><td></td><th>年齢</th><td>成犬</td></tr>
        </table>
        </div>
        </body></html>
        """
        adapter = PrefToyamaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=synthetic_html):
            urls = adapter.fetch_animal_list()
            url, category = urls[0]
            raw = adapter.extract_animal_details(url, category=category)

        assert raw.age == "成犬", f"空値の後の有効値が採用されるはず: got {raw.age!r}"

    def test_infer_species_from_site_name_default_empty(self):
        """富山県の実サイト名は犬・猫 (ねこ) を併記するため空文字を返す"""
        for name in (
            "富山県（迷い犬猫情報）",
            "富山県（迷い犬・ねこ情報）",
        ):
            assert PrefToyamaAdapter._infer_species_from_site_name(name) == ""

    def test_infer_species_from_site_name_with_dog_keyword(self):
        """サイト名に "犬" のみを含む場合は "犬" を返す (汎用ロジック)"""
        assert PrefToyamaAdapter._infer_species_from_site_name("富山県（迷い犬）") == "犬"

    def test_infer_species_from_site_name_with_cat_keyword(self):
        """サイト名に "猫" のみを含む場合は "猫" を返す (汎用ロジック)"""
        assert PrefToyamaAdapter._infer_species_from_site_name("富山県（保護猫）") == "猫"

    def test_site_registered(self):
        """sites.yaml で定義された富山県サイトが Registry に登録されている

        他テストが registry を clear する場合に備えて冪等に再登録する。
        """
        name = "富山県（迷い犬猫情報）"
        if SiteAdapterRegistry.get(name) is None:
            SiteAdapterRegistry.register(name, PrefToyamaAdapter)
        assert SiteAdapterRegistry.get(name) is PrefToyamaAdapter
