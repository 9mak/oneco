"""diagnosis_report.py のユニットテスト (T406)

Discord 通知本文の shaping (サイトあたり最大15行・run あたり最大5サイト・
"+N more") と reports/diagnosis/ への artifact 書き出しを検証する。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from src.data_collector.infrastructure.diagnosis import SelectorCheck, SiteDiagnosis
from src.data_collector.infrastructure.diagnosis_report import (
    build_discord_summary,
    write_artifacts,
)


def _diagnosis(name: str, ok: bool = True) -> SiteDiagnosis:
    return SiteDiagnosis(
        site_name=name,
        diagnosed_at="2026-09-09T00:00:00+09:00",
        list_url=f"https://example.test/{name}/",
        http_status=200,
        redirected=False,
        final_url=f"https://example.test/{name}/",
        charset="utf-8",
        fetch_error=None,
        list_selector_source="registry_list_link",
        is_pdf=False,
        checks=[
            SelectorCheck(
                name="LIST_LINK_SELECTOR", selector_or_label="a.x", match_count=1 if ok else 0
            )
        ],
    )


class TestBuildDiscordSummary:
    def test_empty_list_returns_empty_string(self):
        assert build_discord_summary([]) == ""

    def test_single_site_included_fully(self):
        text = build_discord_summary([_diagnosis("サイトA")])
        assert "サイトA" in text
        assert "+N more" not in text  # sanity: リテラルは含まれない

    def test_caps_at_five_sites_with_plus_n_more(self):
        diagnoses = [_diagnosis(f"サイト{i}") for i in range(8)]
        text = build_discord_summary(diagnoses)
        for i in range(5):
            assert f"サイト{i}" in text
        for i in range(5, 8):
            assert f"サイト{i}" not in text
        assert "+3 サイト" in text

    def test_per_site_block_capped_at_15_lines(self):
        d = _diagnosis("サイトA")
        # 20行分の checks を積んでも summary_lines は 15 行以内
        d.checks = [
            SelectorCheck(name=f"CHECK_{i}", selector_or_label="x", match_count=0)
            for i in range(20)
        ]
        lines = d.summary_lines()
        assert len(lines) <= 15


class TestWriteArtifacts:
    def test_no_diagnoses_returns_none(self, tmp_path):
        assert write_artifacts([], output_dir=tmp_path) is None

    def test_writes_json_and_markdown(self, tmp_path):
        now = datetime(2026, 9, 9, 0, 0, 0, tzinfo=UTC)
        result = write_artifacts(
            [_diagnosis("サイトA"), _diagnosis("サイトB", ok=False)], output_dir=tmp_path, now=now
        )
        assert result is not None
        json_path, md_path = result
        assert json_path.exists()
        assert md_path.exists()
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        assert payload["site_count"] == 2
        names = {s["site_name"] for s in payload["sites"]}
        assert names == {"サイトA", "サイトB"}
        md_text = md_path.read_text(encoding="utf-8")
        assert "サイトA" in md_text
        assert "サイトB" in md_text
