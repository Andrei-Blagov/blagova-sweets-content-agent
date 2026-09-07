"""SQLite history storage for generated posts."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.models import HistoryItem

logger = logging.getLogger(__name__)


class HistoryStore:
    def __init__(self, db_path: Path | None = None) -> None:
        settings = get_settings()
        self.db_path = db_path or settings.db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    style TEXT NOT NULL,
                    goal TEXT NOT NULL,
                    post TEXT NOT NULL,
                    length INTEGER NOT NULL
                )
                """
            )
            conn.commit()

    def add(
        self,
        *,
        source_type: str,
        source: str,
        platform: str,
        style: str,
        goal: str,
        post: str,
        length: int,
    ) -> HistoryItem:
        created_at = datetime.now(timezone.utc).isoformat()
        preview_source = source if len(source) <= 500 else source[:497] + "..."
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO history
                (created_at, source_type, source, platform, style, goal, post, length)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (created_at, source_type, preview_source, platform, style, goal, post, length),
            )
            conn.commit()
            item_id = int(cursor.lastrowid)
        logger.info("History saved id=%s length=%s", item_id, length)
        return HistoryItem(
            id=item_id,
            created_at=created_at,
            source_type=source_type,
            source=preview_source,
            platform=platform,
            style=style,
            goal=goal,
            post=post,
            length=length,
        )

    def list_recent(self, limit: int = 20) -> list[HistoryItem]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, created_at, source_type, source, platform, style, goal, post, length
                FROM history
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._row_to_item(row) for row in rows]

    @staticmethod
    def _row_to_item(row: Any) -> HistoryItem:
        return HistoryItem(
            id=int(row["id"]),
            created_at=str(row["created_at"]),
            source_type=str(row["source_type"]),
            source=str(row["source"]),
            platform=str(row["platform"]),
            style=str(row["style"]),
            goal=str(row["goal"]),
            post=str(row["post"]),
            length=int(row["length"]),
        )
