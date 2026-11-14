#!/usr/bin/env python3
"""oneco v2 静的サイト生成。data/latest.json → site/dist/。

使い方（v2 ディレクトリで）:

    python site/build.py [--data data/latest.json] [--out site/dist] [--config site/config.json]

`python -m site.build` は使えない。`site` は Python 標準ライブラリのモジュール名で、
インタプリタ起動時に先に読み込まれるため、このディレクトリをパッケージとして解決できない。

標準ライブラリだけで動く。HTML に埋める値は全部 esc() を通し、href/src に入れる URL は
safe_url() で http(s) 以外を捨てる。

出力先は前回の build が作ったもの（目印 .oneco-build がある）か空のときだけ中身を消して作り直す。
それ以外のディレクトリを渡すと止まる（消してはいけない場所を消さないため）。

site/static/ の中身（ブランドの SVG・favicon・about の写真）はそのまま出力先にコピーする。
ロゴは旧サイト（frontend/public/brand/）の「ふたつの円」（コーラル = 犬のポム、ブルーグリーン = 猫のビリー）と
細線のワードマーク。配色も旧サイト（frontend/app/globals.css）の primary #0369a1 系を引き継ぐ。

config.json:
    site_name   サイト名
    base_url    公開 URL（OG タグ・sitemap の絶対 URL に使う）
    issues_url  取り下げ・訂正の依頼窓口（GitHub Issues）
    contact_email  GitHub アカウントの無い人向けの連絡先メール（空なら「GitHub アカウント（無料）が必要」と書く）
    affiliate   「迎える準備」枠。[{"title": "…", "url": "https://…", "note": "…", "species": "dog か cat かその一覧（省略でどの子にも）", "beacon": "A8 の計測用画像の URL（省略可）"}]。里親募集の子のページにだけ出す。空なら枠ごと出さない（about も「いまは広告を載せていません」になる）
    ga4_id      GA4 の測定 ID（G-…）。あれば全ページの head に gtag.js を入れ、about に「アクセス解析」の節を出す。無い・形が違うときは何も出さない
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA = ROOT / "data" / "latest.json"
DEFAULT_OUT = ROOT / "site" / "dist"
DEFAULT_CONFIG = ROOT / "site" / "config.json"
STATIC_DIR = ROOT / "site" / "static"
MARKER = ".oneco-build"

DEFAULT_CFG: dict[str, Any] = {
    "site_name": "oneco",
    "base_url": "https://oneco.pet",
    "issues_url": "https://github.com/9mak/oneco/issues",
    "repo_url": "https://github.com/9mak/oneco",
    "tagline": "全国の保護動物情報をひとつに",
    "contact_email": "",
    "affiliate": [],
}

# ブランドマーク「ふたつの円」（site/static/brand/oneco-mark.svg = 旧 frontend/public/brand/oneco-mark.svg。2026-07-08 確定）。
# コーラルの円 = 犬のポム、ブルーグリーンの円 = 猫のビリー。全ページに毎日埋め込むのでインラインでなく <img> で 1 ファイルを参照する
MARK_IMG = '<img class="mark" src="/brand/oneco-mark.svg" width="34" height="34" alt="" decoding="async">'

# ワードマーク（frontend/public/brand/oneco-logo.svg と同じ。細線ジオメトリック、色は currentColor）
WORDMARK_SVG = """<svg class="wordmark" viewBox="-8 -8 610 136" role="img" aria-label="oneco" focusable="false">
<g fill="none" stroke="currentColor" stroke-width="3.2">
<circle cx="61" cy="60" r="51"/>
<path d="M142,110 L142,10 L228,110 L228,10"/>
<path d="M338,10 L266,10 L266,110 L338,110 M266,60 L330,60"/>
<path d="M449.8,32.2 A51,51 0 1 0 449.8,87.8"/>
<circle cx="533" cy="60" r="51"/>
</g>
</svg>"""

# 「ふたつの円」を小さく並べた区切り（about ページで使う）
TWO_CIRCLES_SVG = ('<svg width="44" height="24" viewBox="0 0 44 24" aria-hidden="true" focusable="false">'
                   '<circle cx="17" cy="12" r="10" fill="#E8826E" fill-opacity="0.8"/>'
                   '<circle cx="27" cy="12" r="10" fill="#6FAEBB" fill-opacity="0.8"/></svg>')

SPECIES = {"dog": "犬", "cat": "猫", "other": "その他"}
# 区分の呼び方は 2026-10-02 におまえさんが決めた（「収容」を使わず、飼い主さんが探している子の区分 lost を追加）
KINDS = {"adoption": "里親募集", "sheltered": "保護中", "stray": "迷子", "lost": "探してます"}
KIND_HELP = {
    "adoption": "新しい家族を募集している子",
    "sheltered": "自治体や市民に保護されている子",   # 千葉市・越谷市の「個人保護」は市民が保護している子（T518）
    "stray": "飼い主さんが分からないまま保護されている子",
    "lost": "飼い主さんが探している迷子の子",
}
# 個体ページの「すでに〜場合があります」は区分ごと（探してますの子に「譲渡・返還」とは書かない。2026-11-13 Codex #16）
FINE_BY_KIND = {
    "adoption": "すでに譲渡先が決まっている場合があります。",
    "sheltered": "すでに飼い主さんの元に戻ったり、譲渡されたりしている場合があります。",
    "stray": "すでに飼い主さんの元に戻ったり、譲渡されたりしている場合があります。",
    "lost": "すでに見つかっている場合があります。",
}
NO_SPECIES = "種類の記載なし"   # 自治体のページで犬か猫かも品種も毛色も分からない子（奈良市・呉市。2026-11-13 agy「里親募集の子」の重複）
KIND_ORDER = {"adoption": 0, "sheltered": 1, "stray": 2, "lost": 3}
# 区分ごとの項目名の言い換え（探してます: 収容日・保護場所ではなく、いなくなった日・場所）
FIELD_LABELS_BY_KIND = {"lost": {"shelter_date": "いなくなった日", "location": "いなくなった場所"}}
STATUS = {
    "ok": "掲載あり",
    "empty": "本日は 0 頭",
    "failed": "本日は読めませんでした。自治体のページをご確認ください",
    "ambiguous_empty": "本日は読めませんでした。自治体のページをご確認ください",   # 0 頭に見えるが確定できない日も前回分は載せず failed と同じ扱い
    "link_only": "リンクのみ",
    "disabled": "停止中",
}
# 詳細ページに出す項目（取れているものだけ出す）
FIELDS = [
    ("name", "名前"),
    ("sex", "性別"),
    ("age", "年齢・生年月日"),
    ("breed", "種類"),
    ("color", "毛色"),
    ("size", "大きさ"),
    ("management_no", "管理番号"),
    ("shelter_date", "保護日"),
    ("location", "保護場所・発見場所"),
    ("note", "備考"),
]
PREF_ORDER = [
    "北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県",
    "茨城県", "栃木県", "群馬県", "埼玉県", "千葉県", "東京都", "神奈川県",
    "新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県", "岐阜県", "静岡県", "愛知県",
    "三重県", "滋賀県", "京都府", "大阪府", "兵庫県", "奈良県", "和歌山県",
    "鳥取県", "島根県", "岡山県", "広島県", "山口県",
    "徳島県", "香川県", "愛媛県", "高知県",
    "福岡県", "佐賀県", "長崎県", "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県",
]
PREF_INDEX = {p: i for i, p in enumerate(PREF_ORDER)}
ID_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")


# ---------------------------------------------------------------- helpers

def esc(v: Any) -> str:
    """HTML に埋める値は必ずこれを通す。"""
    return html.escape("" if v is None else str(v), quote=True)


def safe_url(u: Any) -> str:
    """href/src に入れてよい URL だけ返す（http/https 以外は空）。"""
    if not isinstance(u, str):
        return ""
    u = u.strip()
    return u if u.lower().startswith(("http://", "https://")) else ""


def tel_href(phone: str) -> str:
    digits = re.sub(r"[^0-9+]", "", phone)
    return f"tel:{digits}" if digits else ""


def pref_key(p: str) -> tuple[int, str]:
    return PREF_INDEX.get(p, len(PREF_ORDER)), p


def pref_path(p: str) -> str:
    return f"/pref/{quote(p)}/"


def animal_path(aid: str) -> str:
    return f"/animals/{quote(aid)}/"


def fmt_date(s: Any) -> str:
    """'2026-09-28' や '2026-09-28-saga' → '2026年9月28日'。読めなければそのまま。"""
    if not isinstance(s, str):
        return ""
    try:
        d = datetime.strptime(s[:10], "%Y-%m-%d").date()
    except ValueError:
        return s
    return f"{d.year}年{d.month}月{d.day}日"


def iso_date(s: Any) -> str:
    if isinstance(s, str):
        try:
            return datetime.strptime(s[:10], "%Y-%m-%d").date().isoformat()
        except ValueError:
            pass
    return date.today().isoformat()


def species_key(a: dict[str, Any]) -> str:
    """dog | cat | other | none。species が null・空の子（自治体のページで犬か猫か分からない子。T518）は none で、
    犬・猫の絞り込みに入れず「すべて」でだけ出す。dog・cat・other 以外の値は従来どおり other。"""
    sp = a.get("species")
    if sp is None or sp == "":
        return "none"
    return str(sp) if str(sp) in SPECIES else "other"


def species_label(a: dict[str, Any]) -> str:
    """種別の表示名。種別なしの子は空（バッジを出さない）。"""
    k = species_key(a)
    return "" if k == "none" else SPECIES[k]


def species_noun(a: dict[str, Any]) -> str:
    """見出し・説明文の「◯◯の犬」の部分。種別なしの子は「子」（保護中の子）、犬猫以外は「動物」（保護中の動物）。"""
    if species_key(a) == "other":
        return "動物"
    return species_label(a) or "子"


def kind_label(a: dict[str, Any]) -> str:
    return KINDS.get(str(a.get("kind")), str(a.get("kind") or ""))


def kind_phrase(a: dict[str, Any]) -> str:
    """区分と種別をつないだ呼び方。「探してます」は「探してますの犬」と続けられないので「探している犬」にする。"""
    if a.get("kind") == "lost":
        return f"探している{species_noun(a)}"
    return f"{kind_label(a)}の{species_noun(a)}"


# 表記ゆれをそろえる（表示だけ。data.json の値は掲載元のまま）。2026-11-13 おまえさん「違和感がある文字列」
_MIX_BREED = re.compile(r"^(?:雑|雑種|MIX|Mix|mix|ミックス|雑種\s*[(（]\s*ミックス\s*[)）]|ミックス\s*[(（]\s*雑種\s*[)）]"
                        r"|(?:MIX|Mix|mix|ミックス|雑種)\s*[(（]\s*(?:品種)?不明\s*[)）])$")   # 「MIX(品種不明)」（横須賀市）も雑種
_SEX_WORDS = {"雄": "オス", "おす": "オス", "♂": "オス", "雌": "メス", "めす": "メス", "♀": "メス"}
_SEX_HEAD = re.compile(r"^(去勢|避妊|不妊)?(雄|雌|おす|めす|♂|♀)(?=$|[\s(（])")   # 「雄(去勢済み)」「去勢雄」の性別だけ言い換える（「雌雄不明」は触らない）
_NOT_A_BREED = {"その他", "不明", "-", "ー", "犬", "猫", "いぬ", "ねこ", "イヌ", "ネコ",
                "雄", "雌", "オス", "メス", "おす", "めす", "♂", "♀"}   # 品種の欄に種別・性別・「不明」しか無い子（佐賀「雌（オス）」）
_NOT_A_SEX = {"不明", "-", "ー"}
_HEADLINE_SEX = re.compile(r"(?:去勢|不妊|避妊)?(?:オス|メス)")   # 見出しに出す性別はこの形だけ
_NOT_A_COLOR = {"不明", "不詳", "-", "ー", "その他"}
# 毛色の欄に性別・年齢の語や特徴の文が入っている値は見出しに使わない（千葉市「避妊雌」・船橋市「子猫」・「茶色、縞模様あり」）。
_COLOR_NOT_FOR_HEADLINE = re.compile(r"雌|雄|オス|メス|避妊|去勢|不妊|子猫|子犬|成猫|成犬|。|あり")   # 読点だけの多色（「黒、白」）は毛色として使う（#124 F-03）
_EMPTY_NOTES = {"無", "無し", "なし", "有", "-", "ー", "募集中"}   # 備考に出しても意味の無い値（大分「無」「有」・福岡県動物愛護協会「募集中」）
# 名前の欄に入った、名前でないもの（2026-11-13 Codex #7・#13・#14）
_NOT_A_NAME = re.compile(r"探して(?:い)?ます|保護して(?:い)?ます")   # 旭川市あにまある「犬 探しています(フルサワ)」= 告知の見出し
_NAME_IN_NOTE = re.compile(r"名前\s*[:：]\s*([^\s・、。,，/／]+)")     # その子の名前は備考の「・名前:あの」にある
_NOT_AN_AGE = {"不明", "不詳", "-", "ー", "?", "？"}
_ERA = {"令和": 2018, "R": 2018, "r": 2018, "平成": 1988, "H": 1988, "h": 1988}
_DATES = [
    re.compile(r"(?P<y>\d{4})\s*[/\-.]\s*(?P<m>\d{1,2})\s*[/\-.]\s*(?P<d>\d{1,2})"),
    re.compile(r"(?P<y>\d{4})年\s*(?P<m>\d{1,2})月\s*(?P<d>\d{1,2})日"),
    re.compile(r"(?P<era>令和|平成|[RrHh])\s*(?P<y>\d{1,2}|元)\s*[年.\-/、]\s*(?P<m>\d{1,2})\s*[月.\-/]\s*(?P<d>\d{1,2})日?"),
]
_AGE_IN_SIZE = re.compile(r"子|仔|成猫|成犬|子猫|子犬|生後.+|幼齢.*")   # 大きさの欄に年齢が入っている（千葉市「仔」「生後1か月前後」）
_SIZE_WORDS = {"中": "中型", "小": "小型", "大": "大型"}


def disp_breed(v: Any) -> str:
    s = str(v or "").strip()
    return "雑種" if _MIX_BREED.match(s) else s


def disp_sex(v: Any) -> str:
    """性別の表示。頭の 雄・雌 等をオス・メスに、かっこ書きは全角に（「雄(去勢済み)」→「オス（去勢済み）」）。"""
    s = str(v or "").strip()
    s = _SEX_HEAD.sub(lambda m: (m.group(1) or "") + _SEX_WORDS[m.group(2)], s)
    s = re.sub(r"\s+(?=[(（])", "", s)   # 「オス (去勢済)」のかっこ前の空白（#124 F-05）
    return re.sub(r"\(([^()（）]*)\)", r"（\1）", s)


def disp_name(a: dict[str, Any]) -> str:
    """名前の表示。告知の見出し（「探しています」）・管理番号入り・「※」の注記は名前として扱わない。"""
    s = str(a.get("name") or "").strip()
    if not s:
        return ""
    if _NOT_A_NAME.search(s):
        m = _NAME_IN_NOTE.search(str(a.get("note") or ""))
        return m.group(1) if m else ""
    no = str(a.get("management_no") or "").strip()
    if len(no) >= 3 and (s.endswith(no) or s.startswith(no)):   # 福島市「譲渡猫R7ねー35」（管理番号は詳細の表に出る）。短い番号は名前の一部かもしれない（#124 F-09）
        return ""
    return s.split("※", 1)[0].strip()   # 「べティちゃん ※現在アシストファーム南国店にいます」（注記は備考にもある）


_REF_DATE: list[date] = []   # 掲載日（build_site が入れる）。「生まれ」を付けてよいかの判定に使う。空なら今日


def parse_date(s: Any) -> date | None:
    """日付だけの値（令和・R・/・-・. の形）を date に。時刻や注記の付いた値、年の無い値は None。"""
    t = str(s or "").strip()
    for p in _DATES:
        m = p.fullmatch(t)
        if not m:
            continue
        g = m.groupdict()
        y = int(g["y"]) if g["y"] != "元" else 1
        if g.get("era"):
            y += _ERA[g["era"]]
        try:
            return date(y, int(g["m"]), int(g["d"]))
        except ValueError:
            return None
    return None


def norm_date(s: Any) -> str:
    """日付だけの値を「2026年7月23日」に。日付だけでなければ空（元のまま出す）。"""
    d = parse_date(s)
    return f"{d.year}年{d.month}月{d.day}日" if d else ""


def _tidy_numbers(s: str) -> str:
    """数字の後の 才 → 歳、ヶ月 等 → か月、数字の間の ~ → 〜。"""
    s = re.sub(r"(?<=[0-9])才", "歳", s)
    s = re.sub(r"[ヶヵカケ]月", "か月", s)
    return re.sub(r"(?<=[0-9歳月])\s*[~～]\s*(?=[0-9])", "〜", s)


def disp_age(a: dict[str, Any]) -> str:
    """年齢の表示。日付だけなら「2026年6月6日生まれ」、掲載元が推定と書いている日付（レシピの prefix「推定 」）は
    「2026年6月6日生まれ（推定）」。掲載日より後の日付は「生まれ」と言わない（徳島の誤記。#124 F-01）。
    単位の無い数字（沖縄の推定年齢「10」）はそう書き添える。年齢が空か「不明」で大きさの欄に年齢が入っていれば（千葉市「仔」）それを年齢にする。"""
    s = _strip_estimated_unknown(str(a.get("age") or "").strip())
    if not s or s in _NOT_AN_AGE:
        size = str(a.get("size") or "").strip()
        if not _AGE_IN_SIZE.fullmatch(size):
            return s
        if size in ("子", "仔") and species_key(a) in ("dog", "cat"):
            return f"子{species_label(a)}"
        s = size
    est = s.startswith("推定")
    d = parse_date(re.sub(r"^推定\s*", "", s) if est else s)
    if d:
        ymd = f"{d.year}年{d.month}月{d.day}日"
        if d > (_REF_DATE[0] if _REF_DATE else date.today()):
            return f"推定 {ymd}" if est else ymd
        return f"{ymd}生まれ（推定）" if est else f"{ymd}生まれ"
    if re.fullmatch(r"\d+(?:\.\d+)?", s):
        return f"{s}（単位の記載なし）"
    return _tidy_numbers(s)


def _strip_estimated_unknown(s: str) -> str:
    """レシピが「推定 」を足した「推定 不明」は「不明」として扱う（#124 G-03）。"""
    m = re.fullmatch(r"推定\s*(.+)", s)
    return m.group(1) if m and m.group(1) in _NOT_AN_AGE else s


