"""T641: `collector discover --pages`（台帳のページ・親ディレクトリ・環境省リンク集のリンク先から 1〜2 段たどり、
台帳に無い「譲渡・保護・迷子」系のページを月 1 回見つける）。ネットワークなし。取得は FakeFetcher、Discord は httpx.post を差し替え。

- 候補 = 起点のページのリンクのうち、リンク文字が KW に当たり NG に当たらないもの。台帳・latest.json・レシピ本文・確認済み一覧（pages:）にあるものは除く
- 採点 = 性別の語が SEX_MIN 以上、かつ「台帳のページからだけ来て、リンク文字が全部個体番号風」ではないもの → 通知の対象
- リンク切れ = 台帳の URL が HTTP 404・410、または別ホストへの転送で終わったもの（接続失敗・robots 拒否・5xx は数えない）
"""

from pathlib import Path

import pytest
from collector import discover as dmod
from collector import discover_pages as dp
from collector.discover import ENV_URL, load_known, load_known_pages
from collector.discover_pages import (
    MAX_FETCHES,
    MAX_WORKERS,
    SEX_MIN,
    discover_pages,
    find_pages,
    message,
    norm,
    parent,
)
from collector.errors import ErrorInfo
from collector.fetch import FakeFetcher, FetchError
from collector.registry import Source

V2 = Path(__file__).resolve().parent.parent


def _src(slug: str, url: str, *, mode: str = "recipe", enabled: bool = True) -> Source:
    return Source(slug=slug, name=slug, municipality=slug, prefecture="例県", url=url, kind="adoption",
                  mode=mode, enabled=enabled)


def _html(links: list[tuple[str, str]], body: str = "") -> str:
    a = "".join(f'<a href="{u}">{t}</a>' for u, t in links)
    return f"<html><head><title>t</title></head><body>{a}<p>{body}</p></body></html>"


LIST4 = "オス メス オス メス 収容日 保護日"   # 性別の語 4 つ
LIST3 = "オス メス オス"                      # 3 つ（しきい値の 1 つ下）


def _run(pages: dict[str, str], sources: list[Source], tmp_path: Path, *, depth: int = 1, known: str = "",
         latest: str | None = None, recipes: dict[str, str] | None = None, status: dict[str, int] | None = None,
         redirects: dict[str, str] | None = None, fetcher: FakeFetcher | None = None, max_fetches: int = MAX_FETCHES):
    k = tmp_path / "known.yaml"
    k.write_text(f"domains: {{}}\npages:\n{known}" if known else "domains: {}\n", encoding="utf-8")
    lp = tmp_path / "latest.json"
    if latest is not None:
        lp.write_text(latest, encoding="utf-8")
    rd = tmp_path / "recipes"
    rd.mkdir(exist_ok=True)
    for name, text in (recipes or {}).items():
        (rd / name).write_text(text, encoding="utf-8")
    fake = fetcher or FakeFetcher(pages, status=status, redirects=redirects)
    return find_pages(depth=depth, fetcher_factory=lambda: fake, sources=sources, known_path=k, latest_path=lp,
                      recipes_dir=rd, max_fetches=max_fetches), fake


# --- 定数 ---------------------------------------------------------------------------------------

def test_constants_are_pinned():
    assert SEX_MIN == 4
    assert MAX_FETCHES == 5000
    assert MAX_WORKERS == 8
    assert dp.DELAY == 1.5


# --- 正規化・親ディレクトリ ---------------------------------------------------------------------

def test_norm_drops_scheme_www_index_and_trailing_slash_but_keeps_query():
    assert norm("https://www.city.a.lg.jp/x/y/index.html") == "city.a.lg.jp/x/y"
    assert norm("http://city.a.lg.jp/x/y/") == "city.a.lg.jp/x/y"
    assert norm("https://city.a.lg.jp/") == "city.a.lg.jp/"
    assert norm("https://t.jp/a?animal_type=dog") == "t.jp/a?animal_type=dog"
    assert norm("https://t.jp/a?x=1#frag") == "t.jp/a?x=1"


