"""W006 鹿児島県動物愛護ホームページ（dogcat.pref.kagoshima.jp）: POST の form を通して一覧を読む（2026-11-07・ネットワークなし）。

一覧は画像ボタンの JavaScript（search_submit）が anti-forgery トークン付きの form を POST して出す作り。
エンジンに steps の submit_form（入口の form の値を集め、指定の値を足して同じセッションで POST）を足して読む。
fixture（tests/fixtures/w006_pref_kagoshima_*_20261107.html）は 2026-11-07 の実ページ（トークンだけ TOKEN-… に置換）:
入口 2 枚・保護した犬（4 頭）・保護した猫と一般の方が保護の犬（どちらも 0 件）・譲渡センターの犬・里親募集の猫 1・2・14 ページ目・迷子を探している猫。
"""

import dataclasses
from pathlib import Path

import httpx
import pytest
import yaml
from collector.ai_repair import check_recipe_change
from collector.fetch import FakeFetcher, Fetcher, FetchError
from collector.last_ok import RecordingFetcher
from collector.recipe import Executor, Recipe
from collector.recipe_schema import validate_recipe_dict
from collector.registry import load_sources
from collector.run import collect_one

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}
RAW_NOTES = {r["slug"]: r.get("note") for r in yaml.safe_load((ROOT / "registry" / "sources.yaml").read_text(encoding="utf-8"))["sources"]}
HOST = "http://dogcat.pref.kagoshima.jp"
LOST_ACTION = f"{HOST}/Search/Search_lost"
JOUTO_ACTION = f"{HOST}/Search/Search_jouto"
LOST_INDEX = f"{HOST}/Search/Lost_index"
JOUTO_INDEX = f"{HOST}/Search/Jouto_index"


def _fx(name: str) -> str:
    return (FIX / f"w006_pref_kagoshima_{name}_20261107.html").read_text(encoding="utf-8")


def _fetcher(entry: str, entry_fx: str, posts: list[str], **kw) -> FakeFetcher:
    action = LOST_ACTION if entry == LOST_INDEX else JOUTO_ACTION
    pages: dict[str, str | bytes] = {entry: _fx(entry_fx)}
    for i, name in enumerate(posts, 1):
        pages[f"{action}#post{i}"] = _fx(name)
    return FakeFetcher(pages, **kw)


# --- 取れる ---------------------------------------------------------------------
def test_stray_dog_is_read_by_post():
    f = _fetcher(LOST_INDEX, "lost_index", ["stray_dog"])
    c = collect_one(SOURCES["pref_kagoshima-1"], f)
    assert c.status == "ok", c.error
    assert f.post_calls[0][0] == LOST_ACTION
    d = f.post_calls[0][1]
    assert (d["search_type"], d["lost_kubun"]) == ("dog", "lost")
    assert d["__RequestVerificationToken"] == "TOKEN-ENTRY-LOST"      # 入口の form の hidden をそのまま返す
    animals = c.result.animals
    # 4 件のうち 26D0302 は「飼い主さんと一緒に帰りました！」（返還済み）なので載せない
    assert [a["management_no"] for a in animals] == ["26D0310", "26D0309", "26D0308"]
    # 元ページのリンクは POST 専用の結果の URL（GET だとエラーページ）ではなく、人が開ける入口のページ
    assert {a["source_url"] for a in animals} == {LOST_INDEX}
    a0 = animals[0]
    assert (a0["species"], a0["sex"], a0["shelter_date"], a0["location"]) == ("dog", "メス", "2026年11月06日", "鹿屋市")
    assert "お問い合わせ先 鹿屋保健所(0994-52-2113)" in a0["note"]    # 個体ごとの問い合わせ先は掲載元ページの値のまま（括弧は NFKC で半角）
    assert "鹿屋市笠之原町で保護されました" in a0["note"]


def test_zero_hits_is_zero_animals_not_failed():
    f = _fetcher(LOST_INDEX, "lost_index", ["stray_cat_zero"])
    c = collect_one(SOURCES["pref_kagoshima-3"], f)
    assert c.status == "empty" and c.result.animals == []
    assert (f.post_calls[0][1]["search_type"], f.post_calls[0][1]["lost_kubun"]) == ("cat", "lost")


