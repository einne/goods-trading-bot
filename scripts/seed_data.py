"""Seed FAQ/intent/escalation CSV data into database tables."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from db import get_connection, init_db  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
FAQ_CSV = ROOT / "data" / "faq_seed.csv"
INTENT_CSV = ROOT / "data" / "intent_seed.csv"
RULE_CSV = ROOT / "data" / "escalation_rules.csv"
ITEM_CSV = ROOT / "data" / "items_seed.csv"
EVENT_CSV = ROOT / "data" / "events_seed.csv"


def _read_csv(path: Path):
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _seed_sqlite():
    conn, _ = get_connection()
    try:
        faq_rows = _read_csv(FAQ_CSV)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS faq (
                id INTEGER PRIMARY KEY,
                category TEXT NOT NULL,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                keywords TEXT NOT NULL,
                priority INTEGER NOT NULL,
                is_active INTEGER NOT NULL
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS intents (
                id INTEGER PRIMARY KEY,
                intent TEXT NOT NULL,
                faq_id INTEGER,
                category TEXT NOT NULL,
                sample_utterance TEXT NOT NULL,
                keywords TEXT NOT NULL,
                route TEXT NOT NULL,
                priority INTEGER NOT NULL,
                is_active INTEGER NOT NULL
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS escalation_rules (
                id INTEGER PRIMARY KEY,
                rule_name TEXT NOT NULL,
                trigger_faq_ids TEXT,
                trigger_intent TEXT NOT NULL,
                trigger_keywords TEXT NOT NULL,
                extra_condition TEXT,
                escalation_level TEXT NOT NULL,
                target_queue TEXT NOT NULL,
                sla_minutes INTEGER NOT NULL,
                action TEXT NOT NULL,
                priority INTEGER NOT NULL,
                is_active INTEGER NOT NULL
            );
            """
        )

        for row in faq_rows:
            conn.execute(
                """
                INSERT OR REPLACE INTO faq
                (id, category, question, answer, keywords, priority, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(row["id"]),
                    row["category"],
                    row["question"],
                    row["answer"],
                    row["keywords"],
                    int(row["priority"]),
                    1 if row["is_active"].lower() == "true" else 0,
                ),
            )

        for row in _read_csv(INTENT_CSV):
            conn.execute(
                """
                INSERT OR REPLACE INTO intents
                (id, intent, faq_id, category, sample_utterance, keywords, route, priority, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(row["id"]),
                    row["intent"],
                    int(row["faq_id"]) if row.get("faq_id") else None,
                    row["category"],
                    row["sample_utterance"],
                    row["keywords"],
                    row["route"],
                    int(row["priority"]),
                    1 if row["is_active"].lower() == "true" else 0,
                ),
            )

        for row in _read_csv(RULE_CSV):
            conn.execute(
                """
                INSERT OR REPLACE INTO escalation_rules
                (id, rule_name, trigger_faq_ids, trigger_intent, trigger_keywords, extra_condition,
                 escalation_level, target_queue, sla_minutes, action, priority, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(row["id"]),
                    row["rule_name"],
                    row["trigger_faq_ids"],
                    row["trigger_intent"],
                    row["trigger_keywords"],
                    row["extra_condition"],
                    row["escalation_level"],
                    row["target_queue"],
                    int(row["sla_minutes"]),
                    row["action"],
                    int(row["priority"]),
                    1 if row["is_active"].lower() == "true" else 0,
                ),
            )

        # Seed events (idempotent).
        for row in _read_csv(EVENT_CSV):
            conn.execute(
                """
                INSERT OR REPLACE INTO events
                (id, title, event_type, starts_at, ends_at, location, details, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(row["id"]),
                    row["title"],
                    row["event_type"],
                    row["starts_at"],
                    row["ends_at"],
                    row["location"],
                    row["details"],
                    row["status"],
                ),
            )

        # Seed users/items (idempotent).
        user_cache: dict[str, int] = {}
        for row in _read_csv(ITEM_CSV):
            tg_id = row["seller_telegram_user_id"]
            if tg_id not in user_cache:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO users (telegram_user_id, display_name, username, role, is_active)
                    VALUES (?, ?, ?, 'STUDENT', 1)
                    """,
                    (tg_id, row["seller_display_name"], row["seller_username"]),
                )
                conn.execute(
                    """
                    UPDATE users
                    SET display_name = COALESCE(?, display_name),
                        username = COALESCE(?, username)
                    WHERE telegram_user_id = ?
                    """,
                    (row["seller_display_name"], row["seller_username"], tg_id),
                )
                user_row = conn.execute(
                    "SELECT id FROM users WHERE telegram_user_id = ?",
                    (tg_id,),
                ).fetchone()
                user_cache[tg_id] = int(user_row[0])

            conn.execute(
                """
                INSERT OR REPLACE INTO items (
                    id, seller_id, title, category, price, condition_level, description, status, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(row["id"]),
                    user_cache[tg_id],
                    row["title"],
                    row["category"],
                    float(row["price"]),
                    row["condition_level"],
                    row["description"],
                    row["status"],
                    row["created_at"],
                ),
            )

        conn.commit()
        print("Seeded SQLite tables: faq, intents, escalation_rules, events, items")
    finally:
        conn.close()


