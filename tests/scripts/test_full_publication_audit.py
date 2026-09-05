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