def test_hogo_zero_hits_is_zero_animals():
    f = _fetcher(LOST_INDEX, "lost_index", ["hogo_dog_zero"])
    c = collect_one(SOURCES["pref_kagoshima-4"], f)
    assert c.status == "empty"
    assert f.post_calls[0][1]["lost_kubun"] == "keisai_hogo"


def test_douai_dog_is_read_via_jouto_form():
    f = _fetcher(JOUTO_INDEX, "jouto_index", ["douai_dog"])
    c = collect_one(SOURCES["pref_kagoshima-2"], f)
    assert c.status == "ok", c.error
    d = f.post_calls[0][1]
    assert f.post_calls[0][0] == JOUTO_ACTION
    assert (d["search_type"], d["jouto_kubun"]) == ("dog", "douai")
    assert len(c.result.animals) == 7
    assert {a["species"] for a in c.result.animals} == {"dog"}


def test_klost_cat_is_kind_lost_and_reads_ten():
    f = _fetcher(LOST_INDEX, "lost_index", ["klost_cat_p1"])
    # 12 件 = 10 + 2 の 2 ページ目は fixture に無いので、1 ページ目だけの日として pager を外して読む
    f.pages[f"{LOST_ACTION}#post1"] = f.pages[f"{LOST_ACTION}#post1"].replace("paging_next", "paging_x")
    c = collect_one(SOURCES["pref_kagoshima-7"], f)
    assert c.status == "ok", c.error
    assert SOURCES["pref_kagoshima-7"].kind == "lost"
    assert len(c.result.animals) == 10
    assert f.post_calls[0][1]["lost_kubun"] == "keisai_lost"


def test_paging_follows_next_until_last_page():
    f = _fetcher(JOUTO_INDEX, "jouto_index", ["keisai_cat_p1", "keisai_cat_p2", "keisai_cat_p14"])
    # ページ送りの form の token（TOKEN-KEISAI-P1 → 2 ページ目、P2 → 14 ページ目）で辿った順を確かめる。14 ページ目は pager なしで終わる
    c = collect_one(SOURCES["pref_kagoshima-12"], f)
    assert c.status == "ok", c.error
    assert len(c.result.animals) == 30
    assert {a["source_url"] for a in c.result.animals} == {JOUTO_INDEX}
    calls = f.post_calls
    assert len(calls) == 3
    assert calls[0][1]["jouto_kubun"] == "keisai" and calls[0][1]["search_type"] == "cat"
    assert calls[1][1]["act"] == "next" and calls[1][1]["__RequestVerificationToken"] == "TOKEN-KEISAI-P1"
    assert calls[1][1]["jouto_kubun"] == "keisai" and calls[1][1]["search_type"] == "cat"
    assert calls[2][1]["act"] == "next" and calls[2][1]["__RequestVerificationToken"] == "TOKEN-KEISAI-P2"
    # 写真は pending（T630 の許諾待ち）、問い合わせ先は個体の備考へ
    assert SOURCES["pref_kagoshima-12"].photo == "pending"


# --- fail-closed ---------------------------------------------------------------
def test_missing_token_fails_not_zero():
    entry = _fx("lost_index").replace("__RequestVerificationToken", "x_token")
    f = FakeFetcher({LOST_INDEX: entry, f"{LOST_ACTION}#post1": _fx("stray_cat_zero")})
    c = collect_one(SOURCES["pref_kagoshima-3"], f)
    assert c.status == "failed" and "__RequestVerificationToken" in (c.error or "")
    assert f.post_calls == []      # token が無い日は POST しない


def test_missing_form_fails():
    entry = _fx("lost_index").replace('name="type"', 'name="other"')
    f = FakeFetcher({LOST_INDEX: entry, f"{LOST_ACTION}#post1": _fx("stray_cat_zero")})
    c = collect_one(SOURCES["pref_kagoshima-3"], f)
    assert c.status == "failed" and "form" in (c.error or "")


