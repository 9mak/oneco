"""T656 直し 1 回目・項目 9（2026-11-20・ネットワークなし）: 写真の許諾の返事の記録を台帳の note の先頭に足した。

公開サイトの表示は変わらない（photo はもともと ok）。あとで「返事のあった掲載元」を機械的に数えられるように、note の先頭に
「<日付> <相手>から、… と返事（T630）。」を 1 文で置く（city_kawasaki-1・city_morioka-1 と同じ書き方）。経過は ccc の outputs/t630/log.md。
"""

from pathlib import Path

import pytest
import yaml
from collector.registry import load_sources

ROOT = Path(__file__).resolve().parent.parent
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}
RAW = yaml.safe_load((ROOT / "registry" / "sources.yaml").read_text(encoding="utf-8"))["sources"]
NOTES = {d["slug"]: d.get("note") or "" for d in RAW}

REPLIES = {
    **{f"yokosuka_doubutu-{i}": "2026-10-22 横須賀市動物愛護センターから、示した表示方法で写真を表示してよいと返事（T630）。" for i in range(1, 7)},
    "city_kawaguchi-1": "2026-10-23 川口市保健所から、写真を表示してよいと返事（T630）。",
    "city_kawaguchi-2": "2026-10-23 川口市保健所から、写真を表示してよいと返事（T630）。",
    "city_fukushima-1": "2026-10-23 福島市保健所から、示した方法で掲載してよいと返事（T630）。",
    "city_fukushima-2": "2026-10-23 福島市保健所から、示した方法で掲載してよいと返事（T630）。",
    "ikutopia-1": "2026-10-27 新潟市動物ふれあいセンターから、示した掲載方法で問題ないと返事（T630）。",
    "pref_shimane": "2026-10-27 松江保健所から、掲載・表示方法とも問題ないと返事（T630）。",
    "pref_shimane-2": "2026-10-27 松江保健所から、掲載・表示方法とも問題ないと返事（T630）。",
}


@pytest.mark.parametrize("slug", sorted(REPLIES))
def test_reply_is_the_first_sentence_of_the_note(slug):
    assert NOTES[slug].startswith(REPLIES[slug]), slug
    assert SOURCES[slug].photo == "ok" and SOURCES[slug].enabled, slug      # 表示は変わらない
    assert NOTES[slug].count("返事（T630）") == 1, slug                      # 二重に足さない


def test_existing_notes_are_kept_after_the_reply():
    # 後ろに元の note が残る（ikutopia-1・島根の「掲載元ページに…が無いので外した」の記録を消さない）
    assert "2026-10-18 掲載元ページに所在地が無いので外した" in NOTES["ikutopia-1"]
    assert "2026-10-18 掲載元ページに電話が無いので外した" in NOTES["pref_shimane"]
    assert "2026-10-18 掲載元ページに電話が無いので外した" in NOTES["pref_shimane-2"]
    assert "環境省リンク集から追加（2026-10-05 T519）" in NOTES["city_kawaguchi-1"]
    assert "環境省リンク集から追加（2026-10-05 T519）" in NOTES["city_fukushima-2"]


def test_no_personal_names_in_the_reply_notes():
    for slug in REPLIES:
        head = NOTES[slug][: len(REPLIES[slug])]
        assert "様" not in head and "さん" not in head, slug


FIXED = ["hokkaido_okhotsk-4", "hokkaido_okhotsk-5", "hokkaido_okhotsk-6", "hokkaido_sorachi-1", "hokkaido_ishikari-2",
         "hokkaido_hidaka-1", "hokkaido_kamikawa-2", "pref_iwate_kuji", "pref_iwate_oshu", "pref_iwate_chubu",
         "pref_gunma-1", "city_matsumoto-1"]


@pytest.mark.parametrize("slug", FIXED)
def test_fixed_sources_record_what_was_fixed_and_when(slug):
    # 何を・いつ・なぜ直したかを note に残す（kamikawa-2 は link_only から recipe にした記録）
    assert "T656" in NOTES[slug], slug
    assert "2026-11-20" in NOTES[slug], slug