def card_age(a: dict[str, Any]) -> str:
    """カードの下の行に出す年齢。「不明」や単位の無い数字は出さない。"""
    s = _strip_estimated_unknown(str(a.get("age") or "").strip())
    if s in _NOT_AN_AGE or re.fullmatch(r"\d+(?:\.\d+)?", s):
        return ""
    return disp_age(a)


def disp_value(key: str, v: Any) -> str:
    """詳細ページの項目の表示値。空にした項目は出さない。名前・年齢は disp_name・disp_age（子の他の項目を見る）。"""
    if key == "breed":
        return disp_breed(v)
    if key == "sex":
        return disp_sex(v)
    s = str(v or "").strip()
    if key == "note" and s in _EMPTY_NOTES:
        return ""
    if key == "shelter_date":
        return norm_date(s) or s
    if key == "size":
        return _tidy_numbers(_SIZE_WORDS.get(s, s))
    return s


def disp_field(a: dict[str, Any], key: str) -> str:
    if key == "name":
        return disp_name(a)
    if key == "age":
        return disp_age(a)
    if key == "size":   # 大きさの欄の年齢語は、年齢が空か「不明」のときだけ年齢に移す（それ以外は捨てない。#124 F-04）
        age = str(a.get("age") or "").strip()
        if _AGE_IN_SIZE.fullmatch(str(a.get("size") or "").strip()) and (not age or age in _NOT_AN_AGE):
            return ""
    return disp_value(key, a.get(key))


_BREED_PAREN = re.compile(r"(.+?)\s*[(（]\s*([^()（）]+?)\s*[)）]")


def _breed_parts(a: dict[str, Any]) -> tuple[str, str]:
    """(見出しに使う品種, 下の行に回すかっこ書き)。「雑種(キジ白)」→（雑種, キジ白）、本体が「不明」なら
    かっこの中を品種に（「不明(フレンチブルドッグ風)」→（フレンチブルドッグ風, ""））。agy 2026-11-14 ③"""
    breed = disp_breed(a.get("breed"))
    m = _BREED_PAREN.fullmatch(breed)
    base, note = (disp_breed(m.group(1)), m.group(2)) if m else (breed, "")   # 「ミックス(キジ白)」「雑(メインクーン風)」の本体も雑種に
    if base in _NOT_A_BREED and note:
        base, note = note, ""
    return ("" if base in _NOT_A_BREED else base), note


