#!/usr/bin/env python3
"""mempatterns — Detect emergent patterns from memory.db and maintain an Obsidian wiki."""
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

DB_PATH = Path.home() / ".claude" / "memory.db"
WIKI_DIR = Path.home() / ".claude" / "patterns"

CO_EDIT_THRESHOLD = 5
ERROR_RECURRENCE_THRESHOLD = 3
PROJECT_STREAK_THRESHOLD = 5
TOOL_ANOMALY_FACTOR = 2.0


class PatternDetector:
    """Detects patterns from memory.db data."""

    def __init__(self, db_path: Path = DB_PATH, wiki_dir: Path = WIKI_DIR):
        self.db_path = db_path
        self.wiki_dir = wiki_dir
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.conn.close()

    def detect_co_edits(self, threshold: int = CO_EDIT_THRESHOLD) -> list[dict]:
        """Find file pairs frequently edited together in the same session."""
        sql = """
            SELECT a.path AS file_a, b.path AS file_b, COUNT(*) AS cnt
            FROM files_touched a
            JOIN files_touched b
                ON a.session_id = b.session_id
               AND a.path < b.path
            WHERE a.action IN ('edit', 'write', 'create')
              AND b.action IN ('edit', 'write', 'create')
            GROUP BY a.path, b.path
            HAVING cnt >= ?
        """
        rows = self.conn.execute(sql, (threshold,)).fetchall()
        return [
            {
                "files": [row["file_a"], row["file_b"]],
                "count": row["cnt"],
                "kind": "co_edit",
            }
            for row in rows
        ]

    def detect_error_recurrence(
        self, threshold: int = ERROR_RECURRENCE_THRESHOLD
    ) -> list[dict]:
        """Find errors appearing across multiple sessions."""
        sql = """
            SELECT content, content_hash, COUNT(*) AS cnt
            FROM facts
            WHERE type = 'error'
            GROUP BY content_hash
            HAVING cnt >= ?
        """
        rows = self.conn.execute(sql, (threshold,)).fetchall()
        return [
            {
                "content": row["content"],
                "hash": row["content_hash"],
                "count": row["cnt"],
                "kind": "error_recurrence",
            }
            for row in rows
        ]

    def detect_project_streaks(
        self, threshold: int = PROJECT_STREAK_THRESHOLD
    ) -> list[dict]:
        """Find consecutive days of activity per project."""
        sql = """
            SELECT project, DATE(captured_at) AS day
            FROM sessions
            GROUP BY project, day
            ORDER BY project, day
        """
        rows = self.conn.execute(sql).fetchall()

        # Group dates by project
        project_days: dict[str, list[date]] = defaultdict(list)
        for row in rows:
            project_days[row["project"]].append(date.fromisoformat(row["day"]))

        results = []
        for project, days in project_days.items():
            days_sorted = sorted(set(days))
            # Find longest consecutive run
            max_streak = 1
            current_streak = 1
            for i in range(1, len(days_sorted)):
                if days_sorted[i] - days_sorted[i - 1] == timedelta(days=1):
                    current_streak += 1
                    max_streak = max(max_streak, current_streak)
                else:
                    current_streak = 1
            if max_streak >= threshold:
                results.append(
                    {"project": project, "streak": max_streak, "kind": "project_streak"}
                )
        return results

    def detect_tool_anomalies(self, factor: float = TOOL_ANOMALY_FACTOR) -> list[dict]:
        """Find projects with unusual tool usage compared to global average."""
        sql = """
            SELECT s.project, tu.tool_name, AVG(tu.count) AS proj_avg
            FROM tool_usage tu
            JOIN sessions s ON tu.session_id = s.session_id
            GROUP BY s.project, tu.tool_name
        """
        proj_rows = self.conn.execute(sql).fetchall()

        global_sql = """
            SELECT tu.tool_name, AVG(tu.count) AS global_avg
            FROM tool_usage tu
            GROUP BY tu.tool_name
        """
        global_rows = self.conn.execute(global_sql).fetchall()
        global_avgs = {row["tool_name"]: row["global_avg"] for row in global_rows}

        results = []
        for row in proj_rows:
            g_avg = global_avgs.get(row["tool_name"], 0)
            if g_avg == 0:
                continue
            ratio = row["proj_avg"] / g_avg
            if ratio > factor:
                results.append(
                    {
                        "project": row["project"],
                        "tool": row["tool_name"],
                        "project_avg": row["proj_avg"],
                        "global_avg": g_avg,
                        "ratio": ratio,
                        "kind": "tool_anomaly",
                    }
                )
        return results
