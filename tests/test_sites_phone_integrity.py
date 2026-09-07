"""sites.yaml の phone 列が公開して問題ない形かを機械的に守る（T146）

phone は「そのサイトの掲載動物の問い合わせ先」として公開ページに出る。
間違った番号を載せると、無関係な人や警察署に電話が行く。人が一次ソースを
見て 1 サイト 1 回選ぶ運用（`SiteConfig.phone` の docstring 参照）を、
形式面だけでも機械で支える。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from data_collector.domain.normalizer import DataNormalizer
from data_collector.llm.config import SiteConfigLoader

_SITES_YAML = (
    Path(__file__).resolve().parents[1] / "src" / "data_collector" / "config" / "sites.yaml"
)

# 市外局番 2-4 桁 + 市内局番 1-4 桁 + 加入者番号 4 桁。すべて 0 始まり。
_PHONE_FORMAT = re.compile(r"^0\d{1,3}-\d{1,4}-\d{4}$")

# 採ってはいけない番号。
# - 携帯 (0[789]0) は個人の連絡先である可能性が高い。実際に北海道
#   www.douaicenter.jp の個体ページには拾い主個人の携帯が載っている。
#   自治体の窓口が携帯を公式窓口にしている例が出たら、この定数に例外を
#   足したうえでレビューで根拠を残すこと。
_MOBILE_PREFIXES = ("070-", "080-", "090-")
# 警察の代表番号 (誤って拾いやすい。岡崎市・越谷市のページに併記されている)
_DENYLIST = frozenset(
    {
        "0564-58-0110",  # 岡崎警察署
        "048-964-0110",  # 越谷警察署
    }
)


@pytest.fixture(scope="module")
def sites():
    return SiteConfigLoader.load(_SITES_YAML).sites


def test_every_phone_is_wellformed(sites):
    bad = [(s.name, s.phone) for s in sites if s.phone and not _PHONE_FORMAT.match(s.phone)]
    assert not bad, f"phone の形式が不正: {bad}"


def test_no_mobile_numbers(sites):
    """個人の携帯を公開窓口として載せない"""
    bad = [(s.name, s.phone) for s in sites if s.phone and s.phone.startswith(_MOBILE_PREFIXES)]
    assert not bad, f"携帯番号が設定されている: {bad}"


def test_no_known_wrong_numbers(sites):
    bad = [(s.name, s.phone) for s in sites if s.phone in _DENYLIST]
    assert not bad, f"窓口ではない番号 (警察署等) が設定されている: {bad}"


def test_phone_is_optional(sites):
    """未設定のサイトが残っていてよい (段階的に埋める前提)"""
    assert any(s.phone is None for s in sites)
    assert any(s.phone for s in sites)


def test_every_phone_survives_the_public_pipeline(sites):
    """公開前の検査を素通りする値が混ざっていないことを保証する

    PR #327 reviewer F-01: 当初の実装は正規化後の AnimalData を書き換える
    形で、`DataNormalizer._normalize_phone` (桁数 10/11 の検証) と
    `_sanitize_public_phone` (070/080/090/050 の個人番号を落とす) を
    迂回していた。今は raw 側へ入れて同じ経路を通すので、ここでは
    「sites.yaml の値がその経路を通ったあとも同じ値のまま残るか」を
    直接確かめる。落ちる値・書き換わる値は公開に耐えない。
    """
    bad: list[tuple[str, str, str]] = []
    for s in sites:
        if not s.phone:
            continue
        piped = DataNormalizer._sanitize_public_phone(DataNormalizer._normalize_phone(s.phone))
        if piped != s.phone:
            bad.append((s.name, s.phone, piped))
    assert not bad, f"公開経路を通すと値が変わる/落ちる phone がある: {bad}"


def test_sites_with_per_animal_jurisdiction_have_no_fallback(sites):
    """個体ごとに管轄が違うサイトにはサイト既定の phone を置かない

    PR #327 reviewer F-02。フォールバックは「サイトに窓口が1つ」の前提が
    成り立つときだけ安全で、1ページに複数管轄が乗るサイトでは、抽出に
    失敗した個体に**別の保健所**を案内してしまう。

    - 山梨: 本番 233 件中 232 件が個体ごとの管轄保健所番号を持ち実測で8種類
    - 三重: 1ページに9管轄が同居 (桑名・鈴鹿・津・伊賀・松阪・伊勢 ほか)
    - 浜松: 区ごとに窓口が違う (動物愛護教育センター / 保健所浜北支所)
    - 熊本県動愛・静岡: 個体行に保健所名と電話が並ぶ
    """
    per_animal_hosts = (
        "www.pref.yamanashi.jp",
        "mie-dakc.server-shared.com",
        "www.hama-aikyou.jp",
        "www.kumamoto-doubutuaigo.jp",
        "www.pref.shizuoka.jp",
    )
    bad = [
        (s.name, s.phone)
        for s in sites
        if s.phone and any(h in s.list_url for h in per_animal_hosts)
    ]
    assert not bad, f"個体ごとに管轄が違うサイトに既定 phone が設定されている: {bad}"
