"""ops/verify_registry.py: 台帳の電話・所在地を元ページで突合する道具（W006 T616）。ネットワークは使わず fetch を差し替える。"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ops"))

import verify_registry as vr
from collector.registry import Source, load_sources


def page(body: str, links: str = "") -> str:
    return f"<html><head><style>.a{{}}</style><script>var t='03-0000-0000';</script></head><body>{body}{links}</body></html>"


def make_fetch(pages: dict[str, str], calls: list[str] | None = None):
    def fetch(url: str) -> vr.Fetched:
        if calls is not None:
            calls.append(url)
        if url in pages:
            return vr.Fetched(url=url, html=pages[url], error=None)
        return vr.Fetched(url=url, html=None, error="HTTP 404")

    return fetch


# --- 正規化 ---

def test_digits_fullwidth_hyphens_parens_spaces():
    assert vr.digits("０５９－３５２－０６１３") == "0593520613"
    assert vr.digits("(059) 352‐0613") == "0593520613"
    assert vr.digits("059ー352ー0613") == "0593520613"


def test_address_head_kanji_chome_and_ban_go():
    # 台帳「2番2号」とページ「２-２」、「二丁目」と「2丁目」が同じになる
    assert vr.address_head("三重県四日市市諏訪町2番2号（総合会館4F）") == "四日市市諏訪町2-2"
    assert "四日市市諏訪町2-2" in vr.normalize_text("四日市市諏訪町２－２")
    assert vr.address_head("東京都府中市南町2丁目15番20号") == "府中市南町2-15"
    assert "府中市南町2-15" in vr.normalize_text("府中市南町二丁目15番地20")
    assert "南町1-" in vr.normalize_text("府中市南町一丁目")
    # 町名の漢数字（二番町など）は数値化しない
    assert "二番町" in vr.normalize_text("千代田区二番町")


def test_address_head_without_number_is_whole():
    assert vr.address_head("東京都千代田区") == "千代田区"


# --- 判定 ---

def test_phone_and_address_found_on_entry_page():
    pages = {"http://x/": page("<p>電話：０５９－３５２－０６１３</p><p>所在地 三重県四日市市諏訪町２番２号</p>")}
    r = vr.verify_group(make_fetch(pages), "http://x/", "059-352-0613", "三重県四日市市諏訪町2番2号（総合会館4F）")
    assert (r.phone_found, r.address_found) == (True, True)
    assert r.evidence_url == "http://x/"
    assert vr.classify(r) == "match"


def test_script_text_is_ignored():
    pages = {"http://x/": page("<p>なし</p>")}  # script 内に 03-0000-0000 がある
    r = vr.verify_group(make_fetch(pages), "http://x/", "03-0000-0000", None)
    assert r.phone_found is False


def test_found_on_followed_link_same_host_only():
    links = (
        '<a href="/contact/">お問い合わせ</a>'
        '<a href="http://other.example/contact">連絡先</a>'
        '<a href="/news/">お知らせ</a>'
    )
    pages = {
        "http://x/": page("<p>トップ</p>", links),
        "http://x/contact/": page("<p>TEL 059-352-0613</p>"),
        "http://other.example/contact": page("<p>059-352-0613</p>"),
    }
    calls: list[str] = []
    r = vr.verify_group(make_fetch(pages, calls), "http://x/", "059-352-0613", None)
    assert r.phone_found is True
    assert r.evidence_url == "http://x/contact/"
    assert "http://other.example/contact" not in calls


def test_follow_at_most_three_links():
    links = "".join(f'<a href="/c{i}">連絡先{i}</a>' for i in range(6))
    pages = {"http://x/": page("<p>x</p>", links)}
    calls: list[str] = []
    r = vr.verify_group(make_fetch(pages, calls), "http://x/", "059-352-0613", None)
    assert r.phone_found is False
    assert len(calls) == 1 + 3
    assert vr.classify(r) == "mismatch"


def test_href_keyword_match_and_stop_when_all_found():
    links = '<a href="/about/access.html">地図</a><a href="/contact">問合せ</a>'
    pages = {
        "http://x/": page("<p>x</p>", links),
        "http://x/about/access.html": page("<p>059-352-0613</p>"),
        "http://x/contact": page("<p>zzz</p>"),
    }
    calls: list[str] = []
    r = vr.verify_group(make_fetch(pages, calls), "http://x/", "059-352-0613", None)
    assert r.phone_found and calls == ["http://x/", "http://x/about/access.html"]


def test_partial_and_mismatch_with_nearby_values():
    pages = {"http://x/": page("<p>電話 059-111-9999</p><p>四日市市諏訪町9番9号</p>")}
    r = vr.verify_group(make_fetch(pages), "http://x/", "059-352-0613", "三重県四日市市諏訪町2番2号")
    assert (r.phone_found, r.address_found) == (False, False)
    assert vr.classify(r) == "mismatch"
    assert "059-111-9999" in r.nearby_phones
    assert any("諏訪町9-9" in a for a in r.nearby_addresses)
    pages = {"http://x/": page("<p>059-352-0613</p>")}
    r = vr.verify_group(make_fetch(pages), "http://x/", "059-352-0613", "三重県四日市市諏訪町2番2号")
    assert vr.classify(r) == "partial"


def test_unfetchable_and_no_data():
    r = vr.verify_group(make_fetch({}), "http://x/", "059-352-0613", None)
    assert vr.classify(r) == "unfetchable"
    assert "404" in r.reason
    r = vr.verify_group(make_fetch({}), "http://x/", None, None)
    assert vr.classify(r) == "no_data"


def test_only_phone_set_counts_as_match():
    pages = {"http://x/": page("<p>059-352-0613</p>")}
    r = vr.verify_group(make_fetch(pages), "http://x/", "059-352-0613", None)
    assert r.address_found is None and vr.classify(r) == "match"


def test_town_level_match_when_page_omits_city_name():
    # ページが「柏市」を省いて「風早2-4-3」とだけ書く場合は、町名＋番地で一致扱い（address_match="town"）
    pages = {"http://x/": page("<p>〒277-0924 風早二丁目4番地3 電話 04-7190-2828</p>")}
    r = vr.verify_group(make_fetch(pages), "http://x/", "04-7190-2828", "千葉県柏市風早二丁目4番地3（〒277-0924、センター）")
    assert r.address_found is True and r.address_match == "town"
    pages = {"http://x/": page("<p>柏市風早2-4-3</p>")}
    r = vr.verify_group(make_fetch(pages), "http://x/", None, "千葉県柏市風早二丁目4番地3")
    assert r.address_match == "full"
    pages = {"http://x/": page("<p>風早2-5</p>")}
    assert vr.verify_group(make_fetch(pages), "http://x/", None, "千葉県柏市風早二丁目4番地3").address_found is False


# --- 全体 ---

def sources() -> list[Source]:
    def s(slug, url, phone="059-352-0613", address="三重県四日市市諏訪町2番2号"):
        return Source(slug=slug, name=slug, municipality="四日市市", prefecture="三重県", url=url,
                      kind="adoption", phone=phone, address=address)
    return [s("a_1", "http://x/1"), s("a_2", "http://x/2"), s("b_1", "http://x/3", phone="059-000-0000")]


def test_same_group_fetched_once_and_shared():
    pages = {"http://x/1": page("<p>059-352-0613 四日市市諏訪町2-2</p>"), "http://x/3": page("<p>x</p>")}
    calls: list[str] = []
    res = vr.run(sources(), make_fetch(pages, calls), workers=1, today="2026-10-15")
    assert calls.count("http://x/1") == 1 and "http://x/2" not in calls
    assert res["a_1"].phone_found and res["a_2"].phone_found
    assert res["a_2"].evidence_url == "http://x/1"
    assert vr.classify(res["b_1"]) == "mismatch"
    summ = vr.summarize(res)
    assert summ["match"] == 2 and summ["mismatch"] == 1 and summ["total"] == 3


# --- 書き戻し ---

YAML_TEXT = """# 台帳のコメント
sources:
- slug: a_1
  name: A
  municipality: 四日市市
  prefecture: 三重県
  phone: 059-352-0613
  address: 三重県四日市市諏訪町2番2号
  url: http://x/1
  kind: adoption
  # 途中のコメント
  enabled: true
