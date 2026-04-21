"""Item service for listing/publishing/delisting second-hand items."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from db import get_connection


def ensure_user(telegram_user_id: str, display_name: str | None, username: str | None) -> int:
    """Ensure user row exists and return internal user id."""
    conn, engine = get_connection()
    try:
        if engine == "postgres":
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO users (telegram_user_id, display_name, username)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (telegram_user_id)
                    DO UPDATE SET
                        display_name = COALESCE(EXCLUDED.display_name, users.display_name),
                        username = COALESCE(EXCLUDED.username, users.username)
                    RETURNING id
                    """,
                    (telegram_user_id, display_name, username),
                )
                user_id = cur.fetchone()[0]
            conn.commit()
            return int(user_id)

        row = conn.execute(
            "SELECT id FROM users WHERE telegram_user_id = ?",
            (telegram_user_id,),
        ).fetchone()
        if row:
            conn.execute(
                """
                UPDATE users
                SET display_name = COALESCE(?, display_name),
                    username = COALESCE(?, username)
                WHERE id = ?
                """,
                (display_name, username, row["id"]),
            )
            conn.commit()
            return int(row["id"])

        cur = conn.execute(
            """
            INSERT INTO users (telegram_user_id, display_name, username)
            VALUES (?, ?, ?)
            """,
            (telegram_user_id, display_name, username),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def search_active_items(query: str | None = None, limit: int = 8) -> List[Dict[str, Any]]:
    """List active items with optional keyword query."""
    conn, engine = get_connection()
    try:
        if engine == "postgres":
            with conn.cursor() as cur:
                if query:
                    pattern = f"%{query.strip()}%"
                    cur.execute(
                        """
                        SELECT i.id, i.title, i.category, i.price, i.condition_level, i.description,
                               i.status, i.created_at, u.username
                        FROM items i
                        LEFT JOIN users u ON u.id = i.seller_id
                        WHERE i.status = 'ACTIVE'
                          AND (
                                i.title ILIKE %s OR
                                i.category ILIKE %s OR
                                COALESCE(i.description, '') ILIKE %s
                          )
                        ORDER BY i.created_at DESC
                        LIMIT %s
                        """,
                        (pattern, pattern, pattern, limit),
                    )
                else:
                    cur.execute(
                        """
                        SELECT i.id, i.title, i.category, i.price, i.condition_level, i.description,
                               i.status, i.created_at, u.username
                        FROM items i
                        LEFT JOIN users u ON u.id = i.seller_id
                        WHERE i.status = 'ACTIVE'
                        ORDER BY i.created_at DESC
                        LIMIT %s
                        """,
                        (limit,),
                    )
                rows = cur.fetchall()
                columns = [desc[0] for desc in cur.description]
                return [dict(zip(columns, row)) for row in rows]

        if query:
            pattern = f"%{query.strip().lower()}%"
            rows = conn.execute(
                """
                SELECT i.id, i.title, i.category, i.price, i.condition_level, i.description,
                       i.status, i.created_at, u.username
                FROM items i
                LEFT JOIN users u ON u.id = i.seller_id
                WHERE i.status = 'ACTIVE'
                  AND (
                        LOWER(i.title) LIKE ? OR
                        LOWER(i.category) LIKE ? OR
                        LOWER(COALESCE(i.description, '')) LIKE ?
                  )
                ORDER BY i.created_at DESC
                LIMIT ?
                """,
                (pattern, pattern, pattern, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT i.id, i.title, i.category, i.price, i.condition_level, i.description,
                       i.status, i.created_at, u.username
                FROM items i
                LEFT JOIN users u ON u.id = i.seller_id
                WHERE i.status = 'ACTIVE'
                ORDER BY i.created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def list_user_items(telegram_user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    """List items posted by a specific Telegram user."""
    conn, engine = get_connection()
    try:
        if engine == "postgres":
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT i.id, i.title, i.category, i.price, i.condition_level, i.description,
                           i.status, i.created_at, u.username
                    FROM items i
                    JOIN users u ON u.id = i.seller_id
                    WHERE u.telegram_user_id = %s
                    ORDER BY i.created_at DESC
                    LIMIT %s
                    """,
                    (telegram_user_id, limit),
                )
                rows = cur.fetchall()
                columns = [desc[0] for desc in cur.description]
                return [dict(zip(columns, row)) for row in rows]

        rows = conn.execute(
            """
            SELECT i.id, i.title, i.category, i.price, i.condition_level, i.description,
                   i.status, i.created_at, u.username
            FROM items i
            JOIN users u ON u.id = i.seller_id
            WHERE u.telegram_user_id = ?
            ORDER BY i.created_at DESC
            LIMIT ?
            """,
            (telegram_user_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def publish_item(
    *,
    telegram_user_id: str,
    display_name: str | None,
    username: str | None,
    title: str,
    category: str,
    price: float,
    condition_level: str,
    description: str,
) -> Dict[str, Any]:
    """Create item and return created row."""
    seller_id = ensure_user(telegram_user_id, display_name, username)
    conn, engine = get_connection()
    try:
        if engine == "postgres":
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO items (
                        seller_id, title, category, price, condition_level, description, status
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, 'ACTIVE')
                    RETURNING id, seller_id, title, category, price, condition_level, description, status, created_at
                    """,
                    (seller_id, title, category, price, condition_level, description),
                )
                row = cur.fetchone()
                columns = [desc[0] for desc in cur.description]
            conn.commit()
            return dict(zip(columns, row))

        cur = conn.execute(
            """
            INSERT INTO items (
                seller_id, title, category, price, condition_level, description, status
            )
            VALUES (?, ?, ?, ?, ?, ?, 'ACTIVE')
            """,
            (seller_id, title, category, price, condition_level, description),
        )
        conn.commit()
        created = conn.execute(
            """
            SELECT id, seller_id, title, category, price, condition_level, description, status, created_at
            FROM items
            WHERE id = ?
            """,
            (cur.lastrowid,),
        ).fetchone()
        return dict(created)
    finally:
        conn.close()


def delist_item(
    *,
    telegram_user_id: str,
    item_id: int,
) -> Tuple[bool, str]:
    """Set item status to DELISTED if requester is owner."""
    conn, engine = get_connection()
    try:
        if engine == "postgres":
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT i.id, i.status, i.seller_id
                    FROM items i
                    JOIN users u ON u.id = i.seller_id
                    WHERE i.id = %s AND u.telegram_user_id = %s
                    """,
                    (item_id, telegram_user_id),
                )
                row = cur.fetchone()
                if not row:
                    return False, "Item not found or you are not the owner."
                if row[1] != "ACTIVE":
                    return False, f"Item status is {row[1]}, cannot delist again."
                cur.execute(
                    """
                    UPDATE items
                    SET status = 'DELISTED', updated_at = NOW()
                    WHERE id = %s
                    """,
                    (item_id,),
                )
            conn.commit()
            return True, "Item has been delisted successfully."

        row = conn.execute(
            """
            SELECT i.id, i.status, i.seller_id
            FROM items i
            JOIN users u ON u.id = i.seller_id
            WHERE i.id = ? AND u.telegram_user_id = ?
            """,
            (item_id, telegram_user_id),
        ).fetchone()
        if not row:
            return False, "Item not found or you are not the owner."
        if row["status"] != "ACTIVE":
            return False, f"Item status is {row['status']}, cannot delist again."
        conn.execute("UPDATE items SET status = 'DELISTED' WHERE id = ?", (item_id,))
        conn.commit()
        return True, "Item has been delisted successfully."
    finally:
        conn.close()
