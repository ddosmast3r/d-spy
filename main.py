"""Следит за отзывами на Яндекс.Картах, шлёт новые в Telegram и отвечает на кнопки.

Два потока: один опрашивает Яндекс по расписанию, второй слушает нажатия кнопок.
Оба пишут только владельцу.
"""
from __future__ import annotations

import argparse
import logging
import threading
import time
from datetime import datetime, timezone

import httpx

import replier
import telegram_client as tg
from config import DB_PATH, ORGS, POLL_INTERVAL
from storage import Seen
from yandex_reviews import Review, fetch

log = logging.getLogger("watcher")
_lock = threading.Lock()

# последний показанный отзыв, чтобы кнопка черновика знала, к чему его писать
_last: tuple[Review, str] | None = None

# когда в последний раз жаловались на пустой ответ Яндекса, чтобы не спамить каждые 10 минут
_empty_warned: dict[str, float] = {}
_EMPTY_WARN_EVERY = 3600


def check_orgs(seen: Seen, client: httpx.Client, notify: bool, announce_empty: bool = False) -> int:
    """Обходит организации, шлёт новые отзывы. Возвращает число отправленных."""
    sent = 0

    with _lock:
        for org in ORGS:
            try:
                reviews, meta = fetch(org, client)
            except Exception as exc:
                log.error("%s: %s", org.title, exc)
                if announce_empty:
                    tg.send(f"⚠️ {org.title}: не удалось получить отзывы.\n{exc}", client)
                continue

            # Яндекс иногда отдаёт страницу без данных. Молчать об этом нельзя:
            # иначе бот выглядит рабочим, а уведомления тихо перестают приходить.
            if not reviews and seen.count(org.org_id) > 0:
                log.warning("%s: страница отдалась, но отзывов в ней нет", org.title)
                last = _empty_warned.get(org.org_id, 0)
                if notify and time.time() - last > _EMPTY_WARN_EVERY:
                    _empty_warned[org.org_id] = time.time()
                    tg.send(
                        f"⚠️ {org.title}: Яндекс отдал страницу без отзывов. "
                        "Разово это бывает, но если повторяется, парсер пора чинить.",
                        client,
                    )
                continue
            _empty_warned.pop(org.org_id, None)

            first_run = seen.count(org.org_id) == 0
            fresh = [r for r in reviews if not seen.is_known(r.review_id)]

            # Первый запуск: помечаем всё прочитанным, иначе в чат прилетит сотня старых.
            if first_run:
                for review in reviews:
                    seen.remember(review.review_id, org.org_id)
                log.info("%s: первый запуск, помечено %d", org.title, len(reviews))
                if announce_empty:
                    tg.send(f"{org.title}: первый запуск, {len(reviews)} отзывов взяты за базу.", client)
                continue

            for review in sorted(fresh, key=_sort_key):
                if notify:
                    try:
                        tg.send(tg.format_review(review, org.title, org.reviews_url), client)
                        _remember_last(review, org.title)
                        send_draft(review, org.title, client)
                    except Exception as exc:
                        log.error("не отправилось: %s", exc)
                        continue
                else:
                    log.info("[%s] %s %s", org.title, review.stars, review.author)
                seen.remember(review.review_id, org.org_id)
                sent += 1

            log.info("%s: получено %d, новых %d", org.title, len(reviews), len(fresh))

            if announce_empty and not fresh:
                tg.send(f"{org.title}: новых отзывов нет. Всего {meta.review_count or '?'}.", client)

    return sent


def _sort_key(review: Review):
    return review.updated or datetime.min.replace(tzinfo=timezone.utc)


def _remember_last(review: Review, org_title: str) -> None:
    global _last
    _last = (review, org_title)


