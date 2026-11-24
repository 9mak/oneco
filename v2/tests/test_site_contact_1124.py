"""about の運営者を実名に、連絡の節をお問い合わせフォームへの案内に替え、/contact/ を作る（POLICY.md 方針 30 の変更。2026-11-24）。"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).parent / "fixtures"


def _load_build() -> Any:
    spec = importlib.util.spec_from_file_location("oneco_site_build_contact", ROOT / "site" / "build.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


B = _load_build()
CONFIG: dict[str, Any] = {"site_name": "oneco", "base_url": "https://oneco.pet", "affiliate": [],
                          "turnstile_sitekey": "0x4AAAAAAAtest"}


@pytest.fixture
def out(tmp_path: Path) -> Path:
    a = json.loads((FIX / "animals_saga.json").read_text(encoding="utf-8"))
    dist = tmp_path / "dist"
    B.build_site({"date": "2026-11-24", "animals": a["animals"], "sources": a["sources"]}, CONFIG, dist)
    return dist


def _soup(out: Path, rel: str) -> BeautifulSoup:
    return BeautifulSoup((out / rel).read_text(encoding="utf-8"), "lxml")


def test_about_operator_is_the_real_name(out: Path) -> None:
    h = (out / "about/index.html").read_text(encoding="utf-8")
    assert "oneco を運営している小熊 和喜です。" in h
    assert "GitHub: " not in h and "個人（" not in h
    assert "トリミングの専門学校を出て" in h and "ポムとは専門学校で" in h
    assert "サイトの中身と作業の記録は" in h and "GitHub リポジトリ" in h


def test_about_contact_section_points_to_the_form(out: Path) -> None:
    s = _soup(out, "about/index.html")
    h2 = s.select_one("h2#contact")
    assert h2 is not None and h2.get_text() == "掲載内容や運営について"
    assert s.select_one("#takedown") is None
    sec = h2.parent
    assert "写真や情報の掲載についてのご相談、内容の訂正、oneco へのご質問・ご意見は、お問い合わせフォームからお送りください。" in sec.get_text()
    cta = sec.select_one("a.cta")
    assert cta is not None and cta["href"] == "/contact/" and cta.get_text() == "フォームから問い合わせる"
    assert cta.get("target") is None
    assert "自治体のページから消えた子は、oneco からも翌日の更新で消えます。" in sec.get_text()
    txt = str(sec)
    assert txt.index("お問い合わせフォームからお送りください") < txt.index("フォームから問い合わせる") < txt.index("翌日の更新で消えます")
    h = (out / "about/index.html").read_text(encoding="utf-8")
    for gone in ("GitHub Issues", "/issues", "mailto:", "9mak.org", "GitHub アカウント（無料）", "自治体のご担当者様", "取り下げ"):
        assert gone not in h, gone
    desc = s.select_one('meta[name="description"]')["content"]
    assert desc.endswith("運営方針、お問い合わせについて。") and "取り下げ" not in desc


def test_footer_link_goes_to_contact(out: Path) -> None:
    for rel in ("index.html", "about/index.html", "contact/index.html", "404.html"):
        foot = _soup(out, rel).select_one("footer.site-foot")
        links = [(a.get_text(), a["href"]) for a in foot.select(".foot-links a")]
        assert links[2] == ("運営への問い合わせ", "/contact/"), rel


def test_contact_page_form(out: Path) -> None:
    s = _soup(out, "contact/index.html")
    assert s.title.get_text() == "お問い合わせ｜oneco"
    assert s.select_one("h1").get_text() == "お問い合わせ"
    assert s.select_one('meta[name="description"]')["content"] == \
        "写真や情報の掲載についてのご相談、内容の訂正、oneco へのご質問・ご意見をお送りください。"
    assert s.select_one('meta[name="robots"]') is None
    form = s.select_one("main form")
    assert form["method"].lower() == "post" and form["action"] == "/api/contact"

    def field(name: str) -> Any:
        el = form.select_one(f'[name="{name}"]')
        assert el is not None, name
        lab = form.select_one(f'label[for="{el["id"]}"]')
        assert lab is not None, name
        return el, lab.get_text(strip=True)

    el, lab = field("message")
    assert el.name == "textarea" and el.has_attr("required") and el["maxlength"] == "4000" and lab == "お問い合わせ内容（必須）"
    el, lab = field("page_url")
    assert el.name == "input" and el["type"] == "url" and el["maxlength"] == "500" and lab == "該当するページの URL（あれば）"
    el, lab = field("name")
    assert el["type"] == "text" and el["maxlength"] == "100" and lab == "お名前（任意）"
    el, lab = field("reply_to")
    assert el["type"] == "email" and el["maxlength"] == "254" and lab == "返信先のメールアドレス（返信が必要な場合）"
    assert "譲渡の申し込みや迷子の問い合わせは、各子のページにある自治体の問い合わせ先へ直接ご連絡ください。oneco ではお答えできません。" in s.get_text()
    ts = form.select_one("div.cf-turnstile")
    assert ts is not None and ts["data-sitekey"] == "0x4AAAAAAAtest"
    btn = form.select_one('button[type="submit"]')
    assert btn is not None and btn.get_text() == "送信する"
    scripts = [t for t in s.select("script[src]") if "challenges.cloudflare.com" in t["src"]]
    assert len(scripts) == 1 and scripts[0]["src"] == "https://challenges.cloudflare.com/turnstile/v0/api.js"
    assert scripts[0].has_attr("async") and scripts[0].has_attr("defer")


def test_turnstile_script_only_on_contact(out: Path) -> None:
    for p in out.rglob("*.html"):
        has = "challenges.cloudflare.com" in p.read_text(encoding="utf-8")
        assert has == (p == out / "contact/index.html"), p


def test_sitekey_defaults_to_empty(tmp_path: Path) -> None:
    cfg = {k: v for k, v in CONFIG.items() if k != "turnstile_sitekey"}
    dist = tmp_path / "d"
    B.build_site({"date": "2026-11-24", "animals": [], "sources": []}, cfg, dist)
    assert _soup(dist, "contact/index.html").select_one("div.cf-turnstile")["data-sitekey"] == ""


def test_sent_and_error_pages(out: Path) -> None:
    sent = _soup(out, "contact/sent/index.html")
    assert sent.title.get_text() == "お問い合わせ｜oneco" and sent.select_one("h1").get_text() == "お問い合わせ"
    assert "お問い合わせを受け付けました。内容を確認し、必要に応じて、ご記入のメールアドレスへ返信します。" in sent.select_one("main").get_text()
    err = _soup(out, "contact/error/index.html")
    assert err.title.get_text() == "お問い合わせ｜oneco" and err.select_one("h1").get_text() == "お問い合わせ"
    main = err.select_one("main")
    assert "送信できませんでした。時間をおいて、もう一度お試しください。" in main.get_text()
    link = main.select_one('a[href="/contact/"]')
    assert link is not None and link.get_text() == "お問い合わせ"
    for s in (sent, err):
        assert s.select_one('meta[name="robots"]')["content"] == "noindex"
        assert s.select_one("form") is None


def test_sitemap_has_contact_only(out: Path) -> None:
    sm = (out / "sitemap.xml").read_text(encoding="utf-8")
    assert "<loc>https://oneco.pet/contact/</loc>" in sm
    assert "/contact/sent/" not in sm and "/contact/error/" not in sm


def test_torisage_never_appears_in_public_pages(out: Path) -> None:
    for p in out.rglob("*"):
        if p.is_file() and p.suffix in {".html", ".xml", ".txt", ".json"}:
            assert "取り下げ" not in p.read_text(encoding="utf-8"), p


def test_old_config_keys_are_gone() -> None:
    assert "issues_url" not in B.DEFAULT_CFG and "contact_email" not in B.DEFAULT_CFG
    cfg = json.loads((ROOT / "site" / "config.json").read_text(encoding="utf-8"))
    assert "issues_url" not in cfg and "contact_email" not in cfg and cfg["turnstile_sitekey"] == ""
