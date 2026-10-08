"""T519 グループ 6（堺市・吹田市・寝屋川市・八尾市・西宮市）の台帳とレシピのテスト（ネットワークなし）。

2026-10-05 に実ページから抜いた HTML を直書きしている。動物が載った日の作りが未確認の自治体（堺・吹田・寝屋川・八尾・
西宮の迷子）は、「0 頭の日を 0 頭と読む」「案内文や飾り画像を偽の 1 頭にしない」ことだけを確かめる。
"""

from collector.extract import Result, build
from collector.fetch import FakeFetcher
from collector.recipe import Executor, Recipe
from collector.registry import Source, load_sources


def _load(slug: str) -> tuple[Source, Recipe]:
    src = next(s for s in load_sources() if s.slug == slug)
    recipe = Recipe.load(src.recipe_path)
    recipe.encoding = None
    return src, recipe


def _run(slug: str, pages: dict[str, str]) -> tuple[Source, Result]:
    src, recipe = _load(slug)
    ex = Executor(FakeFetcher(pages), recipe)
    docs = ex.resolve(src.url)
    return src, build(src, recipe, docs, ex.visited)


# --- 堺市 ---------------------------------------------------------------------------------
SAKAI_TOP = "https://www.eonet.ne.jp/~sakai-doshi/"
SAKAI_MENU = "https://www.eonet.ne.jp/~sakai-doshi/html/menu.html"
SAKAI_TOP_HTML = ('<html><body><p>堺市保護収容動物情報</p><p>ご注意 掲載期間は収容日を含む 4 日間</p>'
                  '<a href="html/menu.html">堺市の保護動物収容情報はこちら</a></body></html>')
SAKAI_EMPTY = """<html><body><table><tr><td><p align="right">動物情報</p></td></tr></table><hr>
<table><tr><td><div><h1><font>現在、
保護・収容動物情報は</font></h1><h1><font>ありません。</font></h1>
<p>※ここに情報がなくても、市民の方や警察署から、保護している動物の情報が寄せられていることがあります。</p></div></td></tr></table>
<table><tr><td><h1><img src="../images/d_pic1.gif" width="200" height="149"></h1><p>人と動物が共存するうるおいのある社会へ</p></td></tr></table>
<table><tr><td><a href="https://www.eonet.ne.jp/~sakai-doshi/">堺市保護収容動物情報へ</a><img src="../images/return.gif"></td></tr></table></body></html>"""


def test_sakai_entry():
    src, _ = _load("eonet_sakai-1")
    assert (src.kind, src.species, src.mode, src.url) == ("stray", "mixed", "recipe", SAKAI_TOP)
    assert src.phone == "072-228-0168" and src.prefecture == "大阪府"


def test_sakai_zero_day_is_empty_not_a_fake_animal():
    """0 頭の日の menu.html には飾り画像（d_pic1.gif・return.gif）だけの表がある。それを 1 頭にしない。"""
    _, res = _run("eonet_sakai-1", {SAKAI_TOP: SAKAI_TOP_HTML, SAKAI_MENU: SAKAI_EMPTY})
    assert res.animals == [] and res.empty_confirmed is True


def test_sakai_unknown_layout_is_not_confirmed_empty():
    """一覧の作りが変わって 0 頭の文言も無い日は「0 頭」と確定させない（読めなかった扱い）。"""
    changed = "<html><body><table><tr><td><img src='a.gif'><p>お知らせ</p></td></tr></table></body></html>"
    _, res = _run("eonet_sakai-1", {SAKAI_TOP: SAKAI_TOP_HTML, SAKAI_MENU: changed})
    assert res.animals == [] and res.empty_confirmed is not True


# --- 吹田市 -------------------------------------------------------------------------------
SUITA = "https://www.city.suita.osaka.jp/kurashi/1018501/1018506/1022049.html"
SUITA_EMPTY = """<html><body><div id="voice"><h1>動物保護情報</h1><div class="box"><p class="update">更新日 2026年9月14日</p></div>
<p>現在、吹田市保健所に保護されている動物の情報をご覧いただけます。<br>この情報は、本来の飼い主を探す目的で掲載しています。</p><h2>保護している動物</h2>
<p>現在保護情報はありません。</p>
<ul>
</ul><h2>返還について</h2>
<p>1．返還を行う場所</p>
<ul>
<li>吹田市出口町19番3号</li>
<li>健康医療部衛生管理課（吹田市保健所内）</li>
</ul>
<p>2．返還の際に必要なもの</p>
<ul>
<li>返還手数料　3,900円</li>
<li>飼養管理費　1日当たり250円</li>
<li>キャリーケース</li>
</ul></div></body></html>"""


