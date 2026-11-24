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
    "tagline": "全国の動物の里親募集・迷子情報をひとつに",
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
# 区分の呼び方（2026-11-15 UI 刷新）: 収集の kind 4 つを、利用者の目的で「里親募集」と「迷子情報」の 2 つに分ける。
# 迷子情報の中は「保護中」（sheltered・stray）と「飼い主が探してます」（lost）。指示書は「施設で保護中」だったが、
# 千葉市・旭川市・越谷市・埼玉県の個人保護など市民が自宅で保護している子もいる（T518）ので、場所を断定しない「保護中」にした
# （PR #126 の reviewer と Codex の指摘、2026-11-15 おまえさん決定）
KINDS = {"adoption": "里親募集", "sheltered": "保護中", "stray": "保護中", "lost": "飼い主が探してます"}
GROUPS = {"adopt": "里親募集", "missing": "迷子情報"}
MISSING_SUB = {"sheltered": "shelter", "stray": "shelter", "lost": "lost"}   # 迷子情報の内訳の絞り込み
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
# 詳細ページの「この子の情報」に出す項目（この順で、取れているものだけ）。名前は見出し、大きさは出さない（2026-11-15 UI 刷新）
FIELDS = [
    ("breed", "種類"),
    ("color", "毛色"),
    ("sex", "性別"),
    ("age", "年齢"),
    ("shelter_date", "保護日"),
    ("location", "保護・発見場所"),
    ("management_no", "管理番号"),
    ("note", "メモ"),
]
# 表に出しても意味の無い値（「性別: 不明」「毛色: -」）
EMPTY_VALS = {"", "-", "ー", "不明", "不詳", "その他", "なし", "無", "無し"}
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
# トップのタイルと都道府県ページの近隣県バーの地方ブロック（この順で並べる。関東は東京から）
REGIONS: list[tuple[str, list[str]]] = [
    ("北海道・東北", ["北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県"]),
    ("関東", ["東京都", "神奈川県", "埼玉県", "千葉県", "茨城県", "栃木県", "群馬県"]),
    ("中部", ["新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県", "岐阜県", "静岡県", "愛知県"]),
    ("近畿", ["三重県", "滋賀県", "京都府", "大阪府", "兵庫県", "奈良県", "和歌山県"]),
    ("中国・四国", ["鳥取県", "島根県", "岡山県", "広島県", "山口県", "徳島県", "香川県", "愛媛県", "高知県"]),
    ("九州・沖縄", ["福岡県", "佐賀県", "長崎県", "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県"]),
]
REGION_OF = {p: name for name, prefs in REGIONS for p in prefs}
# 掲載元の建物のアイコン（カードの掲載元の頭）
ICO_ORG = ('<svg class="ico" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" '
           'stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M2.5 14h11M3.5 14V6.5l4.5-3 4.5 3V14M6.5 14v-3.5h3V14M6.5 7.5h3"/></svg>')
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


_SORT_DATES = [   # 並べ替え用。parse_date と違い、日付の後ろに時刻・時間帯・曜日の注記が付いていてもよい（先頭が日付であること）
    re.compile(r"(?P<y>\d{4})\s*[/\-.年]\s*(?P<m>\d{1,2})\s*[/\-.月]\s*(?P<d>\d{1,2})(?!\d)"),
    # 「令和8(2026)年 11月11日」（西暦の併記）、「R7 8/27」（年と月日の区切りが空白）も読む
    re.compile(r"(?P<era>令和|平成|[RrHh])\s*(?P<y>\d{1,2}|元)(?:\s*\(\d{4}\))?(?:\s*[年.\-/、]\s*|\s+)(?P<m>\d{1,2})\s*[月.\-/]\s*(?P<d>\d{1,2})(?!\d)"),
    re.compile(r"(?P<m>\d{1,2})\s*(?:月\s*|/)(?P<d>\d{1,2})(?!\d)"),   # 年の無い日付
]


def parse_shelter_date(s: Any, ref: date | None) -> date | None:
    """一覧を新しい順に並べるための収容日・保護日（POLICY.md 方針 40）。読めなければ None（推測しない）。
    年の無い日付（「9月12日」）は、データの日付 ref より後の月日なら前の年、そうでなければ同じ年とみなす。ref が無ければ今日。"""
    t = str(s or "").strip()
    for p in _SORT_DATES:
        m = p.match(t)
        if not m:
            continue
        g = m.groupdict()
        try:
            if g.get("y") is None:
                today = ref or date.today()
                d = date(today.year, int(g["m"]), int(g["d"]))
                return d if d <= today else date(today.year - 1, int(g["m"]), int(g["d"]))
            y = int(g["y"]) if g["y"] != "元" else 1
            if g.get("era"):
                y += _ERA[g["era"]]
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
        note = _breed_parts(a)[1] if used == "breed" else ""   # 見出しから外した品種のかっこ書き（「キジ白」）
        parts = [note] if note and note not in (color, sex) else []   # 毛色・見出しの性別と同じなら重ねない（#125 H-02）
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


# ---------------------------------------------------------------- 2026-11-15 UI 刷新: カードと区分

def kind_group(a: dict[str, Any]) -> str:
    """adopt（里親募集）| missing（迷子情報）。"""
    return "adopt" if a.get("kind") == "adoption" else "missing"


def pref_short(p: str) -> str:
    """タイル・近隣県の表示名。北海道はそのまま、それ以外は末尾の都・府・県を落とす（「東京」「青森」）。"""
    return p if p == "北海道" else re.sub(r"[都府県]$", "", p)


def card_title(a: dict[str, Any]) -> str:
    """カードと個体ページの見出し。名前があれば名前、無ければ「名無しの犬」「名無しの猫」「名無しの動物」。
    飼い主が探してますの子は飼い主には名前があるはずなので「迷子の犬」（PR #126 Codex 7、2026-11-15 おまえさん決定）。
    毛色や管理番号は混ぜない（性別・年齢・種類は下の小さなバッジにある）。<title> は検索結果で見分けられるよう headline() のまま。"""
    name = disp_name(a)
    if name and name not in EMPTY_VALS:
        return name
    noun = SPECIES[species_key(a)] if species_key(a) in ("dog", "cat") else "動物"
    return f"迷子の{noun}" if a.get("kind") == "lost" else f"名無しの{noun}"


_ATTR_SEX = re.compile(r"(?:去勢|不妊|避妊)?(オス|メス|雄|雌|おす|めす|♂|♀)")
_ATTR_SEX_DONE = re.compile(r"[、・,\s]*(?:去勢|不妊|避妊)?(?:手術)?(?:済み?|スミ|ずみ)$")   # 「オス、去勢済み」「メス・不妊済み」


def attr_sex(v: Any) -> str:
    """カードの性別バッジ。かっこ書きや手術の注記を外して オス・メス だけ。複数頭の欄（「メス:4匹 オス:2匹」）や「不明」は出さない。"""
    s = re.sub(r"\s*[(（].*$", "", str(v or "")).strip()
    m = _ATTR_SEX.fullmatch(_ATTR_SEX_DONE.sub("", s))
    return _SEX_WORDS.get(m.group(1), m.group(1)) if m else ""


def card_attrs(a: dict[str, Any]) -> list[str]:
    """カードの小さなバッジ。性別 → 年齢 → 種類 の順で、あるものだけ（最大 3 つ）。毛色・大きさは出さない。"""
    breed = _breed_parts(a)[0]   # 雑種の言い換え済み。種別・性別・「不明」だけの欄は空、かっこ書きは外す
    age = card_age(a)
    return [v for v in (attr_sex(a.get("sex")), age, breed) if v not in EMPTY_VALS]   # 「不詳」「なし」等は出さない（#126 Codex 6）


