"""Черновик ответа через локальную Ollama.

Жёсткие правила стиля проверяются кодом после генерации, а не только просьбой в промпте:
модель инструкции нарушает, детерминированный фильтр — нет.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import httpx
from dotenv import load_dotenv

from style import SYSTEM, build_prompt

load_dotenv()  # не полагаемся на порядок импортов: грузим .env здесь же

EXAMPLES_PATH = Path(__file__).parent / "examples.json"


def _host() -> str:
    return os.getenv("OLLAMA_HOST", "").rstrip("/")


def _model() -> str:
    return os.getenv("OLLAMA_MODEL", "qwen2.5:7b")


def enabled() -> bool:
    return bool(_host())


def _load_examples() -> list[dict]:
    if not EXAMPLES_PATH.exists():
        return []
    return json.loads(EXAMPLES_PATH.read_text(encoding="utf-8"))


def health(client: httpx.Client) -> tuple[bool, str]:
    host = _host()
    if not host:
        return False, "OLLAMA_HOST не задан в .env"
    try:
        response = client.get(f"{host}/api/tags", timeout=10)
        models = [m["name"] for m in response.json().get("models", [])]
        if not models:
            return False, "Ollama отвечает, но моделей нет. Скачайте: ollama pull <модель>"
        if _model() not in models:
            return False, f"модели {_model()} нет. Доступны: {', '.join(models)}"
        return True, f"Ollama на связи, модель {_model()}"
    except Exception as exc:
        return False, f"Ollama недоступна: {exc}"


def _clean(text: str, author: str | None) -> str:
    """Приводим вывод модели к нашим правилам, не надеясь на её послушность."""
    text = text.strip()

    # модели любят обрамлять ответ кавычками или markdown
    text = re.sub(r"^```[a-z]*\n?|```$", "", text).strip()
    if len(text) > 1 and text[0] in "\"«'" and text[-1] in "\"»'":
        text = text[1:-1].strip()

    # правило 2: никаких длинных тире
    text = text.replace(" — ", ", ").replace("—", ",")

    # правило 3: подпись отрезаем, если модель её всё-таки приписала
    text = re.sub(r"\n+\s*(С уважением|Команда|Администрация)[^\n]*$", "", text, flags=re.I).strip()

    # правило 1: приветствие отдельной строкой
    greeting = f"Здравствуйте, {author}!" if author else "Здравствуйте!"
    first, _, rest = text.partition("\n")
    if re.match(r"^\s*(здравствуйте|добрый день|привет|доброго)", first, re.I):
        body = rest.strip() or ""
        # приветствие и текст слиплись в одну строку — разделяем
        if not body:
            m = re.match(r"^\s*([^!.\n]*[!.])\s*(.*)$", first, re.S)
            if m:
                greeting, body = m.group(1).strip(), m.group(2).strip()
    else:
        body = text
    return f"{greeting}\n{body}".strip()


def draft(review_text: str, author: str | None, rating: int | None,
          org_title: str, client: httpx.Client) -> str:
    prompt = build_prompt(review_text, author, rating, org_title, _load_examples())
    response = client.post(
        f"{_host()}/api/chat",
        json={
            "model": _model(),
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "think": False,  # gemma4 — reasoning-модель; без этого бюджет уходит в thinking, а ответ пустой
            "options": {"temperature": 0.7, "num_predict": 1200},
        },
        timeout=180,
    )
    response.raise_for_status()
    raw = response.json()["message"]["content"]
    return _clean(raw, author)
