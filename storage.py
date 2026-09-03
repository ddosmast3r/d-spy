"""Какие отзывы уже видели. SQLite, чтобы переживать перезапуск."""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path


class Seen:
    def __init__(self, path: str, check_same_thread: bool = True) -> None:
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(Path(path), check_same_thread=check_same_thread)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS seen ("
            " review_id TEXT PRIMARY KEY,"
            " org_id    TEXT NOT NULL,"
            " added_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )
        # Показанные в чате отзывы получают короткий номер, чтобы к любому из них
        # можно было позвать черновик командой /dN, а не только к последнему.
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS shown ("
            " n         INTEGER PRIMARY KEY AUTOINCREMENT,"
            " review_id TEXT UNIQUE NOT NULL,"
            " org_id    TEXT NOT NULL,"
            " org_title TEXT NOT NULL,"
            " author    TEXT,"
            " rating    INTEGER,"
            " text      TEXT,"
            " shown_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )
        self._conn.commit()

    def is_known(self, review_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute("SELECT 1 FROM seen WHERE review_id = ?", (review_id,))
            return cur.fetchone() is not None

    def remember(self, review_id: str, org_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO seen (review_id, org_id) VALUES (?, ?)",
                (review_id, org_id),
            )
            self._conn.commit()

    def count(self, org_id: str) -> int:
        with self._lock:
            cur = self._conn.execute("SELECT COUNT(*) FROM seen WHERE org_id = ?", (org_id,))
            return cur.fetchone()[0]

    def register(self, review, org_title: str) -> int:
        """Короткий номер отзыва для команды /dN. Повторный показ номер не меняет."""
        with self._lock:
            cur = self._conn.execute("SELECT n FROM shown WHERE review_id = ?", (review.review_id,))
            row = cur.fetchone()
            if row:
                return row[0]
            cur = self._conn.execute(
                "INSERT INTO shown (review_id, org_id, org_title, author, rating, text)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (review.review_id, review.org_id, org_title, review.author,
                 review.rating, review.text),
            )
            self._conn.commit()
            return cur.lastrowid

    def shown(self, n: int) -> dict | None:
        with self._lock:
            cur = self._conn.execute(
                "SELECT review_id, org_id, org_title, author, rating, text FROM shown WHERE n = ?",
                (n,),
            )
            row = cur.fetchone()
        if not row:
            return None
        keys = ("review_id", "org_id", "org_title", "author", "rating", "text")
        return dict(zip(keys, row))

    def close(self) -> None:
        with self._lock:
            self._conn.close()