def _headline_parts(a: dict[str, Any]) -> tuple[str, str, str]:
    """(見出しの本体, 使った項目 breed|color|species|none, 性別)。"""
    breed, _ = _breed_parts(a)
    sex = disp_sex(re.sub(r"\s*[(（].*$", "", str(a.get("sex") or "")))   # 「オス(去勢済)」のかっこ書きは見出しでは外す（下の行と詳細の表に出す）
    sex = sex if _HEADLINE_SEX.fullmatch(sex) else ""   # 複数頭をまとめた欄（「メス:4匹 オス:2匹」）等は見出しに出さない（#123 reviewer F-02）
    color = str(a.get("color") or "").strip()
    color = "" if color in _NOT_A_COLOR or len(color) > 12 or _COLOR_NOT_FOR_HEADLINE.search(color) else color
    if breed:
        return breed, "breed", sex
    if color:
        return f"{color}の{species_noun(a)}", "color", sex
    if species_key(a) == "none":
        return NO_SPECIES, "none", sex   # 区分で呼ぶとバッジと重なる（「里親募集」＋「里親募集の子」。agy 2026-11-13）
    return species_noun(a), "species", sex


def headline(a: dict[str, Any]) -> str:
    """カード・詳細の見出し。名前があれば名前。無ければ品種と性別（「ミニチュア・シュナウザー（オス）」）、品種が無ければ
    毛色と種別（「茶白の猫（メス）」）、それも無ければ種別（「犬（オス）」）。区分（里親募集など）はバッジにあるので見出しに重ねない。"""
    name = disp_name(a)
    if name:
        return name
    base, _, sex = _headline_parts(a)
    if not sex:
        return base
    return f"{base}・{sex}" if re.search(r"[(（)）]", base) else f"{base}（{sex}）"   # 品種にかっこ書きがあれば（「雑種(柴風)」）かっこを重ねない


def subline(a: dict[str, Any]) -> str:
    """見出しの下の行。見出しに出した項目は重ねない。見出しに性別を出しても手術の注記（「去勢手術済」）は残す。
    何も無い子は管理番号（写真を止めていて同じ見た目のカードが並ぶ熊本県動愛など。agy 2026-11-13）。"""
    raw_sex = disp_sex(a.get("sex"))
    if disp_name(a):
        breed = disp_breed(a.get("breed"))
        parts = ["" if breed in _NOT_A_BREED else breed, "" if raw_sex in _NOT_A_SEX else raw_sex, card_age(a)]
    else:
        _, used, sex = _headline_parts(a)
        color = str(a.get("color") or "").strip()
        parts = [_breed_parts(a)[1]] if used == "breed" else []   # 見出しから外した品種のかっこ書き（「キジ白」）
        parts += [color] if used != "color" and color not in _NOT_A_COLOR else []   # 「不明」だけの行は出さない（#123 F-06）
        if sex:
            m = re.search(r"[(（]\s*([^)）]+?)\s*[)）]", str(a.get("sex") or ""))
            parts += [m.group(1)] if m else []
        elif raw_sex not in _NOT_A_SEX:
            parts += [raw_sex]   # 見出しに出さなかった性別の欄は下の行に
        parts += [card_age(a)]
    parts = [p.strip() for p in parts if p and p.strip()]
    no = str(a.get("management_no") or "").strip()
    if not parts and no:
        parts = [f"管理番号 {no}"]
    return " / ".join(parts)


def photo_alt(a: dict[str, Any]) -> str:
    """詳細ページの写真の alt（「雑種の犬（オス）」「ポチ（犬）」）。カードの写真は alt="" にする（カードの文字で読める。agy ⑦）。"""
    sp = species_noun(a) if species_key(a) != "none" else ""
    name = disp_name(a)
    if name:
        return f"{name}（{sp}）" if sp else name
    base, used, sex = _headline_parts(a)
    if used == "breed" and sp and sp not in base:
        base = f"{base}の{sp}"   # 見出しに種別の語が無ければ足す（読み上げで犬か猫か分かるように。#123 reviewer F-03）
    if not sex:
        return base
    return f"{base}・{sex}" if re.search(r"[(（)）]", base) else f"{base}（{sex}）"


def shorten(s: Any, n: int) -> str:
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


# ---------------------------------------------------------------- page shell

GA4_ID_RE = re.compile(r"G-[A-Z0-9]{4,20}")


def ga4_id(cfg: dict[str, Any]) -> str:
    """config の ga4_id が G-… の形のときだけ返す（形が違えば空。script に埋め込むので形で絞る）。"""
    gid = str(cfg.get("ga4_id") or "").strip()
    return gid if GA4_ID_RE.fullmatch(gid) else ""


def ga4_head(cfg: dict[str, Any]) -> str:
    gid = ga4_id(cfg)
    if not gid:
        return ""
    return (f'\n<script async src="https://www.googletagmanager.com/gtag/js?id={gid}"></script>'
            "\n<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}"
            f"gtag('js', new Date());gtag('config', '{gid}');</script>")


def page(cfg: dict[str, Any], *, title: str, desc: str, path: str, body: str,
         og_image: str = "", og_type: str = "website", extra_head: str = "", body_attrs: str = "",
         data_date: str = "") -> str:
    site = esc(cfg["site_name"])
    base = cfg["base_url"].rstrip("/")
    url = esc(base + path)
    # 写真の無いページは OG 画像にブランドのアバター（ふたつの円）を使う
    og_src = og_image or f"{base}/brand/oneco-avatar-512.png"
    og_img = f'\n<meta property="og:image" content="{esc(og_src)}">'
    full_title = esc(title) if title == cfg["site_name"] else f"{esc(title)}｜{site}"
    tagline = esc(cfg.get("tagline") or "")
    tagline_html = f'<span class="tagline">{tagline}</span>' if tagline else ""
    repo = safe_url(cfg.get("repo_url")) or DEFAULT_CFG["repo_url"]
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{full_title}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{url}">
<meta property="og:type" content="{esc(og_type)}">
<meta property="og:site_name" content="{site}">
<meta property="og:title" content="{full_title}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{url}">{og_img}
<meta name="twitter:card" content="{'summary_large_image' if og_image else 'summary'}">
<meta name="theme-color" content="#ffffff">
<link rel="icon" href="/favicon.ico" sizes="32x32">
<link rel="icon" href="/icon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="stylesheet" href="/style.css">{extra_head}{ga4_head(cfg)}
</head>
<body{body_attrs}>
<header class="site-head">
<div class="site-head-in">
<a class="brand" href="/" aria-label="{site} トップへ">{MARK_IMG}{WORDMARK_SVG}{tagline_html}</a>
<nav class="nav" aria-label="メインナビゲーション"><a href="/">都道府県</a><a href="/sources/">情報源</a><a href="/about/">このサイトについて</a></nav>
</div>
</header>
<main class="wrap">
{body}
</main>
<footer class="site-foot">
<div class="foot-brand"><img src="/brand/oneco-mark.svg" width="28" height="28" alt="" loading="lazy"><span>ふたつの円は、犬のポムと猫のビリー。<a href="/about/">このサイトについて</a></span></div>
<p>掲載しているのは各自治体が公開している情報です。{f'データ確認日：{esc(fmt_date(data_date))}。' if data_date else ''}最新の状況は自治体のページ・電話でご確認ください。</p>
<p><a href="/sources/">情報源の一覧</a> ・ <a href="/about/#takedown">取り下げ・訂正の依頼</a> ・ <a href="{esc(repo)}" rel="noopener" target="_blank">GitHub</a></p>
</footer>
</body>
</html>
"""


# ---------------------------------------------------------------- partials

def placeholder(a: dict[str, Any] | None = None) -> str:
    """写真が無い子の枠。絵は CSS（.ph の疑似要素）だけで描く。写真を止めている掲載元（T630: 許諾待ち・不可）の子は
    掲載元には写真があるので「写真はありません」とは書かない。それ以外も、取れなかっただけかもしれないので「無い」とは言い切らない（Codex #22）。"""
    msg = "写真は自治体のページで見られます" if a and a.get("_photo_withheld") else "写真は自治体のページでご確認ください"
    sp = species_key(a) if a else "none"
    cls = f"ph ph-{sp}" if sp in ("dog", "cat") else "ph"   # 犬・猫はシルエット、それ以外は肉球（2026-11-13）
    return f'<div class="{cls}" role="img" aria-label="{msg}"><span>{msg}</span></div>'


def media(a: dict[str, Any], *, big: bool = False) -> str:
    img = safe_url(a.get("image_url"))
    if not img:
        return f'<div class="media">{placeholder(a)}</div>'
    # カードはリンクの中の見出し・下の行・自治体名で読めるので、写真は飾り（alt=""）。同じ語を 4 回読み上げない（agy ⑦）
    alt = esc(photo_alt(a)) if big else ""
    attrs = 'loading="eager" fetchpriority="high"' if big else 'loading="lazy"'
    # 自治体サイトの写真を直接表示する。取れなかったときは JS でプレースホルダに差し替える
    return (f'<div class="media"><img src="{esc(img)}" alt="{alt}" referrerpolicy="no-referrer" {attrs} '
            f'onerror="this.parentNode.classList.add(\'noimg\');this.remove()">{placeholder()}</div>')


def badges(a: dict[str, Any]) -> str:
    sp, kd = species_key(a), str(a.get("kind") or "")
    sp_html = f'<span class="badge sp-{esc(sp)}">{esc(species_label(a))}</span>' if species_label(a) else ""   # 種別なしの子はバッジなし
    return sp_html + f'<span class="badge kd-{esc(kd)}">{esc(kind_label(a))}</span>'


def card(a: dict[str, Any]) -> str:
    sub = subline(a)
    sub_html = f'<p class="sub">{esc(sub)}</p>' if sub else ""
    return f"""<a class="card" href="{esc(animal_path(a['id']))}" data-species="{esc(species_key(a))}" data-kind="{esc(a.get('kind') or '')}">
{media(a)}
<div class="card-body">
<div class="badges">{badges(a)}</div>
<h3>{esc(headline(a))}</h3>
{sub_html}
<p class="muni">{esc(a.get('municipality'))}</p>
</div>
</a>"""


def filter_bar(name: str, options: list[tuple[str, str]], label: str) -> str:
    btns = "".join(
        f'<button type="button" data-filter="{esc(name)}" data-value="{esc(v)}" aria-pressed="{"true" if v == "all" else "false"}">{esc(lb)}</button>'
        for v, lb in options)
    return f'<div class="chips" role="group" aria-label="{esc(label)}">{btns}</div>'