def _seed_postgres():
    conn, _ = get_connection()
    try:
        with conn.cursor() as cur:
            for row in _read_csv(FAQ_CSV):
                cur.execute(
                    """
                    INSERT INTO faq (id, category, question, answer, keywords, priority, is_active)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        category = EXCLUDED.category,
                        question = EXCLUDED.question,
                        answer = EXCLUDED.answer,
                        keywords = EXCLUDED.keywords,
                        priority = EXCLUDED.priority,
                        is_active = EXCLUDED.is_active
                    """,
                    (
                        int(row["id"]),
                        row["category"],
                        row["question"],
                        row["answer"],
                        row["keywords"],
                        int(row["priority"]),
                        row["is_active"].lower() == "true",
                    ),
                )

            for row in _read_csv(INTENT_CSV):
                cur.execute(
                    """
                    INSERT INTO intents
                    (id, intent, faq_id, category, sample_utterance, keywords, route, priority, is_active)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        intent = EXCLUDED.intent,
                        faq_id = EXCLUDED.faq_id,
                        category = EXCLUDED.category,
                        sample_utterance = EXCLUDED.sample_utterance,
                        keywords = EXCLUDED.keywords,
                        route = EXCLUDED.route,
                        priority = EXCLUDED.priority,
                        is_active = EXCLUDED.is_active
                    """,
                    (
                        int(row["id"]),
                        row["intent"],
                        int(row["faq_id"]) if row.get("faq_id") else None,
                        row["category"],
                        row["sample_utterance"],
                        row["keywords"],
                        row["route"],
                        int(row["priority"]),
                        row["is_active"].lower() == "true",
                    ),
                )

            for row in _read_csv(RULE_CSV):
                cur.execute(
                    """
                    INSERT INTO escalation_rules
                    (id, rule_name, trigger_faq_ids, trigger_intent, trigger_keywords, extra_condition,
                     escalation_level, target_queue, sla_minutes, action, priority, is_active)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        rule_name = EXCLUDED.rule_name,
                        trigger_faq_ids = EXCLUDED.trigger_faq_ids,
                        trigger_intent = EXCLUDED.trigger_intent,
                        trigger_keywords = EXCLUDED.trigger_keywords,
                        extra_condition = EXCLUDED.extra_condition,
                        escalation_level = EXCLUDED.escalation_level,
                        target_queue = EXCLUDED.target_queue,
                        sla_minutes = EXCLUDED.sla_minutes,
                        action = EXCLUDED.action,
                        priority = EXCLUDED.priority,
                        is_active = EXCLUDED.is_active
                    """,
                    (
                        int(row["id"]),
                        row["rule_name"],
                        row["trigger_faq_ids"],
                        row["trigger_intent"],
                        row["trigger_keywords"],
                        row["extra_condition"],
                        row["escalation_level"],
                        row["target_queue"],
                        int(row["sla_minutes"]),
                        row["action"],
                        int(row["priority"]),
                        row["is_active"].lower() == "true",
                    ),
                )
            # Seed events (idempotent).
            for row in _read_csv(EVENT_CSV):
                cur.execute(
                    """
                    INSERT INTO events (id, title, event_type, starts_at, ends_at, location, details, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        title = EXCLUDED.title,
                        event_type = EXCLUDED.event_type,
                        starts_at = EXCLUDED.starts_at,
                        ends_at = EXCLUDED.ends_at,
                        location = EXCLUDED.location,
                        details = EXCLUDED.details,
                        status = EXCLUDED.status
                    """,
                    (
                        int(row["id"]),
                        row["title"],
                        row["event_type"],
                        row["starts_at"],
                        row["ends_at"],
                        row["location"],
                        row["details"],
                        row["status"],
                    ),
                )

            # Seed users/items (idempotent).
            user_cache: dict[str, int] = {}
            for row in _read_csv(ITEM_CSV):
                tg_id = row["seller_telegram_user_id"]
                if tg_id not in user_cache:
                    cur.execute(
                        """
                        INSERT INTO users (telegram_user_id, display_name, username, role, is_active)
                        VALUES (%s, %s, %s, 'STUDENT', TRUE)
                        ON CONFLICT (telegram_user_id) DO UPDATE SET
                            display_name = COALESCE(EXCLUDED.display_name, users.display_name),
                            username = COALESCE(EXCLUDED.username, users.username)
                        RETURNING id
                        """,
                        (tg_id, row["seller_display_name"], row["seller_username"]),
                    )
                    user_cache[tg_id] = int(cur.fetchone()[0])

                cur.execute(
                    """
                    INSERT INTO items (
                        id, seller_id, title, category, price, condition_level, description,
                        status, created_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (id) DO UPDATE SET
                        seller_id = EXCLUDED.seller_id,
                        title = EXCLUDED.title,
                        category = EXCLUDED.category,
                        price = EXCLUDED.price,
                        condition_level = EXCLUDED.condition_level,
                        description = EXCLUDED.description,
                        status = EXCLUDED.status,
                        created_at = EXCLUDED.created_at,
                        updated_at = NOW()
                    """,
                    (
                        int(row["id"]),
                        user_cache[tg_id],
                        row["title"],
                        row["category"],
                        float(row["price"]),
                        row["condition_level"],
                        row["description"],
                        row["status"],
                        row["created_at"],
                    ),
                )
        conn.commit()
        print("Seeded PostgreSQL tables: faq, intents, escalation_rules, events, items")
    finally:
        conn.close()


def main():
    init_db()
    conn, engine = get_connection()
    conn.close()
    if engine == "postgres":
        _seed_postgres()
    else:
        _seed_sqlite()


if __name__ == "__main__":
    main()