def card_note(a: dict[str, Any]) -> str:
    """カードのメモ抜粋。「無」「募集中」等の意味の無い値は出さない。長い文は詰める（表示は CSS で 2 行に切る）。"""
    note = disp_value("note", a.get("note"))
    return "" if note in EMPTY_VALS else shorten(note, 120)


# ---------------------------------------------------------------- page shell

GA4_ID_RE = re.compile(r"G-[A-Z0-9]{4,20}")

# JS が動かないとき: タブ・絞り込みのボタンは効かないので隠し、初めのタブ以外で隠していたカードも全部出す（PR #126 reviewer F-03）
NOSCRIPT_CSS = ("\n<noscript><style>.card[hidden]{display:grid!important}"
                ".tablist,.sub-seg,.filter-row,.view-bar{display:none!important}</style></noscript>")


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


# 個体ページの到達・相談行動を GA4 へ送る（ga4_id があるときだけ出力。gtag 未読込でも dataLayer へ積まれる）
GA4_CLICK_JS = """(function(){
  var b=document.querySelector('.detail-box');
  if(!b||typeof gtag!=='function')return;
  var base={prefecture:b.dataset.pref||'',animal_id:b.dataset.id||'',kind:b.dataset.kind||'',species:b.dataset.species||''};
  document.addEventListener('click',function(e){
    var a=e.target&&e.target.closest?e.target.closest('a'):null;
    if(!a)return;
    var p=Object.assign({},base);
    if(a.classList.contains('btn-secondary')||a.classList.contains('ph-btn')){p.link_url=a.href;gtag('event','external_link_click',p);}
    else if(a.classList.contains('btn-primary')&&(a.getAttribute('href')||'').indexOf('tel:')===0){gtag('event','contact_phone_click',p);}
    else if(a.closest('.prep')){p.link_title=(a.textContent||'').trim();gtag('event','affiliate_click',p);}
  });
})();"""


def page(cfg: dict[str, Any], *, title: str, desc: str, path: str, body: str,
         og_type: str = "website", extra_head: str = "", body_attrs: str = "") -> str:
    site = esc(cfg["site_name"])
    base = cfg["base_url"].rstrip("/")
    url = esc(base + path)
    # OG 画像は全ページ oneco のアバター（ふたつの円）1 枚に固定。自治体の写真を SNS 側に取り込ませない（POLICY.md 方針 34）
    og_src = f"{base}/brand/oneco-avatar-512.png"
    og_img = f'\n<meta property="og:image" content="{esc(og_src)}">'
    full_title = esc(title) if title == cfg["site_name"] else f"{esc(title)}｜{site}"
    tagline = esc(cfg.get("tagline") or "")
    tagline_html = f'<span class="tagline">{tagline}</span>' if tagline else ""
    # フッター（2026-11-15 UI 刷新）: リンクは 3 つ。「運営への問い合わせ」は取り下げ・訂正の窓口（about）。フッターで「取り下げ」と
    # 書いて不要な削除依頼を誘わず、動物の相談先（掲載元の自治体）と取り違えないように「運営への」と付ける（PR #126 Codex 8）。
    # 著作権の主張（All Rights Reserved）は付けない（自治体情報のまとめのため）
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
<meta name="twitter:card" content="summary">
<meta name="theme-color" content="#ffffff">
<link rel="icon" href="/favicon.ico" sizes="32x32">
<link rel="icon" href="/icon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="stylesheet" href="/style.css">{NOSCRIPT_CSS}{extra_head}{ga4_head(cfg)}
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
<nav class="foot-links" aria-label="サイトの案内"><a href="/about/">このサイトについて</a><a href="/sources/">情報源の一覧</a><a href="/about/#takedown">運営への問い合わせ</a></nav>
<p class="foot-note">掲載情報は各自治体の公開データに基づきます。<br>最新の状況は掲載元のページ・電話でご確認ください。</p>
<div class="foot-brand"><img src="/brand/oneco-mark.svg" width="18" height="18" alt="" loading="lazy"><span>{site}</span></div>
</footer>
</body>
</html>
"""


# ---------------------------------------------------------------- partials

# 写真なしの枠の絵（2026-11-19）: ロゴ「ふたつの円」を小さくした丸 2 つ（コーラル = 犬のポム、ブルーグリーン = 猫のビリー）。
# agy と作った試作プレビューの .ph-dots。種別では変えない。飾りなので読み上げない
PH_DOTS = '<div class="ph-dots" aria-hidden="true"><i></i><i></i></div>'


def placeholder(a: dict[str, Any] | None = None, *, small: bool = False, button_url: str = "") -> str:
    """写真が無い子の枠。丸 2 つ（PH_DOTS）の下に文を置く。写真を止めている掲載元（T630: 確認が取れるまで出さない・不可）の子は
    掲載元には写真があるので「写真はありません」とは書かない。それ以外も、取れなかっただけかもしれないので「無い」とは言い切らない（Codex #22）。
    small は一覧の小さな枠（96px）用に改行を入れた短い文。button_url があれば「自治体のページで写真を見る」ボタンを添える（個体ページ）。"""
    msg = "写真は自治体のページでご確認ください"   # 止めている子も元から無い子も同じ文（POLICY.md 方針 4）
    shown = "写真は自治体の<br>ページでご確認<br>ください" if small else esc(msg)
    if button_url:   # ボタン（リンク）を含むので role="img" にしない
        return (f'<div class="ph">{PH_DOTS}<span>{shown}</span><a class="ph-btn" href="{esc(button_url)}" rel="noopener" '
                f'target="_blank">自治体のページで写真を見る ↗</a></div>')
    return f'<div class="ph" role="img" aria-label="{msg}">{PH_DOTS}<span>{shown}</span></div>'


def photo_box(a: dict[str, Any], *, big: bool = False) -> str:
    """一覧の写真枠（.thumb）か、個体ページの写真枠（.detail-media）。写真は切り抜かず全体を出す（T625）。"""
    cls = "detail-media" if big else "thumb"
    img = safe_url(a.get("image_url"))
    if not img:
        src = safe_url(a.get("source_url")) if big and a.get("_photo_withheld") else ""   # 写真を見たい人がすぐ掲載元へ行けるように
        return f'<div class="{cls}">{placeholder(a, small=not big, button_url=src)}</div>'
    # カードはリンクの中の見出し・バッジ・自治体名で読めるので、写真は飾り（alt=""）。同じ語を何度も読み上げない（agy ⑦）
    alt = esc(photo_alt(a)) if big else ""
    attrs = 'loading="eager" fetchpriority="high"' if big else 'loading="lazy"'
    # 自治体サイトの写真を直接表示する。取れなかったときは JS でプレースホルダに差し替える
    return (f'<div class="{cls}"><img src="{esc(img)}" alt="{alt}" referrerpolicy="no-referrer" {attrs} '
            f'onerror="this.parentNode.classList.add(\'noimg\');this.remove()">{placeholder(small=not big)}</div>')


def badges(a: dict[str, Any]) -> str:
    """区分のバッジ、続けて種別のバッジ（種別なしの子は区分だけ）。"""
    sp, kd = species_key(a), str(a.get("kind") or "")
    sp_html = f'<span class="badge sp-{esc(sp)}">{esc(species_label(a))}</span>' if species_label(a) else ""
    return f'<div class="card-badges"><span class="badge kd-{esc(kd)}">{esc(kind_label(a))}</span>{sp_html}</div>'


def card(a: dict[str, Any], *, hidden: bool = False) -> str:
    """一覧のカード。日付・場所・大きさ・管理番号は出さない（個体ページの表にある）。"""
    sub = MISSING_SUB.get(str(a.get("kind")), "")
    sub_attr = f' data-sub="{sub}"' if sub else ""
    hidden_attr = " hidden" if hidden else ""
    attrs = "".join(f'<span class="attr">{esc(v)}</span>' for v in card_attrs(a))
    note = card_note(a)
    return (f'<a class="card" href="{esc(animal_path(a["id"]))}" data-species="{esc(species_key(a))}" data-kind="{esc(a.get("kind") or "")}" '
            f'data-group="{kind_group(a)}"{sub_attr}{hidden_attr}>\n'
            f'{photo_box(a)}\n<div class="card-main">\n{badges(a)}\n<h3 class="card-title">{esc(card_title(a))}</h3>\n'
            + (f'<div class="attr-list">{attrs}</div>\n' if attrs else "")
            + f'<p class="card-muni">{ICO_ORG}<span>{esc(a.get("municipality"))}</span></p>\n'
            + (f'<p class="card-note">{esc(note)}</p>\n' if note else "")
            + "</div>\n</a>\n")


# ---------------------------------------------------------------- pages

def build_index(cfg: dict[str, Any], data: dict[str, Any], animals: list[dict[str, Any]]) -> str:
    """トップ（2026-11-15 UI 刷新）: 地域から探す前提の見出し、区分の 3 タブ、地方ブロックごとの 47 都道府県タイル。
    今日 0 頭の県も隠さず薄く出す（0 なのか対象外なのか分かる。Codex #10）。種別の絞り込みは都道府県ページで行う。"""
    cnt: dict[str, Counter[str]] = {}
    for a in animals:
        c = cnt.setdefault(str(a.get("prefecture")), Counter())
        c["all"] += 1
        c[kind_group(a)] += 1
    sp = Counter(species_key(a) for a in animals)
    n_adopt = sum(1 for a in animals if kind_group(a) == "adopt")
    rest = sp["other"] + sp["none"]   # 犬猫以外 + 種類の記載なし
    stats = f"犬 <b>{sp['dog']}</b> ・ 猫 <b>{sp['cat']}</b>" + (f" ・ その他 <b>{rest}</b>" if rest else "")
    extra = sorted((p for p in cnt if p not in PREF_INDEX), key=pref_key)   # 都道府県名でない値（収集側の誤り）も行き先を残す
    def tile(p: str) -> str:
        n = cnt.get(p, Counter())
        return (f'<a class="pref-tile{"" if n["all"] else " is-zero"}" href="{esc(pref_path(p))}" data-pref="{esc(p)}" '
                f'data-all="{n["all"]}" data-adopt="{n["adopt"]}" data-missing="{n["missing"]}">'
                f'<span class="pref-name">{esc(pref_short(p))}</span><span class="pref-num"><b class="n">{n["all"]}</b>頭</span></a>')

    groups = []
    for name, prefs in [*REGIONS, *([("その他", extra)] if extra else [])]:
        tiles = "".join(tile(p) for p in prefs)
        groups.append(f'<section class="region-group"><h2 class="region-title">{esc(name)}</h2><div class="pref-grid">{tiles}</div></section>')
    tab_btns = "\n".join(
        f'<button type="button" class="tab-btn" data-top-tab="{k}" aria-pressed="{"true" if k == "all" else "false"}">{label} <span class="tab-cnt">{n}</span></button>'
        for k, label, n in (("all", "すべて", len(animals)), ("adopt", GROUPS["adopt"], n_adopt), ("missing", GROUPS["missing"], len(animals) - n_adopt)))
    body = f"""<section class="hero">
<h1>都道府県から動物の里親募集・迷子情報を探す</h1>
<p>保護犬・保護猫をはじめ、地域ごとの里親募集と迷子情報を毎日更新しています。</p>
<p class="hero-stats">{esc(fmt_date(data.get('date')))}時点：{stats}</p>
</section>
<a class="resume-box" id="resume" href="/" hidden><span><small>前回見た地域</small><strong id="resume-name"></strong></span><span class="resume-arrow" aria-hidden="true">›</span></a>
<div class="tablist" role="group" aria-label="表示する区分">
{tab_btns}
</div>
{chr(10).join(groups)}
<script>{INDEX_JS}</script>"""
    return page(cfg, title="全国の動物の里親募集・迷子情報", path="/", body=body,
                desc="全国の自治体が公開している保護犬・保護猫の情報を、都道府県ごとに 1 か所で探せます。里親募集と迷子情報を毎日更新、出典つき。")


