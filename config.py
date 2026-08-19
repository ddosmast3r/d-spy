import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Org:
    org_id: str
    title: str
    # «тихая» организация: отзывы редки, показывать пачкой бессмысленно
    quiet: bool = False

    @property
    def reviews_url(self) -> str:
        # by_time — свежие сверху, иначе Яндекс сортирует по релевантности
        return f"https://yandex.ru/maps/org/{self.org_id}/reviews/?ranking=by_time"


def _parse_orgs(raw: str) -> list[Org]:
    orgs = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = [p.strip() for p in chunk.split(":")]
        org_id = parts[0]
        quiet = len(parts) > 2 and parts[-1].lower() == "quiet"
        title_parts = parts[1:-1] if quiet else parts[1:]
        title = ":".join(title_parts).strip() or org_id
        orgs.append(Org(org_id, title, quiet))
    return orgs


BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

# Единственный получатель. Бот не пишет никуда, кроме этого чата.
OWNER_CHAT_ID = int(os.environ["TELEGRAM_CHAT_ID"])

POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "600"))
ORGS = _parse_orgs(os.getenv("ORGS", ""))
DB_PATH = os.getenv("DB_PATH", "seen.db")

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
