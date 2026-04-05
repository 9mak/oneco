"""
FeedGenerator Service

RSS 2.0 / Atom 1.0 フィード生成サービス。
python-feedgen を使用して、AnimalData から標準準拠の XML フィードを生成。

Requirements Coverage:
- 1.1, 1.2: RSS/Atom フィード生成
- 1.3: アイテムメタデータ
- 1.4, 1.5: チャンネル/フィード情報
- 1.7: 画像埋め込み (enclosure タグ)
- 9.6, 9.7: XML エスケープと CDATA セクション
"""

import hashlib
from datetime import UTC, datetime
from typing import Literal

from feedgen.feed import FeedGenerator as PyFeedGenerator

from src.data_collector.domain.models import AnimalData


class FeedGenerationError(Exception):
    """フィード生成エラー"""

    pass


class FeedGenerator:
    """RSS 2.0 / Atom 1.0 フィードジェネレーター"""

    BASE_URL = "https://example.com"  # TODO: 環境変数から取得

    def __init__(self):
        """FeedGenerator インスタンスを初期化"""
        pass

    def generate_rss(
        self,
        animals: list[AnimalData],
        filter_params: dict,
        feed_type: Literal["active", "archive"] = "active",
    ) -> str:
        """
        RSS 2.0 フィードを生成

        Args:
            animals: 動物データリスト
            filter_params: フィルタ条件（タイトル/説明に反映）
            feed_type: "active" または "archive"

        Returns:
            RSS 2.0 XML 文字列

        Raises:
            FeedGenerationError: フィード生成失敗時
        """
        try:
            fg = self._create_feed_generator(filter_params, feed_type, format_type="rss")

            # 各動物データをアイテムとして追加
            for animal in animals:
                self._add_rss_item(fg, animal)

            # RSS 2.0 XML を生成
            return fg.rss_str(pretty=True).decode("utf-8")
        except Exception as e:
            raise FeedGenerationError(f"RSS フィード生成に失敗しました: {e}")

    def generate_atom(
        self,
        animals: list[AnimalData],
        filter_params: dict,
        feed_type: Literal["active", "archive"] = "active",
    ) -> str:
        """
        Atom 1.0 フィードを生成

        Args:
            animals: 動物データリスト
            filter_params: フィルタ条件（タイトル/説明に反映）
            feed_type: "active" または "archive"

        Returns:
            Atom 1.0 XML 文字列

        Raises:
            FeedGenerationError: フィード生成失敗時
        """
        try:
            fg = self._create_feed_generator(filter_params, feed_type, format_type="atom")

            # 各動物データをエントリとして追加
            for animal in animals:
                self._add_atom_entry(fg, animal)

            # Atom 1.0 XML を生成
            return fg.atom_str(pretty=True).decode("utf-8")
        except Exception as e:
            raise FeedGenerationError(f"Atom フィード生成に失敗しました: {e}")

    def _create_feed_generator(
        self, filter_params: dict, feed_type: str, format_type: str
    ) -> PyFeedGenerator:
        """
        FeedGenerator インスタンスを作成し、チャンネル/フィード情報を設定

        Args:
            filter_params: フィルタ条件
            feed_type: "active" または "archive"
            format_type: "rss" または "atom"

        Returns:
            設定済み FeedGenerator インスタンス
        """
        fg = PyFeedGenerator()

        # タイトル生成（フィルタ条件を反映）
        title = self._build_feed_title(filter_params, feed_type)
        description = "条件に合致する保護動物の情報"

        # フィード URL
        query_string = self._build_query_string(filter_params)
        feed_url = f"{self.BASE_URL}/feeds/{format_type}{query_string}"

        # 基本情報設定
        fg.title(title)
        fg.link(href=feed_url, rel="self")
        fg.description(description)

        # Atom の場合は追加フィールド
        if format_type == "atom":
            # Atom の id: tag URI スキーム
            now = datetime.now(UTC)
            feed_id = f"tag:example.com,{now.strftime('%Y-%m-%d')}:/feeds/atom"
            fg.id(feed_id)
            fg.subtitle(description)
            fg.updated(now)

        # RSS の場合は TTL 設定
        if format_type == "rss":
            fg.ttl(3600)  # 1時間ごとの更新チェックを推奨
            fg.lastBuildDate(datetime.now(UTC))

        return fg

    def _build_feed_title(self, filter_params: dict, feed_type: str) -> str:
        """
        フィルタ条件とフィードタイプからタイトルを生成

        Args:
            filter_params: フィルタ条件
            feed_type: "active" または "archive"

        Returns:
            タイトル文字列（例: "保護動物情報 - 犬 / 高知県"）
        """
        base_title = "保護動物アーカイブ" if feed_type == "archive" else "保護動物情報"

        # フィルタ条件を抽出
        conditions = []
        if filter_params.get("species"):
            conditions.append(filter_params["species"])
        if filter_params.get("location"):
            conditions.append(filter_params["location"])
        if filter_params.get("category"):
            category_label = {"adoption": "譲渡対象", "lost": "迷い犬猫"}.get(
                filter_params["category"], filter_params["category"]
            )
            conditions.append(category_label)

        if conditions:
            return f"{base_title} - {' / '.join(conditions)}"
        else:
            return base_title

    def _build_query_string(self, filter_params: dict) -> str:
        """
        フィルタ条件からクエリ文字列を生成

        Args:
            filter_params: フィルタ条件

        Returns:
            クエリ文字列（例: "?species=犬&location=高知"）
        """
        if not filter_params:
            return ""

        # None でない値のみ含める
        params = {k: v for k, v in filter_params.items() if v is not None}
        if not params:
            return ""

        query_parts = [f"{k}={v}" for k, v in params.items()]
        return "?" + "&".join(query_parts)

    def _add_rss_item(self, fg: PyFeedGenerator, animal: AnimalData) -> None:
        """
        RSS アイテムを追加

        Args:
            fg: FeedGenerator インスタンス
            animal: 動物データ
        """
        fe = fg.add_entry()

        # タイトル: 種別 - 地域
        title = f"{animal.species} - {animal.location}"
        fe.title(title)

        # リンク: source_url
        fe.link(href=str(animal.source_url))

        # 説明: 詳細情報
        description = self._build_description(animal)
        fe.description(description)

        # pubDate: shelter_date
        # datetime に変換（date -> datetime、UTC タイムゾーン付き）
        pub_date = datetime.combine(animal.shelter_date, datetime.min.time(), tzinfo=UTC)
        fe.pubDate(pub_date)

        # GUID: source_url の MD5 ハッシュ
        guid = self._generate_guid(str(animal.source_url))
        fe.guid(guid, permalink=False)

        # 画像がある場合、enclosure タグを追加
        if animal.image_urls and len(animal.image_urls) > 0:
            image_url = str(animal.image_urls[0])
            # enclosure タグ: URL, type, length
            # length は不明なので 0 を設定
            fe.enclosure(url=image_url, type="image/jpeg", length="0")

    def _add_atom_entry(self, fg: PyFeedGenerator, animal: AnimalData) -> None:
        """
        Atom エントリを追加

        Args:
            fg: FeedGenerator インスタンス
            animal: 動物データ
        """
        fe = fg.add_entry()

        # タイトル: 種別 - 地域
        title = f"{animal.species} - {animal.location}"
        fe.title(title)

        # リンク: source_url
        fe.link(href=str(animal.source_url))

        # summary: 詳細情報
        summary = self._build_description(animal)
        fe.summary(summary)

        # id: tag URI スキーム
        guid = self._generate_guid(str(animal.source_url))
        now = datetime.now(UTC)
        entry_id = f"tag:example.com,{now.strftime('%Y-%m-%d')}:/animals/{guid}"
        fe.id(entry_id)

        # published: shelter_date
        published = datetime.combine(animal.shelter_date, datetime.min.time(), tzinfo=UTC)
        fe.published(published)

        # updated: status_changed_at または現在時刻
        if animal.status_changed_at:
            # status_changed_at にタイムゾーンがない場合は UTC と仮定
            updated = (
                animal.status_changed_at.replace(tzinfo=UTC)
                if animal.status_changed_at.tzinfo is None
                else animal.status_changed_at
            )
        else:
            updated = now
        fe.updated(updated)

        # 画像がある場合、link rel="enclosure" を追加
        if animal.image_urls and len(animal.image_urls) > 0:
            image_url = str(animal.image_urls[0])
            fe.link(href=image_url, rel="enclosure", type="image/jpeg")

    def _build_description(self, animal: AnimalData) -> str:
        """
        動物データから説明文を生成

        Args:
            animal: 動物データ

        Returns:
            説明文
        """
        parts = [
            f"種別: {animal.species}",
            f"性別: {animal.sex}",
        ]

        if animal.age_months is not None:
            parts.append(f"推定年齢: {animal.age_months}ヶ月")
        if animal.color:
            parts.append(f"毛色: {animal.color}")
        if animal.size:
            parts.append(f"体格: {animal.size}")

        parts.append(f"収容場所: {animal.location}")

        if animal.phone:
            parts.append(f"電話番号: {animal.phone}")

        return "、".join(parts)

    def _generate_guid(self, source_url: str) -> str:
        """
        source_url から GUID を生成（MD5 ハッシュ）

        Args:
            source_url: 元ページの URL

        Returns:
            MD5 ハッシュ値（32文字の16進数文字列）
        """
        return hashlib.md5(source_url.encode()).hexdigest()