def send_draft(review: Review, org_title: str, client: httpx.Client) -> None:
    """Черновик ответа отдельным сообщением, чтобы его было удобно скопировать целиком."""
    if not replier.enabled():
        return
    try:
        text = replier.draft(review.text, review.author, review.rating, org_title, client)
    except Exception as exc:
        log.error("черновик не сгенерировался: %s", exc)
        tg.send(f"⚠️ Черновик не получился: {exc}", client)
        return
    tg.send(f"<b>Черновик ответа</b>\n\n<code>{_escape(text)}</code>", client)


def _escape(text: str) -> str:
    import html
    return html.escape(text)


def handle_button(text: str, seen: Seen, client: httpx.Client) -> None:
    if text in ("/start", "/help"):
        tg.send("Слежу за отзывами. Кнопки внизу.", client)
        return

    if text == tg.BTN_CHECK:
        tg.send("Проверяю…", client)
        check_orgs(seen, client, notify=True, announce_empty=True)
        return

    if text == tg.BTN_STATS:
        for org in ORGS:
            try:
                reviews, meta = fetch(org, client)
                tg.send(tg.format_stats(meta, org.title, reviews), client)
            except Exception as exc:
                tg.send(f"⚠️ {org.title}: {exc}", client)
        return

    if text == tg.BTN_LAST:
        for org in ORGS:
            try:
                reviews, _ = fetch(org, client)
                for review in reversed(reviews[:5]):
                    tg.send(tg.format_review(review, org.title, org.reviews_url), client)
                if reviews:
                    _remember_last(reviews[0], org.title)
            except Exception as exc:
                tg.send(f"⚠️ {org.title}: {exc}", client)
        return

    if text == tg.BTN_DRAFT:
        if not replier.enabled():
            tg.send("Черновики выключены: в .env не задан OLLAMA_HOST.", client)
            return
        ok, message = replier.health(client)
        if not ok:
            tg.send(f"⚠️ {message}", client)
            return
        if not _last:
            tg.send("Пока нечего отвечать: не было ни одного отзыва за эту сессию. "
                    "Нажмите «Последние 5», потом повторите.", client)
            return
        review, org_title = _last
        tg.send(f"Пишу черновик к отзыву: {review.author}…", client)
        send_draft(review, org_title, client)
        return

    tg.send("Не знаю такой команды. Пользуйтесь кнопками внизу.", client)


def listen(seen: Seen) -> None:
    """Длинный опрос кнопок. Чужие сообщения молча отбрасываются."""
    offset = 0
    with httpx.Client() as client:
        while True:
            try:
                for update in tg.get_updates(offset, client):
                    offset = update["update_id"] + 1
                    if not update["from_owner"]:
                        log.warning("сообщение не от владельца, игнорирую")
                        continue
                    handle_button(update["text"], seen, client)
            except Exception as exc:
                log.error("слушатель: %s", exc)
                time.sleep(5)


def watch(seen: Seen, notify: bool) -> None:
    with httpx.Client() as client:
        while True:
            check_orgs(seen, client, notify=notify)
            time.sleep(POLL_INTERVAL)


def main() -> None:
    parser = argparse.ArgumentParser(description="Мониторинг отзывов на Яндекс.Картах")
    parser.add_argument("--once", action="store_true", help="одна проверка и выход, без кнопок")
    parser.add_argument("--dry-run", action="store_true", help="не слать в телеграм")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S"
    )
    if not ORGS:
        raise SystemExit("В .env не задан ORGS")

    seen = Seen(DB_PATH, check_same_thread=False)

    if args.once:
        with httpx.Client() as client:
            check_orgs(seen, client, notify=not args.dry_run)
        seen.close()
        return

    log.info("организаций: %d, интервал: %d с", len(ORGS), POLL_INTERVAL)
    threading.Thread(target=listen, args=(seen,), daemon=True).start()
    try:
        watch(seen, notify=not args.dry_run)
    except KeyboardInterrupt:
        log.info("остановлено")
    finally:
        seen.close()


if __name__ == "__main__":
    main()
