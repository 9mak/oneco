"""W006 T656 付随・項目 1: 個人の携帯電話番号とメールアドレスを公開しない（2026-11-20）。

長崎犬猫ネット 一般譲渡（animal_net_nagasaki-2）は個人・ボランティアの掲示で、備考に「TEL:090-… メール:…@gmail.com」が
そのまま入り、公開の data.json に載っていた。台帳の決まり（松本市「個人の連絡先は取り込まない」、富山市 -2 はリンクのみ）に
合わせ、収集の段階（collector/extract.py の build）で、行から作る全部の文字の項目から携帯・メールを置き換える。
固定電話（自治体・保健所の番号）は消さない。fixture は実ページ（2026-11-20 の last_ok）の番号とメールだけ伏せ字にした写し
（090-0000-0000 / masked@example.jp。test_fixtures_pii_guard が許す形）。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from collector.extract import CONTACT_REDACTED, mask_contacts
from collector.fetch import FakeFetcher
from collector.registry import load_sources
from collector.run import collect_one

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}
NAG = "https://animal-net.pref.nagasaki.jp"
REAL_MOBILE = re.compile(r"(?<![0-9])0[5789]0[-‐−\s.]?[0-9]{4}[-‐−\s.]?[0-9]{4}(?![0-9])")
REAL_MAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")


def _fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _nag2_pages() -> dict[str, str]:
    pages = {f"{NAG}/jyouto/?animal-type={t}": _fx(f"w006_animal_net_nagasaki-2_list_{t}_20261120.html") for t in ("dog", "cat", "others")}
    for no in ("20166", "20165", "20215"):
        pages[f"{NAG}/animal/no-{no}/"] = _fx(f"w006_animal_net_nagasaki-2_no{no}_20261120.html")
    return pages


def test_mask_contacts_replaces_mobile_and_email_but_keeps_the_rest():
    text = "・TEL:090-9998-6582 ・メール:someone.x@gmail.com ★InstagramのDMからでもOK!"
    out, n = mask_contacts(text)
    assert out == f"・TEL:{CONTACT_REDACTED} ・メール:{CONTACT_REDACTED} ★InstagramのDMからでもOK!"
    assert n == 2


@pytest.mark.parametrize("raw", [
    "090-1234-5678", "09012345678", "090 1234 5678", "080.1234.5678", "070-1234-5678", "050-1234-5678",
    "０９０－１２３４－５６７８", "090−1234−5678",
    "a.b+c@example.co.jp", "taro＠gmail.com", "taro(at)gmail.com", "taro[at]gmail.com",
])
def test_mask_contacts_forms(raw: str):
    out, n = mask_contacts(f"連絡は {raw} まで")
    assert out == f"連絡は {CONTACT_REDACTED} まで" and n == 1


@pytest.mark.parametrize("keep", [
    "095-895-2364", "03-3302-3507", "0120-123-456", "0570-123-456", "06-1234-5678", "管理番号 20260123456789",
    "LINE:@020hgkww", "(@mel.tema.cheer.nk /長崎ねこはぴ)", "体重 3.5kg 2026-11-20", "1090-1234-5678",
])
def test_mask_contacts_leaves_landlines_ids_and_non_mail_alone(keep: str):
    assert mask_contacts(keep) == (keep, 0)


def test_mask_contacts_none_and_empty():
    assert mask_contacts(None) == (None, 0)
    assert mask_contacts("") == ("", 0)


def test_nagasaki_2_public_fields_have_no_mobile_or_email():
    c = collect_one(SOURCES["animal_net_nagasaki-2"], FakeFetcher(_nag2_pages()))
    assert c.status == "ok", c.error
    by = {a["management_no"]: a for a in c.result.animals}
    assert set(by) == {"20166", "20165", "20215"}
    for a in c.result.animals:
        for k, v in a.items():
            if k in ("phone", "address") or not isinstance(v, str):
                continue
            assert not REAL_MOBILE.search(v) and not REAL_MAIL.search(v), (a["management_no"], k, v)
    for no in ("20166", "20165"):
        note = by[no]["note"]
        assert CONTACT_REDACTED in note
        assert "医療費等の御負担にご協力をお願いしております" in note      # ほかの文はそのまま
        assert "InstagramのDMからでもOK" in note
        assert "@mel.tema.cheer.nk" in note                              # Instagram の公開名は連絡先の番号・メールではない（残す）
    assert CONTACT_REDACTED not in (by["20215"]["note"] or "")


def test_nagasaki_2_counts_the_replacements_and_ids_do_not_change():
    c = collect_one(SOURCES["animal_net_nagasaki-2"], FakeFetcher(_nag2_pages()))
    assert c.result.contacts_masked == 4          # 2 頭 × （携帯 1・メール 1）
    # 台帳の電話（095-895-2364・県の窓口）は消さない
    assert {a["phone"] for a in c.result.animals} == {"095-895-2364"}
    assert len({a["id"] for a in c.result.animals}) == 3


def test_run_records_the_count_in_report_but_not_in_the_published_sources(tmp_path):
    import json

    from collector import run as run_mod

    src = SOURCES["animal_net_nagasaki-2"]
    out = run_mod.run([src], "2026-11-20", out_dir=tmp_path, fetcher=FakeFetcher(_nag2_pages()), enabled=False)
    report = json.loads((tmp_path / "report-2026-11-20.json").read_text(encoding="utf-8"))
    assert report[0]["contacts_masked"] == 4
    assert "contacts_masked" not in out["sources"][0]
    latest = (tmp_path / "latest.json").read_text(encoding="utf-8")
    assert not REAL_MOBILE.search(latest) and "gmail.com" not in latest
