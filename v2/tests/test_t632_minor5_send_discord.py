"""W006 T632 の小さな直し (5) Discord 送信の共通化。ネットワークなし。"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from collector import notify as notify_mod


# --- (5) Discord 送信の共通化 ----------------------------------------------------------
def test_send_discord_is_shared_between_notify_and_audit(monkeypatch):
    sent: list[dict] = []

    class R:
        def raise_for_status(self):
            pass

    monkeypatch.setattr(notify_mod.httpx, "post", lambda url, json, timeout: sent.append({"url": url, **json}) or R())
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.test/hook")
    notify_mod.send_discord("こんにちは")
    assert sent == [{"url": "https://discord.test/hook", "content": "こんにちは"}]
    monkeypatch.delenv("DISCORD_WEBHOOK_URL")
    with pytest.raises(RuntimeError):
        notify_mod.send_discord("x")

    audit_py = Path(__file__).resolve().parent.parent / "ops" / "audit_empty.py"
    spec = importlib.util.spec_from_file_location("oneco_audit_empty_t632", audit_py)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    assert mod.send_discord is notify_mod.send_discord
    assert not hasattr(mod, "_send_discord")