def test_parent_is_directory_of_the_page():
    assert parent("https://a.jp/x/y/z.html") == "https://a.jp/x/y/"
    assert parent("https://a.jp/x/y/") == "https://a.jp/x/"
    assert parent("https://a.jp/z.html") is None


# --- 起点 ---------------------------------------------------------------------------------------

def test_seeds_include_every_ledger_entry_parent_and_env_targets(tmp_path):
    sources = [
        _src("a-1", "https://www.city.a.lg.jp/x/y/z.html"),
        _src("a-2", "https://www.city.a.lg.jp/x/y/off.html", enabled=False),
        _src("a-3", "https://www.city.a.lg.jp/x/y/link.html", mode="link_only"),
    ]
    env = ('<html><body>' + "".join(f'<a href="https://www.city.e{i}.lg.jp/p.html">e{i}市</a>' for i in range(3))
           + '<a href="https://www.env.go.jp/x">環境省</a></body></html>')
    res, _ = _run({ENV_URL: env}, sources, tmp_path)
    assert set(res.seeds) >= {
        "https://www.city.a.lg.jp/x/y/z.html", "https://www.city.a.lg.jp/x/y/off.html",
        "https://www.city.a.lg.jp/x/y/link.html",           # enabled の真偽・link_only を問わない
        "https://www.city.a.lg.jp/x/y/",                    # 親ディレクトリ
        "https://www.city.e0.lg.jp/p.html", "https://www.city.e2.lg.jp/p.html",   # 環境省リンク集のリンク先
    }
    assert res.seeds["https://www.city.a.lg.jp/x/y/z.html"].startswith("ledger:")
    assert res.seeds["https://www.city.a.lg.jp/x/y/"].startswith("parent:")
    assert res.seeds["https://www.city.e0.lg.jp/p.html"].startswith("env:")
    assert not any("env.go.jp" in u for u in res.seeds)


def test_env_failure_does_not_stop_the_run(tmp_path):
    res, _ = _run({"https://a.jp/x/z.html": _html([])}, [_src("a-1", "https://a.jp/x/z.html")], tmp_path)
    assert res.env_error
    assert "https://a.jp/x/z.html" in res.seeds


# --- KW / NG -------------------------------------------------------------------------------------

def test_kw_ng_split(tmp_path):
    seed = "https://a.jp/x/z.html"
    links = [("https://a.jp/c1", "譲渡犬の一覧"), ("https://a.jp/c2", "迷い犬・迷い猫の情報"),
             ("https://a.jp/n1", "譲渡会の講習について"),      # NG（講習）
             ("https://a.jp/n2", "お知らせ"),                    # KW なし
             ("https://a.jp/n3", "ボランティア募集（譲渡）")]    # NG（ボランティア）
    pages = {seed: _html(links), "https://a.jp/c1": _html([], LIST4), "https://a.jp/c2": _html([], LIST4)}
    res, _ = _run(pages, [_src("a-1", seed)], tmp_path)
    assert {c["url"] for c in res.candidates} == {"https://a.jp/c1", "https://a.jp/c2"}


def test_files_env_and_youtube_are_not_opened(tmp_path):
    seed = "https://a.jp/x/z.html"
    links = [("https://a.jp/譲渡.pdf", "譲渡犬 PDF"), ("https://a.jp/p.xlsx", "譲渡一覧"), ("https://a.jp/p.JPG", "保護犬の写真"),
             ("https://www.env.go.jp/a.html", "収容動物の情報"), ("https://www.youtube.com/watch?v=1", "譲渡犬の動画"),
             ("https://a.jp/ok", "譲渡犬")]
    pages = {seed: _html(links), "https://a.jp/ok": _html([], LIST4)}
    res, fake = _run(pages, [_src("a-1", seed)], tmp_path)
    assert {c["url"] for c in res.candidates} == {"https://a.jp/ok"}
    assert res.fetched == len(set(res.seeds)) + 1   # 起点 + ok だけ。除いたものは開いていない


