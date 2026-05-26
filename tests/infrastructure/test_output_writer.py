"""OutputWriter のユニットテスト"""

import json
from datetime import datetime

import pytest

from src.data_collector.domain.diff_detector import DiffResult
from src.data_collector.domain.models import AnimalData
from src.data_collector.infrastructure.output_writer import OutputWriter


class TestOutputWriter:
    """OutputWriter のテストケース"""

    @pytest.fixture
    def output_writer(self, tmp_path):
        """OutputWriter インスタンスを作成（一時ディレクトリ使用）"""
        # 一時ディレクトリを使用するように OUTPUT_DIR をオーバーライド
        writer = OutputWriter()
        writer.OUTPUT_DIR = tmp_path / "output"
        writer.OUTPUT_FILE = writer.OUTPUT_DIR / "animals.json"
        return writer

    @pytest.fixture
    def sample_animal_data(self):
        """サンプル AnimalData を作成"""
        return [
            AnimalData(
                species="犬",
                sex="男の子",
                age_months=24,
                color="茶色",
                size="中型",
                shelter_date="2026-01-05",
                location="高知県動物愛護センター",
                phone="088-123-4567",
                image_urls=["https://example.com/image1.jpg"],
                source_url="https://example-kochi.jp/animals/123",
                category="adoption",
            ),
            AnimalData(
                species="猫",
                sex="女の子",
                age_months=12,
                color="三毛",
                size="小型",
                shelter_date="2026-01-06",
                location="高知県動物愛護センター",
                phone="088-123-4567",
                image_urls=[],
                source_url="https://example-kochi.jp/animals/124",
                category="adoption",
            ),
        ]

    @pytest.fixture
    def sample_diff_result(self, sample_animal_data):
        """サンプル DiffResult を作成"""
        return DiffResult(new=[sample_animal_data[0]], updated=[], deleted_candidates=[])

    def test_write_output_creates_directory(
        self, output_writer, sample_animal_data, sample_diff_result
    ):
        """出力ディレクトリが自動作成されることを確認"""
        assert not output_writer.OUTPUT_DIR.exists()

        output_writer.write_output(sample_animal_data, sample_diff_result)

        assert output_writer.OUTPUT_DIR.exists()
        assert output_writer.OUTPUT_DIR.is_dir()

    def test_write_output_creates_file(self, output_writer, sample_animal_data, sample_diff_result):
        """JSON ファイルが正しく生成されることを確認"""
        output_path = output_writer.write_output(sample_animal_data, sample_diff_result)

        assert output_path.exists()
        assert output_path.is_file()
        assert output_path == output_writer.OUTPUT_FILE

    def test_write_output_json_structure(
        self, output_writer, sample_animal_data, sample_diff_result
    ):
        """JSON 出力の構造が正しいことを確認"""
        output_path = output_writer.write_output(sample_animal_data, sample_diff_result)

        with open(output_path, encoding="utf-8") as f:
            output_data = json.load(f)

        # 必須フィールドの存在確認
        assert "collected_at" in output_data
        assert "total_count" in output_data
        assert "diff" in output_data
        assert "animals" in output_data

        # diff フィールドの構造確認
        assert "new_count" in output_data["diff"]
        assert "updated_count" in output_data["diff"]
        assert "deleted_count" in output_data["diff"]

    def test_write_output_correct_counts(
        self, output_writer, sample_animal_data, sample_diff_result
    ):
        """カウント値が正しく設定されることを確認"""
        output_path = output_writer.write_output(sample_animal_data, sample_diff_result)

        with open(output_path, encoding="utf-8") as f:
            output_data = json.load(f)

        assert output_data["total_count"] == 2
        assert output_data["diff"]["new_count"] == 1
        assert output_data["diff"]["updated_count"] == 0
        assert output_data["diff"]["deleted_count"] == 0

    def test_write_output_animals_array(
        self, output_writer, sample_animal_data, sample_diff_result
    ):
        """animals 配列が正しくシリアライズされることを確認"""
        output_path = output_writer.write_output(sample_animal_data, sample_diff_result)

        with open(output_path, encoding="utf-8") as f:
            output_data = json.load(f)

        assert len(output_data["animals"]) == 2

        # 最初の動物データの検証
        first_animal = output_data["animals"][0]
        assert first_animal["species"] == "犬"
        assert first_animal["sex"] == "男の子"
        assert first_animal["age_months"] == 24
        assert first_animal["color"] == "茶色"
        assert first_animal["shelter_date"] == "2026-01-05"
        assert first_animal["source_url"] == "https://example-kochi.jp/animals/123"

    def test_write_output_timestamp_format(
        self, output_writer, sample_animal_data, sample_diff_result
    ):
        """collected_at が ISO 8601 形式であることを確認"""
        output_path = output_writer.write_output(sample_animal_data, sample_diff_result)

        with open(output_path, encoding="utf-8") as f:
            output_data = json.load(f)

        collected_at = output_data["collected_at"]
        # ISO 8601 形式のパース確認（例外が発生しなければOK）
        datetime.fromisoformat(collected_at.replace("Z", "+00:00"))
        # Z サフィックスの確認
        assert collected_at.endswith("Z")

    def test_write_output_json_encoding(
        self, output_writer, sample_animal_data, sample_diff_result
    ):
        """JSON が UTF-8 エンコーディングで日本語を含むことを確認"""
        output_path = output_writer.write_output(sample_animal_data, sample_diff_result)

        with open(output_path, encoding="utf-8") as f:
            content = f.read()

        # 日本語が正しくエンコードされていることを確認
        assert "犬" in content
        assert "猫" in content
        assert "男の子" in content
        assert "女の子" in content

    def test_write_output_merges_with_existing_file(
        self, output_writer, sample_animal_data, sample_diff_result
    ):
        """既存ファイルと merge される (CollectorService が per-site で呼ぶため)

        2 回目の write_output で同一 source_url は新しい値に上書き、
        diff カウントは累積される。
        """
        # 最初の書き込み (2 件、new=1)
        output_writer.write_output(sample_animal_data, sample_diff_result)

        # 同じ URL を持つ 1 件で再度書き込み (updated)
        new_data = [sample_animal_data[0]]
        new_diff = DiffResult(new=[], updated=[new_data[0]], deleted_candidates=[])
        output_writer.write_output(new_data, new_diff)

        with open(output_writer.OUTPUT_FILE, encoding="utf-8") as f:
            output_data = json.load(f)

        # merged: 1 つ目 URL は新しい値で上書き、2 つ目 URL は前回分が残る
        assert output_data["total_count"] == 2
        # diff カウントは累積
        assert output_data["diff"]["new_count"] == 1  # 1 回目分
        assert output_data["diff"]["updated_count"] == 1  # 2 回目分

    def test_write_output_empty_data(self, output_writer):
        """空データの場合でも正しく処理されることを確認"""
        empty_data = []
        empty_diff = DiffResult(new=[], updated=[], deleted_candidates=[])

        output_path = output_writer.write_output(empty_data, empty_diff)

        with open(output_path, encoding="utf-8") as f:
            output_data = json.load(f)

        assert output_data["total_count"] == 0
        assert output_data["diff"]["new_count"] == 0
        assert output_data["animals"] == []

    def test_write_output_diff_with_deletions(self, output_writer, sample_animal_data):
        """削除候補がある場合の diff カウント確認"""
        diff_with_deletions = DiffResult(
            new=[sample_animal_data[0]],
            updated=[],
            deleted_candidates=["https://example.com/deleted1", "https://example.com/deleted2"],
        )

        output_path = output_writer.write_output(sample_animal_data, diff_with_deletions)

        with open(output_path, encoding="utf-8") as f:
            output_data = json.load(f)

        assert output_data["diff"]["deleted_count"] == 2

    def test_write_output_accumulates_animals_from_different_sites(
        self, output_writer, sample_animal_data
    ):
        """異なる site の write_output が累積される (209 サイト統合の根本仕様)"""
        site_a = sample_animal_data[0]
        site_b = AnimalData(
            species="犬",
            sex="女の子",
            shelter_date="2026-01-10",
            location="徳島県",
            phone="088-000-0000",
            source_url="https://example-tokushima.jp/animals/1",
            category="adoption",
        )
        site_c = AnimalData(
            species="猫",
            sex="不明",
            shelter_date="2026-01-11",
            location="沖縄県",
            phone="098-000-0000",
            source_url="https://example-okinawa.jp/animals/1",
            category="adoption",
        )

        diff = DiffResult(new=[], updated=[], deleted_candidates=[])
        output_writer.write_output([site_a], diff)
        output_writer.write_output([site_b], diff)
        output_writer.write_output([site_c], diff)

        with open(output_writer.OUTPUT_FILE, encoding="utf-8") as f:
            output_data = json.load(f)

        assert output_data["total_count"] == 3
        urls = {a["source_url"] for a in output_data["animals"]}
        assert "https://example-kochi.jp/animals/123" in urls
        assert "https://example-tokushima.jp/animals/1" in urls
        assert "https://example-okinawa.jp/animals/1" in urls

    def test_reset_clears_output_file(self, output_writer, sample_animal_data, sample_diff_result):
        """reset() で animals.json が削除される"""
        output_writer.write_output(sample_animal_data, sample_diff_result)
        assert output_writer.OUTPUT_FILE.exists()

        output_writer.reset()
        assert not output_writer.OUTPUT_FILE.exists()

    def test_reset_missing_file_no_error(self, output_writer):
        """reset() は output ファイルが無くてもエラーにならない"""
        output_writer.reset()  # 何も無い状態でも OK
