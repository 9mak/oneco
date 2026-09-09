"""fields.py 共通ヘルパーのユニットテスト

実データ由来の文字列 (city_kashiwa/city_machida/douai_tokushima の
_weight_to_size、city_kagoshima の _normalize_sex、city_chiba の
_LABEL_TO_FIELD パース) を使って、抽出元と同じ挙動になることを確認する。
"""

from __future__ import annotations

from data_collector.adapters.rule_based.fields import (
    infer_species,
    normalize_sex,
    parse_jp_date,
    parse_label_value_pairs,
    weight_to_size,
)


class TestWeightToSize:
    def test_small_under_5kg(self) -> None:
        assert weight_to_size("体重：4.9kg") == "小"

    def test_medium_5_to_15kg(self) -> None:
        assert weight_to_size("体重：5.0kg") == "中"
        assert weight_to_size("体重：14.9kg") == "中"

    def test_large_15kg_and_over(self) -> None:
        assert weight_to_size("体重：15kg") == "大"

    def test_range_takes_minimum(self) -> None:
        # city_machida: 範囲表記「3〜4kg」は最小値 (3kg → 小) を採用
        assert weight_to_size("3〜4キログラム") == "小"

    def test_fullwidth_decimal_point(self) -> None:
        # douai_tokushima: 全角小数点「４．９kg」
        assert weight_to_size("４．９kg") == "小"

    def test_no_number_returns_empty(self) -> None:
        assert weight_to_size("不明") == ""
        assert weight_to_size("") == ""

    def test_require_kg_rejects_bare_number(self) -> None:
        # douai_tokushima 系: kg 表記がない数値は体重として扱わない
        assert weight_to_size("管理番号2026", require_kg=True) == ""
        assert weight_to_size("12kg", require_kg=True) == "中"


class TestNormalizeSex:
    def test_male_kanji(self) -> None:
        assert normalize_sex("雄") == "オス"

    def test_female_kanji(self) -> None:
        assert normalize_sex("雌") == "メス"

    def test_passthrough_for_other_values(self) -> None:
        assert normalize_sex("オス") == "オス"
        assert normalize_sex("不明") == "不明"

    def test_empty(self) -> None:
        assert normalize_sex("") == ""


class TestParseJpDate:
    def test_reiwa_full(self) -> None:
        assert parse_jp_date("令和8年5月7日") == "2026-05-07"

    def test_r_dot_notation(self) -> None:
        # 横須賀 doubutu 実表記
        assert parse_jp_date("R8.5.14（木曜日）") == "2026-05-14"

    def test_iso_passthrough(self) -> None:
        assert parse_jp_date("2026-05-07") == "2026-05-07"

    def test_invalid_returns_empty(self) -> None:
        assert parse_jp_date("不明") == ""
        assert parse_jp_date("") == ""


class TestInferSpecies:
    def test_dog_site_name(self) -> None:
        assert infer_species("千葉市（迷子犬）") == "犬"

    def test_cat_site_name(self) -> None:
        assert infer_species("千葉市（迷子猫）") == "猫"

    def test_other_when_no_match(self) -> None:
        assert infer_species("千葉市（迷子その他動物）") == "その他"

    def test_empty(self) -> None:
        assert infer_species("") == "その他"

    def test_url_pattern(self) -> None:
        assert infer_species("https://example.jp/animal/dog/list") == "犬"


class TestParseLabelValuePairs:
    LABEL_TO_FIELD = {
        "保護日": "shelter_date",
        "収容日": "shelter_date",
        "収容場所": "location",
        "種類": "species",
        "毛色": "color",
        "性別": "sex",
        "体格": "size",
    }

    def test_basic_extraction(self) -> None:
        # city_chiba の実際の属性ブロックテキスト相当
        chunk = "収容日：令和8年5月7日\n収容場所：稲毛区小仲台\n種類：柴犬\n毛色：茶\n性別：メス\n体格：中"
        result = parse_label_value_pairs([chunk], self.LABEL_TO_FIELD)
        assert result == {
            "shelter_date": "令和8年5月7日",
            "location": "稲毛区小仲台",
            "species": "柴犬",
            "color": "茶",
            "sex": "メス",
            "size": "中",
        }

    def test_first_match_wins_across_multiple_labels_for_same_field(self) -> None:
        chunk = "保護日：2026-05-01\n収容日：2026-05-02"
        result = parse_label_value_pairs([chunk], self.LABEL_TO_FIELD)
        assert result == {"shelter_date": "2026-05-01"}

    def test_unmapped_label_ignored(self) -> None:
        chunk = "特徴：人懐っこい"
        result = parse_label_value_pairs([chunk], self.LABEL_TO_FIELD)
        assert result == {}

    def test_multiple_chunks(self) -> None:
        result = parse_label_value_pairs(["性別：オス", "体格：小"], self.LABEL_TO_FIELD)
        assert result == {"sex": "オス", "size": "小"}

    def test_valid_values_whitelist_rejects_invalid(self) -> None:
        valid = {"size": frozenset({"小", "中", "大"})}
        chunk = "体格：生後1か月前後"
        result = parse_label_value_pairs([chunk], self.LABEL_TO_FIELD, valid_values=valid)
        assert result == {}

    def test_valid_values_whitelist_accepts_valid(self) -> None:
        valid = {"size": frozenset({"小", "中", "大"})}
        chunk = "体格：中"
        result = parse_label_value_pairs([chunk], self.LABEL_TO_FIELD, valid_values=valid)
        assert result == {"size": "中"}

    def test_empty_and_blank_chunks_skipped(self) -> None:
        result = parse_label_value_pairs(["", "  \n  ", "性別：オス"], self.LABEL_TO_FIELD)
        assert result == {"sex": "オス"}