def test_suita_entry():
    src, _ = _load("city_suita-1")
    assert (src.kind, src.species, src.url) == ("stray", "mixed", SUITA)
    assert src.phone == "06-6339-2226"


def test_suita_zero_day_is_empty_and_return_notes_are_not_animals():
    """0 頭の日に「返還について」の li（返還を行う場所・手数料）を動物にしない。"""
    _, res = _run("city_suita-1", {SUITA: SUITA_EMPTY})
    assert res.animals == [] and res.empty_confirmed is True


def test_suita_unknown_layout_is_not_confirmed_empty():
    changed = SUITA_EMPTY.replace("現在保護情報はありません。", "ただいま準備中です。")
    _, res = _run("city_suita-1", {SUITA: changed})
    assert res.animals == [] and res.empty_confirmed is not True


# --- 寝屋川市 -----------------------------------------------------------------------------
NEYAGAWA = "https://www.city.neyagawa.osaka.jp/kurashi/eisei_doubutsu/inuneko_kankei/13558.html"
NEYAGAWA_EMPTY = """<html><body><div class="wysiwyg"><p>このページの情報は、行方不明になった犬及び猫を捜している飼い主の方に向けてのものです。希望者への譲渡を目的としたものではありません。</p>
<p>動物の譲渡については下記リンクを参考にしてください。</p></div>
<p class="link-item"><a class="icon" href="aigodoubutu_jouto/index.html">譲渡について</a></p>
<h2><span class="bg"><span class="bg2"><span class="bg3">保健所収容動物情報</span></span></span></h2>
<div class="wysiwyg"><p>現在保健所に収容中の動物はいません。</p></div>
<p class="link-item"><a class="icon" href="inunekohenkan_sinsei.html">犬・猫等の返還申請について</a></p>
<h2><span class="bg"><span class="bg2"><span class="bg3">ペット(犬・猫)が逃げてしまった方へ</span></span></span></h2>
<div class="wysiwyg"><p>ペットが逃げてしまった時の対処法について、下記リンクを参考にしてください。</p></div></body></html>"""


def test_neyagawa_entry():
    src, _ = _load("city_neyagawa-1")
    assert (src.kind, src.species, src.url) == ("stray", "mixed", NEYAGAWA)
    assert src.phone == "072-829-7721"


def test_neyagawa_zero_day_is_empty_and_guidance_blocks_are_not_animals():
    _, res = _run("city_neyagawa-1", {NEYAGAWA: NEYAGAWA_EMPTY})
    assert res.animals == [] and res.empty_confirmed is True


def test_neyagawa_unknown_layout_is_not_confirmed_empty():
    changed = NEYAGAWA_EMPTY.replace("現在保健所に収容中の動物はいません。", "ただいま準備中です。")
    _, res = _run("city_neyagawa-1", {NEYAGAWA: changed})
    assert res.animals == [] and res.empty_confirmed is not True


# --- 八尾市 -------------------------------------------------------------------------------
YAO = "https://www.city.yao.osaka.jp/kurashi_tetsuzuki/sumai_kurashi_seikatsu/1012763/1003039/1003051.html"
YAO_EMPTY = """<html><body><div id="voice"><h1>迷い犬・猫 もし犬や猫が逃げ出してしまったら？</h1>
<p>大阪府動物の愛護および管理に関する条例により、飼っている動物が逃げ出した場合は、飼い主はこれを自ら捜索し、収容してください。</p><h2>保健所に収容されている犬・猫などについて</h2>
<p>こちらに掲載されているのは、保健所で保護・収容され、本来の飼い主を探している犬や猫などの情報です。</p>
<p>※現在、保健所では、保護されている動物はいません。</p><h2>迷い動物の届出・問合せについて</h2>
<ul class="objectlink"><li><a href="https://example.jp/start">電子申請によるお届け<span class="small">（外部リンク）</span><img src="new.gif" alt="新しいウィンドウで開きます"></a></li></ul>
<table><caption>八尾市内問合せ先</caption><thead><tr><th>担当部署</th><th>問合せ先</th></tr></thead>
<tbody><tr><td>八尾市保健所（保健衛生課）</td><td>072-994-6643　※月曜～金曜（祝日除く）8時45分～17時15分</td></tr></tbody></table></div></body></html>"""


