"""W006 T630（写真表示のお伺いへの返事 2026-11-13〜16）。

熊本県（11/13 健康危機管理課 動物愛護班）: 表示してよい。センター・団体・個人の譲渡と迷子の 8 ページとも依頼に入れていて、条件は付いていない。
埼玉県（11/16 生活衛生課）: 11/07 に確かめた「個人保護」のページも写真を含めて掲載してよい。
越谷市（11/16 動物管理センター）: 「保健所収容動物の譲渡」のページは写真もリンクも可、
  「個人の方が保護している動物」のページは個人の方からの依頼による掲載なので使用を控えてほしい。
  個人保護は栃木・岐阜と同じく安全側で文字も外してリンクのみ。
  台帳で読んでいる「保護・収容した犬／猫の情報」（-1・-2）は返事で触れられていないので、確認が取れるまで pending のまま。
甲府市（11/16 衛生薬務課）: 写真は削除、所在地などの情報も転記せず市のページへのリンクで確認してもらう形に → リンクのみ。
"""

from pathlib import Path

import pytest
import yaml
from collector.registry import load_sources
from collector.run import collect_one

ROOT = Path(__file__).resolve().parent.parent
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}
NOTES = {
    d["slug"]: d.get("note") or ""
    for d in yaml.safe_load((ROOT / "registry" / "sources.yaml").read_text(encoding="utf-8"))["sources"]
}

KUMAMOTO = [f"kumamoto_doubutuaigo-{i}" for i in range(1, 9)]
SAITAMA_PERSONAL = [
    f"pref_saitama_{k}-2"
    for k in "nanbu asaka chichibu kazo kumagaya sakado center_honsho center_minami".split()
]
LINK_ONLY = ["city_koshigaya_kojin", "city_kofu-1", "city_kofu-2"]


class _NoFetch:
    def get(self, *a, **k):   # 読みに行ったら失敗にする
        raise AssertionError("link_only のページを取得しようとした")


def test_counts():
    assert len(KUMAMOTO) == 8 and len(SAITAMA_PERSONAL) == 8


@pytest.mark.parametrize("slug", KUMAMOTO + SAITAMA_PERSONAL)
def test_photo_ok(slug):
    s = SOURCES[slug]
    assert (s.mode, s.enabled, s.photo) == ("recipe", True, "ok")
    assert "2026-11-1" in NOTES[slug] and "T630" in NOTES[slug]


@pytest.mark.parametrize("slug", LINK_ONLY)
def test_link_only_without_photo(slug):
    s = SOURCES[slug]
    assert (s.mode, s.photo, s.enabled) == ("link_only", "no", True)
    assert s.recipe_path.exists()        # 許諾が変わったときのために残す
    assert "2026-11-16" in NOTES[slug]


@pytest.mark.parametrize("slug", LINK_ONLY)
def test_collect_does_not_fetch(slug):
    assert collect_one(SOURCES[slug], _NoFetch()).status == "link_only"


@pytest.mark.parametrize("slug", ["city_koshigaya-1", "city_koshigaya-2"])
def test_koshigaya_shuuyou_stays_pending(slug):
    # 返事は「保健所収容動物の譲渡」のページについてで、台帳のこのページには触れていない
    s = SOURCES[slug]
    assert (s.mode, s.enabled, s.photo) == ("recipe", True, "pending")
    assert "確認中" in NOTES[slug]