def species_options(c: Counter[str]) -> list[tuple[str, str]]:
    """種別の絞り込み。犬猫以外と種類の記載なしの子がいれば「その他」も出す（agy ⑤）。"""
    opts = [("all", "すべて"), ("dog", "犬"), ("cat", "猫")]
    return [*opts, ("other", "その他")] if c["other"] + c["none"] else opts


def species_counts(c: Counter[str], *, bold: bool) -> str:
    """「犬 30 頭 ・ 猫 67 頭 ・ その他の動物 2 頭 ・ 種類の記載なし 1 頭」（統計の行）。"""
    def n(k: str) -> str:
        return f"<b>{c[k]}</b>" if bold else str(c[k])
    parts = [f"犬 {n('dog')} 頭", f"猫 {n('cat')} 頭"]
    parts += [f"その他の動物 {n('other')} 頭"] if c["other"] else []
    parts += [f"{NO_SPECIES} {n('none')} 頭"] if c["none"] else []
    return " ・ ".join(parts)


# ---------------------------------------------------------------- pages

def build_index(cfg: dict[str, Any], data: dict[str, Any], animals: list[dict[str, Any]]) -> str:
    by_pref: dict[str, Counter[str]] = {}
    for a in animals:
        c = by_pref.setdefault(str(a.get("prefecture") or "不明"), Counter())
        c[species_key(a)] += 1
        c["total"] += 1
    total = Counter(species_key(a) for a in animals)
    ok_sources = sum(1 for s in data.get("sources", []) if s.get("status") == "ok")
    rows = []
    for p in sorted(by_pref, key=pref_key):
        c = by_pref[p]
        rows.append(
            f'<li data-pref="{esc(p)}" data-dog="{c["dog"]}" data-cat="{c["cat"]}" data-other="{c["other"] + c["none"]}" data-total="{c["total"]}">'
            f'<a href="{esc(pref_path(p))}"><span class="pref">{esc(p)}</span>'
            f'<span class="cnt"><b class="n">{c["total"]}</b> 頭</span></a></li>')
    # 今日 1 頭もいない県は一覧から消えるので、0 なのか対象外なのか分かるように名前を出す（Codex #10。島根県）
    empty_prefs = [p for p in PREF_ORDER if p not in by_pref]
    missing = (f'<p class="hint">本日の掲載が無い都道府県：{esc("、".join(empty_prefs))}'
               f'（確認の状況は<a href="/sources/">情報源の一覧</a>にあります）</p>\n' if rows and empty_prefs else "")
    body = f"""<section class="intro">
<h1>保護犬・保護猫を、自治体から探す</h1>
<p>{esc(cfg['site_name'])} は、全国の自治体（動物愛護センター・保健所など）が公開している保護犬・保護猫の情報を 1 か所にまとめたサイトです。毎日それぞれの自治体のページを確認し、その日に掲載されている子を出典つきで載せています。気になる子がいたら、掲載元の自治体に直接ご連絡ください。</p>
<p class="stats">{esc(fmt_date(data.get('date')))}時点：{species_counts(total, bold=True)}（{len(by_pref)} 都道府県・{ok_sources} 自治体ページ）</p>
</section>
<section>
<h2>都道府県から探す</h2>
{filter_bar('species', species_options(total), '動物の種類')}
<ul class="pref-list" id="pref-list">
{chr(10).join(rows) if rows else '<li class="empty">本日の掲載はありません。</li>'}
</ul>
{missing}<p class="hint">区分の意味：{'。'.join(f'{esc(KINDS[k])}＝{esc(KIND_HELP[k])}' for k in KINDS)}。</p>
</section>
<script>
(function(){{
  var list=document.getElementById('pref-list');
  var btns=document.querySelectorAll('[data-filter="species"]');
  function apply(v){{
    btns.forEach(function(b){{b.setAttribute('aria-pressed',b.dataset.value===v?'true':'false');}});
    list.querySelectorAll('li[data-pref]').forEach(function(li){{
      var n=Number(li.dataset[v==='all'?'total':v]||0);
      li.querySelector('.n').textContent=n;
      li.hidden=n===0;
      var a=li.querySelector('a');
      a.search=v==='all'?'':'?species='+v;
    }});
  }}
  btns.forEach(function(b){{b.addEventListener('click',function(){{apply(b.dataset.value);}});}});
}})();
</script>"""
    return page(cfg, title=cfg["site_name"], path="/", body=body, data_date=str(data.get("date") or ""),
                desc="全国の自治体が公開している保護犬・保護猫の情報を、都道府県ごとに 1 か所で探せます。毎日更新、出典つき。")


PREF_JS = """
(function(){
  var grid=document.getElementById('grid');
  var count=document.getElementById('count');
  var empty=document.getElementById('empty');
  var q=new URLSearchParams(location.search);
  var state={species:q.get('species')||'all',kind:q.get('kind')||'all'};
  function known(k){return Array.prototype.some.call(document.querySelectorAll('[data-filter="'+k+'"]'),function(b){return b.dataset.value===state[k];});}
  if(!known('species'))state.species='all';
  if(!known('kind'))state.kind='all';
  function spOk(sp){return state.species==='all'||sp===state.species||(state.species==='other'&&sp==='none');}
  function match(sp,kd){return spOk(sp)&&(state.kind==='all'||kd===state.kind);}
  function syncButtons(){document.querySelectorAll('[data-filter]').forEach(function(b){b.setAttribute('aria-pressed',state[b.dataset.filter]===b.dataset.value?'true':'false');});}
  function apply(){
    syncButtons();var n=0;
    grid.querySelectorAll('.card').forEach(function(c){var s=match(c.dataset.species,c.dataset.kind);c.hidden=!s;if(s)n++;});
    count.textContent=n;empty.hidden=n!==0;
    var p=new URLSearchParams();if(state.species!=='all')p.set('species',state.species);if(state.kind!=='all')p.set('kind',state.kind);
    var qs=p.toString();history.replaceState(null,'',location.pathname+(qs?'?'+qs:''));
  }
  document.querySelectorAll('[data-filter]').forEach(function(b){b.addEventListener('click',function(){state[b.dataset.filter]=b.dataset.value;apply();});});
  if(state.species!=='all'||state.kind!=='all')apply();
})();
"""


def build_pref(cfg: dict[str, Any], data: dict[str, Any], pref: str, animals: list[dict[str, Any]]) -> str:
    c = Counter(species_key(a) for a in animals)
    munis = sorted({str(a.get("municipality") or "") for a in animals})
    cards = "\n".join(card(a) for a in animals)
    # 説明文で「（ほか 56 頭）」と書いても何の子か分からない（agy ④）ので名指しする
    rest_desc = (f"・その他の動物 {c['other']} 頭" if c["other"] else "") + (f"・{NO_SPECIES} {c['none']} 頭" if c["none"] else "")
    body = f"""<nav class="crumbs"><a href="/">都道府県</a> › <span>{esc(pref)}</span></nav>
<h1>{esc(pref)}の保護犬・保護猫</h1>
<p class="stats">{esc(fmt_date(data.get('date')))}時点：{species_counts(c, bold=False)}。掲載元：{esc('、'.join(munis))}</p>
<div class="filters">
{filter_bar('species', species_options(c), '動物の種類')}
{filter_bar('kind', [('all', 'すべての区分'), *KINDS.items()], '掲載の区分')}
</div>
<p class="count" aria-live="polite"><b id="count">{len(animals)}</b> 頭</p>
<div class="grid" id="grid">
{cards}
</div>
<p class="empty" id="empty" hidden>この条件に当てはまる掲載はありません。</p>
<script>{PREF_JS}</script>"""
    return page(cfg, title=f"{pref}の保護犬・保護猫", path=pref_path(pref), body=body,
                body_attrs=f' data-pref="{esc(pref)}"', data_date=str(data.get("date") or ""),
                desc=f"{pref}の自治体が{fmt_date(data.get('date'))}に公開している保護犬 {c['dog']} 頭・保護猫 {c['cat']} 頭{rest_desc}の一覧。出典つき。")


