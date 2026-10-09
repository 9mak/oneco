"""2026-10-05 監査（F6）で直したレシピ 8 枚が、実ページ（10/5）の構造から項目を行末まで・分かれた段落まで取れること（ネットワークなし）。

HTML は 10/5 の実ページから 1〜2 頭分だけ抜いたもの。レシピ本体 v2/recipes/<slug>.yaml をそのまま読む。
"""

from pathlib import Path

from bs4 import BeautifulSoup
from collector.extract import build
from collector.recipe import Doc, Recipe
from collector.registry import Source, load_sources

ROOT = Path(__file__).resolve().parent.parent


def _source(slug: str) -> Source:
    return next(s for s in load_sources(ROOT / "registry" / "sources.yaml") if s.slug == slug)


def _run(slug: str, html: str):
    src = _source(slug)
    recipe = Recipe.load(ROOT / "recipes" / f"{slug}.yaml")
    doc = Doc(url=src.url, html=html, soup=BeautifulSoup(html, "lxml"))
    return build(src, recipe, [doc])


def test_machida_1_color_keeps_words_after_ideographic_space():
    html = """<html><body><h2>現在のペットの保護情報</h2>
    <div class="h3bg"><h3>猫（おす）</h3></div>
    <div class="img-area-r"><p class="imglink-txt-right"><img src="hogo.images/251202hogoneko.jpg"><span>猫</span></p>
    <ul><li>種類：雑種</li><li>性別：おす</li><li>毛色：キジトラ　ハチワレ　白ベース</li><li>首輪：なし</li>
    <li>特徴：右耳桜耳、左耳が切れている</li><li>保護場所：町田市忠生一丁目</li><li>保護日：2025年11月21日</li></ul></div>
    <div class="h3bg"><h3>猫(おす)</h3></div>
    <div class="img-area-r"><p class="imglink-txt-right"><img src="hogo.images/250929hogoneko1.jpg"><span>猫</span></p>
    <ul><li>種類：雑種</li><li>性別：おす</li><li>毛色：キジトラ</li><li>首輪：なし</li>
    <li>特徴：長毛、人懐こい</li><li>保護場所：町田市図師2000番台</li><li>保護日：2025年9月25日</li></ul></div></body></html>"""
    res = _run("city_machida-1", html)
    assert [a["color"] for a in res.animals] == ["キジトラ ハチワレ 白ベース", "キジトラ"]
    assert [a["note"] for a in res.animals] == ["右耳桜耳、左耳が切れている", "長毛、人懐こい"]


def test_mito_1_note_keeps_words_after_space():
    def table(no: str, note: str) -> str:
        return (f"<table><tr><th>管理番号</th><td>{no}</td></tr><tr><th>写真</th><td>掲載予定</td></tr>"
                "<tr><th>保護日</th><td>令和8年9月22日</td></tr><tr><th>保護場所</th><td>水戸市西原</td></tr>"
                "<tr><th>動物</th><td>猫</td></tr><tr><th>種類</th><td>雑種</td></tr><tr><th>毛色</th><td>白</td></tr>"
                f"<tr><th>性別</th><td>オス</td></tr><tr><th>首輪</th><td>無し</td></tr><tr><th>特徴</th><td>{note}</td></tr></table>")

    html = f'<html><body><div id="main_body">{table("保護309", "額に黒ブチ カギシッポ 人懐こい")}{table("保護307", "")}</div></body></html>'
    res = _run("city_mito-1", html)
    by_no = {a["management_no"]: a for a in res.animals}
    assert by_no["保護309"]["note"] == "額に黒ブチ カギシッポ 人懐こい"
    assert by_no["保護307"].get("note") is None          # 特徴が空の子に次の語を付けない


def test_iwate_kamaishi_note_follows_into_the_next_paragraph():
    html = """<html><body><h2>【譲渡】新しい飼い主さんを募集しています</h2>
    <figure class="imagecenter"><img src="umi1.png"><figcaption>2026-7-008C</figcaption></figure>
    <p>仮名：海（うみ）ちゃん<br>管理番号：2026-7-008C<br>動物種別：猫<br>大きさ：小<br>種類：雑種<br>性別：メス<br>毛色：三毛</p>
    <p>性格等：保護されたときは痩せていて、汚れていましたが、すっかり美猫さんに！</p>
    <p>最初は小さいながらもシャーシャー言っていましたが、だいぶ人懐っこくなりました</p>
    <p>不妊去勢手術：未 三種混合ワクチン：済</p>
    <figure class="imageright"><img src="umi2.jpg"><figcaption>カメラを向けると</figcaption></figure>
    <h2>【譲渡】新しい飼い主さんを募集しています</h2>
    <figure class="imagecenter"><img src="onikisu.jpg"><figcaption>2025-6-014C</figcaption></figure>
    <p>仮名：オニキスちゃん 管理番号：2025-6-014C 動物種別：猫 大きさ：中 種類：雑種 性別：メス 毛色：黒 性格等：少し臆病なところがありますが、徐々に慣れてきました。 不妊去勢手術：済 三種混合ワクチン：済</p>
    </body></html>"""
    res = _run("pref_iwate_kamaishi", html)
    umi, oni = res.animals
    assert umi["note"] == "保護されたときは痩せていて、汚れていましたが、すっかり美猫さんに! 最初は小さいながらもシャーシャー言っていましたが、だいぶ人懐っこくなりました"
    assert oni["note"] == "少し臆病なところがありますが、徐々に慣れてきました。"          # 次の項目（不妊去勢手術）の手前で止まる
    assert umi["image_url"].endswith("/umi1.png") and oni["image_url"].endswith("/onikisu.jpg")


