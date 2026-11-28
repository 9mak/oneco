"""1 件に複数の子が名前つきで並ぶ掲載を 1 匹ずつに分ける（POLICY.md 方針 21・24。2026-11-28）。

岩手県の保健所などは、兄弟の子を写真 1 枚・1 件にまとめて「名前：(左)三郎、(右)二郎」「性別：オス×2」のように書く。
レシピに `split_names: true` を書いた掲載元だけ、extract.build がこの関数で分ける。分けるのは次を全部満たす行:

- 名前が「、」で 2 つ以上並ぶ（「左から」や「(左)」「(手前)」の印は外して照合する。表示の名前には印を残す）
- ほかの項目が、全員共通（「オス×2」「みんな女の子」「3匹ともメス」、並びの無い 1 つの値）か、名前ごと
  （「らん→オス　すー→メス」「シルビアちゃんはメス、みかん君はオス」）。どの子の値か分からない形（「黒白、黒白、黒」
  「黒と白」「オスとメス」「オス(左)メス(右)」、1 匹の名前だけを挙げた「三郎は茶色」）が 1 つでもあれば分けない。
  並び順で当てはめることはしない（掲載元が対応を書いていないため）。管理番号だけは、名前と同じ数が
  並ぶとき（宮古「【左側】2026-10-086C（仮名：シルビアちゃん）【右側】2026-10-085C（仮名：みかん君）」をレシピで並べたもの）
  に並び順で当てる
- 複数の子だと言える印がある（位置の印・名前ごとの値・「×2」「みんな」・名前と同じ数の管理番号のどれか）。高崎市の
  「呼名：チビ、チー」のような 1 匹の呼び名は分けない

説明（note）は分けず全員に同じ文を付ける。分けた子のうち、本文に「◯◯は譲渡が決まりました」「◯◯の譲渡が決まりました」
「◯◯は返還されました」のように書かれた子は載せない（方針 21。「決まりそう」「決まりにくい」は決まっていない）。
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_POS = r"(?:左|右|中央|中|真ん中|手前|奥|上|下)(?:側)?"
_POS_MARK = re.compile(rf"\s*[（(【]\s*{_POS}\s*[)）】]\s*")
_LEAD = re.compile(r"^(?:写真の?)?(?:左|右|上|下)から(?:順に)?[、，,\s]*")
_HONORIFIC = r"(?:ちゃん|くん|君|さん|様)"
_CONNECT = r"\s*(?:→|⇒|->|は|：|:|＝|=)\s*"
_OPEN, _CLOSE = "（(「【［[", "）)」】］]"
# 名前ごとの書き方に見える区切り（「C君はオス」「みき→メス」）。知らない名前のこの形は前の子の続きにしない
_LOOKS_MAPPED = re.compile(r"^[^\s、，,]{1,15}?" + _HONORIFIC + r"?\s*(?:→|⇒|->|：|:|＝|=|は(?=\S))")
_COUNT_SUFFIX = re.compile(r"^(.+?)\s*[×xX✕]\s*([0-9０-９]+)\s*$")
_ALL_PREFIX = re.compile(r"^(?:みんな|全員|全て|すべて|全部|ともに|両方とも?|([0-9０-９]+|[二三四五六七八九十])\s*(?:匹|頭|羽)とも(?:に)?)\s*[、，,:：]?\s*(.+)$")
_COUNT_WORD = re.compile(r"[0-9０-９]+\s*(?:匹|頭|羽)")
_KANJI_NUM = {"二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
# 分けて当てはめる項目。name は分ける元、note は全員に同じ文。ほか（section 等の内部の項目）はそのまま写す
_RESOLVE = ("sex", "age", "breed", "color", "size", "shelter_date", "location", "species", "phone")
# 掲載が終わった言い方（extract._CLOSED_LISTING と同じ言い方に、「旅立ちました」と、まだ決まっていない言い方の除外を足した。
# 「見つかりますように」「決まり次第」「決まりにくい」「決まりそう」「決まりましたら」は願い・条件・見込みなので外す。#172 reviewer M-3）
_NOT_YET = r"(?!ます|ません|次第|にくい|づらい|そう|ましたら)"
_CLOSED = (r"返還(?:しました|済|することができました|されました|いたしました|となりました|になりました)"
           r"|飼い?主(?:さん|様)?(?:が見つかり" + _NOT_YET + r"|の(?:元|もと)(?:に|へ)(?:戻り|帰り)(?!たい)|に戻りました)"
           r"|(?:譲渡先?|飼い?主(?:さん|様)?|里親(?:さん|様)?|新しい(?:飼い?主(?:さん|様)?|家族|お家|おうち)|お家|おうち)"
           r"(?:が|も)?(?:決まり|決定|見つかり)" + _NOT_YET
           + r"|譲渡済(?!みの場合)|譲渡(?:されました|しました|決定(?!次第))|旅立ちました")
# 1 つの値に 2 匹分が入っている形（#172 reviewer M-1）。読点のほか「と・/・空白」でつないだ並びは、どの子の値か書いていない
_AND = r"(?<=[\u30A0-\u30FF\u4E00-\u9FFF0-9０-９])と(?=[\u30A0-\u30FF\u4E00-\u9FFF0-9０-９])"
_SEP_WORD = re.compile(rf"\s*(?:{_AND}|[・/／&＆])\s*")
_SEP_SPACE = re.compile(r"\s+")
_MALE = re.compile(r"オス|雄|♂|おす|男の子")
_FEMALE = re.compile(r"メス|雌|♀|めす|女の子")
_PARENS = re.compile(r"[（(][^）)]*[）)]")


@dataclass
class Member:
    fields: dict[str, str | None]
    id_key: str   # ID の元。子ごとの管理番号が分かればそれ、無ければ印と敬称を外した名前
    by_management_no: bool = False   # id_key が子ごとの管理番号


def _num(s: str) -> int:
    return _KANJI_NUM.get(s) or int(unicodedata.normalize("NFKC", s))


def _top_split(value: str, seps: str) -> list[str]:
    """かっこの外にある区切りで切る（「キジトラ(ココは茶色、白)」の中の読点では切らない）。"""
    out, buf, depth = [], [], 0
    for ch in value:
        if ch in _OPEN:
            depth += 1
        elif ch in _CLOSE:
            depth = max(depth - 1, 0)
        if depth == 0 and ch in seps:
            out.append("".join(buf))
            buf = []
            continue
        buf.append(ch)
    out.append("".join(buf))
    return [p.strip() for p in out if p.strip()]


def parse_names(name: str | None) -> tuple[list[str], list[str], bool] | None:
    """(表示の名前, 照合と ID 用の名前〔印と敬称を外す〕, 位置の印があったか)。名前が 2 つ未満なら None。"""
    if not name:
        return None
    s = name.strip()
    marked = bool(_LEAD.match(s))
    s = _LEAD.sub("", s)
    shown = _top_split(s, "、，,")   # かっこの中の読点（「ココ(左、茶色が混じる)」）では切らない
    if len(shown) < 2:
        return None
    keys = []
    for p in shown:
        k, n = _POS_MARK.subn("", p)
        marked = marked or n > 0
        k = re.sub(_HONORIFIC + "$", "", k.strip()) or k.strip()
        if not k or len(k) > 15 or re.search(r"\s|[:：。]", k):
            return None   # 名前でなく文や項目（「性別：…」）が入っている
        keys.append(k)
    if len(set(keys)) != len(keys):
        return None
    return shown, keys, marked


def _mapped(value: str, keys: list[str]) -> list[str] | None:
    """「らん→オス　すー→メス」「シルビアちゃんはメス、みかん君はオス」を名前ごとの値にする。全員の分が無ければ None。"""
    heads = [re.compile(re.escape(k) + _HONORIFIC + "?" + _CONNECT + "(.*)$") for k in keys]
    got: dict[int, str] = {}
    last: int | None = None
    for seg in _top_split(value, "、，,／/ 　\t"):
        hit = next(((i, m.group(1).strip()) for i, h in enumerate(heads) if (m := h.match(seg))), None)
        if hit is None:
            if last is None or _LOOKS_MAPPED.match(seg):
                return None
            got[last] = f"{got[last]} {seg}".strip()   # 「らん→オス 去勢済み」の続き
            continue
        i, v = hit
        if i in got:
            return None
        got[i], last = v, i
    if len(got) != len(keys) or not all(got.values()):
        return None
    return [got[i] for i in range(len(keys))]


def _shared(value: str, n: int, field: str, keys: list[str]) -> tuple[str, bool] | None:
    """全員に共通の値と、「×2」「みんな」のような複数の印があったか。どの子の値か分からない形なら None。"""
    plural = False   # 「×2」「みんな」: 全員が同じと掲載元が書いている（外した値にも下の確認をかける。#172 再レビュー n-2）
    m = _COUNT_SUFFIX.match(value)
    if m:
        if _num(m.group(2)) != n:
            return None
        value, plural = m.group(1).strip(), True
    elif m := _ALL_PREFIX.match(value):
        if m.group(1) and _num(m.group(1)) != n:
            return None
        value, plural = m.group(2).strip(), True
    top = _PARENS.sub("", value)   # かっこの中の注記（「キジトラ(ココは茶色が混じってます。)」）は全員に同じ文として付ける
    if len(_top_split(value, "、，,")) > 1 or _COUNT_WORD.search(value) or _POS_MARK.search(value):
        return None   # 「黒白、黒白、黒」「オス:2匹、メス:1匹」「オス(左)メス(右)」
    if any(re.search(re.escape(k) + _HONORIFIC + "?" + _CONNECT, top) for k in keys):
        return None   # 「三郎は茶色」: 1 匹の名前だけを挙げた値（M-2）
    if field == "sex":
        if _MALE.search(top) and _FEMALE.search(top):
            return None   # 「オスとメス」「雄雌」「オス1メス1」
    elif plural:
        pass   # 「白と黒×2」「みんな白と黒」は全員が白と黒（1 匹が 2 色）と書いてある
    elif field in ("color", "age", "size", "breed", "species"):
        if len([t for t in _SEP_WORD.split(top) if t]) > 1 or len([t for t in _SEP_SPACE.split(top.strip()) if t]) > 1:
            return None   # 「黒と白」「黒・白」「黒 白」「3か月と5か月」
    elif field == "shelter_date" and len([t for t in _SEP_WORD.split(top) if t]) > 1:
        return None
    return value, plural


def _closed_keys(keys: list[str], text: str) -> set[str]:
    """本文で「◯◯は譲渡が決まりました」と書かれた子（照合用の名前）。「ねりちゃん、うるい君は…」は並べた全員。

    名前の後ろの「は・も」から決まった言い方までは読点をまたがない（「三郎と二郎は兄弟で、二郎は譲渡が…」の三郎を外さない）。
    """
    alt = "(?:" + "|".join(re.escape(k) for k in sorted(keys, key=len, reverse=True)) + ")"
    one = alt + _HONORIFIC + r"?(?:[（(][^）)]{0,10}[）)])?"
    gap = rf"(?:(?!{alt})[^。！!？?\n、,]){{0,15}}?"   # 別の子の名前をまたがない（「二郎は、三郎の譲渡が決まりました」の二郎を外さない）
    # 「は・も」の主語は決まった言い方まで 15 字を許し、「の」の主語は決まった言い方がすぐ続く形だけ（「二郎の譲渡が決まりました」。
    # 「二郎の元の飼い主さんが見つかりました」も。「カナンの兄のヤスパーは…」のカナンを外さない。#172 再レビュー N-1）。「ねりもうるいも…」は並べた全員
    pat = re.compile(rf"({one}(?:(?:\s*[、・と,]\s*|\s*も\s*){one})*)\s*(?:(?:は|も)[、,]?\s*{gap}|の(?:元の)?)(?:{_CLOSED})")
    out: set[str] = set()
    for m in re.finditer(alt, text):   # 主語の名前ごとに当てる（「ねりもうるいも…」の 2 匹目も見る）
        hit = pat.match(text, m.start())
        if hit:
            out.update(re.findall(alt, hit.group(1)))   # 長い名前から当てる（「みきお」の中の「みき」を数えない）
    return out


def split_members(f: dict[str, str | None], text: str) -> list[Member] | None:
    """分けられる行なら、載せる子（決まった子を除く）を返す。分けない行は None。text は行の全文（決まった子の判定用）。"""
    parsed = parse_names(f.get("name"))
    if parsed is None:
        return None
    shown, keys, evidence = parsed
    n = len(keys)
    per: dict[str, list[str | None]] = {}
    for k in _RESOLVE:
        v = (f.get(k) or "").strip()
        if not v:
            per[k] = [f.get(k)] * n
            continue
        mapped = _mapped(v, keys)
        if mapped is not None:
            per[k], evidence = list(mapped), True
            continue
        sh = _shared(v, n, k, keys)
        if sh is None:
            return None
        per[k] = [sh[0]] * n
        evidence = evidence or sh[1]
    mgmt_own = False
    mg = (f.get("management_no") or "").strip()
    if mg:
        parts = _top_split(mg, "、，,")
        if len(parts) == n:
            per["management_no"], mgmt_own, evidence = list(parts), True, True
        elif len(parts) == 1:
            per["management_no"] = [mg] * n   # 掲載元が 2 匹に 1 つの番号を付けている（ID には使わない）
        else:
            return None
    if not evidence:
        return None
    closed = _closed_keys(keys, f"{text}\n{f.get('note') or ''}")
    out: list[Member] = []
    for i in range(n):
        if keys[i] in closed:
            continue
        fields = dict(f)
        fields["name"] = shown[i]
        for k, vals in per.items():
            fields[k] = vals[i]
        own = per["management_no"][i] if mgmt_own else None
        out.append(Member(fields, own or keys[i], by_management_no=bool(own)))
    return out