def build_animal(cfg: dict[str, Any], data: dict[str, Any], a: dict[str, Any]) -> str:
    pref = str(a.get("prefecture") or "")
    muni = str(a.get("municipality") or "")
    src = safe_url(a.get("source_url"))
    rows = []
    labels = FIELD_LABELS_BY_KIND.get(str(a.get("kind")), {})
    for key, label in FIELDS:
        v = disp_field(a, key)
        if not v:
            continue
        rows.append(f"<div><dt>{esc(labels.get(key, label))}</dt><dd>{esc(v)}</dd></div>")
    phone = str(a.get("phone") or "").strip()
    addr = str(a.get("address") or "").strip()
    contact = [f"<div><dt>自治体</dt><dd>{esc(muni)}</dd></div>"]
    # contact_scope=operator（県のまとめページ等）は掲載元の運営元の連絡先で、子がいる収容先そのものではない → 「問い合わせ先」と出す（T616）
    operator = str(a.get("contact_scope") or "facility") == "operator"
    phone_label, addr_label = ("問い合わせ先", "問い合わせ先の所在地") if operator else ("電話", "所在地")
    if phone:
        href = tel_href(phone)
        contact.append(f'<div><dt>{phone_label}</dt><dd><a href="{esc(href)}">{esc(phone)}</a></dd></div>' if href
                       else f"<div><dt>{phone_label}</dt><dd>{esc(phone)}</dd></div>")
    if addr:
        contact.append(f"<div><dt>{addr_label}</dt><dd>{esc(addr)}</dd></div>")
    if not phone:
        contact.append("<div><dt>電話</dt><dd>電話番号は自治体のページでご確認ください。</dd></div>")
    # 県のまとめページの運営元の住所を、子のいる場所と思って訪ねないように（掲載元に無いことは断定しない）
    operator_note = ('<p class="fine">この連絡先は掲載元ページの運営窓口です。子がいる場所とは限りません。訪ねる前に、電話か自治体のページでご確認ください。</p>\n'
                     if operator and (phone or addr) else "")
    cta = (f'<a class="cta" href="{esc(src)}" rel="noopener" target="_blank">自治体のページで詳細を見る<small>{esc(muni)}</small></a>'
           if src else f'<p class="cta cta-none">元ページの URL が取れていません。{esc(muni)}にお問い合わせください。</p>')
    # 「迎える準備」枠（広告）は里親募集の子だけ。保護中・迷子・探してます の子は飼い主の元に帰るかもしれない（T506）
    aff = (cfg.get("affiliate") or []) if a.get("kind") == "adoption" else []
    aff_items = []
    for it in aff:
        if not isinstance(it, dict):
            continue
        u, t = safe_url(it.get("url")), str(it.get("title") or "").strip()
        if not u or not t:
            continue
        # 犬用品は犬のページ、猫用品は猫のページにだけ出す（species は dog か cat かその一覧。書かない広告はどの子にも出す）
        species = it.get("species")
        if species and a.get("species") not in (species if isinstance(species, list) else [species]):
            continue
        note = f'<small>{esc(it.get("note"))}</small>' if it.get("note") else ""
        # A8 の広告コードの計測用画像（1×1）。広告リンクと一緒にだけ出す
        beacon_url = safe_url(it.get("beacon"))
        beacon = f'<img border="0" width="1" height="1" src="{esc(beacon_url)}" alt="">' if beacon_url else ""
        aff_items.append(f'<li><a href="{esc(u)}" rel="sponsored nofollow noopener" target="_blank">{esc(t)}</a>{note}{beacon}</li>')
    aff_html = (f'<aside class="prep"><h2>迎える準備</h2><p>迎えたあとに使うものの広告です。収入はサイトの運営費に充てます。</p><ul>{"".join(aff_items)}</ul></aside>'
                if aff_items else "")
    # 広告を載せるページは、広告であることをファーストビュー（写真より上）に出す（T629・A8 の提携条件・ステマ規制）
    pr_html = ('<p class="pr-note"><span>PR</span>このページはアフィリエイト広告を利用しています（ページ下の「迎える準備」枠）。</p>'
               if aff_items else "")
    # 問い合わせのときに伝えるもの。サイト内の ID は自治体に通じないので出さない（Codex #15）。管理番号が無ければ実際に載っている日付・場所
    mgmt = str(a.get("management_no") or "").strip()
    if mgmt:
        ask = f"自治体にお問い合わせのときは、管理番号「{esc(mgmt)}」をお伝えください。"
    else:
        have = [w for k, w in (("shelter_date", labels.get("shelter_date", "保護日")), ("location", "場所")) if disp_value(k, a.get(k))]
        ask = (f"自治体にお問い合わせのときは、このページの{'と'.join(have)}をお伝えください。" if have
               else "自治体にお問い合わせのときは、このページに載っている特徴をお伝えください。" if rows else "")
    ask_html = f'<p class="fine">{ask}</p>' if ask else ""
    desc = (f"飼い主さんが{kind_phrase(a)}。{muni}が{fmt_date(data.get('date'))}時点で公開している情報です。" if a.get("kind") == "lost"
            else f"{muni}が{fmt_date(data.get('date'))}時点で公開している{kind_phrase(a)}。")
    if subline(a):
        desc += subline(a).rstrip("。") + "。"   # 下の行が「…思われます。」で終わると「。。」になる（agy ⑥）
    note = disp_value("note", a.get("note"))   # 本文で出さない備考（「無」「有」）は説明文にも出さない（Codex #17）
    if note:
        desc += shorten(note, 80)
    body = f"""<nav class="crumbs"><a href="/">都道府県</a> › <a href="{esc(pref_path(pref))}">{esc(pref)}</a> › <span>{esc(headline(a))}</span></nav>
{pr_html}<article class="detail" data-id="{esc(a['id'])}">
{media(a, big=True)}
<div class="detail-body">
<div class="badges">{badges(a)}</div>
<h1>{esc(headline(a))}</h1>
<p class="muni">{esc(muni) if pref in muni else f"{esc(muni)}（{esc(pref)}）"}</p>
<p class="kind-help">{esc(KIND_HELP.get(str(a.get('kind')), ''))}</p>
{cta}
<h2>基本情報</h2>
<dl class="facts">
{chr(10).join(rows) if rows else '<div><dd>詳しい情報は自治体のページでご確認ください。</dd></div>'}
</dl>
<h2>連絡先</h2>
<dl class="facts">
{chr(10).join(contact)}
</dl>
{operator_note}<p class="fine">この情報は{esc(fmt_date(data.get('date')))}に自治体のページから取得したものです。{FINE_BY_KIND.get(str(a.get('kind')), '')}</p>
{ask_html}
</div>
</article>
{aff_html}"""
    # 何も分からない子は見出し「種類の記載なし」だけでは何のページか分からないので、タイトルには区分を足す（#124 F-06）
    lead = "飼い主さんが探している動物" if a.get("kind") == "lost" else f"{kind_label(a)}の動物"   # 「探してますの動物」とはしない（#124 G-03）
    title_head = f"{lead}・{headline(a)}" if not disp_name(a) and _headline_parts(a)[1] == "none" else headline(a)
    return page(cfg, title=f"{title_head}｜{muni}", path=animal_path(a["id"]), body=body, og_type="article",
                og_image=safe_url(a.get("image_url")), data_date=str(data.get("date") or ""), desc=shorten(desc, 160))


def source_species(s: dict[str, Any]) -> str:
    """情報源の種別の表示。台帳の種別は dog・cat・mixed だけなので、名前に「その他」があればそれも出す
    （旭川「飼い主が探している その他の動物」を「犬・猫」と出さない。Codex #11）。"""
    sp = str(s.get("species") or "")
    name = str(s.get("name") or "")
    if "その他" not in name:
        return SPECIES.get(sp, "犬・猫") if sp in ("dog", "cat") else "犬・猫"
    have = [w for w in ("犬", "猫") if w in name or sp == {"犬": "dog", "猫": "cat"}[w]]
    return "・".join([*have, "その他の動物"])


def build_sources(cfg: dict[str, Any], data: dict[str, Any]) -> str:
    sources = [s for s in data.get("sources", []) if isinstance(s, dict)]
    by_pref: dict[str, list[dict[str, Any]]] = {}
    for s in sources:
        by_pref.setdefault(str(s.get("prefecture") or "不明"), []).append(s)
    st = Counter(str(s.get("status") or "") for s in sources)
    sections = []
    for p in sorted(by_pref, key=pref_key):
        items = []
        for s in by_pref[p]:
            status = str(s.get("status") or "")
            url = safe_url(s.get("url"))
            link = f'<a href="{esc(url)}" rel="noopener" target="_blank">自治体のページ</a>' if url else ""
            kind = KINDS.get(str(s.get("kind")), "")
            sp = source_species(s)
            if status == "ok":
                res = f'<b>{int(s.get("count") or 0)} 頭</b>'
                if str(s.get("photo") or "ok") == "pending":
                    res += "（写真は許諾の返事待ちのため出していません）"
                elif str(s.get("photo") or "ok") == "no":
                    res += "（写真は自治体の意向で出していません）"
            elif status == "link_only":
                res = "このページは一覧を読み取らず、リンクだけ載せています"
            else:
                res = esc(STATUS.get(status, status))
            # 名前に自治体名が入っていれば下の行で重ねない（「札幌市（迷子犬）」の下に「札幌市 ・ …」。Codex #30）
            muni = str(s.get("municipality") or "")
            meta = [kind, sp] if muni and muni in str(s.get("name") or "") else [muni, kind, sp]
            items.append(
                f'<li class="src st-{esc(status)}"><span class="src-name">{esc(s.get("name"))}</span>'
                f'<span class="src-meta">{esc(" ・ ".join(m for m in meta if m))}</span>'
                f'<span class="src-status">{res}</span><span class="src-link">{link}</span></li>')
        sections.append(f'<h2 id="{esc(p)}">{esc(p)}</h2><ul class="src-list">{"".join(items)}</ul>')
    summary = f"掲載あり {st['ok']} 件、本日 0 頭 {st['empty']} 件、読めなかった {st['failed'] + st['ambiguous_empty']} 件、リンクのみ {st['link_only']} 件"
    if st["disabled"]:
        summary += f"、停止中 {st['disabled']} 件"
    # 読めなかった理由は自治体側の変更だけではない（接続の失敗・503 もある。Codex #12）
    body = f"""<h1>情報源（自治体ページ）の一覧</h1>
<p>{esc(fmt_date(data.get('date')))}に確認した自治体ページ {len(sources)} 件の状況です（{summary}）。「本日は読めませんでした」のページは、接続できなかったり、ページの作りが変わったりして読み取れなかったものです。リンク先で直接ご確認ください。</p>
{chr(10).join(sections) if sections else '<p class="empty">情報源がありません。</p>'}"""
    return page(cfg, title="情報源の一覧", path="/sources/", body=body, data_date=str(data.get("date") or ""),
                desc="oneco が毎日確認している自治体の保護犬・保護猫ページの一覧と、本日の確認状況。")


# about ページの写真（site/static/images/about/）。alt は旧サイト（frontend/app/about/page.tsx）から引き継ぐ
ABOUT_PHOTOS_POM = [
    ("pom-1.jpg", "床にちょこんと座って舌を出して笑う、白い小さな犬のポム"),
    ("pom-2.jpg", "ベッドのそばでこちらを見上げるポム"),
    ("pom-3.jpg", "夜の散歩中、立ち止まって振り返るポム"),
]
ABOUT_PHOTOS_BILLY = [
    ("billy-1.jpg", "両手でほっぺを包まれて、されるがままのビリー"),
    ("billy-2.jpg", "布団の上でくつろぐ、白地に黒ぶちの大きな猫のビリー"),
    ("billy-3.jpg", "気持ちよさそうに眠るビリー"),
    ("billy-4.jpg", "ベランダから外を眺めるビリーの後ろ姿"),
]


def photo_grid(photos: list[tuple[str, str]], caption: str, cls: str) -> str:
    imgs = "".join(
        f'<img src="/images/about/{esc(f)}" alt="{esc(alt)}" width="1200" height="815" loading="lazy" decoding="async">'
        for f, alt in photos)
    return f'<figure class="photos {cls}">{imgs}<figcaption>{esc(caption)}</figcaption></figure>'