def test_iwate_kennan_management_no_in_a_separate_paragraph():
    html = """<html><body><h2>新しい飼い主さんを募集しています</h2>
    <p class="imageleft"><img src="20260730.jpg"></p>
    <p>名前：カテリーナ<br>動物種：猫<br>種類：雑種<br>性別：オス<br>毛色：白と茶<br>大きさ：中<br>推定年齢：2才<br>特徴：おとなしい（慣らし中）</p>
    <p>その他：FIV（＋）/FeLV（－）</p>
    <p>管理番号：26023</p>
    <p class="imageleft"><img src="2026.7.24.jpg"></p>
    <p>名前：キャンディ<br>動物種：猫<br>種類：雑種<br>性別：オス<br>毛色：白黒<br>大きさ：中型<br>推定年齢：5才位<br>特徴：人懐こい<br>その他：FIV(＋)/FeLV(−)<br>管理番号：24035</p>
    <h2>関連情報</h2></body></html>"""
    res = _run("pref_iwate_kennan", html)
    cat, candy = res.animals
    assert (cat["name"], cat["management_no"], cat["note"]) == ("カテリーナ", "26023", "おとなしい(慣らし中)")
    assert cat["image_url"].endswith("/20260730.jpg")
    assert (candy["name"], candy["management_no"]) == ("キャンディ", "24035") and candy["image_url"].endswith("/2026.7.24.jpg")


def test_nagano_2_splits_breed_and_color_in_parentheses():
    html = """<html><body><div class="section"><h2>飼い主募集中の猫の詳細</h2>
    <h3>2026-304</h3><p><img src="304.jpg"></p><p>種類：ミックス（白灰）</p><p>性別：オス</p><p>生年月：2024年7月頃生まれ</p>
    <h3>2026-310</h3><p><img src="310.jpg"></p><p>種類：雑種</p><p>性別：メス</p><p>生年月：2025年1月頃生まれ</p></div></body></html>"""
    res = _run("nagano_hello_animal-2", html)
    a, b = res.animals
    assert (a["breed"], a.get("color")) == ("ミックス", "白灰")
    assert (b["breed"], b.get("color")) == ("雑種", None)         # 括弧が無ければ毛色は空


def _yokosuka(slug: str, rows: list[tuple[str, str]]):
    body = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in rows)
    return _run(slug, f'<html><body><div id="photos"><img src="a.jpg"></div><table>{body}</table></body></html>')


def test_yokosuka_1_and_2_age_and_note_from_the_feature_cell():
    base = [("整理番号", "26-210"), ("分類", "犬(保護収容)"), ("収容日", "R8.9.17（木曜日）"), ("収容場所", "本町"), ("種類", "秋田犬"), ("性別", "メス")]
    dog = _yokosuka("yokosuka_doubutu-1", base + [("特徴", "虎毛、推定1歳"), ("首輪", "無"), ("負傷", "無")]).animals[0]
    assert (dog["color"], dog["age"], dog["note"]) == ("虎毛", "1歳", "虎毛、推定1歳")
    base[0] = ("整理番号", "26-209")
    cat = _yokosuka("yokosuka_doubutu-2", base + [("特徴", "サバ猫、推定２か月齢"), ("首輪", "無"), ("負傷", "有")]).animals[0]
    assert (cat["color"], cat["age"], cat["note"]) == ("サバ猫", "2か月齢", "サバ猫、推定2か月齢")


def test_yokosuka_5_name_from_the_feature_text():
    rows = [("整理番号", "26-111"), ("分類", "猫(譲渡)"), ("種類", "MIX"), ("性別", "オス")]
    for text, name in (("推定4歳の男の子、名前はかぶと（仮）です。完全な人間不信でした。", "かぶと"),
                       ("推定4歳オス、名前はち(仮)去勢手術済みです。", "ち"),
                       ("推定4歳。名前とんぼ(仮)です。少しずつ人に馴れてきて。", "とんぼ")):
        a = _yokosuka("yokosuka_doubutu-5", rows + [("特徴", text)]).animals[0]
        assert a["name"] == name
    plain = _yokosuka("yokosuka_doubutu-5", rows + [("特徴", "年齢不明(推定8歳)、不妊手術済。人馴れしています。")]).animals[0]
    assert plain.get("name") is None                                 # 名前の記載が無い子に名前を作らない