# --- 除外 4 種 -----------------------------------------------------------------------------------

def _excl_pages(seed: str) -> dict[str, str]:
    links = [("https://www.a.jp/ledger/index.html", "譲渡犬（台帳）"), ("https://a.jp/live/", "譲渡猫（本番にある）"),
             ("https://a.jp/recipe/abcdef.html", "保護犬（レシピ）"), ("https://a.jp/known.html", "譲渡犬（確認済み）"),
             ("https://a.jp/new.html", "譲渡犬（新しい）")]
    return {seed: _html(links), "https://a.jp/new.html": _html([], LIST4)}


def test_exclusions_ledger_latest_recipe_known(tmp_path):
    seed = "https://a.jp/x/z.html"
    sources = [_src("a-1", seed), _src("a-2", "https://a.jp/ledger/")]
    latest = '{"animals": [{"source_url": "https://a.jp/live/animal/1"}, {"source_url": null}]}'
    recipes = {"r.yaml": "steps:\n  - url: https://a.jp/recipe/abcdef.html\n"}
    known = "  a.jp/known.html: {status: excluded, note: 掲示板}\n"
    res, _ = _run(_excl_pages(seed), sources, tmp_path, latest=latest, recipes=recipes, known=known)
    assert [c["url"] for c in res.candidates] == ["https://a.jp/new.html"]


def test_latest_matches_the_url_itself_or_anything_below_it(tmp_path):
    seed = "https://a.jp/x/z.html"
    pages = {seed: _html([("https://a.jp/live", "譲渡猫"), ("https://a.jp/liver", "譲渡犬")]),
             "https://a.jp/liver": _html([], LIST4)}
    latest = '{"animals": [{"source_url": "https://a.jp/live"}, {"source_url": "https://a.jp/live/deep/1.html"}]}'
    res, _ = _run(pages, [_src("a-1", seed)], tmp_path, latest=latest)
    assert [c["url"] for c in res.candidates] == ["https://a.jp/liver"]   # live は除外、liver は前方一致でも別物


def test_recipe_tail_needs_five_chars_to_exclude(tmp_path):
    seed = "https://a.jp/x/z.html"
    pages = {seed: _html([("https://a.jp/p/abcd", "譲渡犬"), ("https://a.jp/p/abcde", "譲渡猫")]),
             "https://a.jp/p/abcd": _html([], LIST4), "https://a.jp/p/abcde": _html([], LIST4)}
    res, _ = _run(pages, [_src("a-1", seed)], tmp_path, recipes={"r.yaml": "url: https://a.jp/zzz/abcd\nu2: https://a.jp/p/abcde\n"})
    assert [c["url"] for c in res.candidates] == ["https://a.jp/p/abcd"]   # 4 文字は除かない、5 文字は除く


# --- 採点 ---------------------------------------------------------------------------------------

def test_score_counts_like_gap_triage():
    s = dp.score('<html><head><title>譲渡犬</title></head><body><nav>オス</nav><p>オス メス ♂ 去勢 収容日 管理番号'
                 ' ただいま譲渡対象の犬はいません</p><img src="/a/dog1.jpg"><img src="/img/logo.png"></body></html>')
    assert s == {"sex": 4, "date": 2, "photos": 1, "zero": True, "title": "譲渡犬"}


def test_threshold_and_individual_pages(tmp_path):
    seed = "https://a.jp/x/z.html"
    links = [("https://a.jp/c4", "譲渡犬"), ("https://a.jp/c3", "譲渡猫"), ("https://a.jp/i1", "No.12 譲渡犬"),
             ("https://a.jp/i2", "R8-123 保護猫")]
    pages = {seed: _html(links), "https://a.jp/c4": _html([], LIST4), "https://a.jp/c3": _html([], LIST3),
             "https://a.jp/i1": _html([], LIST4), "https://a.jp/i2": _html([], LIST4)}
    res, _ = _run(pages, [_src("a-1", seed)], tmp_path)
    assert {c["url"] for c in res.targets} == {"https://a.jp/c4"}
    assert {c["url"] for c in res.candidates} == {"https://a.jp/c4", "https://a.jp/c3", "https://a.jp/i1", "https://a.jp/i2"}