def test_error_page_redirect_after_post_fails_not_zero():
    # token 不正・セッション切れの日は 302 → /Shared/Error（実測）。0 頭に見せない
    err = f"{HOST}/Shared/Error"
    f = FakeFetcher({LOST_INDEX: _fx("lost_index"), f"{LOST_ACTION}#post1": _fx("stray_cat_zero")},
                    redirects={f"{LOST_ACTION}#post1": err})
    c = collect_one(SOURCES["pref_kagoshima-3"], f)
    assert c.status == "failed"


def test_zero_text_absent_on_structure_change_fails():
    # 子がいる日の形が崩れて行が 0 になった日は、0 件の文言が無いので 0 頭にならず failed
    html = _fx("stray_dog").replace("t-jouto", "t-other")
    f = FakeFetcher({LOST_INDEX: _fx("lost_index"), f"{LOST_ACTION}#post1": html})
    assert collect_one(SOURCES["pref_kagoshima-1"], f).status == "failed"


def test_child_day_page_never_matches_zero_text():
    for name in ("stray_dog", "douai_dog", "keisai_cat_p1", "klost_cat_p1"):
        assert "検索条件に一致する情報が見つかりませんでした" not in _fx(name), name
    for name in ("stray_cat_zero", "hogo_dog_zero"):
        assert "検索条件に一致する情報が見つかりませんでした" in _fx(name), name


def test_paging_beyond_max_fails_not_truncated():
    # 次ページが続くのに max に達した日は、黙って切らず失敗にする
    pages = {JOUTO_INDEX: _fx("jouto_index")}
    for i in range(1, 40):
        pages[f"{JOUTO_ACTION}#post{i}"] = _fx("keisai_cat_p1")     # pager が付いたまま永遠に続く
    c = collect_one(SOURCES["pref_kagoshima-12"], FakeFetcher(pages))
    assert c.status == "failed" and "max" in (c.error or "")


def test_form_action_to_other_host_is_refused():
    entry = _fx("lost_index").replace('action="/Search/Search_lost"', 'action="http://evil.example/x"', 1)
    f = FakeFetcher({LOST_INDEX: entry})
    c = collect_one(SOURCES["pref_kagoshima-3"], f)
    assert c.status == "failed" and f.post_calls == []


def test_get_form_is_not_submitted():
    entry = _fx("lost_index").replace('method="post" name="type"', 'method="get" name="type"')
    f = FakeFetcher({LOST_INDEX: entry})
    assert collect_one(SOURCES["pref_kagoshima-3"], f).status == "failed" and f.post_calls == []


# --- エンジン ---------------------------------------------------------------
FORM_PAGE = """<html><body><h1>t</h1>
<form action="/go" method="post" name="f">
<input type="hidden" name="tok" value="T1"><input name="keep" value="k"><input type="submit" name="btn" value="go">
<input type="checkbox" name="c1" value="v" checked><input type="checkbox" name="c2" value="v">
<select name="sel"><option value="a">A</option><option value="b" selected>B</option></select>
<select name="multi" multiple><option value="1" selected>1</option><option value="2" selected>2</option><option value="3">3</option></select>
<textarea name="ta">hello</textarea><input name="dis" value="x" disabled>
</form></body></html>"""


def _exec(steps, pages, **kw):
    r = Recipe.from_dict({"rows": "table.t", "steps": steps, **kw})
    f = FakeFetcher(pages)
    return Executor(f, r), f


def test_form_values_are_collected_and_overridden():
    ex, f = _exec([{"submit_form": {"form": "form[name=f]", "set": {"extra": "e", "keep": "over"}}}],
                  {"http://h.example/p": FORM_PAGE, "http://h.example/go#post1": "<html><body>" + "x" * 600 + "</body></html>"})
    ex.resolve("http://h.example/p")
    url, data = f.post_calls[0]
    assert url == "http://h.example/go"
    assert data == {"tok": "T1", "keep": "over", "c1": "v", "sel": "b", "multi": ["1", "2"], "ta": "hello", "extra": "e"}