- slug: b_1
  name: B
  municipality: 四日市市
  prefecture: 三重県
  phone: 059-000-0000
  address: null
  url: http://x/3
  kind: adoption
  verified_at: '2020-01-01'
  verified_url: http://old/
  enabled: true
"""


def test_write_back_keeps_comments_and_order(tmp_path):
    p = tmp_path / "sources.yaml"
    p.write_text(YAML_TEXT, encoding="utf-8")
    pages = {"http://x/1": page("<p>059-352-0613 四日市市諏訪町2-2</p>"), "http://x/3": page("<p>059-000-0000</p>")}
    srcs = load_sources(p)
    res = vr.run(srcs, make_fetch(pages), workers=1, today="2026-10-15")
    n = vr.write_back(p, res, "2026-10-15")
    assert n == 2
    new = p.read_text(encoding="utf-8")
    assert "# 台帳のコメント" in new and "  # 途中のコメント" in new
    assert new.index("slug: a_1") < new.index("slug: b_1")
    data = yaml.safe_load(new)["sources"]
    assert data[0]["verified_at"] == "2026-10-15"
    assert data[0]["verified_phone_url"] == "http://x/1" and data[0]["verified_address_url"] == "http://x/1"
    # address が null の entry は電話だけ検証（address 側の根拠は書かない）
    assert data[1]["verified_at"] == "2026-10-15" and data[1]["verified_phone_url"] == "http://x/3"
    assert "verified_address_url" not in data[1] and "verified_url" not in data[1]
    assert new.count("verified_at") == 2  # 既存行は置換で重複しない
    old = yaml.safe_load(YAML_TEXT)["sources"]
    for o, nw in zip(old, data, strict=True):
        for k, v in o.items():
            if not k.startswith("verified"):
                assert nw[k] == v
    # 読み込みも通る（日付は文字列）
    assert load_sources(p)[0].verified_at == "2026-10-15"


def test_phone_requires_boundaries():
    want = "059-352-0613"
    for body, expect in [
        ("TEL059-352-0613", True), ("(059)352-0613", True), ("０５９ ３５２ ０６１３", True), ("0593520613", True),
        ("1059-352-0613", False),      # 左に数字が続く
        ("059-352-06130", False),      # 右に数字が続く
        ("0059-352-0613", False),
        ("059-352-0613-5", False),     # 続きがある別番号
        ("日付2026059352 0613", False),  # 数字列の途中に偶然含まれるだけ
    ]:
        r = vr.verify_group(make_fetch({"http://x/": page(f"<p>{body}</p>")}), "http://x/", want, None)
        assert r.phone_found is expect, body


def test_town_match_needs_left_boundary_and_is_not_writable():
    addr = "千葉県柏市風早二丁目4番地3"
    ok = vr.verify_group(make_fetch({"http://x/": page("<p>所在地 風早2-4-3</p>")}), "http://x/", None, addr)
    assert ok.address_match == "town" and ok.address_found is True
    ok = vr.verify_group(make_fetch({"http://x/": page("<p>〒277-0924 風早2-4-3</p>")}), "http://x/", None, addr)
    assert ok.address_found is True
    for body in ("12風早2-4-3", "東風早2-4-3"):
        bad = vr.verify_group(make_fetch({"http://x/": page(f"<p>{body}</p>")}), "http://x/", None, addr)
        assert bad.address_found is False, body
    assert vr.verified_urls(ok) is None  # town は書き戻さない


def test_write_back_skips_town_only(tmp_path):
    p = tmp_path / "sources.yaml"
    p.write_text(YAML_TEXT.replace("諏訪町2番2号", "諏訪町2番2号"), encoding="utf-8")
    res = vr.run(load_sources(p), make_fetch({"http://x/1": page("<p>059-352-0613 諏訪町2-2</p>")}), workers=1, today="2026-10-15")
    assert res["a_1"].address_match == "town"
    assert vr.write_back(p, res, "2026-10-15") == 0


def test_parse_failure_is_unfetchable(monkeypatch):
    def boom(html, base):
        raise ValueError("broken")

    monkeypatch.setattr(vr, "parse_html", boom)
    r = vr.verify_group(make_fetch({"http://x/": "<html></html>"}), "http://x/", "059-352-0613", None)
    assert vr.classify(r) == "unfetchable" and "broken" in r.reason


def test_write_back_skips_non_match(tmp_path):
    p = tmp_path / "sources.yaml"
    p.write_text(YAML_TEXT, encoding="utf-8")
    res = vr.run(load_sources(p), make_fetch({}), workers=1, today="2026-10-15")
    assert vr.write_back(p, res, "2026-10-15") == 0
    assert p.read_text(encoding="utf-8") == YAML_TEXT