def test_individual_like_text_from_a_parent_page_is_still_a_target(tmp_path):
    # 台帳のページ「だけ」から来たものが個体ページ。親ディレクトリ・環境省から来たものは一覧の可能性がある
    seed = "https://a.jp/x/z.html"
    pages = {seed: _html([]), "https://a.jp/x/": _html([("https://a.jp/i1", "No.12 譲渡犬")]),
             "https://a.jp/i1": _html([], LIST4)}
    res, _ = _run(pages, [_src("a-1", seed)], tmp_path)
    assert [c["url"] for c in res.targets] == ["https://a.jp/i1"]


def test_candidate_that_fails_to_open_is_not_a_target(tmp_path):
    seed = "https://a.jp/x/z.html"
    res, _ = _run({seed: _html([("https://a.jp/gone", "譲渡犬")])}, [_src("a-1", seed)], tmp_path)
    assert res.targets == []


# --- depth ---------------------------------------------------------------------------------------

def test_depth_2_follows_links_found_on_candidate_pages(tmp_path):
    seed = "https://a.jp/x/z.html"
    pages = {seed: _html([("https://a.jp/hub", "譲渡・保護のご案内")]),
             "https://a.jp/hub": _html([("https://a.jp/deep", "譲渡犬の一覧")], "案内"),
             "https://a.jp/deep": _html([], LIST4)}
    d1 = tmp_path / "d1"
    d1.mkdir()
    r1, _ = _run(pages, [_src("a-1", seed)], d1, depth=1)
    r2, _ = _run(pages, [_src("a-1", seed)], tmp_path, depth=2)
    assert {c["url"] for c in r1.candidates} == {"https://a.jp/hub"}
    assert {c["url"] for c in r2.candidates} == {"https://a.jp/hub", "https://a.jp/deep"}
    assert [c["url"] for c in r2.targets] == ["https://a.jp/deep"]


# --- リンク切れ -----------------------------------------------------------------------------------

class _RaisingFetcher(FakeFetcher):
    def __init__(self, pages: dict[str, str], errors: dict[str, FetchError]) -> None:
        super().__init__(pages)
        self.errors = errors

    def get(self, url, encoding=None):
        if url in self.errors:
            raise self.errors[url]
        return super().get(url, encoding)


def test_broken_links_404_410_and_other_host_redirect(tmp_path):
    ok = {"https://a.jp/ok": _html([])}
    sources = [_src("ok", "https://a.jp/ok"), _src("g404", "https://a.jp/404"), _src("g410", "https://a.jp/410"),
               _src("moved", "https://old.jp/p"), _src("www", "https://a.jp/www"), _src("down", "https://a.jp/down"),
               _src("s503", "https://a.jp/503")]
    pages = {**ok, "https://old.jp/p": _html([]), "https://a.jp/www": _html([]), "https://a.jp/503": _html([])}
    res, _ = _run(pages, sources, tmp_path, status={"https://a.jp/404": 404, "https://a.jp/410": 410, "https://a.jp/503": 503},
                  redirects={"https://old.jp/p": "https://new.jp/q", "https://a.jp/www": "https://www.a.jp/www"})
    got = {b["slug"]: b["reason"] for b in res.broken}
    assert set(got) == {"g404", "g410", "moved"}     # down = 接続失敗、s503 = 5xx、www = 同じサイト → 数えない
    assert got["g404"] == "HTTP 404" and got["g410"] == "HTTP 410"
    assert "new.jp" in got["moved"]


