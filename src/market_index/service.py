"""SQLite-backed public market metadata index."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from threading import Lock


@dataclass(slots=True)
class PublicMarketRecord:
    """Public market metadata exposed by free search endpoints."""

    market_id: str
    title: str
    description: str | None
    creator_account_id: str | None
    category: str | None
    tags: list[str]
    created_at: datetime
    trading_close_at: datetime
    updated_at: datetime
    status: str
    resolved_outcome: str | None
    resolved_at: datetime | None


class SQLiteMarketIndexService:
    """Persist public market metadata for free browsing and search."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._lock = Lock()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def upsert_market(
        self,
        *,
        market_id: str,
        title: str,
        description: str | None,
        creator_account_id: str | None,
        category: str | None,
        tags: list[str],
        created_at: datetime,
        trading_close_at: datetime,
        updated_at: datetime,
        status: str,
        resolved_outcome: str | None,
        resolved_at: datetime | None,
    ) -> None:
        """Insert or update one market metadata row."""

        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO public_markets (
                    market_id,
                    title,
                    description,
                    creator_account_id,
                    category,
                    tags_json,
                    created_at,
                    trading_close_at,
                    updated_at,
                    status,
                    resolved_outcome,
                    resolved_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(market_id) DO UPDATE SET
                    title = excluded.title,
                    description = excluded.description,
                    creator_account_id = excluded.creator_account_id,
                    category = excluded.category,
                    tags_json = excluded.tags_json,
                    created_at = excluded.created_at,
                    trading_close_at = excluded.trading_close_at,
                    updated_at = excluded.updated_at,
                    status = excluded.status,
                    resolved_outcome = excluded.resolved_outcome,
                    resolved_at = excluded.resolved_at
                """,
                (
                    market_id,
                    title,
                    description,
                    creator_account_id,
                    category,
                    json.dumps(tags),
                    created_at.isoformat(),
                    trading_close_at.isoformat(),
                    updated_at.isoformat(),
                    status,
                    resolved_outcome,
                    resolved_at.isoformat() if resolved_at is not None else None,
                ),
            )
            connection.commit()

    def list_markets(
        self,
        *,
        query: str | None = None,
        status: str | None = None,
        category: str | None = None,
        creator_account_id: str | None = None,
        tag: str | None = None,
        limit: int = 50,
    ) -> list[PublicMarketRecord]:
        """Return public markets filtered by optional query and status."""

        sql = """
            SELECT
                market_id,
                title,
                description,
                creator_account_id,
                category,
                tags_json,
                created_at,
                trading_close_at,
                updated_at,
                status,
                resolved_outcome,
                resolved_at
            FROM public_markets
        """
        clauses: list[str] = []
        parameters: list[object] = []

        if query:
            clauses.append("(LOWER(title) LIKE ? OR LOWER(COALESCE(description, '')) LIKE ?)")
            normalized_query = f"%{query.lower()}%"
            parameters.extend([normalized_query, normalized_query])
        if status:
            clauses.append("status = ?")
            parameters.append(status)
        if category:
            clauses.append("LOWER(COALESCE(category, '')) = ?")
            parameters.append(category.lower())
        if creator_account_id:
            clauses.append("LOWER(COALESCE(creator_account_id, '')) = ?")
            parameters.append(creator_account_id.lower())
        if tag:
            clauses.append("LOWER(COALESCE(tags_json, '[]')) LIKE ?")
            parameters.append(f'%"{tag.lower()}"%')
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC LIMIT ?"
        parameters.append(limit)

        with self._lock, self._connect() as connection:
            rows = connection.execute(sql, parameters).fetchall()
        return [self._row_to_record(row) for row in rows]

    def get_market(self, market_id: str) -> PublicMarketRecord:
        """Return one public market metadata row."""

        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    market_id,
                    title,
                    description,
                    creator_account_id,
                    category,
                    tags_json,
                    created_at,
                    trading_close_at,
                    updated_at,
                    status,
                    resolved_outcome,
                    resolved_at
                FROM public_markets
                WHERE market_id = ?
                """,
                (market_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"market '{market_id}' not found")
        return self._row_to_record(row)

    def delete_market(self, market_id: str) -> None:
        """Delete one public market metadata row if it exists."""

        with self._lock, self._connect() as connection:
            connection.execute(
                """
                DELETE FROM public_markets
                WHERE market_id = ?
                """,
                (market_id,),
            )
            connection.commit()

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS public_markets (
                    market_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT,
                    creator_account_id TEXT,
                    category TEXT,
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    trading_close_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    resolved_outcome TEXT,
                    resolved_at TEXT
                )
                """
            )
            self._ensure_column(connection, "public_markets", "creator_account_id", "TEXT")
            self._ensure_column(connection, "public_markets", "category", "TEXT")
            self._ensure_column(connection, "public_markets", "tags_json", "TEXT NOT NULL DEFAULT '[]'")
            self._ensure_column(connection, "public_markets", "trading_close_at", "TEXT")
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_public_markets_status_created_at
                ON public_markets(status, created_at DESC)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_public_markets_title
                ON public_markets(title)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_public_markets_category
                ON public_markets(category)
                """
            )
            connection.commit()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _row_to_record(self, row: tuple[object, ...]) -> PublicMarketRecord:
        created_at = datetime.fromisoformat(str(row[6]))
        trading_close_at = created_at if row[7] is None else datetime.fromisoformat(str(row[7]))
        return PublicMarketRecord(
            market_id=str(row[0]),
            title=str(row[1]),
            description=str(row[2]) if row[2] is not None else None,
            creator_account_id=str(row[3]) if row[3] is not None else None,
            category=str(row[4]) if row[4] is not None else None,
            tags=json.loads(str(row[5])) if row[5] else [],
            created_at=created_at,
            trading_close_at=trading_close_at,
            updated_at=datetime.fromisoformat(str(row[8])),
            status=str(row[9]),
            resolved_outcome=str(row[10]) if row[10] is not None else None,
            resolved_at=datetime.fromisoformat(str(row[11])) if row[11] is not None else None,
        )

    def _ensure_column(self, connection: sqlite3.Connection, table_name: str, column_name: str, definition: str) -> None:
        existing_columns = {
            str(row[1])
            for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        if column_name in existing_columns:
            return
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")
