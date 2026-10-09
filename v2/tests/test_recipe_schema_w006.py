"""W006 T617: AI が返したレシピ dict の strict 検査（collector/recipe_schema.py）。"""

from pathlib import Path

import pytest
import yaml
from collector.recipe_schema import validate_recipe_dict

SRC = "https://www.city.example.jp/animals/"
RECIPES = sorted((Path(__file__).resolve().parent.parent / "recipes").glob("*.yaml"))


def _ok(raw):
    return validate_recipe_dict(raw, SRC)


def _has(errors, word):
    return any(word in e for e in errors)


def test_minimal_recipe_passes():
    assert _ok({"rows": "table.list tr", "fields": {"sex": "td:nth-of-type(2)", "age": {"label": "年齢"}},
                "empty_text": ["現在いません"]}) == []


def test_unknown_keys_rejected_at_each_level():
    assert _has(_ok({"rows": "tr", "evil": 1}), "未知のキー 'evil'")
    assert _has(_ok({"rows": "tr", "row_filter": {"text_has_any": ["a"], "x": 1}}), "row_filter: 未知のキー 'x'")
    assert _has(_ok({"rows": "tr", "fields": {"sex": {"selector": "td", "exec": "rm"}}}), "未知のキー 'exec'")
    assert _has(_ok({"rows": "tr", "steps": [{"run": "x"}]}), "steps[0]: 未知のキー 'run'")
    assert _has(_ok({"rows": "tr", "image": {"selector": "img@src", "cmd": 1}}), "image: 未知のキー")
    assert _has(_ok({"rows": "tr", "species": {"from": "text", "zzz": 1}}), "species: 未知のキー")


def test_non_mapping_rejected():
    assert _ok([1, 2]) != []   # type: ignore[arg-type]


def test_regex_length_syntax_and_nesting():
    assert _has(_ok({"rows": "tr", "rows_regex": "a" * 201}), "201 文字")
    assert _has(_ok({"rows": "tr", "fields": {"n": {"regex": "(unclosed"}}}), "compile できない")
    for evil in ["(a+)+$", "(a*)*b", "(?:\\d+)+x", "([a-z]+)*", "(a+){2,}"]:
        assert _has(_ok({"rows": "tr", "fields": {"n": {"regex": evil}}}), "ネストした量指定子"), evil
    # 普通の regex は通る
    assert _ok({"rows": "tr", "fields": {"n": {"regex": r"No\.?\s*(\d+)"}, "d": {"regex": [r"(\d+)年"]}}}) == []


def test_regex_in_join_is_checked():
    raw = {"rows": "tr", "fields": {"n": {"join": [{"label": "x", "regex": "(a+)+"}]}}}
    assert _has(_ok(raw), "ネストした量指定子")


def test_slow_regex_is_rejected_by_probe():
    # 簡易検出（単一部品の入れ子）をすり抜ける 2 部品の入れ子。実行時間で落ちる
    errs = _ok({"rows": "tr", "rows_regex": r"(\s*[a-z]+)+$"})
    assert _has(errs, "遅い") or _has(errs, "終わらない")
    # 多項式的な遅さ（a* を並べて最後に失敗させる）
    errs = _ok({"rows": "tr", "rows_regex": "a*a*a*a*a*a*a*a*b"})
    assert _has(errs, "遅い") or _has(errs, "終わらない")


def test_benign_quadratic_and_delimited_repeat_regexes_pass():
    for ok in [r"((?:令和|平成)?\s*\d+年\d+月\d+日)", r"^(?!届出番号)(?:[^・、]+[・、])+([^・、]+)$", r"(\S*月生まれ)"]:
        assert _ok({"rows": "tr", "fields": {"n": {"regex": ok}}}) == [], ok


def test_selector_count_and_length():
    assert _has(_ok({"rows": "t" * 201}), "セレクタが 201 文字")
    assert _ok({"rows": ", ".join(["t" * 150] * 3)}) == []   # カンマ区切りは 1 本ずつ数える（各 150 文字）
    many = {f"f{i}": f"td.c{i}" for i in range(45)}
    raw = {"rows": "tr", "fields": many, "empty_selector": [f"div.e{i}" for i in range(10)]}
    assert _has(_ok(raw), "セレクタが 56 本 > 50")