def test_cross_site_redirect_that_the_real_fetcher_raises_is_broken_but_robots_and_connect_are_not(tmp_path):
    errors = {
        "https://a.jp/moved": FetchError("取得不能: 別のサイトへ転送された（new.jp）: https://a.jp/moved",
                                         ErrorInfo("redirect", status=200, host="a.jp")),
        "https://a.jp/robots": FetchError("robots.txt により拒否", ErrorInfo("robots", host="a.jp")),
        "https://a.jp/conn": FetchError("ConnectError", ErrorInfo("connect", host="a.jp")),
        "https://a.jp/5xx": FetchError("HTTP 500", ErrorInfo("http", status=500, host="a.jp")),
    }
    sources = [_src(k, f"https://a.jp/{k}") for k in ("moved", "robots", "conn", "5xx")]
    res, _ = _run({}, sources, tmp_path, fetcher=_RaisingFetcher({}, errors))
    assert [b["slug"] for b in res.broken] == ["moved"]


def test_broken_check_only_for_ledger_urls_not_parents_or_candidates(tmp_path):
    seed = "https://a.jp/x/z.html"
    pages = {seed: _html([("https://a.jp/cand", "譲渡犬")])}     # 親 https://a.jp/x/ と cand は開けない
    res, _ = _run(pages, [_src("a-1", seed)], tmp_path, status={"https://a.jp/x/": 404, "https://a.jp/cand": 404})
    assert res.broken == []


# --- 取得数の上限 ---------------------------------------------------------------------------------

def test_fetch_cap_truncates(tmp_path):
    sources = [_src(f"s{i}", f"https://a.jp/p{i}.html") for i in range(10)]
    pages = {f"https://a.jp/p{i}.html": _html([]) for i in range(10)}
    res, fake = _run(pages, sources, tmp_path, max_fetches=4)
    assert res.fetched == 4
    assert res.truncated
    msg = message(res)
    assert msg is not None and "上限" in msg      # 上限で打ち切った日は、他に何も無くても知らせる


def test_no_truncation_under_cap(tmp_path):
    res, _ = _run({"https://a.jp/p.html": _html([])}, [_src("s", "https://a.jp/p.html")], tmp_path, max_fetches=100)
    assert not res.truncated


# --- 通知 ---------------------------------------------------------------------------------------

class _Post:
    def __init__(self) -> None:
        self.sent: list[str] = []

    def __call__(self, url: str, json: dict, timeout: float):
        self.sent.append(json["content"])

        class _R:
            def raise_for_status(self) -> None:
                return None

        return _R()


@pytest.fixture
def post(monkeypatch):
    p = _Post()
    monkeypatch.setattr(dmod.httpx, "post", p)
    return p


def _setup(tmp_path: Path, known: str = ""):
    seed = "https://a.jp/x/z.html"
    pages = {seed: _html([("https://a.jp/new.html", "譲渡犬の一覧")]), "https://a.jp/new.html": _html([], LIST4)}
    k = tmp_path / "known.yaml"
    k.write_text("domains: {}\npages:\n" + known if known else "domains: {}\n", encoding="utf-8")
    rd = tmp_path / "recipes"
    rd.mkdir(exist_ok=True)
    fake = FakeFetcher(pages)
    return {"fetcher_factory": lambda: fake, "sources": [_src("a-1", seed)], "known_path": k,
            "latest_path": tmp_path / "none.json", "recipes_dir": rd, "out": tmp_path / "out.json"}


def test_notifies_once_when_there_is_a_new_candidate(tmp_path, monkeypatch, post):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://example.invalid/hook")
    assert discover_pages(notify=True, **_setup(tmp_path)) == 0
    assert len(post.sent) == 1
    assert "https://a.jp/new.html" in post.sent[0] and "1 件" in post.sent[0]
    assert len(post.sent[0]) <= 1900


