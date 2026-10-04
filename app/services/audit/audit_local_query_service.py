"""
Audit Local Query Service

Provides read-only query capabilities for local audit logs.
Retrieves, filters, and aggregates audit events from SQLite.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
import sqlite3
from app.repository.db_connection import get_db_connection


class AuditLocalQueryService:
    """Service for querying local audit logs."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection."""
        return get_db_connection(self.db_path)

    def get_audit_events(
        self,
        project_id: Optional[str] = None,
        event_type: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Retrieve audit events with optional filtering.

        Args:
            project_id: Filter by project ID
            event_type: Filter by event type (e.g., 'file.read', 'command.exec')
            start_date: Filter events after this date
            end_date: Filter events before this date
            limit: Maximum number of events to return
            offset: Offset for pagination

        Returns:
            List of audit event dictionaries
        """
        query = "SELECT * FROM audit_logs WHERE 1=1"
        params: List[Any] = []

        if project_id:
            query += " AND project_id = ?"
            params.append(project_id)

        if event_type:
            query += " AND event_type = ?"
            params.append(event_type)

        if start_date:
            query += " AND timestamp >= ?"
            params.append(start_date.isoformat())

        if end_date:
            query += " AND timestamp <= ?"
            params.append(end_date.isoformat())

        query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(query, params)
            columns = [description[0] for description in cursor.description]
            events = []
            for row in cursor.fetchall():
                events.append(dict(zip(columns, row)))
            return events
        finally:
            conn.close()

    def get_event_count(
        self,
        project_id: Optional[str] = None,
        event_type: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> int:
        """Count audit events matching filters."""
        query = "SELECT COUNT(*) FROM audit_logs WHERE 1=1"
        params: List[Any] = []

        if project_id:
            query += " AND project_id = ?"
            params.append(project_id)

        if event_type:
            query += " AND event_type = ?"
            params.append(event_type)

        if start_date:
            query += " AND timestamp >= ?"
            params.append(start_date.isoformat())

        if end_date:
            query += " AND timestamp <= ?"
            params.append(end_date.isoformat())

        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(query, params)
            result = cursor.fetchone()
            return result[0] if result else 0
        finally:
            conn.close()

    def get_events_by_session(
        self,
        session_id: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Retrieve all audit events for a specific session."""
        query = """
            SELECT * FROM audit_logs 
            WHERE session_id = ? 
            ORDER BY timestamp ASC 
            LIMIT ?
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(query, [session_id, limit])
            columns = [description[0] for description in cursor.description]
            events = []
            for row in cursor.fetchall():
                events.append(dict(zip(columns, row)))
            return events
        finally:
            conn.close()

    def get_recent_errors(
        self,
        project_id: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Retrieve recent error events."""
        query = """
            SELECT * FROM audit_logs 
            WHERE severity = 'ERROR'
        """
        params: List[Any] = []

        if project_id:
            query += " AND project_id = ?"
            params.append(project_id)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(query, params)
            columns = [description[0] for description in cursor.description]
            events = []
            for row in cursor.fetchall():
                events.append(dict(zip(columns, row)))
            return events
        finally:
            conn.close()

    def aggregate_events_by_type(
        self,
        project_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, int]:
        """Aggregate event counts by event type."""
        query = """
            SELECT event_type, COUNT(*) as count 
            FROM audit_logs 
            WHERE 1=1
        """
        params: List[Any] = []

        if project_id:
            query += " AND project_id = ?"
            params.append(project_id)

        if start_date:
            query += " AND timestamp >= ?"
            params.append(start_date.isoformat())

        if end_date:
            query += " AND timestamp <= ?"
            params.append(end_date.isoformat())

        query += " GROUP BY event_type"

        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(query, params)
            results = cursor.fetchall()
            return {row[0]: row[1] for row in results}
        finally:
            conn.close()
