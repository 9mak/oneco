"""site_spec.load_all_specs のテスト (T405 reviewer F-01/F-02)

1 ファイルの YAML 破損が他 spec の読み込みを巻き込まない (collector import を
落とさない) ことを検証する。
"""

from __future__ import annotations

import logging
from pathlib import Path

from data_collector.adapters.rule_based.site_spec import load_all_specs

_GOOD_SPEC = """
names: テスト良好サイト
mode: list_detail
list_link_selector: "a.item"
field_selectors:
  species:
    label: "種別"
"""


def _write(directory: Path, name: str, body: str) -> None:
    (directory / name).write_text(body, encoding="utf-8")


class TestLoadAllSpecs:
    def test_missing_dir_returns_empty(self, tmp_path: Path):
        assert load_all_specs(tmp_path / "nope") == []

    def test_loads_valid_specs(self, tmp_path: Path):
        _write(tmp_path, "good.yaml", _GOOD_SPEC)
        specs = load_all_specs(tmp_path)
        assert [s.names for s in specs] == [("テスト良好サイト",)]

    def test_broken_yaml_is_skipped_and_others_survive(self, tmp_path: Path, caplog):
        _write(tmp_path, "bad.yaml", "names: [unclosed\nmode: list_detail\n")
        _write(tmp_path, "good.yaml", _GOOD_SPEC)
        with caplog.at_level(logging.ERROR):
            specs = load_all_specs(tmp_path)
        assert [s.names for s in specs] == [("テスト良好サイト",)]
        assert any("bad.yaml" in rec.getMessage() for rec in caplog.records)

    def test_missing_required_key_is_skipped(self, tmp_path: Path, caplog):
        # mode が無い → KeyError。YAML 構文エラー以外の構築失敗も隔離される
        _write(tmp_path, "nomode.yaml", "names: モード無しサイト\n")
        _write(tmp_path, "good.yaml", _GOOD_SPEC)
        with caplog.at_level(logging.ERROR):
            specs = load_all_specs(tmp_path)
        assert [s.names for s in specs] == [("テスト良好サイト",)]
        assert any("nomode.yaml" in rec.getMessage() for rec in caplog.records)
