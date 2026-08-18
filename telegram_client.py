"""Telegram. Бот пишет ТОЛЬКО владельцу и слушает ТОЛЬКО его."""
from __future__ import annotations

import html

import httpx

from config import BOT_TOKEN, OWNER_CHAT_ID
from yandex_reviews import Meta, Review

API = f"https://api.telegram.org/bot{BOT_TOKEN}"
_MAX_LEN = 3500

BTN_CHECK = "🔄 Проверить сейчас"
BTN_STATS = "📊 Статистика"
BTN_LAST = "📝 Последние 5"
BTN_DRAFT = "🤖 Черновик к последнему"

KEYBOARD = {
    "keyboard": [
        [{"text": BTN_CHECK}],
        [{"text": BTN_STATS}, {"text": BTN_LAST}],
        [{"text": BTN_DRAFT}],
    ],
    "resize_keyboard": True,
    "is_persistent": True,
}


def _clip(text: str) -> str:
    return text if len(text) <= _MAX_LEN else text[:_MAX_LEN] + "…"


def format_review(review: Review, org_title: str, url: str) -> str:
    date = review.updated.strftime("%d.%m.%Y %H:%M") if review.updated else "дата неизвестна"
    body = html.escape(review.text) or "<i>без текста</i>"
    return (
        f"<b>{html.escape(org_title)}</b>\n"
        f"{review.stars}  {html.escape(review.author)}  ·  {date}\n\n"
        f"{_clip(body)}\n\n"
        f'<a href="{html.escape(url)}">Открыть отзывы</a>'
    )


def format_stats(meta: Meta, org_title: str, reviews: list[Review]) -> str:
    lines = [f"<b>{html.escape(org_title)}</b>"]
    if meta.rating:
        lines.append(f"Рейтинг: <b>{meta.rating}</b> ({meta.rating_count} оценок, {meta.review_count} отзывов)")

    recent = [r for r in reviews if r.rating]
    if recent:
        low = sum(1 for r in recent if r.rating <= 3)
        lines.append(f"На последней странице: {len(recent)} отзывов, из них с оценкой 3 и ниже: {low}")

    if meta.aspects:
        lines.append("\nПо темам:")
        for aspect in meta.aspects[:6]:
            lines.append(
                f"  {html.escape(aspect.get('text', '?'))}: "
                f"👍 {aspect.get('positive', 0)}  👎 {aspect.get('negative', 0)}"
            )
    return "\n".join(lines)


def send(text: str, client: httpx.Client, keyboard: bool = True) -> None:
    """Единственная точка отправки. chat_id не параметр: другому адресату не уйдёт."""
    payload = {
        "chat_id": OWNER_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if keyboard:
        payload["reply_markup"] = KEYBOARD
    response = client.post(f"{API}/sendMessage", json=payload, timeout=30)
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram отказал: {data}")


def get_updates(offset: int, client: httpx.Client, timeout: int = 50) -> list[dict]:
    """Длинный опрос. Возвращает только сообщения от владельца, всё чужое отбрасывается."""
    response = client.get(
        f"{API}/getUpdates",
        params={"offset": offset, "timeout": timeout, "allowed_updates": '["message"]'},
        timeout=timeout + 15,
    )
    data = response.json()
    if not data.get("ok"):
        return []

    result = []
    for update in data.get("result", []):
        message = update.get("message") or {}
        chat_id = (message.get("chat") or {}).get("id")
        result.append({"update_id": update["update_id"], "from_owner": chat_id == OWNER_CHAT_ID,
                       "text": (message.get("text") or "").strip()})
    return result