def build_about(cfg: dict[str, Any], data: dict[str, Any]) -> str:
    issues = safe_url(cfg.get("issues_url")) or safe_url(DEFAULT_CFG["issues_url"])
    repo = safe_url(cfg.get("repo_url")) or DEFAULT_CFG["repo_url"]
    site = esc(cfg["site_name"])
    srcs = [s for s in data.get("sources", []) if isinstance(s, dict) and s.get("enabled", True)]
    n_src = len(srcs)
    n_link = sum(1 for s in srcs if s.get("status") == "link_only" or s.get("mode") == "link_only")
    n_read = n_src - n_link
    n_pref = len({str(s.get("prefecture")) for s in srcs if s.get("prefecture")})
    reach = f"{n_pref} 都道府県の {n_src} ページのうち {n_read} ページを毎日読み取り、{n_link} ページはリンクだけを載せています" \
        if n_link else f"{n_pref} 都道府県の {n_src} ページを毎日読み取っています"
    kinds = "・".join(f"{esc(KINDS[k])}（{esc(KIND_HELP[k])}）" for k in KINDS)
    email = str(cfg.get("contact_email") or "").strip()
    if not re.fullmatch(r"[^@\s<>\"']+@[^@\s<>\"']+\.[^@\s<>\"']+", email):
        email = ""
    contact = (f'GitHub アカウントをお持ちでない方は、メール（<a href="mailto:{esc(email)}">{esc(email)}</a>）でもお受けします。'
               if email else "窓口の利用には GitHub アカウント（無料）が必要です。")
    if cfg.get("affiliate"):
        money = ("<p>サーバー代などの運営費をまかなうため、里親募集の子のページの「迎える準備」枠に広告（アフィリエイト）リンクを載せています。"
                 "広告の効果を測るため、そのページを開くと広告配信の A8.net（株式会社ファンコミュニケーションズ）に閲覧の情報が送られます。</p>")
    else:
        money = ("<p>いまは広告を載せていません。載せるときは「迎える準備」枠に広告（アフィリエイト）リンクと明示し、"
                 "収入はサーバー代などの運営費に充てます。</p>")
    analytics = ""
    if ga4_id(cfg):
        analytics = """<section>
<h2>アクセス解析</h2>
<p>どのページがよく見られているかを知ってサイトを良くするため、Google アナリティクスを使っています。ページを開くと、Google LLC に閲覧の情報（見たページ、おおよその地域、使っている端末など）が送られます。Google アナリティクスは、端末を見分けるために Cookie を使います。名前や連絡先など、サイト側であなたを直接特定できる情報は集めておらず、Google にも送っていません。送られた情報は Google のポリシーに沿って扱われます（<a href="https://policies.google.com/technologies/partner-sites?hl=ja" rel="noopener" target="_blank">Google のサービスを使うサイトやアプリから収集した情報の Google による使用</a>）。</p>
<p>パソコンのブラウザでは、<a href="https://tools.google.com/dlpage/gaoptout?hl=ja" rel="noopener" target="_blank">Google アナリティクス オプトアウト アドオン</a>で送信を止められます。ブラウザで Cookie を無効にすると、集められる情報を減らせます。</p>
</section>
"""
    body = f"""<article class="about">
<h1>このサイトについて</h1>
<section>
<h2>{site} とは</h2>
<p>{site} は、全国の自治体（動物愛護センター・保健所・市区町村）が公開している保護犬・保護猫の情報を、出典を明示して 1 か所に集めた、個人運営のサイトです。自治体のページに載っていない情報（保護団体や個人の里親募集など）は扱いません。</p>
<p>載せている子は 4 つに分けています：{kinds}。「探してます」は、飼い主さんが自分の迷子を探している告知のうち、自治体のページに載っているものです。犬猫以外の動物も、自治体のページにあれば載せています。自治体のページで犬か猫か分からない子は、「{NO_SPECIES}」として載せています（絞り込みでは「その他」に出ます）。</p>
<p>いま、{reach}。載っているのは、その日に自治体のページに出ている子です。内容は自治体のページの記載どおりなので、最新とは限りません。気になる子がいたら、掲載元の自治体に直接ご連絡ください。</p>
</section>
<section>
<h2>{site} という名前と、ふたつの円</h2>
<p>{site}（ワンコ）は、「わんこ」の綴りの中に「ねこ（NECO）」がいる名前です。頭の ONE には、ばらばらの情報をひとつに、という意味も重なっています。ロゴのふたつの円は、このサイトのモデルになった犬のポムと猫のビリーを表しています。</p>
<div class="story story-pom">
{photo_grid(ABOUT_PHOTOS_POM, "ポム", "photos-pom")}
<p><strong>コーラルの円は、犬のポムをイメージしています。</strong>私が通っていた専門学校で生まれ、トリミング実習のモデル犬として、学生たちのカット練習に付き合ってくれていた子です。犬舎にいた頃から、私を見つけると寝転んでお腹を見せてくれる子で、学校の里親制度を通じて 4 歳のときにうちに来ました。</p>
<p>最初は 1 階で暮らしてもらうつもりで、専門学校の友人と木のケージまで手作りしました。けれど夜にさびしそうに鳴く声を聞き、その日のうちにあきらめて、それからはずっと私たちと同じ 2 階暮らしです。体重は 3 キロほど。いつも私の横にいて、公園では子どもたちと遊び、家でのシャンプーやカットもおとなしくさせてくれる子でした。</p>
<p>散歩は大好きだったはずが、私が散歩をさぼるうちにビリーと過ごす時間が長くなり、自分のことを猫だと思い始めたのか、気づけばキャットタワーに登ろうとしていたことも。うちで過ごしたのは 5 年間。9 歳のときにお別れをしました。</p>
</div>
<div class="story story-billy">
{photo_grid(ABOUT_PHOTOS_BILLY, "ビリー", "photos-billy")}
<p><strong>ブルーグリーンの円は、猫のビリーをイメージしています。</strong>私が働いていた動物病院の近くで兄弟猫と一緒に拾われ、兄弟が先にもらわれていくなか、ビリーだけが病院に残った子です。その後は病院猫として過ごし、体が大きかったこともあって、血液が必要な子のための輸血ドナーを務めてくれていました。</p>
<p>ふだんの住まいは、大型犬用の犬舎。私は昼休みや仕事終わりにそこから出して、よく一緒に遊んでいました。輸血のたびに軽い麻酔でふらつく姿を見ているうちに、うちに連れて帰ることにしました。</p>
<p>家ではおとなしく、ほっぺを揉まれてもお風呂に入れられても嫌がらない、ポムのちょっかいにも静かに付き合ってくれる子でした。うちで過ごしたのは、同じく 5 年間。9 歳のとき、リンパ腫でお別れをしました。</p>
</div>
<div class="two-circles">{TWO_CIRCLES_SVG}</div>
<p><strong>ふたつの円が重なる場所に、{site} の出発点があります。</strong>ポムは実習のモデル犬として学生の学びに関わり、ビリーは輸血ドナーとして病院で過ごしました。2 匹を見送るときに、行き場を探している子たちがポムやビリーのように誰かの家族になれるようにしようと約束しました。{site} という名前は、その約束に由来しています。</p>
</section>
<section>
<h2>目指していること</h2>
<p>保護された子が里親につながること。そして殺処分をゼロに近づけること。技術はそのための手段でしかありません。</p>
<ul>
<li>里親を考えている方が、住んでいる地域や近くの自治体にいる保護犬・保護猫をすぐ見つけられるようにする</li>
<li>迷子のペットを探している方が、自治体に保護されているかもしれない子を素早く確かめられるようにする</li>
</ul>
</section>
<section>
<h2>運営者</h2>
<p>{site} を作って運営しているのは個人（GitHub: <a href="https://github.com/9mak" rel="noopener" target="_blank">9mak</a>）です。トリミングの専門学校を出て動物病院で働いたあと、IT の仕事に移りました。ポムとは専門学校で、ビリーとは動物病院で出会いました。</p>
<p>サイトの中身と作業の記録は <a href="{esc(repo)}" rel="noopener" target="_blank">GitHub リポジトリ</a> で公開しています。</p>
</section>
<section>
<h2>運営方針</h2>
<ul>
<li>掲載するのは自治体の公開ページに載っている情報だけです。写真・項目は元ページのまま、電話番号と所在地は自治体の公式情報から転記しています。</li>
<li>毎日、各自治体のページを確認して、その日に載っている子を載せます。個体を追跡したり、過去の情報を残したりはしません。</li>
<li>すべての子に「自治体のページで詳細を見る」リンクを付けています。譲渡の申し込みや迷子の問い合わせは、必ず自治体に直接行ってください。{site} は仲介をしません。</li>
<li>読み取りに失敗した自治体は<a href="/sources/">情報源の一覧</a>に「本日は読めませんでした」と表示し、元ページへのリンクを残します。</li>
</ul>
</section>
<section>
<h2 id="takedown">掲載の取り下げ・訂正の依頼</h2>
<p>自治体のご担当者様、写真や情報の権利をお持ちの方、飼い主さんなど、掲載の取り下げ・訂正・リンク方法の変更をご希望の方は、下記の窓口にページの URL とご要望をお書きください。確認のうえ速やかに対応します。{contact}</p>
<p>自治体のページから消えた子は、{site} からも翌日の更新で消えます。</p>
<p><a class="cta" href="{esc(issues)}" rel="noopener" target="_blank">取り下げ・訂正の依頼窓口（GitHub Issues）</a></p>
</section>
<section>
<h2>運営費について</h2>
{money}
<p>{site} は、自治体からも、譲渡を申し込む方からも、お金を受け取りません。譲渡の条件や費用は各自治体の定めによります。</p>
</section>
{analytics}<section>
<h2>免責</h2>
<p>{site} は自治体の公式サイトではなく、自治体との提携や委託もない個人のサイトです。</p>
<p>掲載内容は取得時点の自治体ページに基づきます。すでに譲渡・返還されている場合や、元ページの更新が反映されていない場合があります。ページはプログラムが自動で読み取っているため、写真や項目が別の子のものになるなどの誤りが起きることがあります。最終的な情報は必ず各自治体にご確認ください。誤りに気づいたら、上の窓口からお知らせください。</p>
<p>写真と文章の権利は、各自治体と撮影者にあります。写真は自治体のページから直接表示しています。</p>
<p>掲載内容によって生じた損害について、運営者は責任を負いかねます。</p>
</section>
</article>"""
    return page(cfg, title="このサイトについて", path="/about/", body=body, data_date=str(data.get("date") or ""),
                desc=f"{cfg['site_name']} の名前の由来（犬のポムと猫のビリー）、運営者、運営方針、掲載の取り下げ・訂正の窓口について。")


def build_404(cfg: dict[str, Any]) -> str:
    body = """<h1>ページが見つかりません</h1>
<p>お探しのページは見つかりませんでした。自治体のページから掲載が無くなった子のページは、翌日の更新で消えます。URL が正しいかもご確認ください。</p>
<p><a class="cta" href="/">都道府県の一覧へ戻る</a></p>"""
    return page(cfg, title="ページが見つかりません", path="/404.html", body=body, desc="ページが見つかりません。")


def build_sitemap(cfg: dict[str, Any], data: dict[str, Any], prefs: list[str], animals: list[dict[str, Any]]) -> str:
    base = cfg["base_url"].rstrip("/")
    lastmod = iso_date(data.get("date"))
    paths = ["/", "/sources/", "/about/"] + [pref_path(p) for p in prefs] + [animal_path(a["id"]) for a in animals]
    urls = "\n".join(f"<url><loc>{esc(base + p)}</loc><lastmod>{lastmod}</lastmod></url>" for p in paths)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{urls}\n</urlset>\n'