def test_yao_entry():
    src, _ = _load("city_yao-1")
    assert (src.kind, src.species, src.url) == ("stray", "mixed", YAO)
    assert src.phone == "072-994-6643"


def test_yao_zero_day_is_empty_and_contact_table_is_not_an_animal():
    _, res = _run("city_yao-1", {YAO: YAO_EMPTY})
    assert res.animals == [] and res.empty_confirmed is True


def test_yao_unknown_layout_is_not_confirmed_empty():
    changed = YAO_EMPTY.replace("※現在、保健所では、保護されている動物はいません。", "※ただいま準備中です。")
    _, res = _run("city_yao-1", {YAO: changed})
    assert res.animals == [] and res.empty_confirmed is not True


# --- 西宮市 -------------------------------------------------------------------------------
NISHI_STRAY = "https://www.nishi.or.jp/kenko/hokenjojoho/pet/kainushinokata/pet-maigo.html"
NISHI_ADOPT = "https://www.nishi.or.jp/kenko/hokenjojoho/pet/dobutsujodo.html"
NISHI_STRAY_EMPTY = """<html><body><div class="wysiwyg_wp"><div class="h2bg"><div><h2>ペットが迷子になった飼い主さんへ</h2></div></div><p>ペットが迷子になった場合は、速やかに西宮市動物管理センターへご連絡してください。</p><ul><li>西宮市動物管理センター　電話：0798-81-1220</li></ul>
<div class="h2bg"><div><h2>迷い犬・迷い猫情報</h2></div></div><p>このページには西宮市動物管理センターに収容されている迷い犬・迷い猫の情報を掲載しております。</p></div>
<div class="h2bg"><div><h2>迷子動物のお知らせ</h2></div></div>
<div class="wysiwyg_wp"><p class="img-only">現在、迷子の動物の収容はありません。</p> <br></div></body></html>"""

_NISHI_INTRO = ('<div class="img-area"><p class="img-left"><img src="dobutsujodo.images/keihatsu_1.jpg" alt="譲渡募集チラシ"></p></div>'
                '<div class="wysiwyg_wp"><div class="h2bg"><div><h2>新しい飼い主になりたい方へ</h2></div></div><p>譲渡事業を行っています。</p>')
_NISHI_DOG = ('<div class="h2bg"><div><h2>譲渡犬653<strong>　NEW！</strong>　</h2></div></div>'
              '<p class="img-only"><img alt="ヨウ" src="dobutsujodo.images/youchan.jpeg" height="225" width="300" /></p> <br>'
              '<table><caption>犬の情報（653）</caption><tr><th scope="row">種類</th><td>ヨークシャーテリア</td></tr>'
              '<tr><th scope="row">毛色</th><td>灰＆茶</td></tr><tr><th scope="row">性別</th><td>雄（去勢済み）</td></tr>'
              '<tr><th scope="row">体格</th><td>小</td></tr><tr><th scope="row">毛足</th><td>長め</td></tr>'
              '<tr><th scope="row">その他特徴</th><td><p>13歳ですが、食欲・好奇心ともに旺盛な男の子です。<br>飼い主さんを募集しています。</p></td></tr></table>'
              '<p><a href="https://example.jp/apply"><img alt="譲渡の申し込みは、こちらから" src="/preview/x/click-white.png?e5b8"></a></p><p><br> </p>')
_NISHI_CAT = ('<div class="h2bg"><div><h2>譲渡猫700</h2></div></div>'
              '<p class="img-only"><img alt="みけ" src="dobutsujodo.images/mike.jpg"></p> <br>'
              '<table><caption>猫の情報（700）</caption><tr><th scope="row">種類</th><td>雑種</td></tr>'
              '<tr><th scope="row">毛色</th><td>三毛</td></tr><tr><th scope="row">性別</th><td>雌（避妊済み）</td></tr></table>'
              '<p><a href="https://example.jp/apply"><img alt="申し込み" src="/preview/x/click-white.png"></a></p>')
