"""publication_audit.py のテスト

HTTP 取得を除く純粋ロジック (sample_animals / classify_freshness /
extract_critical_fields / render_html のエスケープ) を検証する。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# scripts/ をパスに通して publication_audit を import
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import publication_audit as pa  # noqa: E402


def _animal(**overrides):
    base = {
        "id": 1,
        "species": "犬",
        "sex": "女の子",
        "age_months": None,
        "color": "黒",
        "size": "小型",
        "shelter_date": "2026-08-01",
        "location": "若松区",
        "prefecture": "福岡県",
        "phone": "093-581-1800",
        "image_urls": ["https://example.jp/a.jpg"],
        "source_url": "https://example.jp/animals/1",
        "category": "sheltered",
        "breed": "雑種",
        "name": None,
        "management_number": None,
        "description": None,
        "status": "sheltered",
        "last_collected_at": "2026-08-04T01:00:00Z",
    }
    base.update(overrides)
    return base


class TestSampleAnimals:
    def test_same_seed_gives_same_sample(self):
        animals = [_animal(id=i) for i in range(200)]
        a = pa.sample_animals(animals, 50, seed=42)
        b = pa.sample_animals(animals, 50, seed=42)
        assert [x["id"] for x in a] == [x["id"] for x in b]

    def test_different_seed_gives_different_sample(self):
        animals = [_animal(id=i) for i in range(200)]
        a = pa.sample_animals(animals, 50, seed=1)
        b = pa.sample_animals(animals, 50, seed=2)
        assert [x["id"] for x in a] != [x["id"] for x in b]

    def test_returns_n_unique_items(self):
        animals = [_animal(id=i) for i in range(200)]
        got = pa.sample_animals(animals, 50, seed=7)
        assert len(got) == 50
        assert len({x["id"] for x in got}) == 50

    def test_returns_all_when_population_smaller_than_n(self):
        animals = [_animal(id=i) for i in range(10)]
        got = pa.sample_animals(animals, 50, seed=7)
        assert len(got) == 10

    def test_returns_empty_for_empty_population(self):
        assert pa.sample_animals([], 50, seed=7) == []


class TestClassifyFreshness:
    def test_collected_on_base_date_is_fresh(self):
        a = _animal(last_collected_at="2026-08-04T01:00:00Z")
        assert pa.classify_freshness(a, "2026-08-04") == "fresh"

    def test_collected_before_base_date_is_stale(self):
        a = _animal(last_collected_at="2026-08-01T01:00:00Z")
        assert pa.classify_freshness(a, "2026-08-04") == "stale"

    def test_no_collection_record_is_unknown(self):
        assert pa.classify_freshness(_animal(last_collected_at=None), "2026-08-04") == "unknown"

    def test_collected_after_base_date_is_fresh(self):
        """収集は日次で走るため、基準日以降はすべて最新とみなす。"""
        a = _animal(last_collected_at="2026-08-05T01:00:00Z")
        assert pa.classify_freshness(a, "2026-08-04") == "fresh"


class TestExtractCriticalFields:
    def test_returns_critical_fields_in_order(self):
        got = pa.extract_critical_fields(_animal())
        assert [f["key"] for f in got] == list(pa.CRITICAL_FIELDS)

    def test_marks_empty_values_as_missing(self):
        got = {f["key"]: f for f in pa.extract_critical_fields(_animal(phone=None, image_urls=[]))}
        assert got["phone"]["missing"] is True
        assert got["image_urls"]["missing"] is True
        assert got["species"]["missing"] is False

    def test_marks_whitespace_only_as_missing(self):
        got = {f["key"]: f for f in pa.extract_critical_fields(_animal(location="   "))}
        assert got["location"]["missing"] is True

    def test_image_urls_display_includes_count(self):
        got = {f["key"]: f for f in pa.extract_critical_fields(_animal())}
        assert "1" in got["image_urls"]["display"]


class TestRenderHtml:
    def test_escapes_html_in_values(self):
        animals = [_animal(location="<script>alert(1)</script>")]
        html = pa.render_html(animals, seed=1, base_date="2026-08-04", site_base="https://x.test")
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html

    def test_links_to_both_source_and_public_page(self):
        animals = [_animal(id=99, source_url="https://muni.example.jp/a/1")]
        html = pa.render_html(animals, seed=1, base_date="2026-08-04", site_base="https://x.test")
        assert "https://muni.example.jp/a/1" in html
        assert "https://x.test/animals/99" in html

    def test_marks_broken_images(self):
        """画像が落ちていること自体が image_urls の誤りなので、見て分かるようにする。"""
        animals = [_animal(image_urls=["https://muni.example.jp/gone.jpg"])]
        html = pa.render_html(animals, seed=1, base_date="2026-08-04", site_base="https://x.test")
        assert "onerror=" in html
        assert "リンク切れ" in html

    def test_supports_dark_mode(self):
        """判定シートは長時間見るものなので、暗所でコントラストが落ちないこと。"""
        animals = [_animal()]
        html = pa.render_html(animals, seed=1, base_date="2026-08-04", site_base="https://x.test")
        assert "prefers-color-scheme: dark" in html

    def test_warns_on_stale_animal(self):
        animals = [_animal(last_collected_at="2026-07-01T00:00:00Z")]
        html = pa.render_html(animals, seed=1, base_date="2026-08-04", site_base="https://x.test")
        assert "最終確認が古い（2026-07-01）" in html
        assert 'data-freshness="stale"' in html


class TestBuildManifest:
    def test_contains_reproduction_info(self):
        animals = [_animal(id=5)]
        m = pa.build_manifest(animals, seed=42, base_date="2026-08-04", population=898)
        assert m["seed"] == 42
        assert m["population"] == 898
        assert m["sampled_ids"] == [5]
        assert m["sample_size"] == 1

    def test_is_json_serializable(self):
        m = pa.build_manifest([_animal()], seed=1, base_date="2026-08-04", population=1)
        json.dumps(m, ensure_ascii=False)


class TestFetchAnimals:
    def test_paginates_until_exhausted(self, monkeypatch):
        pages = {
            0: {"items": [_animal(id=1)], "meta": {"total_count": 2, "has_next": True}},
            1: {"items": [_animal(id=2)], "meta": {"total_count": 2, "has_next": False}},
        }
        calls = []

        def fake_get_json(url):
            offset = int(url.split("offset=")[1])
            calls.append(offset)
            return pages[offset // 1]

        monkeypatch.setattr(pa, "get_json", fake_get_json)
        got = pa.fetch_animals("https://api.test", limit=1)
        assert [a["id"] for a in got] == [1, 2]
        assert calls == [0, 1]

    def test_stops_on_empty_page_despite_has_next(self, monkeypatch):
        """API が同じページを返し続けても無限ループしないこと。"""

        def fake_get_json(url):
            return {"items": [], "meta": {"total_count": 5, "has_next": True}}

        monkeypatch.setattr(pa, "get_json", fake_get_json)
        got = pa.fetch_animals("https://api.test", limit=100)
        assert got == []


class TestMissingDefinitionMatchesProduction:
    """欠損の定義は本体 (quality_metrics) と1つに保つ。別実装だと食い違う。"""

    def test_placeholder_unknown_is_missing(self):
        got = {f["key"]: f for f in pa.extract_critical_fields(_animal(location="不明"))}
        assert got["location"]["missing"] is True

    def test_dash_placeholder_is_missing(self):
        got = {f["key"]: f for f in pa.extract_critical_fields(_animal(species="-"))}
        assert got["species"]["missing"] is True

    def test_uses_same_predicate_as_production(self):
        from src.data_collector.domain.quality_metrics import is_missing_value

        assert pa._is_missing is not None
        for value in (None, "", "  ", "不明", "－", "なし", "？", [], "犬", ["u"]):
            assert pa._is_missing(value) == is_missing_value(value)


class TestParseRowIndex:
    def test_extracts_row_number_from_virtual_url(self):
        assert pa.parse_row_index("https://x.test/list.html#row=84") == 84

    def test_returns_none_for_per_animal_url(self):
        assert pa.parse_row_index("https://x.test/animals/detail/12") is None

    def test_returns_none_for_missing_url(self):
        assert pa.parse_row_index(None) is None

    def test_returns_none_for_unparsable_row(self):
        assert pa.parse_row_index("https://x.test/list.html#row=abc") is None


class TestMatchHints:
    def test_skips_placeholder_values(self):
        hints = dict(pa.extract_match_hints(_animal(sex="不明", breed="雑種", name=None)))
        assert "性別" not in hints
        assert hints["品種"] == "雑種"
        assert "名前" not in hints


class TestRowHintRendering:
    def test_shows_row_position_for_virtual_url(self):
        """一覧内の1行を指す仮想URLは開いても飛ばないので、位置と手がかりを出す。"""
        animals = [
            _animal(source_url="https://muni.test/list.html#row=83", management_number="A-1")
        ]
        html = pa.render_html(animals, seed=1, base_date="2026-08-04", site_base="https://x.test")
        assert "84番目" in html
        assert "自動では移動しない" in html
        assert "A-1" in html

    def test_labels_pdf_source_as_pdf(self):
        animals = [_animal(source_url="https://muni.test/0531dog.pdf#row=2")]
        html = pa.render_html(animals, seed=1, base_date="2026-08-04", site_base="https://x.test")
        assert "PDF内の" in html

    def test_no_row_hint_for_per_animal_url(self):
        animals = [_animal(source_url="https://muni.test/animals/1")]
        html = pa.render_html(animals, seed=1, base_date="2026-08-04", site_base="https://x.test")
        assert "自動では移動しない" not in html

    def test_notes_hidden_images(self):
        animals = [_animal(image_urls=[f"https://x.test/{i}.jpg" for i in range(6)])]
        html = pa.render_html(animals, seed=1, base_date="2026-08-04", site_base="https://x.test")
        assert "ほか3枚は元ページで確認" in html

    def test_unknown_freshness_wording_differs_from_stale(self):
        animals = [_animal(last_collected_at=None)]
        html = pa.render_html(animals, seed=1, base_date="2026-08-04", site_base="https://x.test")
        assert "一度も確認されていない" in html
        assert "最終確認が古い" not in html


class TestMain:
    """引数解析からファイル書き出しまでの配線を通しで固定する。"""

    def _stub_api(self, monkeypatch, animals):
        def fake_fetch(api_base, limit=100):
            return animals

        monkeypatch.setattr(pa, "fetch_animals", fake_fetch)

    def test_writes_html_and_json(self, monkeypatch, tmp_path):
        self._stub_api(monkeypatch, [_animal(id=i) for i in range(10)])
        rc = pa.main(["--n", "3", "--seed", "5", "--out-dir", str(tmp_path)])
        assert rc == 0
        htmls = list(tmp_path.glob("publication_audit_*.html"))
        jsons = list(tmp_path.glob("publication_audit_*.json"))
        assert len(htmls) == 1
        assert len(jsons) == 1
        manifest = json.loads(jsons[0].read_text(encoding="utf-8"))
        assert manifest["seed"] == 5
        assert manifest["sample_size"] == 3
        assert manifest["population"] == 10

    def test_exclude_stale_shrinks_population(self, monkeypatch, tmp_path):
        animals = [_animal(id=1, last_collected_at="2026-08-04T00:00:00Z")] + [
            _animal(id=i, last_collected_at="2026-07-01T00:00:00Z") for i in range(2, 10)
        ]
        self._stub_api(monkeypatch, animals)
        pa.main(["--n", "50", "--seed", "5", "--out-dir", str(tmp_path), "--exclude-stale"])
        manifest = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))
        assert manifest["population"] == 1
        assert manifest["sampled_ids"] == [1]

    def test_includes_stale_by_default(self, monkeypatch, tmp_path):
        animals = [_animal(id=1, last_collected_at="2026-08-04T00:00:00Z")] + [
            _animal(id=i, last_collected_at="2026-07-01T00:00:00Z") for i in range(2, 10)
        ]
        self._stub_api(monkeypatch, animals)
        pa.main(["--n", "50", "--seed", "5", "--out-dir", str(tmp_path)])
        manifest = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))
        assert manifest["population"] == 9

    def test_returns_error_when_population_empty(self, monkeypatch, tmp_path):
        self._stub_api(monkeypatch, [])
        assert pa.main(["--out-dir", str(tmp_path)]) == 1

    def test_base_date_follows_newest_collection(self, monkeypatch, tmp_path):
        """基準日は実行日ではなく、母集団で最も新しい収集日にそろえる。"""
        animals = [
            _animal(id=1, last_collected_at="2026-07-20T00:00:00Z"),
            _animal(id=2, last_collected_at="2026-07-21T00:00:00Z"),
        ]
        self._stub_api(monkeypatch, animals)
        pa.main(["--n", "2", "--seed", "1", "--out-dir", str(tmp_path)])
        manifest = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))
        assert manifest["base_date"] == "2026-07-21"
        by_id = {s["id"]: s["freshness"] for s in manifest["sampled"]}
        assert by_id[2] == "fresh"
        assert by_id[1] == "stale"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
