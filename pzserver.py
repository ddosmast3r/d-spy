"""Управление сервером Project Zomboid на игровом ПК по SSH.

Бот живёт на Pi, сервер на ПК. Ходим по отдельному ключу, sudo на ПК разрешён
без пароля только для systemctl этого сервиса, ничего сверх.
"""
from __future__ import annotations

import os
import subprocess

from dotenv import load_dotenv

load_dotenv()  # не зависим от порядка импортов


def _host() -> str:
    return os.getenv("PZ_PC_HOST", "")


def _user() -> str:
    return os.getenv("PZ_PC_USER", "master")


def _key() -> str:
    return os.getenv("PZ_SSH_KEY", "/opt/reviews-watcher/.ssh/id_ed25519")


def _service() -> str:
    return os.getenv("PZ_SERVICE", "pzserver")


def _public_ip() -> str:
    return os.getenv("PZ_PUBLIC_IP", "")


def enabled() -> bool:
    return bool(_host())


def _ssh(remote_cmd: str, timeout: int = 45) -> subprocess.CompletedProcess:
    cmd = [
        "ssh", "-n", "-i", _key(),
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "ConnectTimeout=10",
        f"{_user()}@{_host()}", remote_cmd,
    ]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def is_active() -> bool:
    try:
        r = _ssh(f"sudo systemctl is-active {_service()}", timeout=15)
        return r.stdout.strip() == "active"
    except Exception:
        return False


def status_text() -> str:
    if not enabled():
        return "Управление сервером выключено (не задан PZ_PC_HOST)."
    try:
        active = is_active()
    except Exception as exc:
        return f"⚠️ Не могу связаться с ПК: {exc}"
    if active:
        addr = _public_ip() or _host()
        return f"🎮 Сервер Project Zomboid работает.\nПодключение: {addr}:16261"
    return "🛑 Сервер выключен."


def start() -> str:
    if not enabled():
        return "Управление сервером выключено."
    if is_active():
        return "Сервер уже работает."
    try:
        r = _ssh(f"sudo systemctl start {_service()}", timeout=30)
        if r.returncode != 0:
            return f"⚠️ Не удалось запустить: {r.stderr.strip() or r.stdout.strip()}"
    except Exception as exc:
        return f"⚠️ Ошибка запуска: {exc}"
    return "Запускаю сервер, поднимется примерно за 30 секунд. Нажмите «Статус сервера», чтобы проверить."


def stop() -> str:
    if not enabled():
        return "Управление сервером выключено."
    if not is_active():
        return "Сервер и так выключен."
    try:
        # серверу нужно время сохранить мир, даём запас
        r = _ssh(f"sudo systemctl stop {_service()}", timeout=100)
        if r.returncode != 0:
            return f"⚠️ Не удалось остановить: {r.stderr.strip() or r.stdout.strip()}"
    except Exception as exc:
        return f"⚠️ Ошибка остановки: {exc}"
    return "Сервер останавливается, мир сохраняется."