def test_does_not_notify_once_the_page_is_in_known(tmp_path, monkeypatch, post):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://example.invalid/hook")
    kw = _setup(tmp_path, "  a.jp/new.html: {status: pending, note: 確認中}\n")
    assert discover_pages(notify=True, **kw) == 0
    assert post.sent == []


def test_notifies_for_broken_link_alone(tmp_path, monkeypatch, post):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://example.invalid/hook")
    kw = _setup(tmp_path)
    kw["fetcher_factory"] = lambda: FakeFetcher({}, status={"https://a.jp/x/z.html": 404})
    assert discover_pages(notify=True, **kw) == 0
    assert len(post.sent) == 1 and "リンク切れ" in post.sent[0] and "a-1" in post.sent[0]


def test_without_notify_flag_never_sends(tmp_path, monkeypatch, post):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://example.invalid/hook")
    assert discover_pages(notify=False, **_setup(tmp_path)) == 0
    assert post.sent == []


def test_without_webhook_only_prints(tmp_path, monkeypatch, post, capsys):
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    assert discover_pages(notify=True, **_setup(tmp_path)) == 0
    assert post.sent == []
    assert "DISCORD_WEBHOOK_URL" in capsys.readouterr().out


def test_message_is_capped_in_length_and_items(tmp_path):
    seed = "https://a.jp/x/z.html"
    links = [(f"https://a.jp/c{i}", f"譲渡犬の一覧{i}") for i in range(40)]
    pages = {seed: _html(links), **{f"https://a.jp/c{i}": _html([], LIST4 + "x" * 5) for i in range(40)}}
    res, _ = _run(pages, [_src("a-1", seed)], tmp_path)
    assert len(res.targets) == 40
    msg = message(res)
    assert msg is not None and len(msg) <= 1900
    assert msg.count("https://a.jp/c") == dp.NOTIFY_MAX_ITEMS
    assert "ほか" in msg


def test_out_json_is_written(tmp_path):
    import json
    kw = _setup(tmp_path)
    discover_pages(**kw)
    data = json.loads(kw["out"].read_text(encoding="utf-8"))
    assert data["targets"][0]["url"] == "https://a.jp/new.html"
    assert {"seeds", "fetched", "truncated", "candidates", "broken"} <= set(data)


# --- CLI ---------------------------------------------------------------------------------------

def test_cli_passes_pages_options(monkeypatch):
    from collector import __main__ as cli

    got: dict = {}
    monkeypatch.setattr(dp, "discover_pages", lambda **kw: got.update(kw) or 0)
    assert cli.main(["discover", "--pages", "--depth", "2", "--notify", "--out", "/tmp/x.json"]) == 0
    assert got["depth"] == 2 and got["notify"] is True and str(got["out"]) == "/tmp/x.json"


def test_cli_plain_discover_is_unchanged(monkeypatch):
    from collector import __main__ as cli

    called: dict = {}
    monkeypatch.setattr(dmod, "discover", lambda **kw: called.update(kw) or 0)
    monkeypatch.setattr(dp, "discover_pages", lambda **kw: pytest.fail("--pages なしで呼ばれた"))
    assert cli.main(["discover", "--notify"]) == 0
    assert called == {"json_out": False, "notify": True}


def test_cli_rejects_depth_3():
    from collector import __main__ as cli

    with pytest.raises(SystemExit):
        cli.main(["discover", "--pages", "--depth", "3"])


# --- collect.sh --------------------------------------------------------------------------------

def test_collect_sh_runs_pages_only_on_first_monday():
    sh = (V2 / "ops" / "collect.sh").read_text(encoding="utf-8")
    cmd = '"$PY" -m collector discover --pages --notify'
    assert cmd in sh
    i = sh.index(cmd)
    cond = sh[sh.rindex("\nif ", 0, i): i]                      # このコマンドを囲む if の条件
    assert "%u" in cond and "%d" in cond and "TZ=Asia/Tokyo" in cond   # JST の月曜 かつ 日付 1〜7
    assert '= "1"' in cond and "-le 7" in cond
    assert "失敗には数えない" in sh[i: i + 400] and "step discover_pages" not in sh   # step を使わない = 日次収集の失敗に数えない
    assert sh.index('"$PY" -m collector discover --notify') < i < sh.index('audit_empty.py" --data')


