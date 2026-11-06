"""empty の見張り（W006 T632）。

empty（0 頭と確定した日）は ok と同じ扱いで、通知も AI 修復も止まる。行の読み方が崩れて子がいるのに empty が続いても、
サイトには「本日は 0 頭」と出るだけで誰も気づかない。そこで、0 頭と確定した日のページ本文の指紋を slug ごとに state に持ち、
empty が続いているのに本文が変わった日を通知する（「0 頭のままか見直して」という合図。AI 修復は起動しない・公開データは変えない）。

指紋にするのは「0 頭の根拠が成立した文書」の本文のうち、ナビ・ヘッダ・フッタ・script・style を除いたところ。
日付や件数の数字は 0 に揃え（NFKC で全角も半角へ）、毎日変わる「更新日」「アクセス数」では変わらないようにする。
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import date as date_cls
from typing import TYPE_CHECKING, Any

from bs4 import BeautifulSoup

if TYPE_CHECKING:
    from .recipe import Doc

# 本文の外にある部分。サイト共通のメニュー・お知らせ欄・検索フォームは、子がいてもいなくても変わらない or 毎日変わるので除く
_CHROME = (
    "script",
    "style",
    "noscript",
    "template",
    "head",
    "header",
    "footer",
    "nav",
    "aside",
    "select",
    "iframe",
    "svg",
)
# 本文の入れ物の候補。見つからなければ body 全体
_MAIN = (
    "main",
    "[role=main]",
    "#main",
    "#contents",
    "#content",
    "#main_body",
    "#mainContents",
    "article",
)

# 最初のこの日数は記録だけ（events に出す）で通知しない。指紋が毎日変わるサイトが多いと分かったときに誤報で埋まらないよう、
# 見張りを入れた最初の週は実データで誤報の率を測る（PR 本文に測った値を書く）
QUIET_DAYS = 7


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"\d+", "0", text)
    return re.sub(r"\s+", " ", text).strip()


def doc_text(doc: Doc) -> str:
    """文書 1 枚の指紋の素。PDF は本文そのもの、HTML は入れ物の本文（上の除外後）。"""
    if doc.is_pdf:
        return _norm(doc.pdf_text or "")
    if doc.soup is None:
        return ""
    soup = BeautifulSoup(str(doc.soup), "lxml")  # 元の soup は他の判定でも使うので触らない
    for el in soup.select(",".join(_CHROME)):
        el.decompose()
    for sel in _MAIN:
        el = soup.select_one(sel)
        if el is not None and len(el.get_text(strip=True)) > 20:
            return _norm(el.get_text(" ", strip=True))
    return _norm(soup.get_text(" ", strip=True))


def fingerprint(pool: list[Doc], urls: list[str]) -> dict[str, Any] | None:
    """0 頭の根拠が成立した文書（urls）の指紋。{"fp": 16 桁, "chars": 文字数, "docs": 文書数}。文書が無ければ None。"""
    docs = [d for d in pool if d.url in set(urls)]
    if not docs:
        return None
    text = "\n".join(doc_text(d) for d in docs)
    return {
        "fp": hashlib.sha256(text.encode("utf-8")).hexdigest()[:16],
        "chars": len(text),
        "docs": len(docs),
    }


def _days(a: str, b: str) -> int | None:
    try:
        return (date_cls.fromisoformat(a) - date_cls.fromisoformat(b)).days
    except ValueError:
        return None


def judge(st: dict[str, Any], row: dict[str, Any], date: str) -> dict[str, Any] | None:
    """今日の row（status=empty で row["empty_fp"] がある）を、前回までの state（slug の st["empty_watch"]）と比べる。
    本文が変わっていれば {"from": 前回の日付, "chars": [前, 今]} を返す。基準が無い・同じ・前回が empty でなかった日は None。
    前回が empty でなかった（failed・ok を挟んだ）日は基準を取り直すだけで知らせない（その日は読めた・読めなかったの通知が出ている）。"""
    cur = row.get("empty_fp")
    ew = st.get("empty_watch")
    if row.get("status") != "empty" or not cur or not isinstance(ew, dict):
        return None
    # 同じ日の再実行では、その日の最初の基準（ref）と比べる。今日書いた値と比べると変化が消える
    base = (
        ew.get("ref")
        if ew.get("date") == date
        else {"fp": ew.get("fp"), "chars": ew.get("chars"), "date": ew.get("date")}
    )
    if not base or not base.get("fp") or base["fp"] == cur["fp"]:
        return None
    prev_status = st.get("prev_status") if st.get("last_date") == date else st.get("last_status")
    if prev_status != "empty":
        return None
    return {"from": base.get("date"), "chars": [base.get("chars"), cur.get("chars")]}


def update(st: dict[str, Any], row: dict[str, Any], date: str) -> None:
    """state の slug 欄に基準を書く。empty の日は今日の指紋、ok の日は忘れる（子がいたなら次の empty は新しい基準から）。
    failed・ambiguous_empty の日は触らない。"""
    status = row.get("status")
    if status == "ok":
        st.pop("empty_watch", None)
        return
    cur = row.get("empty_fp")
    if status != "empty" or not cur:
        return
    old = st.get("empty_watch") if isinstance(st.get("empty_watch"), dict) else None
    new = {"fp": cur["fp"], "chars": cur["chars"], "date": date}
    if old and old.get("date") == date:
        new["ref"] = old.get("ref")  # 同じ日の再実行: 最初の基準を持ち越す
    elif old and old.get("fp"):
        new["ref"] = {"fp": old["fp"], "chars": old.get("chars"), "date": old.get("date")}
    st["empty_watch"] = new


def quiet(state: dict[str, Any], date: str) -> bool:
    """見張りを入れてから QUIET_DAYS 日以内か（その間は記録だけで通知しない）。state["empty_watch_since"] に最初の日を持つ。"""
    since = state.get("empty_watch_since")
    if not since:
        return True  # まだ何も記録していない最初の日
    d = _days(date, str(since))
    return d is not None and d < QUIET_DAYS  # 日付が読めないときは黙らない側に倒す
