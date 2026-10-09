"""AI が書いたレシピ（raw dict）を、実行する前に strict に検査する（W006 T617）。

recipe.py の `Recipe.from_dict` は未知キーを黙って捨て、正規表現やセレクタの大きさも見ない。
修復で LLM が返した YAML は自治体ページ（信頼できない入力）の影響を受けうるので、案として保存する前に
ここで次を検査する。違反が 1 つでもあれば案は採らない。

- 未知キー（トップ階層と、ネストした dict のキー）
- 正規表現: 長さ 200 以内・compile できる・ネストした量指定子 `(a+)+` 型でない・ダミー文字列で 0.2 秒以内
- セレクタ: 全部で 50 本以内・各 200 文字以内
- URL: 台帳の source_url と同じホスト（www. の差は許す）だけ。javascript: / file: / data: は拒否
- 文字列のリスト: 50 個以内

許可キーの根拠は docs/RECIPE.md と recipes/*.yaml の実使用（tests/test_recipe_schema_w006.py が全レシピを通す）。
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from typing import Any
from urllib.parse import urlparse

from .recipe import Recipe

MAX_REGEX_LEN = 200
MAX_SELECTOR_LEN = 200
MAX_SELECTORS = 50
MAX_LIST_ITEMS = 50
MAX_MAP_ITEMS = 100
MAX_PAGES = 200          # steps[].max / max_pages の上限（最大の台帳でも数十ページ）
MAX_WAIT_MS = 60_000     # render.wait_ms の上限（fetch.WAIT_FOR_MS と同じ 60 秒）
# 10,000 文字・0.2 秒だと、(\d+)年 や \s* を並べた普通の抽出 regex（探索が O(n^2) になるだけ）まで 30 本ほど落ちる。
# 指数的・3 乗以上の遅さは 2,000 文字・0.2 秒で確実に落ち、2 乗は 10,000 文字・3 秒の上限で許す
REGEX_TIME_LIMIT = 0.2
REGEX_PROBE_LEN = 2_000
REGEX_LONG_LEN = 10_000
REGEX_LONG_LIMIT = 3.0

# ネストしたキーの許可リスト（docs/RECIPE.md）。項目名（fields.<名前>）は自由（row_filter.field_* の参照先になる）
STEP_KEYS = {
    "follow", "follow_text", "follow_all", "paginate", "pdf_links", "render", "render_json",
    "skip_errors", "rendered", "max",
}
RENDER_KEYS = {"wait_for", "wait_ms"}
RENDER_JSON_KEYS = {"match", "path", "follow", "max", "render"}
ROW_FILTER_KEYS = {"text_has_any", "text_lacks", "min_text_length", "field_lacks", "field_has_any"}
IMAGE_KEYS = {"selector", "exclude", "scope", "stop_at", "strip_query", "match_field"}
FIELD_SPEC_KEYS = {
    "selector", "attr", "label", "regex", "default", "index", "header", "header_row", "from", "join", "sep",
}
SPECIES_KEYS = {"from", "selector", "map", "allow_other", "infer"}
PDF_KEYS = {"mode", "header_row", "header_has", "columns"}
EMPTY_ABSENT_KEYS = {"page", "none"}

_BAD_SCHEMES = ("javascript:", "file:", "data:", "vbscript:")
# 量指定子の付いた 1 つの部品だけを括弧に入れ、さらに繰り返すもの: (a+)+ (\d*)* ([a-z]+){2,} (?:.+)*
# 複数部品の入れ子（(\s*[a-z]+)+$ など）は下のダミー文字列での実行時間で拒否する。
# 区切り文字付きの繰り返し ((?:[^、]+、)+) は壊れないので、ここでは拒否しない。
_NESTED_QUANT = re.compile(
    r"\((?:\?:)?(?:\\.|\[[^\]]*\]|[^()\\\[\]|])[+*]\??\)\s*(?:[+*]|\{\d+,\d*\})"
)

_PROBE_SCRIPT = r"""
import json, re, sys, time
patterns = json.load(sys.stdin)
short, long_ = __SHORT__, __LONG__


