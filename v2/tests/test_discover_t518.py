"""T518 ⑤: 環境省リンク集と台帳の差分を週 1 回通知する（ネットワークなし。取得は FakeFetcher、Discord は httpx.post を差し替え）。

- 確認済みの差分は registry/discover_known.yaml（ドメインごとに pending / excluded / covered）に持ち、一覧に無い差分だけを通知する
- 差分が無ければ送らない。DISCORD_WEBHOOK_URL が無ければ表示だけ
- リンク集が取れない・リンクが極端に少ない（ページの形が変わった）ときは rc=1 で 1 通（日次収集の失敗には数えない。collect.sh 側）
"""

from pathlib import Path

import pytest

from collector import discover as dmod
from collector.discover import (ENV_URL, Known, compute, discover, env_links, load_known, message,
                                failure_message)
from collector.fetch import FakeFetcher
from collector.registry import Source, load_sources

FIXTURES = Path(__file__).parent / "fixtures"


def _src(slug: str, url: str, name: str = "") -> Source:
    return Source(slug=slug, name=name or slug, municipality=name or slug, prefecture="例県", url=url, kind="adoption")


def _page(rows: list[tuple[str, str]], filler: int = 0) -> str:
    """環境省のリンク集に似せた表。filler 件の無関係な自治体を足して「極端に少ない」判定を避ける。"""
    cells = [f'<tr><td><a href="{u}">{n}</a></td></tr>' for n, u in rows]
    cells += [f'<tr><td><a href="https://www.city.filler{i}.lg.jp/a.html">埋め{i}市</a></td></tr>' for i in range(filler)]
    return ('<html><body><a href="/nature/index.html">環境省内</a>'
            '<a href="https://www.env.go.jp/other.html">環境省の別ページ</a>'
            f'<table>{"".join(cells)}</table></body></html>')


class _Post:
    """httpx.post の差し替え。送った content を貯める。"""

    def __init__(self) -> None:
        self.sent: list[str] = []

    def __call__(self, url: str, json: dict, timeout: float):  # noqa: A002
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


