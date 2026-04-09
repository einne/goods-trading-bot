"""Event query service for campus second-hand activities."""

from __future__ import annotations

from typing import Any, Dict, List

from db import get_connection


def search_upcoming_events(query: str | None = None, limit: int = 8) -> List[Dict[str, Any]]:
    """Return upcoming active events ordered by start time."""
    conn, engine = get_connection()
    try:
        if engine == "postgres":
            with conn.cursor() as cur:
                if query:
                    pattern = f"%{query.strip()}%"
                    cur.execute(
                        """
                        SELECT id, title, event_type, starts_at, ends_at, location, details, status
                        FROM events
                        WHERE status = 'ACTIVE'
                          AND starts_at >= NOW()
                          AND (
                                title ILIKE %s OR
                                event_type ILIKE %s OR
                                location ILIKE %s OR
                                COALESCE(details, '') ILIKE %s
                          )
                        ORDER BY starts_at ASC
                        LIMIT %s
                        """,
                        (pattern, pattern, pattern, pattern, limit),
                    )
                else:
                    cur.execute(
                        """
                        SELECT id, title, event_type, starts_at, ends_at, location, details, status
                        FROM events
                        WHERE status = 'ACTIVE'
                          AND starts_at >= NOW()
                        ORDER BY starts_at ASC
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
                SELECT id, title, event_type, starts_at, ends_at, location, details, status
                FROM events
                WHERE status = 'ACTIVE'
                  AND (
                        LOWER(title) LIKE ? OR
                        LOWER(event_type) LIKE ? OR
                        LOWER(location) LIKE ? OR
                        LOWER(COALESCE(details, '')) LIKE ?
                  )
                ORDER BY starts_at ASC
                LIMIT ?
                """,
                (pattern, pattern, pattern, pattern, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, title, event_type, starts_at, ends_at, location, details, status
                FROM events
                WHERE status = 'ACTIVE'
                ORDER BY starts_at ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