# トップのタブ: タイルの頭数とリンク先の ?tab= を切り替える。前回見た県（都道府県ページが localStorage に残す）があれば近道を出す
INDEX_JS = """
(function(){
  var tabs=document.querySelectorAll('button[data-top-tab]');
  var tiles=document.querySelectorAll('a.pref-tile');
  var resume=document.getElementById('resume');
  var last='';
  try{last=localStorage.getItem('oneco_last_pref')||'';}catch(e){}
  if(!Array.prototype.some.call(tiles,function(t){return t.dataset.pref===last;}))last='';
  function query(tab){return tab==='all'?'':'?tab='+encodeURIComponent(tab);}
  function apply(tab){
    tabs.forEach(function(b){b.setAttribute('aria-pressed',b.dataset.topTab===tab?'true':'false');});
    tiles.forEach(function(t){
      var n=Number(t.dataset[tab]||0);
      t.querySelector('.n').textContent=n;
      t.classList.toggle('is-zero',n===0);
      t.search=query(tab);
    });
    if(last)resume.href='/pref/'+encodeURIComponent(last)+'/'+query(tab);
  }
  if(last){document.getElementById('resume-name').textContent=last+'の一覧を開く';resume.hidden=false;apply('all');}
  tabs.forEach(function(b){b.addEventListener('click',function(){apply(b.dataset.topTab);});});
})();
"""