# --- discover_known.yaml の pages 節 ---------------------------------------------------------------

def test_load_known_pages_reads_fields(tmp_path):
    p = tmp_path / "k.yaml"
    p.write_text("domains: {}\npages:\n  www.a.jp/x/index.html: {status: covered, note: 台帳にある, slugs: [a-1]}\n"
                 "  b.jp/y: {status: excluded, note: 掲示板}\n", encoding="utf-8")
    k = load_known_pages(p)
    assert set(k) == {"a.jp/x", "b.jp/y"}            # キーは読み込み時にも正規化する
    assert k["a.jp/x"].status == "covered" and k["a.jp/x"].slugs == ["a-1"]
    assert k["b.jp/y"].note == "掲示板"


def test_load_known_pages_rejects_bad_status_and_missing_section(tmp_path):
    p = tmp_path / "k.yaml"
    p.write_text("domains: {}\npages:\n  a.jp/x: {status: maybe}\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_known_pages(p)
    p.write_text("domains: {}\n", encoding="utf-8")
    assert load_known_pages(p) == {}
    assert load_known_pages(tmp_path / "nothing.yaml") == {}


def test_repo_known_pages_shape_and_domains_untouched():
    import yaml

    raw = yaml.safe_load((V2 / "registry" / "discover_known.yaml").read_text(encoding="utf-8"))
    pages = raw["pages"]
    assert pages, "pages: 節が空"
    for key, v in pages.items():
        assert norm("https://" + key) == key, f"キーが正規化されていない: {key}"
        assert v["status"] in ("pending", "excluded", "covered"), key
        assert v.get("note"), f"note が無い: {key}"
        assert set(v) <= {"status", "note", "slugs"}, key
    assert "www.pref.tottori.lg.jp/220718.htm" not in pages and "pref.tottori.lg.jp/220718.htm" in pages
    assert "city.miyazaki.miyazaki.jp/life/pet/protection/51367.html" in pages
    assert "city.miyazaki.miyazaki.jp/life/pet/protection/84989.html" in pages
    assert len(load_known()) >= 40          # 既存の domains: 節は読める
    assert len(load_known_pages()) == len(pages)


# --- #131 の独立レビュー（2026-11-18）の指摘 --------------------------------------------------------

def test_malformed_href_on_a_page_does_not_stop_the_run(tmp_path):
    # Q1: 起点のページに壊れたリンク（urljoin が ValueError を出す「http://[bad」）が 1 つあっても、そのリンクを飛ばして続ける。
    # 落ちると月 1 回の実行が丸ごと止まり、同じページがある限り毎月止まる
    seed = "https://a.jp/x/z.html"
    pages = {seed: '<html><body><a href="http://[bad">譲渡</a><a href="https://a.jp/new.html">譲渡犬の一覧</a></body></html>',
             "https://a.jp/new.html": _html([], LIST4)}
    res, _ = _run(pages, [_src("a-1", seed)], tmp_path)
    assert [t["url"] for t in res.targets] == ["https://a.jp/new.html"]


def test_unexpected_failure_is_reported_to_discord(tmp_path, monkeypatch, post):
    # Q1: 想定していない落ち方をした月は、Discord に 1 通送る（黙って機能しなくなるのを防ぐ）。日次収集の失敗には数えない
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://example.invalid/hook")
    kw = _setup(tmp_path)

    def boom():
        raise RuntimeError("壊れた")

    kw["fetcher_factory"] = boom
    assert discover_pages(notify=True, **kw) == 1
    assert len(post.sent) == 1
    assert "失敗" in post.sent[0] and "RuntimeError" in post.sent[0]


def test_unexpected_failure_without_notify_raises(tmp_path):
    kw = _setup(tmp_path)

    def boom():
        raise RuntimeError("壊れた")

    kw["fetcher_factory"] = boom
    with pytest.raises(RuntimeError):
        discover_pages(notify=False, **kw)


def test_recipe_text_excludes_only_id_like_tails_or_the_whole_url(tmp_path):
    # Q2: レシピ本文の部分一致で外すのは、数字 4 桁以上を含む末尾（ページ ID）だけ。index.html・neko.html・animal のような
    # 一般的な末尾は、ほかの自治体のレシピやコメントにも出てくるので外さない（本物の掲載漏れを黙って外さない）。
    # レシピに URL がそのまま書いてあるページは、末尾の形に関係なく外す
    seed = "https://a.jp/x/z.html"
    links = [("https://a.jp/pet/index.html", "譲渡犬"), ("https://a.jp/pet/neko.html", "譲渡猫"), ("https://a.jp/pet/animal", "保護動物"),
             ("https://a.jp/pet/1020659.html", "迷子情報"), ("https://a.jp/pet/jouto.html", "譲渡の一覧")]
    pages = {seed: _html(links), **{u: _html([], LIST4) for u, _ in links}}
    recipes = {"other.yaml": "# 一覧は https://b.jp/list/index.html の形式\n"
                             "follow_all: \"a[href*='neko.html'], a[href*='animal'], a[href*='1020659']\"\n"
                             "urls: [\"https://www.a.jp/pet/jouto.html\"]\n"}
    res, _ = _run(pages, [_src("a-1", seed)], tmp_path, recipes=recipes)
    assert sorted(c["url"] for c in res.candidates) == ["https://a.jp/pet/animal", "https://a.jp/pet/index.html", "https://a.jp/pet/neko.html"]


def test_message_puts_broken_links_first_and_never_cuts_a_line(tmp_path):
    # Q3: 候補が多い月でも、リンク切れ（台帳の URL の壊れ）は全部載り、行の途中で切れず、省いた行数が分かる
    seed = "https://a.jp/x/z.html"
    title = "長い題名" * 20
    links = [(f"https://a.jp/list/c{i}", f"譲渡犬の一覧{i}") for i in range(40)]
    body = f"<html><head><title>{title}</title></head><body><p>{LIST4}</p></body></html>"
    pages = {seed: _html(links), **{u: body for u, _ in links}}
    gone = [_src(f"b-{i}", f"https://a.jp/gone/{i}.html?kind=1&species=2&very_long_query_parameter_name_for_the_test=value{i}") for i in range(9)]
    sources = [_src("a-1", seed), *gone]
    res, _ = _run(pages, sources, tmp_path, status={s.url: 404 for s in gone})
    assert len(res.targets) == 40 and len(res.broken) == 9
    msg = message(res)
    assert msg is not None and len(msg) <= dp.NOTIFY_MAX_CHARS
    assert all(f"b-{i} " in msg for i in range(9))
    assert msg.index("リンク切れ（") < msg.index("候補（")
    whole = {f"- b-{i} {s.url}（HTTP 404）" for i, s in enumerate(gone)}
    lines = msg.split("\n")
    assert whole <= set(lines)                                    # リンク切れの行は 1 行も欠けず、途中で切れていない
    assert lines[-1].startswith("（") and "省いた" in lines[-1]   # 上限で省いた行があることを最後の行で知らせる


def test_message_says_truncation_before_the_lists(tmp_path):
    seed = "https://a.jp/x/z.html"
    links = [(f"https://a.jp/list/c{i}", f"譲渡犬の一覧{i}") for i in range(6)]
    pages = {seed: _html(links), **{u: _html([], LIST4) for u, _ in links}}
    res, _ = _run(pages, [_src("a-1", seed)], tmp_path, max_fetches=3)
    assert res.truncated
    msg = message(res)
    assert msg is not None
    assert msg.split("\n")[1].startswith("取得数が上限")
