"""Database helpers for local SQLite and cloud PostgreSQL logging."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, Tuple

DB_PATH = Path("data/smartsupport.db")


def _sqlite_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _postgres_connection():
    import psycopg2  # Imported lazily so local SQLite mode still works without this package.

    database_url = os.getenv("DATABASE_URL", "").strip()
    return psycopg2.connect(database_url)


def get_connection():
    """Return a tuple of (connection, engine_name)."""
    database_url = os.getenv("DATABASE_URL", "").strip()
    if database_url.startswith("postgresql://") or database_url.startswith("postgres://"):
        return _postgres_connection(), "postgres"
    return _sqlite_connection(), "sqlite"


def init_db() -> None:
    """Initialize minimal runtime tables.

    Full PostgreSQL business schema is maintained in `database/schema_postgres.sql`.
    """
    conn, engine = get_connection()
    try:
        if engine == "postgres":
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_logs (
                        id BIGSERIAL PRIMARY KEY,
                        request_id TEXT,
                        telegram_user_id TEXT,
                        raw_input TEXT NOT NULL,
                        detected_intent TEXT,
                        route_mode TEXT,
                        faq_id INTEGER,
                        rule_id INTEGER,
                        bot_response TEXT NOT NULL,
                        llm_model TEXT,
                        llm_estimated_cost NUMERIC(12, 6),
                        latency_ms INTEGER,
                        is_fallback BOOLEAN DEFAULT FALSE,
                        error_message TEXT,
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    );
                    """
                )
            conn.commit()
            return

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT,
                telegram_user_id TEXT,
                raw_input TEXT NOT NULL,
                detected_intent TEXT,
                route_mode TEXT,
                faq_id INTEGER,
                rule_id INTEGER,
                bot_response TEXT NOT NULL,
                llm_model TEXT,
                llm_estimated_cost REAL,
                latency_ms INTEGER,
                is_fallback INTEGER DEFAULT 0,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_user_id TEXT UNIQUE NOT NULL,
                display_name TEXT,
                username TEXT,
                role TEXT DEFAULT 'STUDENT',
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                seller_id INTEGER,
                title TEXT NOT NULL,
                category TEXT NOT NULL,
                price REAL NOT NULL DEFAULT 0,
                condition_level TEXT NOT NULL DEFAULT 'UNKNOWN',
                description TEXT,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                event_type TEXT NOT NULL,
                starts_at TIMESTAMP,
                ends_at TIMESTAMP,
                location TEXT NOT NULL,
                details TEXT,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_message TEXT NOT NULL,
                bot_response TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


def log_chat(
    user_message: str,
    bot_response: str,
    *,
    telegram_user_id: str | None = None,
    detected_intent: str | None = None,
    route_mode: str | None = None,
    faq_id: int | None = None,
    rule_id: int | None = None,
    llm_model: str | None = None,
    llm_estimated_cost: float | None = None,
    latency_ms: int | None = None,
    is_fallback: bool = False,
    error_message: str | None = None,
    request_id: str | None = None,
) -> None:
    """Persist structured interaction logs."""
    conn, engine = get_connection()
    try:
        row: Dict[str, Any] = {
            "request_id": request_id,
            "telegram_user_id": telegram_user_id,
            "raw_input": user_message,
            "detected_intent": detected_intent,
            "route_mode": route_mode,
            "faq_id": faq_id,
            "rule_id": rule_id,
            "bot_response": bot_response,
            "llm_model": llm_model,
            "llm_estimated_cost": llm_estimated_cost,
            "latency_ms": latency_ms,
            "is_fallback": is_fallback,
            "error_message": error_message,
        }

        if engine == "postgres":
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO user_logs (
                        request_id, telegram_user_id, raw_input, detected_intent, route_mode,
                        faq_id, rule_id, bot_response, llm_model, llm_estimated_cost,
                        latency_ms, is_fallback, error_message
                    )
                    VALUES (
                        %(request_id)s, %(telegram_user_id)s, %(raw_input)s, %(detected_intent)s, %(route_mode)s,
                        %(faq_id)s, %(rule_id)s, %(bot_response)s, %(llm_model)s, %(llm_estimated_cost)s,
                        %(latency_ms)s, %(is_fallback)s, %(error_message)s
                    );
                    """,
                    row,
                )
            conn.commit()
            return

        conn.execute(
            """
            INSERT INTO user_logs (
                request_id, telegram_user_id, raw_input, detected_intent, route_mode,
                faq_id, rule_id, bot_response, llm_model, llm_estimated_cost,
                latency_ms, is_fallback, error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["request_id"],
                row["telegram_user_id"],
                row["raw_input"],
                row["detected_intent"],
                row["route_mode"],
                row["faq_id"],
                row["rule_id"],
                row["bot_response"],
                row["llm_model"],
                row["llm_estimated_cost"],
                row["latency_ms"],
                1 if row["is_fallback"] else 0,
                row["error_message"],
            ),
        )
        # Keep backward-compatible table for old queries.
        conn.execute(
            "INSERT INTO chat_logs (user_message, bot_response) VALUES (?, ?)",
            (user_message, bot_response),
        )
        conn.commit()
    finally:
        conn.close()