# 都道府県ページの絞り込み。カードはページに全部あり、表示だけ切り替える（data.json を読まない。2026-11-09）。
# 状態（目的のタブ・迷子の内訳・種別・列数）は sessionStorage に残し、個体ページの「‹ ○○の一覧へ」で戻ったときに戻す。
# URL にも replaceState で書く（共有・ブラウザの戻る用）。URL に tab があればそちらを優先する。
# URL の値はボタンの値と比べるだけで、セレクタや HTML には入れない（#124 reviewer G-01）
PREF_JS = """
(function(){
  var list=document.getElementById('list'),count=document.getElementById('count'),empty=document.getElementById('empty'),sub=document.getElementById('sub');
  var cards=Array.prototype.slice.call(list.querySelectorAll('a.card'));
  var pref=document.body.getAttribute('data-pref')||'';
  var KEY='oneco_pref_state',VKEY='oneco_view';
  var state={tab:list.getAttribute('data-default-tab')||'adopt',sub:'all',sp:'all',view:'list'};
  function btns(k){return Array.prototype.slice.call(document.querySelectorAll('button[data-'+k+']'));}
  function known(k){return btns(k).some(function(b){return b.dataset[k]===state[k];});}
  try{localStorage.setItem('oneco_last_pref',pref);}catch(e){}
  var q=new URLSearchParams(location.search);
  var KIND={adoption:'adopt/all',sheltered:'missing/shelter',stray:'missing/shelter',lost:'missing/lost'};   // 旧 URL の ?kind=（#126 Codex 1）
  var tab=q.get('tab'),sub0=q.get('sub'),kd=q.get('kind');
  if(!tab&&kd&&Object.prototype.hasOwnProperty.call(KIND,kd)){tab=KIND[kd].split('/')[0];sub0=KIND[kd].split('/')[1];}
  try{
    state.view=sessionStorage.getItem(VKEY)||state.view;
    var s=JSON.parse(sessionStorage.getItem(KEY)||'null');
    if(!tab&&s&&s.pref===pref){state.tab=s.tab;state.sub=s.sub;state.sp=s.sp;}
  }catch(e){}
  if(tab){state.tab=tab;state.sub=sub0||'all';state.sp=q.get('species')||'all';}
  else if(q.get('species')){state.sp=q.get('species');}
  if(q.get('view'))state.view=q.get('view');
  function apply(){
    if(!known('tab'))state.tab=list.getAttribute('data-default-tab')||'adopt';
    if(state.tab!=='missing'||!known('sub'))state.sub='all';
    var hasOther=cards.some(function(c){return c.dataset.group===state.tab&&(c.dataset.species==='other'||c.dataset.species==='none');});
    if(!known('sp')||(state.sp==='other'&&!hasOther))state.sp='all';
    if(state.view!=='grid')state.view='list';
    ['tab','sub','sp','view'].forEach(function(k){btns(k).forEach(function(b){b.setAttribute('aria-pressed',b.dataset[k]===state[k]?'true':'false');});});
    if(sub)sub.hidden=state.tab!=='missing';
    btns('sp').forEach(function(b){if(b.dataset.sp==='other')b.hidden=!hasOther;});
    var n=0;
    cards.forEach(function(c){
      var sp=c.dataset.species;
      var ok=c.dataset.group===state.tab&&(state.sub==='all'||c.dataset.sub===state.sub)&&(state.sp==='all'||sp===state.sp||(state.sp==='other'&&sp==='none'));
      c.hidden=!ok;if(ok)n++;
    });
    count.textContent=n;empty.hidden=n!==0;
    list.className=(state.view==='grid'?'animal-grid':'animal-list')+(state.sp==='all'?'':' sp-filtered');
    document.querySelectorAll('a.neighbor-chip').forEach(function(a){a.search='?tab='+encodeURIComponent(state.tab);});
    try{sessionStorage.setItem(KEY,JSON.stringify({pref:pref,tab:state.tab,sub:state.sub,sp:state.sp}));sessionStorage.setItem(VKEY,state.view);}catch(e){}
    var p=new URLSearchParams(location.search);   // utm_ などの他のクエリとハッシュは残す（GA4 の流入元。#126 Codex）
    ['tab','sub','species','view','kind'].forEach(function(k){p.delete(k);});
    p.set('tab',state.tab);
    if(state.sub!=='all')p.set('sub',state.sub);
    if(state.sp!=='all')p.set('species',state.sp);
    if(state.view!=='list')p.set('view',state.view);
    history.replaceState(history.state,'',location.pathname+'?'+p.toString()+location.hash);
  }
  ['tab','sub','sp','view'].forEach(function(k){btns(k).forEach(function(b){b.addEventListener('click',function(){state[k]=b.dataset[k];if(k==='tab')state.sub='all';apply();});});});
  apply();
})();
"""


def _pressed(on: bool) -> str:
    return "true" if on else "false"


def build_pref(cfg: dict[str, Any], data: dict[str, Any], pref: str, animals: list[dict[str, Any]]) -> str:
    """都道府県ページ（2026-11-15 UI 刷新）。0 頭の県も作る。初めは里親募集のタブ（里親募集が 0 頭で迷子情報があれば迷子情報）。"""
    c = Counter(species_key(a) for a in animals)
    n_adopt = sum(1 for a in animals if kind_group(a) == "adopt")
    n_missing = len(animals) - n_adopt
    tab = "missing" if n_adopt == 0 and n_missing else "adopt"
    shown = [a for a in animals if kind_group(a) == tab]
    other_in_tab = any(species_key(a) in ("other", "none") for a in shown)
    region = REGION_OF.get(pref)
    neighbors = ""
    if region:
        chips = "".join(
            (f'<a class="neighbor-chip active" href="{esc(pref_path(p))}" aria-current="page">' if p == pref
             else f'<a class="neighbor-chip" href="{esc(pref_path(p))}">') + f"{esc(pref_short(p))}</a>"
            for p in dict(REGIONS)[region])
        neighbors = f'<nav class="neighbor-bar" aria-label="{esc(region)}の都道府県"><span class="neighbor-label">{esc(region)}</span>{chips}</nav>\n'
    tabs = "".join(
        f'<button type="button" class="tab-btn" data-tab="{k}" aria-pressed="{_pressed(k == tab)}">{GROUPS[k]} <span class="tab-cnt">{n}</span></button>'
        for k, n in (("adopt", n_adopt), ("missing", n_missing)))
    sub_seg = ""
    if any(a.get("kind") == "lost" for a in animals):   # 飼い主が探してます がいる県だけ、迷子情報の内訳を選べる
        sub_btns = "".join(f'<button type="button" class="sub-seg-btn" data-sub="{k}" aria-pressed="{_pressed(k == "all")}">{label}</button>'
                           for k, label in (("all", "すべて"), ("shelter", KINDS["sheltered"]), ("lost", KINDS["lost"])))
        sub_seg = f'<div class="sub-seg" id="sub" role="group" aria-label="迷子情報の内訳"{"" if tab == "missing" else " hidden"}>{sub_btns}</div>\n'
    sp_opts = [("all", "すべて"), ("dog", "犬"), ("cat", "猫")]
    if c["other"] + c["none"]:   # 犬猫以外と種類の記載なしの子は「その他」で絞れる（agy ⑤）。開いているタブにいなければ隠す
        sp_opts.append(("other", "その他"))
    sp_btns = "".join(f'<button type="button" class="chip-btn" data-sp="{k}" aria-pressed="{_pressed(k == "all")}"'
                      f'{" hidden" if k == "other" and not other_in_tab else ""}>{label}</button>' for k, label in sp_opts)
    cards = "".join(card(a, hidden=kind_group(a) != tab) for a in animals)
    # 説明文で「（ほか 56 頭）」と書いても何の子か分からない（agy ④）ので名指しする
    rest_desc = (f"・その他の動物 {c['other']} 頭" if c["other"] else "") + (f"・{NO_SPECIES} {c['none']} 頭" if c["none"] else "")
    body = f"""<nav class="crumbs"><a class="back-link" href="/">‹ 地域を選ぶ</a><span class="date-note">{esc(fmt_date(data.get('date')))}時点</span></nav>
<h1>{esc(pref)}</h1>
{neighbors}<div class="tablist" role="group" aria-label="目的の切り替え">{tabs}</div>
{sub_seg}<div class="filter-row"><div class="chips" role="group" aria-label="動物の種類">{sp_btns}</div></div>
<div class="view-bar"><span aria-live="polite">該当 <b id="count">{len(shown)}</b> 頭</span><div class="view-toggle" role="group" aria-label="表示の切り替え"><button type="button" data-view="list" aria-pressed="true">1列表示</button><button type="button" data-view="grid" aria-pressed="false">2列表示</button></div></div>
<div class="animal-list" id="list" data-default-tab="{tab}">
{cards}</div>
<div class="empty-box" id="empty"{"" if not shown else " hidden"}>現在掲載されている子はありません。自治体の公式ページに掲載がある場合もあるため、<a href="/sources/#{esc(quote(pref))}">情報源の一覧</a>もあわせてご確認ください。</div>
<script>{PREF_JS}</script>"""
    return page(cfg, title=f"{pref}の動物の里親募集・迷子情報", path=pref_path(pref), body=body, body_attrs=f' data-pref="{esc(pref)}"',
                desc=f"{pref}の自治体が{fmt_date(data.get('date'))}に公開している保護犬 {c['dog']} 頭・保護猫 {c['cat']} 頭{rest_desc}の一覧。里親募集と迷子情報。出典つき。")


