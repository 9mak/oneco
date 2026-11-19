"""W006 T644: 本番と CI で依存の版をそろえる。

2026-11-18 まで requirements.txt に版の指定が無く、本番クローン（作った日の soupsieve 2.10）と CI（毎回最新の 4.1.1）で
セレクタの受け付け方が違っていた。requirements.txt を「名前==版」だけにし、CI は同じファイルを -c（constraints）で使う。
"""

from __future__ import annotations

import re
from pathlib import Path

V2 = Path(__file__).resolve().parent.parent
REQ = V2 / "requirements.txt"
CI = V2.parent / ".github" / "workflows" / "v2-ci.yml"
PIN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*==[0-9][0-9A-Za-z.]*$")


def _pins() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in REQ.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        assert PIN.match(line), f"版が固定されていない行: {line}"
        name, version = line.split("==", 1)
        out[name.lower()] = version
    return out


def test_every_requirement_is_pinned_to_one_version() -> None:
    pins = _pins()
    # collector が import するもの（soupsieve は beautifulsoup4 の依存だが、セレクタの挙動を決めるので名指しで固定する）
    assert {"httpx", "beautifulsoup4", "soupsieve", "lxml", "pyyaml", "pdfplumber", "playwright"} <= set(pins)


def test_ci_installs_runtime_packages_with_the_same_pins() -> None:
    installs = [ln.strip() for ln in CI.read_text(encoding="utf-8").splitlines() if "pip install" in ln and "ruff" not in ln]
    assert installs, "v2-ci.yml に pip install の行が無い"
    for line in installs:
        assert "-c v2/requirements.txt" in line, f"CI が版を固定せずに入れている: {line}"