def test_require_missing_or_empty_raises():
    from collector.recipe import RecipeError
    ex, _ = _exec([{"submit_form": {"form": "form[name=f]", "require": ["nope"]}}],
                  {"http://h.example/p": FORM_PAGE})
    with pytest.raises(RecipeError):
        ex.resolve("http://h.example/p")
    page = FORM_PAGE.replace('value="T1"', 'value=""')
    ex, _ = _exec([{"submit_form": {"form": "form[name=f]", "require": ["tok"]}}], {"http://h.example/p": page})
    with pytest.raises(RecipeError):
        ex.resolve("http://h.example/p")


def test_post_is_recorded_per_ordinal_and_replayed(tmp_path):
    from collector.last_ok import load_replay, save_last_ok
    f = _fetcher(JOUTO_INDEX, "jouto_index", ["keisai_cat_p1", "keisai_cat_p2", "keisai_cat_p14"])
    rec = RecordingFetcher(f)
    ex = Executor(rec, Recipe.load(ROOT / "recipes" / "pref_kagoshima-12.yaml"))
    docs = ex.resolve(SOURCES["pref_kagoshima-12"].url)
    assert len(docs) == 3 and rec.pages.keys() >= {JOUTO_INDEX, f"{JOUTO_ACTION}#post1", f"{JOUTO_ACTION}#post3"}
    assert save_last_ok(tmp_path, "pref_kagoshima-12", "2026-11-07", rec, count=30)
    replay = load_replay(tmp_path, "pref_kagoshima-12")
    assert replay is not None
    c = collect_one(SOURCES["pref_kagoshima-12"], replay)
    assert c.status == "ok" and len(c.result.animals) == 30


def test_fetcher_post_sends_form_referer_and_keeps_cookies():
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        if req.method == "GET":
            return httpx.Response(200, headers={"content-type": "text/html", "set-cookie": "sid=abc; path=/"},
                                  content=b"<html><body>" + b"x" * 600 + b"</body></html>")
        return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"},
                              content="<html><body>結果".encode() + b"x" * 600 + b"</body></html>")

    f = Fetcher(delay=0, respect_robots=False)
    f.client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    f.get("http://h.example/p")
    page = f.post("http://h.example/go", {"a": "1", "m": ["x", "y"]}, referer="http://h.example/p")
    post = seen[-1]
    assert post.method == "POST" and post.headers["referer"] == "http://h.example/p"
    assert post.headers["cookie"] == "sid=abc"
    assert post.content == b"a=1&m=x&m=y"
    assert "結果" in (page.html or "")
    f.post("http://h.example/go", {"a": "1"})
    assert len(seen) == 3          # POST は同じ内容でも取り直す（キャッシュしない）


def test_fetcher_post_respects_robots():
    f = Fetcher(delay=0, respect_robots=True)

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/robots.txt":
            return httpx.Response(200, content=b"User-agent: *\nDisallow: /go\n")
        raise AssertionError("robots 拒否なのに送った")

    f.client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(FetchError):
        f.post("http://h.example/go", {"a": "1"})


# --- schema・AI 修復 -----------------------------------------------------------
def _raw(step):
    return {"rows": "table.t", "steps": [step]}


def test_schema_accepts_valid_and_rejects_bad_submit_form():
    ok = {"submit_form": {"form": "form[name=type]", "set": {"search_type": "dog"}, "require": ["tok"]}}
    assert validate_recipe_dict(_raw(ok), LOST_INDEX) == []
    paging = {"submit_form": {"form": "form[name=paging]", "set": {"act": "next"}, "repeat_while": "a.paging_next", "max": 30}}
    assert validate_recipe_dict(_raw(paging), LOST_INDEX) == []
    for bad in (
        {"submit_form": {"form": "form", "action": "http://evil.example/x"}},          # 未知のキー（宛先は form の action だけ）
        {"submit_form": {"set": {"a": "b"}}},                                            # form が無い
        {"submit_form": {"form": "form", "set": {"a": 1}}},                              # 値が文字列でない
        {"submit_form": {"form": "form", "set": ["a"]}},
        {"submit_form": {"form": "form", "require": "tok"}},
        {"submit_form": {"form": "form", "max": 99999}},
        {"submit_form": "form"},
    ):
        assert validate_recipe_dict(_raw(bad), LOST_INDEX), bad


