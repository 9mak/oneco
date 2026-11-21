"""W006 T630 北海道（環境生活部自然環境局自然環境課）の返事（2026-11-20）。

各振興局の犬猫情報のページについて、道のフォームからまとめてお伺いした（2026-11-12）。
返事: 保健所等のウェブサイトへのリンクを載せることは問題ない。一方、公開している文章や画像等の
転載・複製・再利用は、掲載後の情報を継続的に確認することが難しいため、希望に沿うことが難しい。

→ 道のサイト（*.pref.hokkaido.lg.jp）の掲載元 42 件は、写真も文字も載せずリンクだけにする。
  レシピは許諾が変わったときのために残す（久留米市・福岡市と同じ）。
  札幌市・旭川市・函館市・小樽市など、道以外が運営するサイトの掲載元は対象外。
"""

from pathlib import Path
from urllib.parse import urlparse

import pytest
import yaml
from collector.registry import load_sources
from collector.run import collect_one

ROOT = Path(__file__).resolve().parent.parent
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}
RAW = yaml.safe_load((ROOT / "registry" / "sources.yaml").read_text(encoding="utf-8"))["sources"]
NOTES = {d["slug"]: d.get("note") or "" for d in RAW}


def _on_pref_site(url: str) -> bool:
    return urlparse(url).netloc.endswith(".pref.hokkaido.lg.jp")


PREF = sorted(s.slug for s in SOURCES.values() if _on_pref_site(s.url))

# 2026-11-20 の時点でレシピを持っていた 33 件（残りの 9 件は前から link_only でレシピなし）
HAD_RECIPE = [
    "hokkaido_hidaka-1", "hokkaido_hidaka-2", "hokkaido_hiyama-1", "hokkaido_iburi-1", "hokkaido_iburi-3",
    "hokkaido_ishikari-1", "hokkaido_ishikari-2", "hokkaido_ishikari-3", "hokkaido_kamikawa-1",
    "hokkaido_kamikawa-3", "hokkaido_kamikawa-4", "hokkaido_kushiro-1", "hokkaido_kushiro-2",
    "hokkaido_nemuro-1", "hokkaido_nemuro-2", "hokkaido_okhotsk-1", "hokkaido_okhotsk-2",
    "hokkaido_okhotsk-3", "hokkaido_okhotsk-4", "hokkaido_okhotsk-5", "hokkaido_okhotsk-6",
    "hokkaido_oshima-1", "hokkaido_oshima-2", "hokkaido_oshima-3", "hokkaido_rumoi-1",
    "hokkaido_shiribeshi-1", "hokkaido_shiribeshi-2", "hokkaido_sorachi-1", "hokkaido_sorachi-4",
    "hokkaido_souya-1", "hokkaido_souya-2", "hokkaido_tokachi-1", "hokkaido_tokachi-2",
]


class _NoFetch:
    def get(self, *a, **k):
        raise AssertionError("link_only のページを取得しようとした")


def test_every_pref_page_is_in_scope():
    assert len(PREF) == 42
    # hokkaido_ で始まる掲載元は全部が道のサイトで、道のサイトの掲載元は全部が hokkaido_
    assert PREF == sorted(k for k in SOURCES if k.startswith("hokkaido_"))


@pytest.mark.parametrize("slug", PREF)
def test_link_only_without_photo(slug):
    s = SOURCES[slug]
    assert (s.mode, s.photo, s.enabled) == ("link_only", "no", True)
    assert "2026-11-20" in NOTES[slug] and "T630" in NOTES[slug] and "転載" in NOTES[slug]


@pytest.mark.parametrize("slug", HAD_RECIPE)
def test_recipes_are_kept_for_a_future_permission(slug):
    s = SOURCES[slug]
    assert s.recipe_path is not None and s.recipe_path.exists()


@pytest.mark.parametrize("slug", PREF)
def test_collect_does_not_fetch(slug):
    assert collect_one(SOURCES[slug], _NoFetch()).status == "link_only"


def test_other_operators_in_hokkaido_are_untouched():
    others = {s.slug: s for s in SOURCES.values() if s.prefecture == "北海道" and not _on_pref_site(s.url)}
    for slug in ("city_sapporo-1", "city_sapporo-4", "spec_douaicenter-1", "city_hakodate-1", "city_otaru-1"):
        assert slug in others
        assert others[slug].mode == "recipe", slug
    assert all("2026-11-20 北海道" not in NOTES[k] for k in others)
