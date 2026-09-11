"""
AnimalRepository - データアクセス層

Repository パターンによる動物データのCRUD操作を提供します。
Pydantic AnimalData と SQLAlchemy Animal モデルの変換を担当します。
"""

import logging
from datetime import UTC, date, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.data_collector.domain.models import AnimalData, AnimalStatus
from src.data_collector.domain.status_transition import (
    StatusTransitionValidator,
)
from src.data_collector.infrastructure.database.models import Animal, AnimalStatusHistory

logger = logging.getLogger(__name__)


def _escape_like(value: str) -> str:
    r"""LIKE/ILIKE のワイルドカード (\\ % _) をエスケープし、ユーザー入力を
    リテラルな部分一致として扱う。``escape="\\"`` と併用する。

    これが無いと ``location=%`` で全件マッチ、``q=A_B`` の ``_`` が任意 1 文字
    に化ける。SQLi は SQLAlchemy のバインド変数で防御されているため、
    本関数は意味論的正しさ (部分一致のリテラル化) を担う。
    """
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# カタカナ ァ..ン (U+30A1..U+30F3) と ひらがな ぁ..ん (U+3041..U+3093) は
# コードポイントが 0x60 オフセットで規則対応する。SQLite には translate() が無いため
# (PostgreSQL にはある)、保存値を SQL で正規化せず「検索語を両仮名へ展開して OR」する。
_KATA_TO_HIRA = {c: c - 0x60 for c in range(0x30A1, 0x30F4)}
_HIRA_TO_KATA = {c: c + 0x60 for c in range(0x3041, 0x3094)}


def _kana_search_variants(q: str) -> list[str]:
    """検索語をカタカナ/ひらがな両方へ正規化した重複なし候補を返す。

    品種(breed)のカナ表記揺れ（例: 「チワワ」と「ちわわ」）を吸収するため、
    元の語・全ひらがな化・全カタカナ化の3候補で OR 検索する。漢字↔読み変換は非対象。
    """
    variants: list[str] = []
    for v in (q, q.translate(_KATA_TO_HIRA), q.translate(_HIRA_TO_KATA)):
        if v not in variants:
            variants.append(v)
    return variants


class NotFoundError(Exception):
    """リソースが見つからない場合のエラー"""

    def __init__(self, resource: str, resource_id: int):
        self.resource = resource
        self.resource_id = resource_id
        super().__init__(f"{resource} with id {resource_id} not found")


