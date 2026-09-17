"""掲載位置の仮想 URL を個体ごとの安定キーへ付け替える (T413)

1 ページに複数頭が載るサイトの adapter は、個体を `<list_url>#row=N` のような
掲載位置の仮想 URL で区別している。掲載順がずれると同じ URL に別の子が入り、
URL 再利用検知 (T138) による退避+再挿入か、species/sex/breed が同じ別の子の
無警告の上書きになる。`#pdf=<ファイル名>&row=N` は日付入り PDF の差し替えで
全員の URL が変わり、差し替えのたびに id と first_seen_at がリセットされる。

収集直後に、管理番号 → 先頭画像のファイル名の順で個体のキーを作り、ページ内で
一意なら `<ページ URL>#animal=<キー>` へ付け替える。T066 (香川・茨城の PDF) と
T135 (徳島) が adapter ごとに入れた `#animal=<安定キー>` と同じ形にそろえる。
キーが無い子やページ内でキーが重なる子は区別の手がかりが無いため、位置の URL のまま残す。

同じファイル名の画像を時期をずらして別の子に使い回すサイトでは、同じ URL に別の子が
入りうる。これは位置 URL で同じ掲載位置に別の子が入るのと同じ状況で、save_animal の
識別判定 (T138) が見る。同じページに同名の画像が同時に並ぶときは一意にならないので
付け替えない。「画像なし」系の共通画像はそもそもキーに使わない。
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Sequence
from urllib.parse import quote, unquote, urlsplit

from pydantic import HttpUrl, TypeAdapter

from .models import AnimalData

# 掲載位置で個体を区別している仮想 URL の fragment
_POSITIONAL_FRAGMENT = re.compile(r"(?:row|h3)=\d+|pdf=[^&#]+&row=\d+")
# NFKC では "-" にならないハイフン類 (U+2010〜U+2015, U+2212)
_HYPHENS = str.maketrans(dict.fromkeys("‐‑‒–—―−", "-"))
# ハイフン代わりの長音符 (「7西ーD0092」「９ー２」)。かな・カナの直後は本来の長音なので残す
_PROLONGED_AS_HYPHEN = re.compile(r"(?<![぀-ヿ])ー")
# 個体を表さない「画像なし」系の共通画像
_PLACEHOLDER_IMAGE = re.compile(
    r"no[-_]?(?:image|photo|img)|now[-_]?printing|coming[-_]?soon|dummy", re.IGNORECASE
)
_HTTP_URL: TypeAdapter[HttpUrl] = TypeAdapter(HttpUrl)


def page_url(url: str) -> str:
    """fragment を除いたページの URL"""
    return url.split("#", 1)[0]


def is_positional_virtual_url(url: str) -> bool:
    """掲載位置で個体を区別している仮想 URL (`#row=N` / `#h3=N` / `#pdf=…&row=N`) か"""
    _, sep, fragment = url.partition("#")
    return bool(sep) and _POSITIONAL_FRAGMENT.fullmatch(fragment) is not None


def management_key(management_number: str | None) -> str | None:
    """管理番号をキーの形へ正規化する (全角/半角・ハイフン類・空白の揺れをそろえる)"""
    if not management_number:
        return None
    normalized = unicodedata.normalize("NFKC", management_number).translate(_HYPHENS)
    normalized = _PROLONGED_AS_HYPHEN.sub("-", normalized)
    return re.sub(r"\s+", "", normalized) or None


def image_key(image_urls: Sequence[HttpUrl | str]) -> str | None:
    """先頭画像のファイル名 (クエリを除き % エンコードを戻したもの)。使えなければ None"""
    if not image_urls:
        return None
    name = unquote(urlsplit(str(image_urls[0])).path.rsplit("/", 1)[-1])
    if not name or _PLACEHOLDER_IMAGE.search(name):
        return None
    return name


def individual_keys_match(
    management_a: str | None,
    images_a: Sequence[HttpUrl | str],
    management_b: str | None,
    images_b: Sequence[HttpUrl | str],
) -> bool:
    """管理番号 (両方にあるとき) か、先頭画像のファイル名で同じ子を指しているか"""
    mgmt_a, mgmt_b = management_key(management_a), management_key(management_b)
    if mgmt_a and mgmt_b:
        return mgmt_a == mgmt_b
    img_a, img_b = image_key(images_a), image_key(images_b)
    return img_a is not None and img_a == img_b


def stabilize_virtual_urls(animals: Sequence[AnimalData]) -> list[AnimalData]:
    """掲載位置の仮想 URL を、ページ内で一意な個体キーの URL へ付け替えたリストを返す

    入力は変更しない。付け替えない子は同じオブジェクトのまま返す。
    """
    urls = [str(animal.source_url) for animal in animals]
    keys: dict[int, str] = {}
    for i, (animal, url) in enumerate(zip(animals, urls, strict=True)):
        if not is_positional_virtual_url(url):
            continue
        key = management_key(animal.management_number) or image_key(animal.image_urls)
        if key:
            keys[i] = key

    per_page = Counter((page_url(urls[i]), key) for i, key in keys.items())
    taken = set(urls)
    result = list(animals)
    for i, key in keys.items():
        page = page_url(urls[i])
        if per_page[(page, key)] != 1:
            continue
        new_url = _HTTP_URL.validate_python(f"{page}#animal={quote(key, safe='')}")
        if str(new_url) in taken:
            # adapter が付けた安定キーの URL など、同じ回の別の子の URL と重なる
            continue
        result[i] = animals[i].model_copy(update={"source_url": new_url})
    return result
