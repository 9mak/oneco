"""fixture に私人の連絡先が残っていないことを守るテスト（T519 公開ゲート 2 回目 F-01）。

生のテキストの正規表現だけでは &#64; や全角の数字を取りこぼしたので、html.unescape と NFKC に
かけた文字列で走査する。見るのは次の 4 種類。
- 携帯・IP 電話（070/080/090/050）: 伏せ字 0X0-0000-0000 以外は落とす
- メール（@・&#64;・(a)・[at]・(at)）: example / mihon.jp / *.lg.jp / *.go.jp 以外は落とす
- 長野市の「連絡先／」の li: 伏せ字以外は落とす（窓口の番号だけが出る nagano1 は除く）
- 松本市の「掲載希望者（連絡先）」「譲渡希望者（連絡先）」の欄: 姓が 〇〇 以外、番号が伏せ字以外なら落とす
"""

from __future__ import annotations

import html
import re
import unicodedata
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

FIX = Path(__file__).resolve().parent / "fixtures"
HTML_FILES = sorted(FIX.glob("*.html"))

MOBILE = re.compile(r"(?<![0-9])0[5789]0[-‐‑–—−\s.]?[0-9]{4}[-‐‑–—−\s.]?[0-9]{4}(?![0-9])")
EMAIL = re.compile(
    r"[A-Za-z0-9._%+-]{2,}\s*(?:@|\(a\)|\[at\]|\(at\))\s*([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)",
    re.I,
)
OK_EMAIL_DOMAIN = ("example", "mihon.jp", ".lg.jp", ".go.jp")
PHONE = re.compile(r"^(0[0-9]{1,4})-?([0-9]{1,4})-?([0-9]{3,4})")
# 長野市の窓口（長野市保健所動物愛護センター）の番号だけが「連絡先／」に出る fixture
NAGANO_OFFICIAL_ONLY = ("t519v_g5_nagano1_",)
BUSINESS = re.compile("法人|会|カフェ|団体|センター|病院|協会|店")


def _text(path: Path) -> str:
    raw = path.read_text(encoding="utf-8", errors="replace")
    return unicodedata.normalize("NFKC", html.unescape(raw))


def _is_placeholder(digits: str) -> bool:
    return digits[3:] == "00000000" or digits == "0000000000"


@pytest.mark.parametrize("path", HTML_FILES, ids=[p.name for p in HTML_FILES])
def test_fixture_has_no_private_contact(path: Path) -> None:
    text = _text(path)
    plain = re.sub(r"<[^>]+>", " ", text)

    mobiles = sorted(
        {m.group(0) for m in MOBILE.finditer(plain) if not _is_placeholder(re.sub(r"[^0-9]", "", m.group(0)))}
    )
    assert not mobiles, f"{path.name}: 携帯・IP 電話の形が {len(mobiles)} 件（伏せ字 0X0-0000-0000 にする）"

    emails = sorted(
        {m.group(0) for m in EMAIL.finditer(plain) if not any(k in m.group(1).lower() for k in OK_EMAIL_DOMAIN)}
    )
    assert not emails, f"{path.name}: 私人のメールの形が {len(emails)} 件（masked@example.jp にする）"

    soup = BeautifulSoup(text, "lxml")
    if not path.name.startswith(NAGANO_OFFICIAL_ONLY):
        bad_li = 0
        for li in soup.find_all("li"):
            m = re.match(r"^連絡先\d?\s*[/／]\s*(.*)$", li.get_text(strip=True))
            if not m:
                continue
            v = m.group(1).strip()
            if "@" in v or "(a)" in v:
                bad_li += "example" not in v
                continue
            mm = PHONE.match(v)
            if mm and not _is_placeholder("".join(mm.groups())):
                bad_li += 1
        assert bad_li == 0, f"{path.name}: 「連絡先／」の項目に伏せ字でない連絡先が {bad_li} 件"

    bad_cell = 0
    for td in soup.find_all(["td", "th"]):
        label = td.get_text(strip=True).replace(" ", "")
        if not re.fullmatch(r"(掲載|譲渡)希望者[(（]連絡先[)）]", label):
            continue
        nxt = td.find_next_sibling(["td", "th"])
        if nxt is None:
            continue
        v = nxt.get_text(" ", strip=True)
        m = re.match(r"^(.*?)\s*[(（]\s*(0[0-9]{1,4})-?([0-9]{1,4})-?([0-9]{3,4})\s*[)）]", v)
        if not m:
            continue
        name = m.group(1).strip()
        if name and name != "〇〇" and not name.endswith("〇〇") and not BUSINESS.search(name):
            bad_cell += 1
        if not _is_placeholder(m.group(2) + m.group(3) + m.group(4)):
            bad_cell += 1
    assert bad_cell == 0, f"{path.name}: 「希望者（連絡先）」の欄に伏せ字でない姓・番号が {bad_cell} 件"
