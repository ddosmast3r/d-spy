"""Забор отзывов со страницы организации на Яндекс.Картах.

Отзывы отдаются прямо в HTML, внутри <script type="application/json" class="state-view">.
Ни капча, ни исполнение JS не нужны.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx

from config import USER_AGENT, Org

_STATE_RE = re.compile(
    r'<script type="application/json" class="state-view">(.*?)</script>', re.S
)


@dataclass(frozen=True)
class Review:
    review_id: str
    org_id: str
    author: str
    rating: int | None
    text: str
    updated: datetime | None

    @property
    def stars(self) -> str:
        if not self.rating:
            return "без оценки"
        return "★" * self.rating + "☆" * (5 - self.rating)


@dataclass
class Meta:
    rating: float | None = None
    rating_count: int | None = None
    review_count: int | None = None
    aspects: list[dict] = field(default_factory=list)


def _walk(node, out: list[dict], key_test) -> None:
    if isinstance(node, dict):
        if key_test(node):
            out.append(node)
            return
        for value in node.values():
            _walk(value, out, key_test)
    elif isinstance(node, list):
        for value in node:
            _walk(value, out, key_test)


def _parse_time(raw) -> datetime | None:
    if not raw:
        return None
    if isinstance(raw, (int, float)):
        return datetime.fromtimestamp(raw / 1000, tz=timezone.utc)
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


def _extract_meta(state: dict) -> Meta:
    meta = Meta()

    rating_blocks: list[dict] = []
    _walk(state, rating_blocks, lambda d: "ratingValue" in d and "reviewCount" in d)
    if rating_blocks:
        block = rating_blocks[0]
        meta.rating = round(float(block.get("ratingValue")), 1)
        meta.rating_count = block.get("ratingCount")
        meta.review_count = block.get("reviewCount")

    aspect_blocks: list[dict] = []
    _walk(state, aspect_blocks, lambda d: "aspects" in d and isinstance(d.get("aspects"), list))
    if aspect_blocks:
        meta.aspects = aspect_blocks[0]["aspects"]

    return meta


def fetch(org: Org, client: httpx.Client) -> tuple[list[Review], Meta]:
    response = client.get(
        org.reviews_url,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "ru,en;q=0.9"},
        follow_redirects=True,
        timeout=30,
    )
    response.raise_for_status()

    match = _STATE_RE.search(response.text)
    if not match:
        raise RuntimeError(
            f"{org.title}: не найден state-view. Яндекс поменял вёрстку или показал капчу."
        )
    state = json.loads(match.group(1))

    raw: list[dict] = []
    _walk(state, raw, lambda d: "reviewId" in d and "text" in d and "author" in d)

    reviews = []
    for item in raw:
        if item.get("businessId") and item["businessId"] != org.org_id:
            continue
        reviews.append(
            Review(
                review_id=item["reviewId"],
                org_id=org.org_id,
                author=(item.get("author") or {}).get("name") or "Аноним",
                rating=item.get("rating"),
                text=(item.get("text") or "").strip(),
                updated=_parse_time(item.get("updatedTime") or item.get("createdTime")),
            )
        )

    reviews.sort(key=lambda r: r.updated or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return reviews, _extract_meta(state)