_NISHI_NO_CAT = '<div class="h2bg"><div><h2>現在、譲渡可能な猫はいません。</h2></div></div><p class="img-only">　　　　</p> '
_NISHI_NO_DOG = '<div class="h2bg"><div><h2>現在、譲渡可能な犬はいません。</h2></div></div><p class="img-only">　　　　</p> '
_NISHI_DONE = ('<div class="h2bg"><div><h2>譲渡先が決まりましたので、お知らせします。ありがとうございました。</h2></div></div>'
               '<p class="img-only">　　　<img alt="いなり1" src="dobutsujodo.images/inari1.JPG" /></p>'
               '<p class="img-only">　　　<img alt="こんぶ" src="dobutsujodo.images/konnbu.png" /></p><br></div>')


def _nishi_adopt(body: str) -> str:
    return f"<html><body>{_NISHI_INTRO}{body}{_NISHI_DONE}</body></html>"


def test_nishinomiya_entries():
    s1, _ = _load("nishi_nishinomiya-1")
    s2, _ = _load("nishi_nishinomiya-2")
    assert (s1.kind, s1.url, s1.prefecture) == ("stray", NISHI_STRAY, "兵庫県")
    assert (s2.kind, s2.url, s2.species) == ("adoption", NISHI_ADOPT, "mixed")
    assert s1.phone == s2.phone == "0798-81-1220"


def test_nishinomiya_adoption_reads_the_dog_with_own_photo_and_ignores_adopted_section():
    _, res = _run("nishi_nishinomiya-2", {NISHI_ADOPT: _nishi_adopt(_NISHI_DOG + _NISHI_NO_CAT)})
    assert len(res.animals) == 1
    a = res.animals[0]
    assert (a["species"], a["management_no"], a["breed"], a["color"], a["sex"], a["size"]) == (
        "dog", "653", "ヨークシャーテリア", "灰&茶", "雄(去勢済み)", "小")
    assert a["image_url"] == "https://www.nishi.or.jp/kenko/hokenjojoho/pet/dobutsujodo.images/youchan.jpeg"
    assert "13歳" in a["note"] and "長め" not in a["note"]


def test_nishinomiya_adoption_cat_section_is_a_cat_and_dog_photo_does_not_leak():
    _, res = _run("nishi_nishinomiya-2", {NISHI_ADOPT: _nishi_adopt(_NISHI_DOG + _NISHI_CAT)})
    assert [(a["species"], a["management_no"]) for a in res.animals] == [("dog", "653"), ("cat", "700")]
    assert res.animals[1]["image_url"].endswith("/dobutsujodo.images/mike.jpg")


def test_nishinomiya_adoption_zero_day_and_unknown_layout():
    _, res = _run("nishi_nishinomiya-2", {NISHI_ADOPT: _nishi_adopt(_NISHI_NO_DOG + _NISHI_NO_CAT)})
    assert res.animals == [] and res.empty_confirmed is True
    _, res2 = _run("nishi_nishinomiya-2", {NISHI_ADOPT: _nishi_adopt("<p>準備中</p>")})
    assert res2.animals == [] and res2.empty_confirmed is not True


def test_nishinomiya_stray_zero_day_is_empty_and_guidance_is_not_an_animal():
    _, res = _run("nishi_nishinomiya-1", {NISHI_STRAY: NISHI_STRAY_EMPTY})
    assert res.animals == [] and res.empty_confirmed is True
    # 0 頭の日に文言を出さない版（Wayback 2025-04・2026-03。T519v）: 枠の見出し「迷い犬・迷い猫情報」はあり、動物の見出し・表が無い → 0 頭
    no_sentence = NISHI_STRAY_EMPTY.replace("現在、迷子の動物の収容はありません。", "ただいま準備中です。")
    _, res2 = _run("nishi_nishinomiya-1", {NISHI_STRAY: no_sentence})
    assert res2.animals == [] and res2.empty_confirmed is True
    # 動物の見出し（迷い犬No.12）や表があるのに行が読めない日は 0 頭にしない（読めなかったで通知に出る）
    unreadable = NISHI_STRAY_EMPTY.replace("現在、迷子の動物の収容はありません。", "<h2>迷い犬No.12</h2><p>詳細は準備中です。</p>")
    _, res3 = _run("nishi_nishinomiya-1", {NISHI_STRAY: unreadable})
    assert res3.animals == [] and res3.empty_confirmed is not True