def build_animal(cfg: dict[str, Any], data: dict[str, Any], a: dict[str, Any]) -> str:
    """個体ページ（2026-11-15 UI 刷新）: 写真 → バッジと見出し → この子の情報 → 掲載元・所在地 → 連絡の枠。
    枠の外に日付と「すでに〜場合があります」。広告（迎える準備）はその下で、里親募集の子だけ。"""
    pref = str(a.get("prefecture") or "")
    muni = str(a.get("municipality") or "")
    src = safe_url(a.get("source_url"))
    kind = str(a.get("kind") or "")
    labels = FIELD_LABELS_BY_KIND.get(kind, {})
    rows = []
    for key, label in FIELDS:
        v = disp_field(a, key)
        if v in EMPTY_VALS:
            continue
        rows.append(f"<div><dt>{esc(labels.get(key, label))}</dt><dd>{esc(v)}</dd></div>")
    phone = str(a.get("phone") or "").strip()
    addr = str(a.get("address") or "").strip()
    tel = tel_href(phone) if phone else ""
    # contact_scope=operator（県のまとめページ等）は掲載元の運営元の連絡先で、子がいる収容先そのものではない → 「問い合わせ先」と出す（T616）
    operator = str(a.get("contact_scope") or "facility") == "operator"
    contact = [f"<div><dt>掲載元</dt><dd>{esc(muni)}</dd></div>"]
    if addr:
        contact.append(f"<div><dt>{'問い合わせ先の所在地' if operator else '所在地'}</dt><dd>{esc(addr)}</dd></div>")
    if not phone:
        contact.append("<div><dt>電話</dt><dd>自治体のページでご確認ください</dd></div>")
    elif not tel:   # 数字の無い電話の欄（電話をかけるボタンにできない）は表に出す
        contact.append(f"<div><dt>{'問い合わせ先' if operator else '電話'}</dt><dd>{esc(phone)}</dd></div>")
    # 県のまとめページの運営元の住所を、子のいる場所と思って訪ねないように（掲載元に無いことは断定しない）
    operator_note = ('<p class="fine">この連絡先は掲載元ページの運営窓口です。子がいる場所とは限りません。訪ねる前に、電話か自治体のページでご確認ください。</p>\n'
                     if operator and (phone or addr) else "")
    lead = "お迎えのご相談は掲載元の自治体へ" if kind == "adoption" else "お心当たりのある方は掲載元へご連絡ください"
    actions = [f'<p class="action-lead">{lead}</p>']
    if tel:
        actions.append(f'<a class="btn-primary" href="{esc(tel)}">{"問い合わせ先 " if operator else ""}{esc(phone)} に電話する</a>')
    actions.append(f'<a class="btn-secondary" href="{esc(src)}" rel="noopener" target="_blank">自治体の公式ページを見る ↗</a>' if src
                   else f'<p class="action-none">元ページの URL が取れていません。{esc(muni)}にお問い合わせください。</p>')
    # 「迎える準備」枠（広告）は里親募集の子だけ。保護中・迷子・探してます の子は飼い主の元に帰るかもしれない（T506）
    aff = (cfg.get("affiliate") or []) if kind == "adoption" else []
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
    aff_html = (f'<aside class="prep"><h2>迎える準備</h2><p>迎えたあとに使うものの広告です。収入はサイトの運営費に充てます。</p><ul>{"".join(aff_items)}</ul></aside>\n'
                if aff_items else "")
    # 広告を載せるページは、広告であることをファーストビュー（写真より上）に出す（T629・A8 の提携条件・ステマ規制）
    pr_html = ('<p class="pr-note"><span>PR</span>このページはアフィリエイト広告を利用しています（ページ下の「迎える準備」枠）。</p>\n'
               if aff_items else "")
    desc = (f"飼い主さんが{kind_phrase(a)}。{muni}が{fmt_date(data.get('date'))}時点で公開している情報です。" if kind == "lost"
            else f"{muni}が{fmt_date(data.get('date'))}時点で公開している{kind_phrase(a)}。")
    if subline(a):
        desc += subline(a).rstrip("。") + "。"   # 下の行が「…思われます。」で終わると「。。」になる（agy ⑥）
    note = disp_value("note", a.get("note"))   # 本文で出さない備考（「無」「有」）は説明文にも出さない（Codex #17）
    if note:
        desc += shorten(note, 80)
    ga4_click = f"<script>{GA4_CLICK_JS}</script>" if ga4_id(cfg) else ""
    body = f"""<nav class="crumbs"><a class="back-link" href="{esc(pref_path(pref))}">‹ {esc(pref)}の一覧へ</a></nav>
{pr_html}<article class="detail-box" data-id="{esc(a['id'])}" data-pref="{esc(pref)}" data-kind="{esc(kind)}" data-species="{esc(species_key(a))}">
{photo_box(a, big=True)}
<div class="detail-body">
{badges(a)}
<h1 class="detail-title">{esc(card_title(a))}</h1>
<h2 class="detail-sec">この子の情報</h2>
<dl class="facts">
{chr(10).join(rows) if rows else '<div><dd>詳しい情報は自治体のページでご確認ください。</dd></div>'}
</dl>
<h2 class="detail-sec">掲載元・所在地</h2>
<dl class="facts">
{chr(10).join(contact)}
</dl>
{operator_note}<div class="action-card">
{chr(10).join(actions)}
</div>
</div>
</article>
<p class="detail-fine">{esc(fmt_date(data.get('date')))}時点の自治体公開情報です。<br>{FINE_BY_KIND.get(kind, '')}</p>
{aff_html}{ga4_click}"""
    # タイトル（検索結果・タブ）は見分けがつくよう品種と性別（headline）。何も分からない子は区分を足す（#124 F-06）
    lead_t = "飼い主さんが探している動物" if kind == "lost" else f"{kind_label(a)}の動物"   # 「探してますの動物」とはしない（#124 G-03）
    title_head = f"{lead_t}・{headline(a)}" if not disp_name(a) and _headline_parts(a)[1] == "none" else headline(a)
    return page(cfg, title=f"{title_head}｜{muni}", path=animal_path(a["id"]), body=body, og_type="article",
                desc=shorten(desc, 160))


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
                if str(s.get("photo") or "pending") == "pending":
                    # まだお伺いしていない自治体もあるので「返事待ち」とは書かない（2026-11-22 方針 1・2）
                    res += "（写真は自治体の確認が取れるまで出していません）"
                elif str(s.get("photo") or "pending") == "no":
                    # 飼い主が探している迷子（lost）のページは、自治体の返事ではなくこちらの決まりで写真を出していない
                    # （飼い主の方が届け出た写真と思われるため。町田市 -2〜-4 ほか）。自治体の意向とは書かない（T652）
                    res += "（写真は出していません）" if str(s.get("kind")) == "lost" else "（写真は自治体の意向で出していません）"
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
    return page(cfg, title="情報源の一覧", path="/sources/", body=body,
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
<p>個別の子のページでは、「自治体の公式ページを見る」などの公式ページへのボタン、電話のボタン、「迎える準備」枠の広告リンクを押したときにも、どのボタンを押したか、その子の種別（犬・猫などの種類と、里親募集・迷子などの区分）、都道府県、子の管理番号を Google アナリティクスに送ります。電話番号は送りません。</p>
<p>パソコンのブラウザでは、<a href="https://tools.google.com/dlpage/gaoptout?hl=ja" rel="noopener" target="_blank">Google アナリティクス オプトアウト アドオン</a>で送信を止められます。ブラウザで Cookie を無効にすると、集められる情報を減らせます。</p>
</section>
"""
    body = f"""<article class="about">
<h1>このサイトについて</h1>
<section>
<h2>{site} とは</h2>
<p>{site} は、全国の自治体（動物愛護センター・保健所・市区町村）が公開している保護犬・保護猫の情報を、出典を明示して 1 か所に集めた、個人運営のサイトです。自治体のページに載っていない情報（保護団体や個人の里親募集など）は扱いません。</p>
<p>載せている子は、探す目的で「里親募集」（新しい家族を募集している子）と「迷子情報」に分けています。迷子情報は、「保護中」（自治体の施設や、市民の方に保護されている子）と「飼い主が探してます」（飼い主さんが自分の迷子を探している告知のうち、自治体のページに載っているもの）の 2 つです。犬猫以外の動物も、自治体のページにあれば載せています。自治体のページで犬か猫か分からない子は、種別を付けずに載せています（絞り込みでは「その他」に出ます）。</p>
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
<li>すべての子に「自治体の公式ページを見る」ボタンを付けています。譲渡の申し込みや迷子の問い合わせは、必ず自治体に直接行ってください。{site} は仲介をしません。</li>
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
    return page(cfg, title="このサイトについて", path="/about/", body=body,
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
   ブランドの 2 色（コーラル #E8826E = 犬のポム、ブルーグリーン #6FAEBB = 猫のビリー）は about ページの飾りと、写真なしの枠の丸 2 つに使う。
   2026-11-15 UI 刷新（agy と作った試作プレビュー）: 幅 860px、区分は 里親募集 = 緑・保護中 = 青・飼い主が探してます = オレンジ */
:root{--bg:#fcfbf9;--card:#fff;--ink:#1f2937;--mute:#5b6775;--line:#e5e7eb;--accent:#0369a1;--accent-dark:#075985;--accent-soft:#f0f9ff;--accent-line:#bae6fd;--focus:#3b82f6;--coral:#E8826E;--teal:#6FAEBB;--dog:#fdeae4;--dog-ink:#9a3a26;--cat:#e4f1f4;--cat-ink:#21606c;--adopt:#d1fae5;--adopt-ink:#065f46;--shelter:#e0f2fe;--shelter-ink:#075985;--lost:#ffedd5;--lost-ink:#9a3412}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Helvetica Neue","Hiragino Sans","Hiragino Kaku Gothic ProN","Noto Sans JP","Yu Gothic",Meiryo,sans-serif;line-height:1.6;font-size:16px;padding-bottom:env(safe-area-inset-bottom,0px)}
a{color:var(--accent)}
button{font-family:inherit}
:focus-visible{outline:2px solid var(--focus);outline-offset:2px}
img{max-width:100%;display:block}
h1{font-size:1.4rem;margin:.2em 0 .5em;line-height:1.35}
h2{font-size:1.1rem;margin:1.6em 0 .5em}
h3{font-size:1rem;margin:0}
p{margin:.4em 0}
.wrap{max-width:860px;margin:0 auto;padding:16px}
.site-head{position:sticky;top:0;z-index:50;background:rgba(255,255,255,.94);-webkit-backdrop-filter:blur(8px);backdrop-filter:blur(8px);border-bottom:1px solid var(--line)}
.site-head-in{max-width:860px;margin:0 auto;padding:10px 16px;display:flex;align-items:center;justify-content:space-between;gap:12px}
.brand{display:flex;align-items:center;gap:10px;min-width:0;min-height:44px;color:var(--ink);text-decoration:none;border-radius:6px}
.brand .mark{flex:none;width:32px;height:32px}
.brand .wordmark{flex:none;width:88px;height:20px;display:block}
.brand .tagline{font-size:.75rem;color:var(--mute);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-left:2px}
@media (max-width:640px){.brand .tagline{display:none}}
.nav{display:flex;gap:14px;flex-wrap:wrap;font-size:.9rem}
.nav a{color:var(--mute);text-decoration:none;padding:4px 2px;border-radius:4px}
.nav a:hover{color:var(--accent);text-decoration:underline}
@media (max-width:520px){.site-head-in{flex-wrap:wrap;padding:8px 16px}.nav{flex:1 1 100%;gap:16px}}
.site-foot{max-width:860px;margin:28px auto 0;padding:18px 16px;color:var(--mute);font-size:.82rem;border-top:1px solid var(--line);line-height:1.6}
.foot-links{display:flex;flex-wrap:wrap;gap:6px 14px;margin-bottom:10px;font-size:.8rem}
.foot-links a{color:var(--accent);text-decoration:none;font-weight:500}
.foot-links a:hover{text-decoration:underline}
.foot-note{font-size:.78rem;line-height:1.6;margin:0 0 12px}
.foot-brand{display:flex;align-items:center;gap:6px;font-size:.78rem}
.foot-brand img{flex:none;width:18px;height:18px}
.hint,.fine{color:var(--mute);font-size:.85rem}
.empty{color:var(--mute)}
/* トップ */
.hero{margin-bottom:14px}
.hero h1{font-size:1.28rem;line-height:1.35;margin:0 0 6px}
.hero p{font-size:.88rem;color:var(--mute);line-height:1.5;margin:0}
.hero .hero-stats{margin-top:6px;font-size:.8rem}
.resume-box{display:flex;align-items:center;justify-content:space-between;gap:12px;background:var(--accent-soft);border:1px solid var(--accent-line);border-radius:12px;padding:10px 14px;margin-bottom:16px;text-decoration:none;color:var(--ink);min-height:52px}
.resume-box small{display:block;font-size:12px;color:var(--accent-dark);font-weight:600}
.resume-box strong{font-size:1rem}
.resume-arrow{font-size:1.1rem;color:var(--accent);font-weight:700;flex:none}
.tablist{display:flex;border-bottom:1px solid var(--line);margin-bottom:12px;overflow-x:auto;scrollbar-width:none}
.tablist::-webkit-scrollbar{display:none}
.tab-btn{appearance:none;background:none;border:none;cursor:pointer;flex:1 1 auto;min-width:0;min-height:46px;padding:10px 6px;font-size:.9rem;font-weight:600;color:var(--mute);position:relative;display:inline-flex;align-items:center;justify-content:center;gap:4px;white-space:nowrap}
@media (min-width:480px){.tab-btn{padding:10px 12px;font-size:.95rem;gap:6px}}
.tab-btn[aria-pressed="true"]{color:var(--accent)}
.tab-btn[aria-pressed="true"]::after{content:"";position:absolute;left:0;right:0;bottom:0;border-bottom:3px solid var(--accent)}
.tab-cnt{font-size:.75rem;font-weight:600;background:#eef1f4;color:var(--mute);padding:1px 6px;border-radius:999px}
.tab-btn[aria-pressed="true"] .tab-cnt{background:var(--accent-soft);color:var(--accent-dark)}
.region-group{margin-bottom:18px}
.region-title{font-size:.82rem;color:var(--mute);font-weight:700;margin:0 0 8px;letter-spacing:.03em}
.pref-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(145px,1fr));gap:8px}
.pref-tile{display:flex;align-items:center;justify-content:space-between;gap:6px;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px;min-height:48px;text-decoration:none;color:var(--ink)}
.pref-tile:hover{border-color:var(--accent)}
.pref-tile.is-zero{background:#f6f7f8;border-style:dashed}
.pref-tile.is-zero .pref-name{color:var(--mute);font-weight:500}
.pref-tile.is-zero .pref-num b{color:var(--mute)}
.pref-name{font-weight:600;font-size:.95rem}
.pref-num{font-size:.85rem;color:var(--mute);white-space:nowrap}
.pref-num b{color:var(--accent);font-size:1rem}
/* 都道府県ページ */
.crumbs{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:4px;overflow-wrap:anywhere}
.back-link{display:inline-flex;align-items:center;gap:4px;font-size:.9rem;font-weight:600;text-decoration:none;color:var(--accent);min-height:44px;padding-right:8px}
.date-note{font-size:.8rem;color:var(--mute);white-space:nowrap}
.crumbs+h1{font-size:1.35rem;margin:0 0 8px}
.neighbor-bar{display:flex;align-items:center;gap:6px;overflow-x:auto;padding-bottom:6px;margin-bottom:10px;scrollbar-width:none}
.neighbor-bar::-webkit-scrollbar{display:none}
.neighbor-label{font-size:.78rem;color:var(--mute);white-space:nowrap;flex:none;margin-right:2px}
.neighbor-chip{flex:none;text-decoration:none;font-size:.82rem;color:var(--ink);background:#fff;border:1px solid var(--line);border-radius:999px;padding:5px 12px;min-height:42px;display:inline-flex;align-items:center}
.neighbor-chip.active{background:var(--ink);color:#fff;border-color:var(--ink)}
.sub-seg{display:flex;gap:3px;padding:3px;background:#eef2f5;border-radius:10px;margin-bottom:10px}
.sub-seg-btn{appearance:none;border:none;background:transparent;color:var(--mute);font-size:clamp(.74rem,3.3vw,.82rem);font-weight:500;padding:7px 8px;border-radius:8px;cursor:pointer;flex:1 1 auto;min-width:0;white-space:nowrap;text-align:center;min-height:42px}
.sub-seg-btn[aria-pressed="true"]{background:#fff;color:var(--accent-dark);font-weight:700;box-shadow:0 1px 2px rgba(15,23,42,.08)}
.filter-row{display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap;margin-bottom:10px}
.chips{display:flex;gap:6px;flex-wrap:wrap}
.chip-btn{appearance:none;background:#fff;border:1px solid var(--line);color:var(--ink);border-radius:999px;padding:6px 14px;font-size:.86rem;cursor:pointer;min-height:42px;display:inline-flex;align-items:center}
.chip-btn[aria-pressed="true"]{background:var(--accent);color:#fff;border-color:var(--accent);font-weight:600}
.view-bar{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:10px;font-size:.88rem;color:var(--mute)}
.view-bar b{color:var(--ink)}
.view-toggle{display:inline-flex;border:1px solid var(--line);border-radius:8px;overflow:hidden;background:#fff}
.view-toggle button{appearance:none;border:none;background:none;padding:5px 12px;font-size:.8rem;color:var(--mute);cursor:pointer;min-height:42px}
.view-toggle button[aria-pressed="true"]{background:var(--accent-soft);color:var(--accent-dark);font-weight:600}
.empty-box{text-align:center;padding:28px 16px;background:#fff;border:1px solid var(--line);border-radius:12px;color:var(--mute);font-size:.92rem;line-height:1.7}
/* バッジ */
.card-badges{display:flex;align-items:center;gap:4px;flex-wrap:wrap;min-width:0}
.badge{display:inline-flex;align-items:center;font-size:11px;font-weight:700;padding:2px 8px;border-radius:999px;line-height:1.4;white-space:nowrap;background:#eef1f4;color:var(--ink)}
.badge.kd-adoption{background:var(--adopt);color:var(--adopt-ink)}
.badge.kd-sheltered,.badge.kd-stray{background:var(--shelter);color:var(--shelter-ink)}
.badge.kd-lost{background:var(--lost);color:var(--lost-ink)}
.badge.sp-dog{background:var(--dog);color:var(--dog-ink)}.badge.sp-cat{background:var(--cat);color:var(--cat-ink)}.badge.sp-other{background:#eef1f4;color:var(--ink)}
.sp-filtered .badge.sp-dog,.sp-filtered .badge.sp-cat,.sp-filtered .badge.sp-other{display:none}
/* カード: 1 列（写真が左） */
.animal-list{display:flex;flex-direction:column;gap:10px}
.card{display:grid;grid-template-columns:96px minmax(0,1fr);gap:12px;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px;align-items:start;text-decoration:none;color:var(--ink)}
@media (min-width:560px){.card{grid-template-columns:120px minmax(0,1fr);padding:12px}}
.card:hover{border-color:var(--accent)}
.thumb{position:relative;width:96px;height:96px;border-radius:8px;background:#e9edf1;overflow:hidden}
@media (min-width:560px){.thumb{width:120px;height:104px}}
.thumb img{width:100%;height:100%;object-fit:contain}
.card-main{min-width:0;display:flex;flex-direction:column;gap:4px}
.card-title{font-size:.98rem;font-weight:700;line-height:1.3;overflow-wrap:anywhere}
.attr-list{display:flex;flex-wrap:wrap;gap:4px;margin:1px 0}
.attr{display:inline-flex;align-items:center;font-size:12px;color:#334155;background:#f1f5f9;border-radius:5px;padding:1px 7px;line-height:1.45;overflow-wrap:anywhere}
.card-muni{display:flex;align-items:flex-start;gap:5px;line-height:1.4;font-size:.8rem;color:var(--mute);margin:0}
.ico{width:14px;height:14px;flex:none;margin-top:2px;color:var(--mute)}
.card-note{font-size:.8rem;color:var(--mute);background:#f8fafc;border-radius:6px;padding:4px 8px;margin:2px 0 0;overflow-wrap:anywhere;display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;overflow:hidden}
/* カード: 2 列（スマホ 2 列・600px 以上 3 列。写真が上） */
.animal-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
@media (min-width:600px){.animal-grid{grid-template-columns:repeat(3,minmax(0,1fr))}}
.animal-grid .card{grid-template-columns:1fr;padding:0;overflow:hidden;gap:0}
.animal-grid .thumb{width:100%;height:auto;aspect-ratio:4/3;border-radius:0}
.animal-grid .card-main{padding:8px 10px 10px;gap:3px}
.animal-grid .card-title{font-size:.9rem}
.animal-grid .attr{font-size:11px;padding:1px 5px}
.animal-grid .card-muni{font-size:.76rem}
.animal-grid .card-note{display:none}
/* 写真が無いときの枠（絵はロゴと同じ色の丸 2 つ .ph-dots。丸・文・ボタンをひとまとまりで中央に置く。種別では変えない） */
.thumb img+.ph,.detail-media img+.ph{display:none}
.thumb.noimg .ph,.detail-media.noimg .ph{display:flex}
.ph{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:4px 2px;background:linear-gradient(160deg,#e8edf2,#d3dbe3);color:#5b6775;text-align:center}
.ph-dots{display:flex;margin-bottom:4px}
.ph-dots i{display:block;width:14px;height:14px;border-radius:50%;opacity:.65}
.ph-dots i:first-child{background:var(--coral);margin-right:-4px}
.ph-dots i:last-child{background:var(--teal)}
.ph span{letter-spacing:0;line-height:1.3}
.thumb .ph span{font-size:10px}
.animal-grid .thumb .ph span{font-size:12px}
.detail-media .ph span{font-size:13px;padding:0 8px}
.ph-btn{margin-top:10px;padding:7px 14px;border-radius:999px;background:#fff;color:var(--accent-dark);border:1px solid var(--accent-line);font-size:12.5px;font-weight:600;text-decoration:none;min-height:42px;display:inline-flex;align-items:center}
/* 個体ページ */
.detail-media{position:relative;aspect-ratio:4/3;max-height:360px;width:100%;background:#e9edf1;overflow:hidden}
.detail-media img{width:100%;height:100%;object-fit:contain}
.detail-box{background:var(--card);border:1px solid var(--line);border-radius:14px;overflow:hidden}
.detail-body{padding:16px}
.detail-title{font-size:1.35rem;margin:8px 0 4px;overflow-wrap:anywhere}
.detail-sec{margin:20px 0 0;font-size:.98rem;color:var(--ink)}
.detail-title+.detail-sec{margin-top:12px}
.facts{margin:6px 0 0;display:grid}
.facts>div{display:grid;grid-template-columns:7.5em 1fr;gap:8px;padding:8px 0;border-bottom:1px solid var(--line);font-size:.92rem;align-items:baseline}
.facts>div:last-child{border-bottom:none}
@media (max-width:360px){.facts>div{grid-template-columns:1fr;gap:2px}}
.facts dt{color:var(--mute);font-size:.85rem}
.facts dd{margin:0;overflow-wrap:anywhere;white-space:pre-line}
.action-card{background:var(--accent-soft);border:1px solid var(--accent-line);border-radius:12px;padding:12px 14px;margin-top:20px;display:flex;flex-direction:column;gap:8px}
.action-lead{font-size:.85rem;font-weight:700;color:var(--accent-dark);margin:0}
.btn-primary{display:flex;align-items:center;justify-content:center;gap:6px;background:var(--accent);color:#fff;text-decoration:none;font-weight:700;border-radius:10px;padding:12px 16px;min-height:48px;text-align:center}
.btn-primary:hover{background:var(--accent-dark)}
.btn-secondary{display:flex;align-items:center;justify-content:center;gap:6px;background:#fff;color:var(--accent-dark);border:1px solid var(--accent-line);text-decoration:none;font-weight:600;border-radius:10px;padding:10px 14px;min-height:44px;text-align:center}
.action-none{margin:0;font-size:.9rem}
.detail-fine{margin:12px 4px 0;font-size:.78rem;color:var(--mute);line-height:1.5;text-align:center}
.cta{display:block;background:var(--accent);color:#fff;text-decoration:none;text-align:center;font-weight:700;font-size:1.05rem;padding:14px 16px;border-radius:12px;margin:14px 0}
.cta:hover{background:var(--accent-dark)}
.pr-note{margin:0 0 10px;font-size:.85rem;color:var(--mute)}
.pr-note span{display:inline-block;font-weight:700;font-size:.75rem;color:var(--ink);border:1px solid var(--mute);border-radius:4px;padding:0 6px;margin-right:6px}
.prep{margin-top:20px;background:#fffaf0;border:1px solid #f0e2c2;border-radius:14px;padding:12px 16px}
.prep h2{margin-top:.2em}
.prep ul{padding-left:1.2em;margin:.4em 0}
.prep li{margin:.3em 0}
.prep small{display:block;color:var(--mute)}
.prep img{position:absolute}
/* 情報源・about */
.src-list{list-style:none;padding:0;margin:0 0 8px;display:grid;gap:8px}
.src{display:grid;gap:2px;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px}
@media (min-width:720px){.src{grid-template-columns:2fr 1.5fr 1.2fr auto;align-items:center;gap:12px}}
.src-name{font-weight:600}
.src-meta{color:var(--mute);font-size:.85rem}
.src-status{font-size:.9rem}
.src.st-failed .src-status,.src.st-ambiguous_empty .src-status{color:#b91c1c}
.src.st-ok .src-status b{color:var(--accent)}
.src-link{font-size:.9rem}
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
    """写真を出さない掲載元の slug（台帳 photo が ok 以外。T630: 確認が取れるまで出さない・不可）。
    photo が無い掲載元（T630 より前の収集・台帳から消えた掲載元）も出さない（2026-11-22 方針 1・2）。"""
    return {str(s.get("slug")) for s in data.get("sources", [])
            if isinstance(s, dict) and str(s.get("photo") or "pending") != "ok"}


def strip_photos(data: dict[str, Any]) -> dict[str, Any]:
    """photo が ok 以外の掲載元の子から image_url を落とした data を返す（該当が無ければ同じ dict をそのまま返す）。"""
    hidden = no_photo_sources(data)
    if not hidden:
        return data
    animals = [({**a, "image_url": None} if a.get("source") in hidden else a) if isinstance(a, dict) else a
               for a in data.get("animals", [])]
    return {**data, "animals": animals}


LINK_ONLY_PRIVATE_KEYS = ("phone", "address", "verified_phone_url", "verified_address_url")


def strip_link_only_contacts(data: dict[str, Any]) -> dict[str, Any]:
    """公開する data.json から、リンクのみの掲載元（台帳 mode か収集の status が link_only）の電話・所在地を外す。

    リンクのみは、自治体から文章や画像の転載を断られた（久留米市・福岡市・北海道）か、個人の掲載などで、
    ページには名前とリンクしか出していない。data.json にだけ台帳の電話・所在地が残っていたので外す（2026-11-21 T630）。
    外すものが無ければ data をそのまま返す（呼び出し側は元のファイルをコピーできる）。
    """
    srcs = data.get("sources")
    if not isinstance(srcs, list):
        return data
    out: list[Any] = []
    changed = False
    for s in srcs:
        if (isinstance(s, dict) and "link_only" in (s.get("mode"), s.get("status"))
                and any(s.get(k) is not None for k in LINK_ONLY_PRIVATE_KEYS)):
            out.append({**s, **dict.fromkeys(LINK_ONLY_PRIVATE_KEYS)})
            changed = True
        else:
            out.append(s)
    return {**data, "sources": out} if changed else data


def build_site(data: dict[str, Any], cfg: dict[str, Any], out: Path, data_path: Path | None = None) -> dict[str, int]:
    """data（animals JSON の中身）から out/ を生成。data_path があれば data.json はそのファイルのコピー。
    写真を出さない掲載元（台帳 photo が ok 以外）があるときは image_url を落とした data を書く。"""
    cfg = {**DEFAULT_CFG, **cfg}
    prepare_out(out)
    # 掲載元には写真があるが、確認が取れるまで・不可で止めている子（枠に「写真は自治体のページでご確認ください」と出す）
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
    # stable: 里親募集→保護中→迷子→探してます。同じ区分の中は、日付のある子を新しい順 → 日付の無い子（POLICY.md 方針 40。2026-11-24）。
    # 同じ日付・日付の無い子どうしは掲載元の順（元の並び）を保つ。年の無い日付はデータの日付で年を決める
    def _order(a: dict[str, Any]) -> tuple[int, int, int]:
        d = parse_shelter_date(a.get("shelter_date"), d0)
        return (KIND_ORDER.get(str(a.get("kind")), 9), 0 if d else 1, -d.toordinal() if d else 0)
    animals.sort(key=_order)

    by_pref: dict[str, list[dict[str, Any]]] = {}
    for a in animals:
        by_pref.setdefault(str(a["prefecture"]), []).append(a)
    # 都道府県ページは今日 0 頭の県も含めて 47 すべて作る（トップのタイルから 404 にならない。2026-11-15 UI 刷新）
    prefs = sorted({*PREF_ORDER, *by_pref}, key=pref_key)

    write(out, "index.html", build_index(cfg, data, animals))
    for p in prefs:
        write(out, f"pref/{p}/index.html", build_pref(cfg, data, p, by_pref.get(p, [])))
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
    public = strip_link_only_contacts(data)
    if data_path is not None and public is data:
        shutil.copyfile(data_path, out / "data.json")
    else:
        write(out, "data.json", json.dumps(public, ensure_ascii=False, indent=1))
    write(out, MARKER, f"{datetime.now().isoformat(timespec='seconds')} {data.get('date', '')}\n")
    return {"animals": len(animals), "prefectures": len(by_pref), "sources": len(data.get("sources", [])), "skipped": skipped}


def merge_registry_photo(data: dict[str, Any], registry: Path) -> dict[str, Any]:
    """台帳（sources.yaml）の photo を slug ごとに data["sources"] へ合流させる。
    収集時の台帳に photo が無かった日のデータでも、今の台帳の判断で写真を止められるようにする（T630）。
    台帳に photo を書いていない掲載元は pending（collector.registry.Source の既定と同じ。2026-11-22 方針 1・2）。"""
    import yaml  # 収集側の依存。build 単体では使わないのでここで読む

    reg = yaml.safe_load(registry.read_text(encoding="utf-8")) or {}
    photo = {str(s.get("slug")): str(s.get("photo") or "pending") for s in reg.get("sources", []) if isinstance(s, dict)}
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
                    help="台帳 sources.yaml。渡すと photo（ok | pending | no。書いていなければ pending）を合流させ、ok 以外の掲載元の写真を出さない")
    args = ap.parse_args(argv)
    n = build(args.data, args.out, args.config, registry=args.registry)
    print(f"{args.out}: {n['animals']} 頭・{n['prefectures']} 都道府県・情報源 {n['sources']} 件"
          + (f"（id 不正・重複で {n['skipped']} 件を除外）" if n["skipped"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