def _known_file(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "known.yaml"
    p.write_text(text, encoding="utf-8")
    return p


# --- リンク集の読み取り ------------------------------------------------------------------

def test_env_links_drops_env_go_jp_and_strips_www():
    links = env_links(_page([("秋田市", "https://www.city.akita.lg.jp/a.html"), ("動画", "https://www.youtube.com/watch?v=x")]))
    assert set(links) == {"city.akita.lg.jp", "youtube.com"}
    assert links["city.akita.lg.jp"] == [("https://www.city.akita.lg.jp/a.html", "秋田市")]


# --- 差分の計算（known の除外・状態ごと） --------------------------------------------------

def test_compute_separates_known_and_unknown():
    links = {
        "city.akita.lg.jp": [("https://www.city.akita.lg.jp/a.html", "秋田市")],
        "youtube.com": [("https://www.youtube.com/watch?v=x", "")],
        "city.new.lg.jp": [("https://www.city.new.lg.jp/a.html", "新市")],
        "pref.ok.lg.jp": [("https://www.pref.ok.lg.jp/", "例県")],
    }
    sources = [_src("pref_ok", "https://www.pref.ok.lg.jp/list.html"),
               _src("sapca", "https://www.sapca.jp/lost", "滋賀県動物保護管理センター（迷い犬猫）"),
               _src("gone_x", "https://gone.example.jp/", "消えた市")]
    known = {
        "city.akita.lg.jp": Known("pending", name="秋田市", task="T519"),
        "youtube.com": Known("excluded", note="動画"),
        "sapca.jp": Known("covered", slugs=["sapca"], note="リンク集は滋賀県のページを指す"),
        "old.example.jp": Known("pending", name="古い市"),
    }
    d = compute(links, sources, known)
    assert sorted(d.new) == ["city.akita.lg.jp", "city.new.lg.jp", "youtube.com"]
    assert d.gone == ["gone.example.jp", "sapca.jp"]
    assert list(d.unknown_new) == ["city.new.lg.jp"]
    assert d.unknown_gone == ["gone.example.jp"]
    assert d.by_status() == {"pending": ["city.akita.lg.jp"], "excluded": ["youtube.com"], "covered": ["sapca.jp"]}
    # 一覧にあるが今の差分に無い = 台帳に入った or リンク集から消えた。known から外してよい
    assert d.stale == ["old.example.jp"]


def test_load_known_rejects_unknown_status(tmp_path):
    p = _known_file(tmp_path, "domains:\n  a.example.jp: {status: maybe}\n")
    with pytest.raises(ValueError, match="maybe"):
        load_known(p)


def test_load_known_reads_fields(tmp_path):
    p = _known_file(tmp_path, (
        "domains:\n"
        "  city.akita.lg.jp: {status: pending, name: 秋田市, task: T519}\n"
        "  sapca.jp: {status: covered, slugs: [spec_sapca], note: 滋賀県}\n"))
    k = load_known(p)
    assert k["city.akita.lg.jp"] == Known("pending", name="秋田市", task="T519")
    assert k["sapca.jp"].slugs == ["spec_sapca"]


# --- 通知文 --------------------------------------------------------------------------------

def test_message_lists_new_and_gone_with_request_phrase():
    links = {"city.new.lg.jp": [("https://www.city.new.lg.jp/a.html", "新市")]}
    sources = [_src("gone_x-1", "https://gone.example.jp/a", "消えた市（譲渡犬）")]
    msg = message(compute(links, sources, {}))
    assert msg is not None
    assert "環境省リンク集に新しい自治体 1 件" in msg
    assert "- 新市 https://www.city.new.lg.jp/a.html" in msg
    assert "差分を台帳に足して" in msg
    assert "リンク集から消えた 1 件" in msg
    assert "gone.example.jp" in msg and "gone_x-1" in msg


def test_message_none_when_all_known():
    links = {"city.akita.lg.jp": [("https://www.city.akita.lg.jp/a.html", "秋田市")]}
    known = {"city.akita.lg.jp": Known("pending", name="秋田市")}
    assert message(compute(links, [], known)) is None


def test_failure_message_says_not_daily_failure():
    m = failure_message("HTTP 404: " + ENV_URL)
    assert "環境省リンク集" in m and "HTTP 404" in m and "日次収集" in m


# --- discover(): 送る・送らない ----------------------------------------------------------

def test_discover_notifies_once_for_unknown_diff(tmp_path, monkeypatch, post):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.example/hook")
    html = _page([("新市", "https://www.city.new.lg.jp/a.html")], filler=100)
    known = "domains:\n" + "".join(f"  city.filler{i}.lg.jp: {{status: pending}}\n" for i in range(100))
    rc = discover(notify=True, fetcher=FakeFetcher({ENV_URL: html}), sources=[],
                  known_path=_known_file(tmp_path, known))
    assert rc == 0
    assert len(post.sent) == 1
    assert "新しい自治体 1 件" in post.sent[0] and "新市" in post.sent[0]


def test_discover_does_not_send_when_no_unknown_diff(tmp_path, monkeypatch, post):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.example/hook")
    html = _page([], filler=100)
    known = "domains:\n" + "".join(f"  city.filler{i}.lg.jp: {{status: pending}}\n" for i in range(100))
    rc = discover(notify=True, fetcher=FakeFetcher({ENV_URL: html}), sources=[],
                  known_path=_known_file(tmp_path, known))
    assert rc == 0
    assert post.sent == []


def test_discover_without_notify_flag_never_sends(tmp_path, monkeypatch, post):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.example/hook")
    html = _page([("新市", "https://www.city.new.lg.jp/a.html")], filler=100)
    rc = discover(fetcher=FakeFetcher({ENV_URL: html}), sources=[], known_path=_known_file(tmp_path, "domains: {}\n"))
    assert rc == 0
    assert post.sent == []


def test_discover_without_webhook_only_prints(tmp_path, monkeypatch, post, capsys):
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    html = _page([("新市", "https://www.city.new.lg.jp/a.html")], filler=100)
    rc = discover(notify=True, fetcher=FakeFetcher({ENV_URL: html}), sources=[],
                  known_path=_known_file(tmp_path, "domains: {}\n"))
    assert rc == 0
    assert post.sent == []
    out = capsys.readouterr().out
    assert "新市" in out and "DISCORD_WEBHOOK_URL" in out


# --- リンク集が取れない・形が変わった -------------------------------------------------------

def test_discover_fetch_failure_returns_1_and_sends_one(tmp_path, monkeypatch, post):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.example/hook")
    rc = discover(notify=True, fetcher=FakeFetcher({}, status={ENV_URL: 404}), sources=[],
                  known_path=_known_file(tmp_path, "domains: {}\n"))
    assert rc == 1
    assert len(post.sent) == 1 and "HTTP 404" in post.sent[0]


def test_discover_too_few_links_is_structure_change(tmp_path, monkeypatch, post):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.example/hook")
    html = _page([("新市", "https://www.city.new.lg.jp/a.html")], filler=3)   # 4 ドメインだけ
    rc = discover(notify=True, fetcher=FakeFetcher({ENV_URL: html}), sources=[],
                  known_path=_known_file(tmp_path, "domains: {}\n"))
    assert rc == 1
    assert len(post.sent) == 1
    assert "4 ドメイン" in post.sent[0]
    assert "新市" not in post.sent[0]   # 形が変わったときは差分を出さない（全部「消えた」扱いの誤報を防ぐ）


def test_discover_fetch_failure_without_notify_does_not_send(tmp_path, monkeypatch, post):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.example/hook")
    rc = discover(fetcher=FakeFetcher({}, status={ENV_URL: 503}), sources=[],
                  known_path=_known_file(tmp_path, "domains: {}\n"))
    assert rc == 1
    assert post.sent == []


# --- repo の確認済み一覧（2026-10-05 のリンク集で通知すべき差分 0 件） -------------------------

def test_repo_known_covers_20261005_diff():
    html = (FIXTURES / "t518_env_link_20261005.html").read_text(encoding="utf-8")
    d = compute(env_links(html), load_sources(), load_known())
    assert d.unknown_new == {} and d.unknown_gone == []   # 件数は台帳に足すと減るので見ない（T519）


def test_repo_known_is_consistent_with_registry():
    """pending / excluded は台帳に無いドメインだけ（台帳に足したら known から外す）。covered の slugs は台帳にある。"""
    sources = load_sources()
    reg_domains = {dmod._domain(s.url) for s in sources}
    slugs = {s.slug for s in sources}
    for domain, k in load_known().items():
        if k.status in ("pending", "excluded"):
            assert domain not in reg_domains, f"{domain} は台帳に入った。discover_known.yaml から外す"
        if k.status == "covered":
            assert k.slugs, f"{domain}: covered には slugs が要る"
            assert set(k.slugs) <= slugs, f"{domain}: 台帳に無い slug {set(k.slugs) - slugs}"


def test_env_links_ignores_non_http_links():
    """javascript:・mailto:・tel: のリンクは空のドメインとして数えない（「新しい自治体」の誤報になる。2026-10-05 公開前レビュー F-03）。"""
    html = ('<a href="javascript:void(0)">戻る</a><a href="mailto:info@env.example">メール</a><a href="tel:0000">電話</a>'
            '<a href="https://www.city.example.lg.jp/a.html">例市</a>')
    assert list(env_links(html)) == ["city.example.lg.jp"]