def test_urls_host_and_scheme():
    assert _ok({"rows": "tr", "url": "https://city.example.jp/other/"}) == []       # www. の差は許す
    assert _has(_ok({"rows": "tr", "url": "https://evil.test/"}), "別のホスト")
    assert _has(_ok({"rows": "tr", "url": "javascript:alert(1)"}), "許さないスキーム")
    assert _has(_ok({"rows": "tr", "source_url": "file:///etc/passwd"}), "許さないスキーム")
    assert _has(_ok({"rows": "tr", "url": "data:text/html,x"}), "許さないスキーム")
    assert _ok({"rows": "tr", "source_url": "doc"}) == []
    assert _has(_ok({"rows": "tr", "steps": [{"follow": "https://evil.test/x"}]}), "別のホスト")
    assert _has(_ok({"rows": "tr", "steps": [{"follow_all": "javascript:void(0)"}]}), "許さないスキーム")
    assert _ok({"rows": "tr", "steps": [{"follow_all": "a.detail@href"}, {"paginate": "div.next a@href"}]}) == []
    assert _has(_ok({"rows": "tr", "steps": [{"render_json": {"match": "x", "path": "a", "follow": "https://evil.test/?{value}"}}]}),
                "別のホスト")


def test_string_lists_capped_at_50():
    assert _ok({"rows": "tr", "empty_text": [f"w{i}" for i in range(50)]}) == []
    assert _has(_ok({"rows": "tr", "empty_text": [f"w{i}" for i in range(51)]}), "51 個 > 50")
    assert _has(_ok({"rows": "tr", "row_filter": {"text_lacks": [f"w{i}" for i in range(51)]}}), "51 個")
    assert _has(_ok({"rows": "tr", "empty_text": [1, 2]}), "文字列でない")


def _urls_by_recipe():
    from collector.registry import load_sources

    out: dict[Path, list[str]] = {}
    for src in load_sources():
        out.setdefault(src.recipe_path, []).append(src.url)
    return out


URLS = _urls_by_recipe()

# 既存レシピのうち schema に通らないもの（W006 T617 の報告事項。schema を緩めず、人が判断するまで現状を固定する）
KNOWN_VIOLATIONS = {
    "pref_ishikawa": "別のホスト",       # 入口が委託先サイト aigo-ishikawa.jp（台帳は pref.ishikawa.lg.jp）
    "city_matsumoto-6": "セレクタが 281 文字",   # image.selector が 200 文字超の単一セレクタ
    "city_matsumoto-7": "セレクタが 281 文字",
    "city_matsumoto-8": "セレクタが 281 文字",
    # 数字だけのダミー 1 万文字で 2 乗以上に遅い日付 regex（reviewer S2 で数字入りダミーを足して検出）。
    # 実ページの行は短いので動作上は問題ないが、LLM 出力の門としては落とす。人が書き直すまで固定
    "city_toyama-1": "正規表現が遅い",
    "pref_oita-1": "正規表現が",
    "pref_oita-2": "正規表現が",
    "pref_oita-3": "正規表現が",
}


@pytest.mark.parametrize("path", RECIPES, ids=lambda p: p.stem)
def test_every_existing_recipe_passes(path):
    """既存の全レシピが、それを使う台帳エントリ全部の URL に対して合格する（通らないなら schema でなくレシピ側を疑う）。"""
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    urls = URLS.get(path)
    if not urls:
        pytest.skip("台帳から参照されていないレシピ")
    for url in urls:
        errors = validate_recipe_dict(raw, url)
        known = KNOWN_VIOLATIONS.get(path.stem)
        if known:
            # 現状の違反は報告済みの 2 件だけ。別の違反が増えたら落とす
            assert errors and all(known in e for e in errors), f"{path.name}: {errors}"
        else:
            assert errors == [], f"{path.name} @ {url}"