def test_ai_repair_cannot_add_or_change_submit_form():
    old = yaml.safe_load((ROOT / "recipes" / "pref_kagoshima-1.yaml").read_text(encoding="utf-8"))
    assert check_recipe_change(old, old) == []
    changed = yaml.safe_load(yaml.safe_dump(old))
    changed["steps"][0]["submit_form"]["set"]["lost_kubun"] = "keisai_hogo"
    assert any("submit_form" in v for v in check_recipe_change(old, changed))
    removed = dict(old, steps=[])
    assert any("submit_form" in v for v in check_recipe_change(old, removed))
    plain = {"rows": "table.t"}
    added = {"rows": "table.t", "steps": [{"submit_form": {"form": "form", "set": {"x": "y"}}}]}
    assert any("submit_form" in v for v in check_recipe_change(plain, added))
    assert any("submit_form" in v for v in check_recipe_change(None, added))


# --- 台帳 ---------------------------------------------------------------------
EXPECT = {
    # slug: (kind, species, 入口, form の値)
    "pref_kagoshima-1": ("stray", "dog", LOST_INDEX),
    "pref_kagoshima-3": ("stray", "cat", LOST_INDEX),
    "pref_kagoshima-4": ("stray", "dog", LOST_INDEX),
    "pref_kagoshima-5": ("stray", "cat", LOST_INDEX),
    "pref_kagoshima-6": ("lost", "dog", LOST_INDEX),
    "pref_kagoshima-7": ("lost", "cat", LOST_INDEX),
    "pref_kagoshima-2": ("adoption", "dog", JOUTO_INDEX),
    "pref_kagoshima-8": ("adoption", "cat", JOUTO_INDEX),
    "pref_kagoshima-9": ("adoption", "dog", JOUTO_INDEX),
    "pref_kagoshima-10": ("adoption", "cat", JOUTO_INDEX),
    "pref_kagoshima-11": ("adoption", "dog", JOUTO_INDEX),
    "pref_kagoshima-12": ("adoption", "cat", JOUTO_INDEX),
}
KUBUN = {1: "lost", 3: "lost", 4: "keisai_hogo", 5: "keisai_hogo", 6: "keisai_lost", 7: "keisai_lost",
         2: "douai", 8: "douai", 9: "kanrisyo", 10: "kanrisyo", 11: "keisai", 12: "keisai"}


@pytest.mark.parametrize("slug", sorted(EXPECT))
def test_registry_entries(slug):
    kind, species, entry = EXPECT[slug]
    s = SOURCES[slug]
    assert (s.kind, s.species, s.url) == (kind, species, entry)
    assert (s.mode, s.enabled, s.photo) == ("recipe", True, "pending")
    assert s.phone == "0995-44-6301" and s.address and "霧島市隼人町小田1493-1" in s.address
    note = RAW_NOTES[slug]
    assert note and "link_only" not in note and "読めない" not in note and "2026-11-07" in note
    raw = yaml.safe_load((ROOT / "recipes" / f"{slug}.yaml").read_text(encoding="utf-8"))
    n = int(slug.rsplit("-", 1)[1])
    form = raw["steps"][0]["submit_form"]
    key = "lost_kubun" if entry == LOST_INDEX else "jouto_kubun"
    assert form["set"] == {"search_type": species, key: KUBUN[n]}
    assert form["require"] == ["__RequestVerificationToken"]
    assert validate_recipe_dict(raw, s.url) == []
    # 動物愛護センターの譲渡対象だけ、収容・飼養先がセンターそのもの。ほかは個体ごとの保健所があるので operator
    assert s.contact_scope == ("facility" if KUBUN[n] == "douai" else "operator")


def test_no_personal_contact_is_read():
    # 個人の連絡先は読まない: 問い合わせ先は保健所・センターの欄だけを note に入れる。氏名・個人の電話を取る項目は無い
    for slug in EXPECT:
        raw = yaml.safe_load((ROOT / "recipes" / f"{slug}.yaml").read_text(encoding="utf-8"))
        assert set(raw["fields"]) <= {"management_no", "sex", "age", "shelter_date", "location", "note"}
        assert dataclasses.is_dataclass(SOURCES[slug])
