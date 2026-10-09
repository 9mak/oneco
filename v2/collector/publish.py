"""日次ファイルの原子的な公開と manifest（W006 T610・T623）。

run() の出力を out_dir/.tmp-<run_id>/ に全部書き、読み直して検査してから os.replace で最終位置へ動かす。
検査に落ちたら何も動かさない（latest.json は前日のまま）。
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .registry import REGISTRY_PATH, ROOT


class PublishError(RuntimeError):
    pass


def _dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1)


def _check(name: str, path: Path, date: str) -> None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise PublishError(f"{name} が読み直せない: {e}") from e
    if name.startswith(("animals-", "latest")):
        if not isinstance(data, dict) or not isinstance(data.get("animals"), list):
            raise PublishError(f"{name}: animals が list でない")
        if data.get("date") != date:
            raise PublishError(f"{name}: date が {date} と一致しない（{data.get('date')}）")


def publish(out_dir: Path, run_id: str, date: str, files: dict[str, Any]) -> list[Path]:
    """files = {ファイル名: JSON にする中身}。順序どおりに最終位置へ置く（latest 系は呼び出し側が最後に並べる）。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = out_dir / f".tmp-{run_id}"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir()
    try:
        for name, obj in files.items():
            (tmp / name).write_text(_dumps(obj), encoding="utf-8")
        for name in files:
            _check(name, tmp / name, date)
        placed = []
        for name in files:
            os.replace(tmp / name, out_dir / name)
            placed.append(out_dir / name)
        return placed
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _hash_files(paths: list[Path], base: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(paths):
        h.update(str(p.relative_to(base)).encode())
        h.update(b"\0")
        h.update(p.read_bytes())
        h.update(b"\0")
    return h.hexdigest()[:16]


def code_sha(root: Path = ROOT) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() or None if r.returncode == 0 else None


def build_manifest(run_id: str, date: str, report: list[dict[str, Any]], animals_count: int, held: bool,
                   root: Path = ROOT, registry_path: Path = REGISTRY_PATH) -> dict[str, Any]:
    recipes = list((root / "recipes").glob("*.yaml")) if (root / "recipes").is_dir() else []
    return {
        "run_id": run_id, "date": date, "code_sha": code_sha(root),
        "recipe_sha": _hash_files(recipes, root),
        "registry_sha": _hash_files([registry_path], registry_path.parent) if registry_path.exists() else None,
        "animals_count": animals_count,
        "sources_ok": sum(1 for r in report if r["status"] in ("ok", "empty")),
        "sources_failed": sum(1 for r in report if r["status"] in ("failed", "ambiguous_empty")),
        "held": held,
    }


def promote(date: str, out_dir: Path) -> int:
    """animals-<date>.json を latest.json に戻す（回線断などで据え置かれた日を、確認のうえ手で公開する）。0=戻した 2=できない"""
    src = out_dir / f"animals-{date}.json"
    if not src.exists():
        print(f"{src.name} が無い")
        return 2
    try:
        data = json.loads(src.read_text(encoding="utf-8"))
    except ValueError as e:
        print(f"{src.name} が読めない: {e}")
        return 2
    data["held"] = False
    files: dict[str, Any] = {"latest.json": data}
    mf = out_dir / f"manifest-{date}.json"
    if mf.exists():
        try:
            m = json.loads(mf.read_text(encoding="utf-8"))
            files["manifest-latest.json"] = {**m, "held": False, "promoted": True}
        except ValueError:
            print(f"{mf.name} が読めないので manifest-latest は更新しない")
    try:
        publish(out_dir, f"promote-{date}", date, files)
    except PublishError as e:
        print(f"戻せない: {e}")
        return 2
    print(f"latest.json を {date} に戻した（{len(data['animals'])} 頭）")
    return 0