def build_robots(cfg: dict[str, Any]) -> str:
    return f"User-agent: *\nAllow: /\nSitemap: {cfg['base_url'].rstrip('/')}/sitemap.xml\n"


# ---------------------------------------------------------------- CSS

CSS = """
/* 配色は旧サイト frontend/app/globals.css の WCAG AA パレットを引き継ぐ:
   primary #0369a1（白地 7.21:1）/ #075985（hover）、文字 #1f2937 / #5b6775、focus #3b82f6。
   ブランドの 2 色（コーラル #E8826E = 犬のポム、ブルーグリーン #6FAEBB = 猫のビリー）は
   犬・猫のバッジと about ページの飾りに使う。区分（里親募集・保護中・迷子）は旧サイトの緑・青・琥珀の淡色、探してます は淡い紫 */
:root{--bg:#fcfbf9;--card:#fff;--ink:#1f2937;--mute:#5b6775;--line:#e5e7eb;--accent:#0369a1;--accent-dark:#075985;--accent-ink:#fff;--accent-50:#f0f9ff;--accent-100:#e0f2fe;--coral:#E8826E;--teal:#6FAEBB;--focus:#3b82f6;--dog:#fdeae4;--dog-ink:#9a3a26;--cat:#e4f1f4;--cat-ink:#21606c;--adopt:#d1fae5;--adopt-ink:#065f46;--shelter:#e0f2fe;--shelter-ink:#075985;--stray:#fef3c7;--stray-ink:#92400e;--lost:#ede9fe;--lost-ink:#5b21b6;--ph:#b3c0cc}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Helvetica Neue","Hiragino Sans","Hiragino Kaku Gothic ProN","Noto Sans JP","Yu Gothic",Meiryo,sans-serif;line-height:1.6;font-size:16px}
a{color:var(--accent)}
:focus-visible{outline:2px solid var(--focus);outline-offset:2px}
img{max-width:100%;display:block}
h1{font-size:1.4rem;margin:.2em 0 .5em;line-height:1.35}
h2{font-size:1.1rem;margin:1.6em 0 .5em}
h3{font-size:1rem;margin:0}
p{margin:.4em 0}
code{font-size:.85em;background:#eef1f4;padding:.1em .3em;border-radius:4px}
.wrap{max-width:1040px;margin:0 auto;padding:16px}
.site-head{position:sticky;top:0;z-index:50;background:rgba(255,255,255,.94);-webkit-backdrop-filter:blur(6px);backdrop-filter:blur(6px);border-bottom:1px solid var(--line)}
.site-head-in{max-width:1040px;margin:0 auto;padding:10px 16px;display:flex;align-items:center;justify-content:space-between;gap:12px}
.brand{display:flex;align-items:center;gap:10px;min-width:0;color:var(--ink);text-decoration:none;border-radius:6px}
.brand .mark{flex:none;width:34px;height:34px}
.brand .wordmark{flex:none;width:99px;height:22px;display:block}
.brand .tagline{font-size:.8rem;color:var(--mute);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-left:2px}
@media (max-width:640px){.brand .tagline{display:none}}
.nav{display:flex;gap:14px;flex-wrap:wrap;font-size:.9rem}
.nav a{color:var(--mute);text-decoration:none;padding:4px 2px;border-radius:4px}
.nav a:hover{color:var(--accent);text-decoration:underline}
@media (max-width:520px){.site-head-in{flex-wrap:wrap;padding:8px 16px}.nav{flex:1 1 100%;gap:16px}}
.site-foot{max-width:1040px;margin:32px auto 0;padding:16px;color:var(--mute);font-size:.85rem;border-top:1px solid var(--line)}
.foot-brand{display:flex;align-items:center;gap:8px;margin-bottom:6px}
.foot-brand img{flex:none}
.crumbs{font-size:.85rem;color:var(--mute);margin-bottom:8px;overflow-wrap:anywhere}
.intro p{max-width:70ch}
.stats{color:var(--mute);font-size:.95rem}
.hint,.fine{color:var(--mute);font-size:.85rem}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0}
.chips button{appearance:none;border:1px solid var(--line);background:#fff;color:var(--ink);border-radius:999px;padding:6px 14px;font-size:.9rem;cursor:pointer;min-height:36px}
.chips button[aria-pressed="true"]{background:var(--accent);color:#fff;border-color:var(--accent)}
.filters{display:flex;flex-direction:column;gap:2px}
.count{margin:8px 0;color:var(--mute)}
.pref-list{list-style:none;padding:0;margin:8px 0;display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px}
.pref-list li a{display:flex;justify-content:space-between;align-items:baseline;gap:8px;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px;text-decoration:none;color:var(--ink);min-height:48px}
.pref-list li a:hover{border-color:var(--accent)}
.pref-list .pref{font-weight:600}
.pref-list .cnt{color:var(--mute);font-size:.9rem;white-space:nowrap}
.pref-list .cnt b{color:var(--accent);font-size:1.1rem}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px}
@media (min-width:480px){.grid{grid-template-columns:repeat(auto-fill,minmax(200px,1fr))}}
.card{display:flex;flex-direction:column;background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden;text-decoration:none;color:var(--ink)}
.card:hover{border-color:var(--accent);box-shadow:0 2px 8px rgba(0,0,0,.06)}
.card-body{padding:10px 12px 12px;display:flex;flex-direction:column;gap:4px}
.card h3{font-size:.98rem;line-height:1.35}
.card .sub{font-size:.85rem;color:var(--mute);margin:0;overflow-wrap:anywhere;display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;overflow:hidden}
.card .muni{font-size:.8rem;color:var(--mute);margin:0}
.badges{display:flex;gap:6px;flex-wrap:wrap}
.badge{display:inline-block;font-size:.75rem;padding:2px 8px;border-radius:999px;background:#eef1f4;color:var(--ink);line-height:1.5}
.badge.sp-dog{background:var(--dog);color:var(--dog-ink)}.badge.sp-cat{background:var(--cat);color:var(--cat-ink)}
.badge.kd-adoption{background:var(--adopt);color:var(--adopt-ink)}.badge.kd-sheltered{background:var(--shelter);color:var(--shelter-ink)}.badge.kd-stray{background:var(--stray);color:var(--stray-ink)}.badge.kd-lost{background:var(--lost);color:var(--lost-ink)}
.media{position:relative;aspect-ratio:4/3;background:#e9edf1;overflow:hidden;container-type:inline-size}
.media img{width:100%;height:100%;object-fit:contain}
.media img+.ph{display:none}
.media.noimg .ph{display:flex}
.ph{position:absolute;inset:0;display:flex;align-items:flex-end;justify-content:center;padding-bottom:6%;background:linear-gradient(160deg,#e8edf2,#d3dbe3);color:#6b7a88;font-size:clamp(9px,7cqw,30px)}
.ph span{font-size:max(13px,.5em);letter-spacing:.05em;text-align:center;padding:0 8px;line-height:1.4}
.ph::before{content:"";position:absolute;left:50%;top:50%;width:2.8em;height:2.4em;margin:-.7em 0 0 -1.4em;background:var(--ph);border-radius:50%/55% 55% 45% 45%}
.ph::after{content:"";position:absolute;left:50%;top:50%;width:5em;height:2.2em;margin:-2.5em 0 0 -2.5em;background:radial-gradient(circle at .6em 1.6em,var(--ph) .55em,transparent .6em),radial-gradient(circle at 1.9em .6em,var(--ph) .6em,transparent .65em),radial-gradient(circle at 3.1em .6em,var(--ph) .6em,transparent .65em),radial-gradient(circle at 4.4em 1.6em,var(--ph) .55em,transparent .6em)}
.detail{display:grid;gap:16px;background:var(--card);border:1px solid var(--line);border-radius:14px;overflow:hidden}
@media (min-width:720px){.detail{grid-template-columns:minmax(0,5fr) minmax(0,6fr)}.detail .media{aspect-ratio:auto;min-height:320px;height:100%}}
.detail .media{border-radius:0}
.detail-body{padding:4px 16px 16px}
@media (min-width:720px){.detail-body{padding:20px 20px 20px 4px}}
.detail h1{font-size:1.45rem}
.detail .muni{color:var(--mute);margin:0}
.kind-help{color:var(--mute);font-size:.9rem}
.facts{margin:0;display:grid;gap:6px}
.facts>div{display:grid;grid-template-columns:7.5em 1fr;gap:8px;padding:6px 0;border-bottom:1px solid var(--line);align-items:baseline}
@media (max-width:480px){.facts>div{grid-template-columns:1fr;gap:2px}}
.facts dt{color:var(--mute);font-size:.9rem}
.facts dd{margin:0;overflow-wrap:anywhere;white-space:pre-line}
.cta{display:block;background:var(--accent);color:#fff;text-decoration:none;text-align:center;font-weight:700;font-size:1.05rem;padding:14px 16px;border-radius:12px;margin:14px 0}
.cta small{display:block;font-weight:400;font-size:.8rem;opacity:.85;margin-top:2px}
.cta:hover{background:var(--accent-dark)}
.cta-none{background:#eef1f4;color:var(--ink);font-weight:400;font-size:.95rem}
.pr-note{margin:0 0 10px;font-size:.85rem;color:var(--mute)}
.pr-note span{display:inline-block;font-weight:700;font-size:.75rem;color:var(--ink);border:1px solid var(--mute);border-radius:4px;padding:0 6px;margin-right:6px}
.prep{margin-top:20px;background:#fffaf0;border:1px solid #f0e2c2;border-radius:14px;padding:12px 16px}
.prep h2{margin-top:.2em}
.prep ul{padding-left:1.2em;margin:.4em 0}
.prep li{margin:.3em 0}
.prep small{display:block;color:var(--mute)}
.prep img{position:absolute}
.src-list{list-style:none;padding:0;margin:0 0 8px;display:grid;gap:8px}
.src{display:grid;gap:2px;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px}
@media (min-width:720px){.src{grid-template-columns:2fr 1.5fr 1.2fr auto;align-items:center;gap:12px}}
.src-name{font-weight:600}
.src-meta{color:var(--mute);font-size:.85rem}
.src-status{font-size:.9rem}
.src.st-failed .src-status,.src.st-ambiguous_empty .src-status{color:#b91c1c}
.src.st-ok .src-status b{color:var(--accent)}
.src-link{font-size:.9rem}
.empty{color:var(--mute)}
.about{max-width:72ch;overflow:clip;padding:0 2px}
.about p{line-height:1.8}
.about h2{margin-top:2em}
.story{position:relative;isolation:isolate;margin:1.2em 0 2em}
.story::before{content:"";position:absolute;z-index:-1;border-radius:50%;opacity:.13;pointer-events:none;width:260px;height:260px}
.story-pom::before{background:var(--coral);left:-130px;bottom:-40px}
.story-billy::before{background:var(--teal);right:-150px;bottom:-70px;width:340px;height:340px}
.photos{margin:0 0 12px;display:grid;gap:8px;grid-template-columns:repeat(2,1fr)}
.photos img{width:100%;height:auto;aspect-ratio:3/2;object-fit:contain;border-radius:10px;background:#e9edf1}
.photos figcaption{grid-column:1/-1;text-align:center;color:var(--mute);font-size:.8rem}
.photos-pom img:first-child{grid-column:1/-1}
@media (min-width:600px){.photos-pom{grid-template-columns:repeat(3,1fr)}.photos-pom img:first-child{grid-column:1/3;grid-row:1/3;height:100%;aspect-ratio:auto}}
.two-circles{display:flex;justify-content:center;margin:28px 0 14px}
[hidden]{display:none!important}
"""