class AnimalRepository:
    """
    動物データリポジトリ

    データアクセスロジックをカプセル化し、
    Pydantic モデルと SQLAlchemy モデルの変換を提供します。
    """

    def __init__(self, session: AsyncSession):
        """
        AnimalRepository を初期化

        Args:
            session: データベースセッション
        """
        self.session = session
        # T138: URL 再利用 (同一 source_url が別個体を指すようになる) を検知して
        # 旧レコードをアーカイブした回数。呼び出し元 (CollectorService) が
        # run summary に「URL再利用検知 N件」として出すために参照する。
        self.url_reuse_count: int = 0

    def _to_orm(self, animal_data: AnimalData) -> Animal:
        """
        Pydantic AnimalData を SQLAlchemy Animal に変換

        Args:
            animal_data: Pydantic 動物データ

        Returns:
            Animal: SQLAlchemy ORM モデル
        """
        return Animal(
            species=animal_data.species,
            sex=animal_data.sex,
            age_months=animal_data.age_months,
            color=animal_data.color,
            size=animal_data.size,
            shelter_date=animal_data.shelter_date,
            location=animal_data.location,
            prefecture=animal_data.prefecture,
            phone=animal_data.phone,
            image_urls=[str(url) for url in animal_data.image_urls],
            source_url=str(animal_data.source_url),
            category=animal_data.category,
            # 個体識別フィールド
            breed=animal_data.breed,
            name=animal_data.name,
            management_number=animal_data.management_number,
            description=animal_data.description,
            # 拡張フィールド
            status=animal_data.status.value if animal_data.status else "sheltered",
            status_changed_at=animal_data.status_changed_at,
            outcome_date=animal_data.outcome_date,
            local_image_paths=animal_data.local_image_paths or [],
            # T159: _to_orm は新規行の生成にのみ使われる (通常 INSERT 経路と
            # URL 再利用検知による archive+再挿入経路の両方)。呼び出し元の
            # animal_data.first_seen_at は無視し、常に現在時刻を初回収集日時
            # として設定する。
            first_seen_at=datetime.now(UTC),
        )

    @staticmethod
    def _fingerprint(
        *,
        species: str | None,
        sex: str | None,
        breed: str | None,
        shelter_date: date | None,
    ) -> tuple[str, ...] | None:
        """species/sex/breed/shelter_date から個体フィンガープリントを算出する。

        全フィールドが揃っている場合のみ算出できる (どれか欠ければ None)。
        """
        if species and sex and breed and shelter_date:
            return (species, sex, breed, str(shelter_date))
        return None

    @classmethod
    def _identity_verdict(
        cls,
        *,
        existing_management_number: str | None,
        existing_species: str | None,
        existing_sex: str | None,
        existing_breed: str | None,
        existing_shelter_date: date | None,
        new_management_number: str | None,
        new_species: str | None,
        new_sex: str | None,
        new_breed: str | None,
        new_shelter_date: date | None,
    ) -> str:
        """既存個体と新規データが同一個体かどうかを判定する (T138: URL 再利用検知用)。

        岡山市等で detail ページの source_url が別個体に再利用される実例が
        確認された (1D2026049 → 1D2025093)。同一 source_url でも個体が入れ替わって
        いれば「別個体」とみなし、上書きせずアーカイブする。

        判定方針 (レビュー指摘 F-03 対応):
        - management_number は「両側にある場合だけ」優先的に比較する。
          片側だけ management_number が有る/無い状態 (抽出が収集回ごとに
          ぶれるサイトで起こりうる) を「別個体」と誤判定しないため、
          mgmt の有無の非対称性そのものでは判定材料にしない。
        - management_number で比較できない場合は species/sex/breed/shelter_date
          のフィンガープリントで比較する (両側で算出できる場合のみ)。
        - どちらの方法でも比較材料が揃わない場合は "unknown" (識別不能) を返す。

        Returns:
            "same": 同一個体とみなせる (通常の更新へ)
            "different": 別個体とみなせる (アーカイブ+新規挿入へ)
            "unknown": 判定材料が無い (従来通り上書きするが警告ログを残す)
        """
        if existing_management_number and new_management_number:
            return "same" if existing_management_number == new_management_number else "different"

        existing_fp = cls._fingerprint(
            species=existing_species,
            sex=existing_sex,
            breed=existing_breed,
            shelter_date=existing_shelter_date,
        )
        new_fp = cls._fingerprint(
            species=new_species, sex=new_sex, breed=new_breed, shelter_date=new_shelter_date
        )
        if existing_fp and new_fp:
            return "same" if existing_fp == new_fp else "different"

        return "unknown"

    async def _archive_and_replace(
        self,
        existing_animal: Animal,
        animal_data: AnimalData,
        source_site: str | None,
    ) -> Animal:
        """既存レコードをアーカイブしてから新規レコードとして挿入する (T138)。

        URL 再利用 (同一 source_url が別個体を指すようになった) を検知した際に
        呼ぶ。CLAUDE.md の「データを失わない」原則に従い、旧レコードは
        upsert で上書きせず `AnimalArchive` へ退避してから削除し、新規個体は
        別行として挿入する。

        Returns:
            Animal: 新規挿入後の ORM モデル (id 採番済み)
        """
        # archive_repository は repository.py を import しているため、
        # モジュールトップレベルで逆 import すると循環 import になる。
        # メソッド内の遅延 import で回避する。
        from .archive_repository import ArchiveRepository

        archive_repo = ArchiveRepository(self.session)
        await archive_repo.insert_archive(existing_animal)
        await self.session.delete(existing_animal)
        await self.session.flush()

        self.url_reuse_count += 1
        logger.warning(
            "[URL再利用検知] source_url=%s は既存個体と異なる個体を指しています。"
            "旧レコード (id=%s) をアーカイブし、新規個体として登録します。",
            animal_data.source_url,
            existing_animal.id,
        )

        orm_animal = self._to_orm(animal_data)
        self.session.add(orm_animal)
        if source_site is not None:
            orm_animal.source_site = source_site
        orm_animal.last_collected_at = datetime.now(UTC)

        await self.session.commit()
        await self.session.refresh(orm_animal)
        return orm_animal

    def _to_pydantic(self, orm_animal: Animal) -> AnimalData:
        """
        SQLAlchemy Animal を Pydantic AnimalData に変換

        Args:
            orm_animal: SQLAlchemy ORM モデル

        Returns:
            AnimalData: Pydantic 動物データ
        """
        return AnimalData(
            species=orm_animal.species,
            sex=orm_animal.sex,
            age_months=orm_animal.age_months,
            color=orm_animal.color,
            size=orm_animal.size,
            shelter_date=orm_animal.shelter_date,
            location=orm_animal.location,
            prefecture=orm_animal.prefecture,
            phone=orm_animal.phone,
            image_urls=orm_animal.image_urls or [],
            source_url=orm_animal.source_url,
            category=orm_animal.category,
            # 個体識別フィールド
            breed=orm_animal.breed,
            name=orm_animal.name,
            management_number=orm_animal.management_number,
            description=orm_animal.description,
            # 拡張フィールド
            status=AnimalStatus(orm_animal.status) if orm_animal.status else None,
            status_changed_at=orm_animal.status_changed_at,
            outcome_date=orm_animal.outcome_date,
            local_image_paths=orm_animal.local_image_paths or None,
            last_collected_at=orm_animal.last_collected_at,
            first_seen_at=orm_animal.first_seen_at,
        )

    async def save_animal(
        self, animal_data: AnimalData, source_site: str | None = None
    ) -> AnimalData:
        """
        動物データを保存（upsert）

        source_url が既存の場合は更新、新規の場合は挿入します。

        Args:
            animal_data: 保存する動物データ
            source_site: 収集元サイト識別名 (SiteConfig.name)。消滅同期削除のスコープ
                に使う。収集経路から渡す。None のときは既存値を変更しない。

        Returns:
            AnimalData: 保存後のデータ（IDを含む）

        Raises:
            DatabaseError: データベース接続エラー
            ValidationError: バリデーションエラー
        """
        # 既存レコードを検索。UNIQUE 制約撤廃 (T138) 後は理論上複数行ヒットしうる
        # ため limit(1) で「最初の1件」に絞る (F-02 と同じ理由)。
        stmt = select(Animal).where(Animal.source_url == str(animal_data.source_url)).limit(1)
        result = await self.session.execute(stmt)
        existing_animal = result.scalar_one_or_none()

        # T138: URL 再利用検知。同一 source_url でも個体が入れ替わっていれば
        # 「別個体」とみなし、上書きせずアーカイブしてから新規行を挿入する。
        if existing_animal:
            verdict = self._identity_verdict(
                existing_management_number=existing_animal.management_number,
                existing_species=existing_animal.species,
                existing_sex=existing_animal.sex,
                existing_breed=existing_animal.breed,
                existing_shelter_date=existing_animal.shelter_date,
                new_management_number=animal_data.management_number,
                new_species=animal_data.species,
                new_sex=animal_data.sex,
                new_breed=animal_data.breed,
                new_shelter_date=animal_data.shelter_date,
            )
            if verdict == "unknown":
                # 判定材料 (両側 management_number、または両側フィンガープリント)
                # が揃わない場合は、URL 再利用かどうか判定できないため従来通り
                # 上書きする。ただし無警告のまま別個体を上書きしている可能性を
                # 握り潰さないよう必ずログに残す。
                logger.warning(
                    "[URL再利用検知不能] source_url=%s の個体識別情報が不足しており "
                    "別個体かどうか判定できないため、従来通り上書きします "
                    "(既存 management_number=%s, 新規 management_number=%s)",
                    animal_data.source_url,
                    existing_animal.management_number,
                    animal_data.management_number,
                )
            elif verdict == "different":
                orm_animal = await self._archive_and_replace(
                    existing_animal, animal_data, source_site
                )
                return self._to_pydantic(orm_animal)
            # else: 同一個体 (identity 一致) なので通常の更新へ続行

        if existing_animal:
            # 既存レコードを更新
            existing_animal.species = animal_data.species
            existing_animal.sex = animal_data.sex
            existing_animal.age_months = animal_data.age_months
            existing_animal.color = animal_data.color
            existing_animal.size = animal_data.size
            # shelter_date: 実サイト由来の日付は常に反映する。推定値 (収集日
            # フォールバック/未来日クランプ) は「初回収集日」の意味しか持たない
            # ため、既存レコードの値を毎日の再収集で上書きしない。上書きすると
            # 日付の無いサイトの個体が毎日「昨日収容」へロールし続ける (T055)。
            if not (animal_data.shelter_date_estimated and existing_animal.shelter_date):
                existing_animal.shelter_date = animal_data.shelter_date
            existing_animal.location = animal_data.location
            existing_animal.prefecture = animal_data.prefecture
            existing_animal.phone = animal_data.phone
            existing_animal.image_urls = [str(url) for url in animal_data.image_urls]
            existing_animal.category = animal_data.category
            # 個体識別フィールドは category 同様に無条件上書き
            # (ソースから値が消えたら None で上書きし、古い値を残留させない)
            existing_animal.breed = animal_data.breed
            existing_animal.name = animal_data.name
            existing_animal.management_number = animal_data.management_number
            existing_animal.description = animal_data.description
            # 拡張フィールドは明示的に設定された場合のみ更新
            if animal_data.status is not None:
                existing_animal.status = animal_data.status.value
            if animal_data.status_changed_at is not None:
                existing_animal.status_changed_at = animal_data.status_changed_at
            if animal_data.outcome_date is not None:
                existing_animal.outcome_date = animal_data.outcome_date
            if animal_data.local_image_paths is not None:
                existing_animal.local_image_paths = animal_data.local_image_paths
            orm_animal = existing_animal
        else:
            # 新規レコードを挿入
            orm_animal = self._to_orm(animal_data)
            self.session.add(orm_animal)

        # 収集経路から渡されたサイト識別名を記録（消滅同期削除のスコープ用）
        if source_site is not None:
            orm_animal.source_site = source_site

        # 収集(クロール)が成功してここに来た時点の時刻を記録。
        # animal_data の値は使わず常に現在時刻で上書きする(「いつ確認されたか」
        # を示す値なので、呼び出し元が古い値を渡しても意味を持たせない)。
        orm_animal.last_collected_at = datetime.now(UTC)

        await self.session.commit()
        await self.session.refresh(orm_animal)

        return self._to_pydantic(orm_animal)

    async def prune_disappeared(
        self,
        source_site: str,
        seen_source_urls: set[str],
        *,
        allow_full_prune: bool = False,
    ) -> int:
        """指定サイトで今回の収集に出てこなかった動物（= ソースから消えた）を削除する。

        ソースに掲載が無い＝もういない、とみなしてライブから外し、ポータルを
        ソースと同期させる。

        Args:
            source_site: 対象サイトの識別名 (SiteConfig.name)
            seen_source_urls: 今回の収集で確認できた source_url の集合
            allow_full_prune: seen_source_urls が空でも、対象サイトの残存
                レコードを全削除してよいかの明示フラグ (T106 で追加)。デフォルト
                False = 既存の安全弁を維持 (何もしない)。呼び出し元
                (CollectorService._should_force_empty_prune) が
                「連続 N 回以上 0 件、かつ zero_count_verifier が確定 NONE」の
                ときだけ True を渡す。それ以外 (adapter 破損の可能性がある通常の
                0 件 run) は False のままにして誤削除を防ぐ。

        Returns:
            削除した件数

        安全策:
        - seen_source_urls が空（収集0件 / adapter 破損の可能性）かつ
          allow_full_prune=False（既定）のときは、サイト全体を誤って消さない
          よう **何もしない**。この既定の安全弁は allow_full_prune の追加で
          弱めていない。
        - source_site でスコープするため、他サイトや未タグ(NULL)の行は消さない。
        - 万一まだ在籍する子を誤って消しても、次回収集で再登録されるため復旧可能。
        """
        if not seen_source_urls and not allow_full_prune:
            return 0
        stmt = delete(Animal).where(Animal.source_site == source_site)
        if seen_source_urls:
            # notin_() の空集合渡し (allow_full_prune=True かつ 0 件収集時) は
            # SQLAlchemy バージョン依存の挙動になりうるため、意図を明示するために
            # 空でないときだけ notin_ フィルタを付ける (空のときは source_site
            # 一致行を無条件で全削除する設計)。
            stmt = stmt.where(Animal.source_url.notin_(seen_source_urls))
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount or 0

    async def get_animal_by_id(self, animal_id: int) -> AnimalData | None:
        """
        IDで動物データを取得

        Args:
            animal_id: 動物ID

        Returns:
            Optional[AnimalData]: 動物データ、存在しない場合は None
        """
        stmt = select(Animal).where(Animal.id == animal_id)
        result = await self.session.execute(stmt)
        orm_animal = result.scalar_one_or_none()

        if orm_animal:
            return self._to_pydantic(orm_animal)
        return None

    async def get_animal_id_by_source_url(self, source_url: str) -> int | None:
        """
        source_url に一致する動物の DB id を取得

        AnimalData (pydantic) は id を持たないため、id が必要な呼び出し元
        (SNS 投稿の oneco 詳細ページリンク生成等) 向けに用意する専用ルックアップ。

        Args:
            source_url: 元ページURL

        Returns:
            Optional[int]: 動物ID、存在しない場合は None

        Note:
            T138 で `Animal.source_url` の DB レベル UNIQUE 制約を撤廃したため、
            理論上は同一 source_url が複数行にヒットしうる (アプリケーション層の
            save_animal が通常運用では active 行を高々1件に保つが、それはDB
            制約による保証ではない)。`scalar_one_or_none()` は複数行ヒットで
            `MultipleResultsFound` を送出するため、レビュー指摘 (F-02) を受けて
            `.first()` 相当の「最初の1件」取得に変更し、将来別の書き込み経路が
            増えても静かに壊れないようにする。
        """
        stmt = select(Animal.id).where(Animal.source_url == source_url).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_animals_first_seen_between(
        self,
        *,
        start: datetime,
        end: datetime,
    ) -> list[AnimalData]:
        """first_seen_at が [start, end) の範囲にある公開中の動物を返す (T160)。

        SNS 日次まとめが「前日の新着」を集計するための専用クエリ。
        list_animals() の shelter_date フィルタと違い first_seen_at (T159) で
        範囲検索する点が異なるため別メソッドとして独立させる。

        Args:
            start: 範囲開始 (timezone-aware, 含む)
            end: 範囲終了 (timezone-aware, 含まない)

        Returns:
            list[AnimalData]: 対象動物一覧 (件数上限なし。日次まとめの母集団は
                通常数十〜数百件程度で全国日次収集の規模に収まるため)
        """
        stmt = select(Animal).where(
            Animal.first_seen_at >= start,
            Animal.first_seen_at < end,
            Animal.status == AnimalStatus.SHELTERED.value,
        )
        result = await self.session.execute(stmt)
        animals = result.scalars().all()
        return [self._to_pydantic(a) for a in animals]

    async def list_animals(
        self,
        species: str | None = None,
        sex: str | None = None,
        location: str | None = None,
        prefecture: str | None = None,
        category: str | None = None,
        shelter_date_from: date | None = None,
        shelter_date_to: date | None = None,
        status: AnimalStatus | None = None,
        q: str | None = None,
        include_non_public: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AnimalData], int]:
        """
        動物データをフィルタリング・ページネーションして取得

        Args:
            species: 動物種別フィルタ
            sex: 性別フィルタ
            location: 場所フィルタ（部分一致）
            category: カテゴリフィルタ ('adoption' または 'lost')
            shelter_date_from: 収容日開始
            shelter_date_to: 収容日終了
            status: ステータスフィルタ
            limit: 取得件数（最大1000、デフォルト50）
            offset: オフセット（デフォルト0）

        Returns:
            Tuple[List[AnimalData], int]: (動物データリスト, 総件数)
        """
        # クエリベースを作成
        stmt = select(Animal)

        # フィルタ適用
        filters = []
        if species:
            filters.append(Animal.species == species)
        if sex:
            filters.append(Animal.sex == sex)
        if location:
            filters.append(Animal.location.like(f"%{_escape_like(location)}%", escape="\\"))
        if prefecture:
            filters.append(Animal.prefecture == prefecture)
        if category:
            filters.append(Animal.category == category)
        if shelter_date_from:
            filters.append(Animal.shelter_date >= shelter_date_from)
        if shelter_date_to:
            filters.append(Animal.shelter_date <= shelter_date_to)
        if status:
            filters.append(Animal.status == status.value)
        if not include_non_public:
            # 死亡(deceased)個体は公開対象から除外する（データ境界での強制）。
            # NULL status の行を誤って落とさないよう is_distinct_from で null-safe に比較。
            filters.append(Animal.status.is_distinct_from(AnimalStatus.DECEASED.value))
        if q:
            # キーワード検索: 複数フィールドを OR で部分一致（ILIKE）
            # 「茶白」「人懐っこい」「子犬」など自由テキストで
            # species/color/size/location/prefecture を横断検索
            from sqlalchemy import or_

            keyword = f"%{_escape_like(q)}%"
            # 品種はカタカナ↔ひらがなの揺れを吸収するため検索語を両仮名へ展開して照合
            breed_clauses = [
                Animal.breed.ilike(f"%{_escape_like(v)}%", escape="\\")
                for v in _kana_search_variants(q)
            ]
            filters.append(
                or_(
                    Animal.species.ilike(keyword, escape="\\"),
                    Animal.color.ilike(keyword, escape="\\"),
                    Animal.size.ilike(keyword, escape="\\"),
                    Animal.location.ilike(keyword, escape="\\"),
                    Animal.prefecture.ilike(keyword, escape="\\"),
                    *breed_clauses,
                )
            )

        if filters:
            stmt = stmt.where(*filters)

        # 総件数を取得
        count_stmt = select(func.count()).select_from(stmt.subquery())
        count_result = await self.session.execute(count_stmt)
        total_count = count_result.scalar()

        # ソートとページネーション適用
        stmt = stmt.order_by(Animal.shelter_date.desc())
        stmt = stmt.limit(limit).offset(offset)

        # データ取得
        result = await self.session.execute(stmt)
        orm_animals = result.scalars().all()

        # Pydantic モデルに変換
        animal_data_list = [self._to_pydantic(a) for a in orm_animals]

        return animal_data_list, total_count

    async def list_animals_orm(
        self,
        species: str | None = None,
        sex: str | None = None,
        location: str | None = None,
        prefecture: str | None = None,
        category: str | None = None,
        shelter_date_from: date | None = None,
        shelter_date_to: date | None = None,
        status: AnimalStatus | None = None,
        q: str | None = None,
        include_non_public: bool = False,
        sort: str = "newest",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Animal], int]:
        """
        動物データをフィルタリング・ページネーションして取得（ORMモデルとして）

        Args:
            species: 動物種別フィルタ
            sex: 性別フィルタ
            location: 場所フィルタ（部分一致）
            category: カテゴリフィルタ ('adoption' または 'lost')
            shelter_date_from: 収容日開始
            shelter_date_to: 収容日終了
            status: ステータスフィルタ
            limit: 取得件数（最大1000、デフォルト50）
            offset: オフセット（デフォルト0）

        Returns:
            Tuple[List[Animal], int]: (動物ORMモデルリスト, 総件数)
        """
        # クエリベースを作成
        stmt = select(Animal)

        # フィルタ適用
        filters = []
        if species:
            filters.append(Animal.species == species)
        if sex:
            filters.append(Animal.sex == sex)
        if location:
            filters.append(Animal.location.like(f"%{_escape_like(location)}%", escape="\\"))
        if prefecture:
            filters.append(Animal.prefecture == prefecture)
        if category:
            filters.append(Animal.category == category)
        if shelter_date_from:
            filters.append(Animal.shelter_date >= shelter_date_from)
        if shelter_date_to:
            filters.append(Animal.shelter_date <= shelter_date_to)
        if status:
            filters.append(Animal.status == status.value)
        if not include_non_public:
            # 死亡(deceased)個体は公開対象から除外する（データ境界での強制）。
            # NULL status の行を誤って落とさないよう is_distinct_from で null-safe に比較。
            filters.append(Animal.status.is_distinct_from(AnimalStatus.DECEASED.value))
        if q:
            from sqlalchemy import or_

            keyword = f"%{_escape_like(q)}%"
            # 品種はカタカナ↔ひらがなの揺れを吸収するため検索語を両仮名へ展開して照合
            breed_clauses = [
                Animal.breed.ilike(f"%{_escape_like(v)}%", escape="\\")
                for v in _kana_search_variants(q)
            ]
            filters.append(
                or_(
                    Animal.species.ilike(keyword, escape="\\"),
                    Animal.color.ilike(keyword, escape="\\"),
                    Animal.size.ilike(keyword, escape="\\"),
                    Animal.location.ilike(keyword, escape="\\"),
                    Animal.prefecture.ilike(keyword, escape="\\"),
                    *breed_clauses,
                )
            )

        if filters:
            stmt = stmt.where(*filters)

        # 総件数を取得
        count_stmt = select(func.count()).select_from(stmt.subquery())
        count_result = await self.session.execute(count_stmt)
        total_count = count_result.scalar()

        # ソートとページネーション適用（id を tie-breaker にして安定化）
        if sort == "oldest":
            stmt = stmt.order_by(Animal.shelter_date.asc(), Animal.id.asc())
        else:
            stmt = stmt.order_by(Animal.shelter_date.desc(), Animal.id.desc())
        stmt = stmt.limit(limit).offset(offset)

        # データ取得
        result = await self.session.execute(stmt)
        orm_animals = result.scalars().all()

        return orm_animals, total_count

    async def get_animal_by_id_orm(
        self, animal_id: int, include_non_public: bool = False
    ) -> Animal | None:
        """
        IDで動物データを取得（ORMモデルとして）

        Args:
            animal_id: 動物ID
            include_non_public: True なら死亡(deceased)個体も返す（内部の status 更新・
                画像パス更新・削除フロー用）。False（既定/公開）は deceased を None 扱いに
                して、ルート層で 404 を返させる。

        Returns:
            Optional[Animal]: 動物ORMモデル、存在しない/非公開の場合は None
        """
        stmt = select(Animal).where(Animal.id == animal_id)
        if not include_non_public:
            stmt = stmt.where(Animal.status.is_distinct_from(AnimalStatus.DECEASED.value))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_status(
        self,
        animal_id: int,
        new_status: AnimalStatus,
        outcome_date: date | None = None,
        changed_by: str | None = None,
    ) -> AnimalData:
        """
        動物のステータスを更新

        トランザクション内でステータス更新とステータス履歴の記録を原子的に実行します。

        Args:
            animal_id: 動物ID
            new_status: 新しいステータス
            outcome_date: 成果日（adopted/returned の場合）
            changed_by: 変更者（オプション）

        Returns:
            AnimalData: 更新後のデータ

        Raises:
            StatusTransitionError: 不正なステータス遷移
            NotFoundError: 動物が存在しない
        """
        # 動物を取得
        # 内部管理フロー（status 更新・画像パス更新・削除）は deceased も対象にする。
        orm_animal = await self.get_animal_by_id_orm(animal_id, include_non_public=True)
        if orm_animal is None:
            raise NotFoundError("Animal", animal_id)

        # 現在のステータスを取得
        old_status = AnimalStatus(orm_animal.status)

        # ステータス遷移を検証
        validator = StatusTransitionValidator()
        validator.validate_transition(old_status, new_status)

        # ステータスを更新
        orm_animal.status = new_status.value
        orm_animal.status_changed_at = datetime.now(UTC)

        # outcome_date の設定（adopted/returned の場合）
        if outcome_date is not None:
            orm_animal.outcome_date = outcome_date
        elif new_status in (AnimalStatus.ADOPTED, AnimalStatus.RETURNED):
            # outcome_date が未指定の場合はステータス変更日を使用
            orm_animal.outcome_date = orm_animal.status_changed_at.date()

        # ステータス履歴を記録
        history = AnimalStatusHistory(
            animal_id=animal_id,
            old_status=old_status.value,
            new_status=new_status.value,
            changed_at=orm_animal.status_changed_at,
            changed_by=changed_by,
        )
        self.session.add(history)

        # コミット
        await self.session.commit()
        await self.session.refresh(orm_animal)

        return self._to_pydantic(orm_animal)

    async def list_animals_by_status(
        self,
        status: AnimalStatus,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AnimalData], int]:
        """
        ステータスで動物をフィルタリング

        Args:
            status: フィルタするステータス
            limit: 取得件数（デフォルト50）
            offset: オフセット（デフォルト0）

        Returns:
            Tuple[List[AnimalData], int]: (動物データリスト, 総件数)
        """
        return await self.list_animals(status=status, limit=limit, offset=offset)

    async def update_local_image_paths(
        self,
        animal_id: int,
        local_paths: list[str],
    ) -> AnimalData:
        """
        ローカル画像パスを更新

        Args:
            animal_id: 動物ID
            local_paths: ローカル画像パスのリスト

        Returns:
            AnimalData: 更新後のデータ

        Raises:
            NotFoundError: 動物が存在しない
        """
        # 動物を取得
        # 内部管理フロー（status 更新・画像パス更新・削除）は deceased も対象にする。
        orm_animal = await self.get_animal_by_id_orm(animal_id, include_non_public=True)
        if orm_animal is None:
            raise NotFoundError("Animal", animal_id)

        # ローカル画像パスを更新
        orm_animal.local_image_paths = local_paths

        # コミット
        await self.session.commit()
        await self.session.refresh(orm_animal)

        return self._to_pydantic(orm_animal)

    async def find_archivable_animals(
        self,
        retention_days: int = 180,
        limit: int = 1000,
    ) -> list[Animal]:
        """
        アーカイブ対象の動物を検索

        保持期間（デフォルト180日）を経過した adopted または returned ステータスの
        動物を返します。deceased はアーカイブ対象外です。

        Args:
            retention_days: 保持期間（日数、デフォルト180）
            limit: 取得件数（デフォルト1000）

        Returns:
            List[Animal]: アーカイブ対象の動物 ORM モデルリスト
        """
        from datetime import timedelta

        # 保持期限の計算
        cutoff_date = datetime.now(UTC) - timedelta(days=retention_days)

        # アーカイブ対象: adopted または returned で、status_changed_at が cutoff_date より前
        stmt = (
            select(Animal)
            .where(
                Animal.status.in_(["adopted", "returned"]),
                Animal.status_changed_at <= cutoff_date,
            )
            .order_by(Animal.status_changed_at)
            .limit(limit)
        )

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def delete_animal(self, animal_id: int) -> None:
        """
        動物レコードを削除

        Args:
            animal_id: 動物ID

        Raises:
            NotFoundError: 動物が存在しない
        """
        # 内部管理フロー（status 更新・画像パス更新・削除）は deceased も対象にする。
        orm_animal = await self.get_animal_by_id_orm(animal_id, include_non_public=True)
        if orm_animal is None:
            raise NotFoundError("Animal", animal_id)

        await self.session.delete(orm_animal)
        await self.session.commit()

    async def get_status_counts(self) -> dict:
        """
        ステータス別の動物件数を取得

        Returns:
            dict: {status: count} 形式のステータス別件数
        """
        stmt = select(Animal.status, func.count()).group_by(Animal.status)
        result = await self.session.execute(stmt)
        counts = {row[0]: row[1] for row in result.all()}
        return counts