def probes(n):
    # 数字・数字と空白の交互も入れる（(\d+\s?)+$ 型は数字だけで指数的に伸びる。reviewer S2）
    return ["a" * n + "!", " " * n + "!", "\u3042" * n, "a " * (n // 2) + "!", "-" * n,
            "1" * n + "!", "1 " * (n // 2) + "!", "12" * (n // 2) + "!"]


def worst(rx, n):
    w = 0.0
    for s in probes(n):
        t = time.perf_counter()
        rx.search(s)
        w = max(w, time.perf_counter() - t)
    return w


for i, p in enumerate(patterns):
    rx = re.compile(p)
    w1 = worst(rx, short)
    w2 = worst(rx, long_) if w1 <= __LIMIT__ else 0.0
    print(i, w1, w2, flush=True)
"""
_PROBE_SCRIPT = (
    _PROBE_SCRIPT.replace("__SHORT__", str(REGEX_PROBE_LEN))
    .replace("__LONG__", str(REGEX_LONG_LEN))
    .replace("__LIMIT__", repr(REGEX_TIME_LIMIT))
)


def _split_selector_list(sel: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    quote = ""
    cur: list[str] = []
    for ch in sel:
        if quote:
            if ch == quote:
                quote = ""
        elif ch in "'\"":
            quote = ch
        elif ch in "([":
            depth += 1
        elif ch in ")]":
            depth = max(0, depth - 1)
        elif ch == "," and depth == 0:
            parts.append("".join(cur).strip())
            cur = []
            continue
        cur.append(ch)
    parts.append("".join(cur).strip())
    return [p for p in parts if p]


def _host(url: str) -> str:
    h = (urlparse(url).hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


class _Check:
    def __init__(self, source_url: str) -> None:
        self.errors: list[str] = []
        self.base_host = _host(source_url)
        self.selectors: list[tuple[str, str]] = []
        self.regexes: list[tuple[str, str]] = []

    def int_max(self, where: str, v: Any, limit: int) -> None:
        if v is None:
            return
        if isinstance(v, bool) or not isinstance(v, int):
            self.err(f"{where}: 整数でない")
        elif v < 0 or v > limit:
            self.err(f"{where}: {v} は 0〜{limit} の範囲外")

    def err(self, msg: str) -> None:
        self.errors.append(msg)

    # --- 構造 ---
    def keys(self, where: str, d: Any, allowed: set[str]) -> dict[str, Any]:
        if not isinstance(d, dict):
            self.err(f"{where}: マッピングでない（{type(d).__name__}）")
            return {}
        for k in d:
            if k not in allowed:
                self.err(f"{where}: 未知のキー {k!r}")
        return d

    def str_list(self, where: str, v: Any) -> list[str]:
        if isinstance(v, str):
            return [v]
        if not isinstance(v, list):
            self.err(f"{where}: 文字列か文字列のリストでない（{type(v).__name__}）")
            return []
        if len(v) > MAX_LIST_ITEMS:
            self.err(f"{where}: {len(v)} 個 > {MAX_LIST_ITEMS}")
        bad = [x for x in v if not isinstance(x, str)]
        if bad:
            self.err(f"{where}: 文字列でない要素がある")
            return [x for x in v if isinstance(x, str)]
        return v

    # --- 個別 ---
    def selector(self, where: str, v: Any, with_attr: bool = False) -> None:
        if not isinstance(v, str):
            self.err(f"{where}: セレクタが文字列でない")
            return
        if with_attr and "@" in v:
            v = v.rsplit("@", 1)[0] if re.search(r"@[A-Za-z_-]+$", v) else v
        # `a, b, c` は 3 本として数える（括弧・引用符の中のカンマは区切りでない）
        for part in _split_selector_list(v):
            self.selectors.append((where, part))
            if len(part) > MAX_SELECTOR_LEN:
                self.err(f"{where}: セレクタが {len(part)} 文字 > {MAX_SELECTOR_LEN}")

    def regex(self, where: str, v: Any) -> None:
        if not isinstance(v, str):
            self.err(f"{where}: 正規表現が文字列でない")
            return
        if len(v) > MAX_REGEX_LEN:
            self.err(f"{where}: 正規表現が {len(v)} 文字 > {MAX_REGEX_LEN}")
            return
        try:
            re.compile(v)
        except re.error as e:
            self.err(f"{where}: 正規表現が compile できない: {e}")
            return
        if _NESTED_QUANT.search(v):
            self.err(f"{where}: ネストした量指定子（ReDoS の疑い）: {v}")
            return
        self.regexes.append((where, v))

    def url(self, where: str, v: Any) -> None:
        if not isinstance(v, str):
            self.err(f"{where}: URL が文字列でない")
            return
        low = v.strip().lower()
        if low.startswith(_BAD_SCHEMES):
            self.err(f"{where}: 許さないスキーム: {v[:60]}")
            return
        if not low.startswith(("http://", "https://")):
            self.err(f"{where}: http(s) の URL でない: {v[:60]}")
            return
        if _host(v) != self.base_host:
            self.err(f"{where}: 台帳と別のホスト {_host(v)!r}（台帳は {self.base_host!r}）")

    def step_link(self, where: str, v: Any) -> None:
        """follow 系: `セレクタ@属性`。絶対 URL を直接書いた場合はホストを検査する。"""
        if not isinstance(v, str):
            self.err(f"{where}: 文字列でない")
            return
        low = v.strip().lower()
        if low.startswith(_BAD_SCHEMES):
            self.err(f"{where}: 許さないスキーム: {v[:60]}")
        elif low.startswith(("http://", "https://")):
            self.url(where, v)
        else:
            self.selector(where, v, with_attr=True)

    def field_spec(self, where: str, spec: Any, depth: int = 0) -> None:
        if isinstance(spec, str):
            self.selector(where, spec)
            return
        d = self.keys(where, spec, FIELD_SPEC_KEYS)
        if "selector" in d:
            self.selector(f"{where}.selector", d["selector"])
        if "regex" in d:
            for i, r in enumerate(self.str_list(f"{where}.regex", d["regex"])):
                self.regex(f"{where}.regex[{i}]", r)
        if "label" in d:
            self.str_list(f"{where}.label", d["label"])
        if "join" in d:
            j = d["join"]
            if not isinstance(j, list) or len(j) > MAX_LIST_ITEMS or depth >= 2:
                self.err(f"{where}.join: リストでない・{MAX_LIST_ITEMS} 個超・深すぎる")
            else:
                for i, sub in enumerate(j):
                    self.field_spec(f"{where}.join[{i}]", sub, depth + 1)


_PROBE_CACHE: dict[str, tuple[float, float]] = {}   # 同じ regex（レシピ間で共有が多い）は 1 回だけ測る


def _probe_regexes(items: list[tuple[str, str]]) -> list[str]:
    """正規表現を別プロセスで長いダミーに当て、遅いもの・終わらないものを返す（in-process だと ReDoS で止まる）。"""
    todo = list(dict.fromkeys(p for _, p in items if p not in _PROBE_CACHE))
    hung: set[str] = set()
    failed = False
    while todo:
        try:
            proc = subprocess.run(
                [sys.executable, "-I", "-c", _PROBE_SCRIPT],
                input=json.dumps(todo),
                capture_output=True, text=True, check=False, timeout=4 + 2 * len(todo),
            )
            stdout, timed_out = proc.stdout, False
        except subprocess.TimeoutExpired as e:
            raw = e.stdout or ""
            stdout = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
            timed_out = True
        got = 0
        for line in stdout.splitlines():
            parts = line.split()
            if len(parts) == 3 and parts[0].isdigit():
                _PROBE_CACHE[todo[int(parts[0])]] = (float(parts[1]), float(parts[2]))
                got += 1
        if got >= len(todo):
            break
        if not timed_out:
            failed = True
            break
        hung.add(todo[got])   # 終わらなかった 1 本。残りを別プロセスで測り直す
        _PROBE_CACHE[todo[got]] = (float("inf"), float("inf"))
        todo = todo[got + 1:]
    out: list[str] = []
    for where, pat in items:
        if pat not in _PROBE_CACHE:
            continue
        w1, w2 = _PROBE_CACHE[pat]
        if pat in hung:
            out.append(f"{where}: 正規表現が時間内に終わらない（ReDoS の疑い）: {pat}")
        elif w1 > REGEX_TIME_LIMIT:
            out.append(f"{where}: 正規表現が遅い（{REGEX_PROBE_LEN:,} 文字で {w1:.2f} 秒 > {REGEX_TIME_LIMIT} 秒）: {pat}")
        elif w2 > REGEX_LONG_LIMIT:
            out.append(f"{where}: 正規表現が遅い（{REGEX_LONG_LEN:,} 文字で {w2:.2f} 秒 > {REGEX_LONG_LIMIT} 秒）: {pat}")
    if failed:
        out.append("正規表現の検査を完了できなかった（子プロセスの異常終了）")
    return out


def validate_recipe_dict(raw: dict[str, Any], source_url: str) -> list[str]:
    """違反の一覧を返す。空なら合格。source_url は台帳の入口 URL（ホスト照合の基準）。"""
    if not isinstance(raw, dict):
        return ["レシピが YAML のマッピングでない"]
    c = _Check(source_url)
    c.keys("recipe", raw, set(Recipe.__dataclass_fields__))

    for key in ("rows", "row_until", "transpose", "empty_container"):
        if raw.get(key) is not None:
            c.selector(key, raw[key])
    c.int_max("max_pages", raw.get("max_pages"), MAX_PAGES)
    if raw.get("encoding") is not None and not (isinstance(raw["encoding"], str) and len(raw["encoding"]) <= 40):
        c.err("encoding: 40 文字以内の文字列でない")
    if raw.get("rows_regex") is not None:
        c.regex("rows_regex", raw["rows_regex"])
    for key in ("url", "base_url"):
        if raw.get(key) is not None:
            c.url(key, raw[key])
    if raw.get("source_url") is not None and raw["source_url"] != "doc":
        c.url("source_url", raw["source_url"])

    if "empty_text" in raw:
        c.str_list("empty_text", raw["empty_text"])
    if "empty_selector" in raw:
        for i, s in enumerate(c.str_list("empty_selector", raw["empty_selector"])):
            c.selector(f"empty_selector[{i}]", s)
    if "empty_absent" in raw:
        ea = c.keys("empty_absent", raw["empty_absent"], EMPTY_ABSENT_KEYS)
        for k in EMPTY_ABSENT_KEYS & ea.keys():
            c.selector(f"empty_absent.{k}", ea[k])

    if "steps" in raw:
        steps = raw["steps"]
        if not isinstance(steps, list):
            c.err("steps: リストでない")
        else:
            for i, st in enumerate(steps):
                w = f"steps[{i}]"
                d = c.keys(w, st, STEP_KEYS)
                for k in ("follow", "follow_all", "paginate", "pdf_links"):
                    if k in d:
                        c.step_link(f"{w}.{k}", d[k])
                if "follow_text" in d and not isinstance(d["follow_text"], str):
                    c.err(f"{w}.follow_text: 文字列でない")
                c.int_max(f"{w}.max", d.get("max"), MAX_PAGES)
                if isinstance(d.get("render"), dict):
                    rd = c.keys(f"{w}.render", d["render"], RENDER_KEYS)
                    if "wait_for" in rd:
                        c.selector(f"{w}.render.wait_for", rd["wait_for"])
                    c.int_max(f"{w}.render.wait_ms", rd.get("wait_ms"), MAX_WAIT_MS)
                if "render_json" in d:
                    rj = c.keys(f"{w}.render_json", d["render_json"], RENDER_JSON_KEYS)
                    if "follow" in rj:
                        c.step_link(f"{w}.render_json.follow", rj["follow"])
                    c.int_max(f"{w}.render_json.max", rj.get("max"), MAX_PAGES)

    if "row_filter" in raw:
        rf = c.keys("row_filter", raw["row_filter"], ROW_FILTER_KEYS)
        for k in ("text_has_any", "text_lacks"):
            if k in rf:
                c.str_list(f"row_filter.{k}", rf[k])
        for k in ("field_lacks", "field_has_any"):
            if k in rf:
                fl = rf[k]
                if not isinstance(fl, dict):
                    c.err(f"row_filter.{k}: マッピングでない")
                else:
                    if len(fl) > MAX_LIST_ITEMS:
                        c.err(f"row_filter.{k}: {len(fl)} 項目 > {MAX_LIST_ITEMS}")
                    for name, words in fl.items():
                        c.str_list(f"row_filter.{k}.{name}", words)

    if "image" in raw:
        img = raw["image"]
        if isinstance(img, str):
            c.selector("image", img, with_attr=True)
        else:
            d = c.keys("image", img, IMAGE_KEYS)
            if "selector" in d:
                c.selector("image.selector", d["selector"], with_attr=True)
            if "exclude" in d:
                c.str_list("image.exclude", d["exclude"])
            for k in ("scope", "stop_at"):
                if d.get(k) is not None:
                    c.selector(f"image.{k}", d[k])

    if "fields" in raw:
        fields = raw["fields"]
        if not isinstance(fields, dict):
            c.err("fields: マッピングでない")
        else:
            if len(fields) > MAX_LIST_ITEMS:
                c.err(f"fields: {len(fields)} 項目 > {MAX_LIST_ITEMS}")
            for name, spec in fields.items():
                c.field_spec(f"fields.{name}", spec)

    if "species" in raw:
        sp = c.keys("species", raw["species"], SPECIES_KEYS)
        if "selector" in sp:
            c.selector("species.selector", sp["selector"])
        if "map" in sp:
            if not isinstance(sp["map"], dict):
                c.err("species.map: マッピングでない")
            elif len(sp["map"]) > MAX_MAP_ITEMS:
                c.err(f"species.map: {len(sp['map'])} 項目 > {MAX_MAP_ITEMS}")

    if "pdf" in raw:
        c.keys("pdf", raw["pdf"], PDF_KEYS)

    if len(c.selectors) > MAX_SELECTORS:
        c.err(f"セレクタが {len(c.selectors)} 本 > {MAX_SELECTORS}")

    return c.errors + _probe_regexes(c.regexes)