# 写真なしの枠の絵（2026-11-13）: 犬は垂れ耳とまるい鼻先、猫はとがった耳としっぽの、座った姿のシルエット。色は肉球と同じ #b3c0cc
_PH_SVG = {
    "dog": ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><g fill="#b3c0cc">'
            '<ellipse cx="50" cy="71" rx="19" ry="21"/><circle cx="50" cy="35" r="15"/><ellipse cx="50" cy="44" rx="8" ry="6.5"/>'
            '<ellipse cx="35.5" cy="36" rx="5.5" ry="11" transform="rotate(18 35.5 36)"/>'
            '<ellipse cx="64.5" cy="36" rx="5.5" ry="11" transform="rotate(-18 64.5 36)"/></g>'
            '<path d="M66 84 Q84 80 80 64" fill="none" stroke="#b3c0cc" stroke-width="6" stroke-linecap="round"/></svg>'),
    "cat": ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><g fill="#b3c0cc">'
            '<ellipse cx="50" cy="71" rx="18" ry="21"/><circle cx="50" cy="36" r="14"/>'
            '<path d="M37 31 L39 15 L49 25 Z"/><path d="M63 31 L61 15 L51 25 Z"/></g>'
            '<path d="M66 86 Q88 84 82 62" fill="none" stroke="#b3c0cc" stroke-width="5.5" stroke-linecap="round"/></svg>'),
}
CSS += "".join(
    f'.ph-{sp}::before{{width:4.2em;height:4.2em;margin:-2.7em 0 0 -2.1em;border-radius:0;'
    f'background:url("data:image/svg+xml,{quote(svg)}") center/contain no-repeat}}\n.ph-{sp}::after{{display:none}}\n'
    for sp, svg in _PH_SVG.items())


# ---------------------------------------------------------------- driver

def load_config(path: Path | None) -> dict[str, Any]:
    cfg = dict(DEFAULT_CFG)
    if path and path.exists():
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            cfg.update(raw)
    if not safe_url(cfg.get("base_url")):
        sys.exit(f"config の base_url が http(s) で始まっていない: {cfg.get('base_url')!r}")
    return cfg


def prepare_out(out: Path) -> None:
    """出力先を空にする。前回の build 先か空ディレクトリのときだけ消す。"""
    if out.exists():
        if not out.is_dir():
            sys.exit(f"出力先がディレクトリではない: {out}")
        if any(out.iterdir()) and not (out / MARKER).exists():
            sys.exit(f"出力先 {out} は build が作ったものではないので消さない。空にするか別の --out を指定してください。")
        shutil.rmtree(out)
    out.mkdir(parents=True)


def write(out: Path, rel: str, text: str) -> None:
    p = out / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def no_photo_sources(data: dict[str, Any]) -> set[str]:
    """写真を出さない掲載元の slug（台帳 photo が ok 以外。T630: 許諾の返事待ち・不可）。"""
    return {str(s.get("slug")) for s in data.get("sources", [])
            if isinstance(s, dict) and str(s.get("photo") or "ok") != "ok"}


def strip_photos(data: dict[str, Any]) -> dict[str, Any]:
    """photo が ok 以外の掲載元の子から image_url を落とした data を返す（該当が無ければ同じ dict をそのまま返す）。"""
    hidden = no_photo_sources(data)
    if not hidden:
        return data
    animals = [({**a, "image_url": None} if a.get("source") in hidden else a) if isinstance(a, dict) else a
               for a in data.get("animals", [])]
    return {**data, "animals": animals}


def build_site(data: dict[str, Any], cfg: dict[str, Any], out: Path, data_path: Path | None = None) -> dict[str, int]:
    """data（animals JSON の中身）から out/ を生成。data_path があれば data.json はそのファイルのコピー。
    写真を出さない掲載元（台帳 photo が ok 以外）があるときは image_url を落とした data を書く。"""
    cfg = {**DEFAULT_CFG, **cfg}
    prepare_out(out)
    # 掲載元には写真があるが、許諾待ち・不可で止めている子（枠に「写真は自治体のページで見られます」と出す）
    hidden = no_photo_sources(data)
    withheld = {str(a.get("id")) for a in data.get("animals", [])
                if isinstance(a, dict) and a.get("source") in hidden and a.get("image_url")}
    stripped = strip_photos(data)
    if stripped is not data:
        data, data_path = stripped, None
    raw_animals = [a for a in data.get("animals", []) if isinstance(a, dict)]
    seen: set[str] = set()
    animals: list[dict[str, Any]] = []
    skipped = 0
    for a in raw_animals:
        aid = str(a.get("id") or "")
        if not ID_RE.fullmatch(aid) or aid in seen or not a.get("prefecture"):
            skipped += 1
            continue
        seen.add(aid)
        # ページを組むときだけ使う印。data.json（data の dict）には入れない
        animals.append({**a, "_photo_withheld": True} if aid in withheld else a)
    d0 = parse_date(str(data.get("date") or "")[:10])
    _REF_DATE[:] = [d0] if d0 else []
    # stable: 里親募集→保護中→迷子→探してます。同じ区分の中では写真のある子を先に（写真を止めている子は写真なし扱い。2026-11-13）。元の順は保つ
    animals.sort(key=lambda a: (KIND_ORDER.get(str(a.get("kind")), 9), 0 if safe_url(a.get("image_url")) else 1))

    by_pref: dict[str, list[dict[str, Any]]] = {}
    for a in animals:
        by_pref.setdefault(str(a["prefecture"]), []).append(a)
    prefs = sorted(by_pref, key=pref_key)

    write(out, "index.html", build_index(cfg, data, animals))
    for p in prefs:
        write(out, f"pref/{p}/index.html", build_pref(cfg, data, p, by_pref[p]))
    for a in animals:
        write(out, f"animals/{a['id']}/index.html", build_animal(cfg, data, a))
    write(out, "sources/index.html", build_sources(cfg, data))
    write(out, "about/index.html", build_about(cfg, data))
    write(out, "404.html", build_404(cfg))
    write(out, "sitemap.xml", build_sitemap(cfg, data, prefs, animals))
    write(out, "robots.txt", build_robots(cfg))
    write(out, "style.css", CSS.strip() + "\n")
    if STATIC_DIR.is_dir():
        shutil.copytree(STATIC_DIR, out, dirs_exist_ok=True)
    if data_path is not None:
        shutil.copyfile(data_path, out / "data.json")
    else:
        write(out, "data.json", json.dumps(data, ensure_ascii=False, indent=1))
    write(out, MARKER, f"{datetime.now().isoformat(timespec='seconds')} {data.get('date', '')}\n")
    return {"animals": len(animals), "prefectures": len(prefs), "sources": len(data.get("sources", [])), "skipped": skipped}


def merge_registry_photo(data: dict[str, Any], registry: Path) -> dict[str, Any]:
    """台帳（sources.yaml）の photo を slug ごとに data["sources"] へ合流させる。
    収集時の台帳に photo が無かった日のデータでも、今の台帳の判断で写真を止められるようにする（T630）。"""
    import yaml  # 収集側の依存。build 単体では使わないのでここで読む

    reg = yaml.safe_load(registry.read_text(encoding="utf-8")) or {}
    photo = {str(s.get("slug")): str(s.get("photo") or "ok") for s in reg.get("sources", []) if isinstance(s, dict)}
    if not photo:
        return data
    sources = [({**s, "photo": photo[str(s.get("slug"))]} if isinstance(s, dict) and str(s.get("slug")) in photo else s)
               for s in data.get("sources", [])]
    return {**data, "sources": sources}


def build(data_path: Path, out: Path, cfg: dict[str, Any] | Path | None = None,
          registry: Path | None = None) -> dict[str, int]:
    """ファイルから読んで build_site。cfg は dict か config.json のパス（None なら既定）。
    registry を渡すと台帳の photo を合流させてから生成する（写真を止めた掲載元は data.json も書き直す）。"""
    if not isinstance(cfg, dict):
        cfg = load_config(cfg if isinstance(cfg, Path) else DEFAULT_CONFIG)
    try:
        data = json.loads(data_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        sys.exit(f"データが無い: {data_path}（先に `python -m collector run` を実行）")
    if not isinstance(data, dict) or not isinstance(data.get("animals"), list):
        sys.exit(f"データ形式が違う（animals 配列が無い）: {data_path}")
    if registry is not None:
        merged = merge_registry_photo(data, registry)
        if merged is not data and no_photo_sources(merged):
            return build_site(merged, cfg, out, data_path=None)
    return build_site(data, cfg, out, data_path=data_path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="oneco v2 静的サイト生成: data/latest.json → site/dist/")
    ap.add_argument("--data", type=Path, default=DEFAULT_DATA, help="animals JSON（既定: data/latest.json）")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="出力先（既定: site/dist）")
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="設定（既定: site/config.json）")
    ap.add_argument("--registry", type=Path, default=None,
                    help="台帳 sources.yaml。渡すと photo（ok | pending | no）を合流させ、ok 以外の掲載元の写真を出さない")
    args = ap.parse_args(argv)
    n = build(args.data, args.out, args.config, registry=args.registry)
    print(f"{args.out}: {n['animals']} 頭・{n['prefectures']} 都道府県・情報源 {n['sources']} 件"
          + (f"（id 不正・重複で {n['skipped']} 件を除外）" if n["skipped"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
