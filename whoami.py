"""Показывает chat_id тех, кто писал боту. Нужен один раз, чтобы заполнить TELEGRAM_CHAT_ID."""
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

token = os.environ["TELEGRAM_BOT_TOKEN"]
data = httpx.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=30).json()

if not data.get("ok"):
    raise SystemExit(f"Telegram вернул ошибку: {data}")

chats = {}
for update in data.get("result", []):
    message = update.get("message") or update.get("edited_message") or {}
    chat = message.get("chat") or {}
    if chat.get("id"):
        chats[chat["id"]] = chat

if not chats:
    raise SystemExit("Никто боту не писал. Отправьте боту /start и запустите снова.")

for chat_id, chat in chats.items():
    who = chat.get("username") or chat.get("first_name") or chat.get("title") or "?"
    print(f"TELEGRAM_CHAT_ID={chat_id}   ({chat.get('type')}, {who})")
