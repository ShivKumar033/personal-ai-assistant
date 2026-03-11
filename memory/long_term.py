"""
JARVIS AI — Long-Term Memory (Phase 6)

Persistent key-value and tabular storage for user preferences,
facts, and settings using SQLite.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger


class LongTermMemory:
    """SQLite-backed memory for tracking persistent entities and preferences."""

    def __init__(self, db_path: str = "logs/memory/long_term.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._init_db()

    def _init_db(self) -> None:
        """Create tables if they don't exist."""
        with self._conn:
            # Simple Key-Value store for preferences
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS preferences (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            
            # Facts store for unstructured knowledge extracted from conversations
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic TEXT NOT NULL,
                    fact TEXT NOT NULL,
                    confidence REAL DEFAULT 1.0,
                    created_at TEXT NOT NULL
                )
                """
            )

    # ── Key-Value Preferences ────────────────────────────────

    def set_preference(self, key: str, value: Any) -> None:
        """Store a persistent preference/setting."""
        now = datetime.now(timezone.utc).isoformat()
        try:
            val_str = json.dumps(value)
            with self._conn:
                self._conn.execute(
                    """
                    INSERT INTO preferences (key, value, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
                    """,
                    (key, val_str, now)
                )
            logger.debug(f"Saved preference: {key}={value}")
        except Exception as e:
            logger.error(f"Failed to save preference: {e}")

    def get_preference(self, key: str, default: Any = None) -> Any:
        """Retrieve a persistent preference/setting."""
        cursor = self._conn.execute("SELECT value FROM preferences WHERE key = ?", (key,))
        row = cursor.fetchone()
        if row:
            try:
                return json.loads(row[0])
            except json.JSONDecodeError:
                return row[0]
        return default

    def get_all_preferences(self) -> Dict[str, Any]:
        """Fetch all stored preferences."""
        prefs = {}
        cursor = self._conn.execute("SELECT key, value FROM preferences")
        for key, value_str in cursor.fetchall():
            try:
                prefs[key] = json.loads(value_str)
            except json.JSONDecodeError:
                prefs[key] = value_str
        return prefs

    def delete_preference(self, key: str) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM preferences WHERE key = ?", (key,))

    # ── Facts Database ───────────────────────────────────────

    def remember_fact(self, topic: str, fact: str, confidence: float = 1.0) -> int:
        """Store an important fact learned during conversation."""
        now = datetime.now(timezone.utc).isoformat()
        with self._conn:
            cursor = self._conn.execute(
                """
                INSERT INTO facts (topic, fact, confidence, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (topic.lower(), fact, confidence, now)
            )
            logger.info(f"Learned new fact about '{topic}': {fact}")
            return cursor.lastrowid

    def recall_facts(self, topic: str) -> List[Dict[str, Any]]:
        """Retrieve all facts known about a topic."""
        cursor = self._conn.execute(
            "SELECT id, fact, confidence, created_at FROM facts WHERE topic LIKE ?",
            (f"%{topic.lower()}%",)
        )
        return [
            {"id": row[0], "fact": row[1], "confidence": row[2], "created_at": row[3]}
            for row in cursor.fetchall()
        ]

    def close(self) -> None:
        self._conn.close()
