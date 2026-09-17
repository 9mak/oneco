"""full_publication_audit.py の純粋ロジックのテスト (T140)

run_audit は全サイトへの実 HTTP fetch と adapter 実行を伴う一回性スクリプトのため
単体テスト対象にせず、sites.yaml から週次カウント監査 (scripts/site_count_audit.py,
T105) の盲点ホストを静的に判定する count_audit_blind_hosts だけをここで固定する
(test_publication_audit.py と同じ分離方針)。

判定は site_count_audit.py の group_and_flag の comparable 条件と対になっている。
向きが逆 (あちらは comparable=True の条件、こちらは False になる条件) なので、
片方だけ直すと静かにズレる。両者を変更するときは必ず対で見ること。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import full_publication_audit as fpa  # noqa: E402


def _site(host: str, path: str = "/list", **overrides) -> dict:
    base = {"name": f"{host}{path}", "list_url": f"https://{host}{path}"}
    base.update(overrides)
    return base


class TestCountAuditBlindHosts:
    def test_empty(self):
        assert fpa.count_audit_blind_hosts([]) == set()

    def test_host_with_all_selectors_is_not_blind(self):
        sites = [
            _site("a.example.jp", "/dog", list_link_pattern="a[href*='/detail/']"),
            _site("a.example.jp", "/cat", list_link_pattern="a[href*='/detail/']"),
        ]
        assert fpa.count_audit_blind_hosts(sites) == set()

    def test_host_without_selector_is_blind(self):
        sites = [_site("b.example.jp")]
        assert fpa.count_audit_blind_hosts(sites) == {"b.example.jp"}

    def test_one_missing_selector_drags_down_whole_host(self):
        """comparable 判定はホスト単位なので、同居サイトが1件でも欠けると巻き添えになる"""
        sites = [
            _site("c.example.jp", "/dog", list_link_pattern="a[href*='/detail/']"),
            _site("c.example.jp", "/cat"),
        ]
        assert fpa.count_audit_blind_hosts(sites) == {"c.example.jp"}

    def test_pdf_selector_makes_host_blind(self):
        """PDF セレクタはリンク先 PDF 内の頭数を数えられないため掲載数比較に使えない"""
        sites = [_site("d.example.jp", pdf_link_pattern="a[href$='.pdf']")]
        assert fpa.count_audit_blind_hosts(sites) == {"d.example.jp"}

    def test_pdf_selector_drags_down_sibling_with_list_selector(self):
        sites = [
            _site("e.example.jp", "/dog", list_link_pattern="a[href*='/detail/']"),
            _site("e.example.jp", "/cat", pdf_link_pattern="a[href$='.pdf']"),
        ]
        assert fpa.count_audit_blind_hosts(sites) == {"e.example.jp"}

    def test_requires_js_makes_host_blind(self):
        sites = [
            _site(
                "f.example.jp",
                list_link_pattern="a[href*='/detail/']",
                requires_js=True,
            )
        ]
        assert fpa.count_audit_blind_hosts(sites) == {"f.example.jp"}

    def test_blind_and_clean_hosts_are_separated(self):
        sites = [
            _site("g.example.jp", list_link_pattern="a[href*='/detail/']"),
            _site("h.example.jp"),
        ]
        assert fpa.count_audit_blind_hosts(sites) == {"h.example.jp"}

    def test_real_sites_yaml_majority_is_blind(self):
        """実データでの回帰固定。T133 実測で 93 ホスト中 80 ホストが盲点だった。

        adapter 実装やセレクタ登録が進めばこの数は減るはずなので、増えた場合は
        監査カバレッジが後退したことを意味する。
        """
        blind = fpa.count_audit_blind_hosts(fpa.load_sites_yaml())
        assert len(blind) <= 80


class TestBuildSiteConfig:
    def test_every_site_matches_production_loader(self):
        """T416: 監査が adapter に渡す SiteConfig は本番の収集と同じ値でなければならない

        以前は sites.yaml の一部の項目だけを手で写していたため、phone (68 サイト)・
        default_species (愛媛県・収容中)・fields などが落ち、愛媛県 (収容中) の species が
        本番「犬」に対し監査側「その他」になった。本番と違う値で突き合わせると、
        致命フィールドの誤検知や見逃しになる。
        """
        from data_collector.llm.config import SiteConfigLoader

        production = {
            site.name: site.model_dump()
            for site in SiteConfigLoader.load(
                fpa.ROOT / "src/data_collector/config/sites.yaml"
            ).sites
        }

        mismatched = [
            raw["name"]
            for raw in fpa.load_sites_yaml()
            if fpa.build_site_config(raw).model_dump() != production[raw["name"]]
        ]

        assert mismatched == []


class TestCollectSiteStableVirtualUrls:
    def test_positional_virtual_urls_are_rekeyed_like_production(self, monkeypatch):
        """T413: 本番の収集経路と同じく、掲載位置の仮想 URL を安定キーへ付け替えてから返す

        付け替えないと、公開 API (付け替え後の URL) と source_url で突き合わせたときに
        位置 URL のサイトが全頭「掲載漏れ疑い (adapter_only)」と「API のみ」に割れる。
        """
        from datetime import date

        from data_collector.domain.models import AnimalData

        page = "https://www.city.example.lg.jp/pet/search_cat.html"
        images = {
            f"{page}#h3=0": "https://www.city.example.lg.jp/img/260916mayoineko.jpg",
            f"{page}#h3=1": "https://www.city.example.lg.jp/img/210129mayoineko2.jpg",
        }

        class _PositionalAdapter:
            def __init__(self, site_config):
                pass

            def fetch_animal_list(self):
                return [(url, "lost") for url in images]

            def extract_animal_details(self, url, category):
                return url

            def normalize(self, url):
                return AnimalData(
                    species="猫",
                    shelter_date=date(2026, 9, 16),
                    location="東京都町田市",
                    source_url=url,
                    category="lost",
                    image_urls=[images[url]],
                )

        monkeypatch.setattr(fpa.SiteAdapterRegistry, "get", lambda name: _PositionalAdapter)

        # 本番の sites.yaml と同じく必須項目 (prefecture_code) をそろえる (T416 で監査も本番と同じ検証を通る)
        out = fpa.collect_site(
            {
                "name": "テストサイト（迷子猫）",
                "prefecture": "東京都",
                "prefecture_code": "13",
                "list_url": page,
            }
        )

        assert out["status"] == "ok"
        assert [a["source_url"] for a in out["animals"]] == [
            f"{page}#animal=260916mayoineko.jpg",
            f"{page}#animal=210129mayoineko2.jpg",
        ]
