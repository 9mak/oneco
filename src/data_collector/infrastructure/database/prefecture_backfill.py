"""prefecture が NULL の歴史的 orphan レコードを source_url ホストから補完する。

2026-05-22 (commit e3d7166) に site_config.prefecture フォールバック
(base.py の _default_normalize) が導入されるより前に収集された約 36 件は
prefecture=NULL のまま残存している。これらは source_url が 404 (ソース消滅) の
ため再収集で上書きされず、待っても解消しない orphan であるため、host→prefecture
で一度だけ補完する。

冪等: prefecture が既に入っている行 (NULL でも空文字でもない) は WHERE 句で
除外されるため、何度実行しても安全。値は sites.yaml の当該サイト prefecture と
一致しており (host→prefecture は 1:1)、万一当該 URL が将来再収集されても
同一値で上書きされ矛盾しない。

`animals_archive` は prefecture 列を持たないため対象外 (active `animals` のみ)。
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Connection

# source_url に含まれる識別ドメイン → 正しい都道府県。
# sites.yaml の当該サイト prefecture と一致させること (host→prefecture は 1:1)。
# 沖縄県は aniwel-pref.okinawa と city.naha.okinawa.jp の 2 ホストに対応する。
PREFECTURE_BY_HOST: tuple[tuple[str, str], ...] = (
    ("aniwel-pref.okinawa", "沖縄県"),
    ("city.naha.okinawa.jp", "沖縄県"),
    ("kumamoto-doubutuaigo.jp", "熊本県"),
    ("city.kurashiki.okayama.jp", "岡山県"),
    ("zaidan-fukuoka-douai.or.jp", "福岡県"),
    ("animal-net.pref.nagasaki.jp", "長崎県"),
)


def backfill_null_prefectures(connection: Connection) -> int:
    """NULL/空文字の prefecture を host→prefecture で補完し、影響行数を返す。

    Args:
        connection: 同期 SQLAlchemy Connection (alembic の op.get_bind() か、
            async エンジンの run_sync 経由で渡される sync Connection)。

    Returns:
        更新された行数の合計 (冪等のため 2 回目以降は 0)。
    """
    total = 0
    for host, prefecture in PREFECTURE_BY_HOST:
        result = connection.execute(
            text(
                "UPDATE animals SET prefecture = :prefecture "
                "WHERE (prefecture IS NULL OR prefecture = '') "
                "AND source_url LIKE :pattern"
            ),
            {"prefecture": prefecture, "pattern": f"%{host}%"},
        )
        total += result.rowcount or 0
    return total
