"""Minimal, read-only Allos SQLite adapter. Never accepts model-written SQL."""
import os
import re
import sqlite3
from datetime import date
from pathlib import Path
from urllib.parse import quote

# Explicit review list. New Allos tables are not automatically exposed.
TABLES = frozenset({
    "activities", "activity_laps", "allergies", "allergy_reactions",
    "appointments", "body_metrics", "care_goals", "care_plan_items",
    "conditions", "dental_procedures", "encounters", "endurance_plans",
    "exercise_sets", "family_history", "fasts", "fitness_assessments",
    "fitness_assessment_entries", "food_daily_totals", "food_log_events",
    "food_sensitivities", "frequency_targets", "glucose_trace", "goals",
    "hr_minutes", "illness_episodes", "imaging_studies", "immunizations",
    "injuries", "intake_item_logs", "intake_items", "medical_records",
    "medication_courses", "metric_samples", "mood_logs", "niggles",
    "optical_prescriptions", "practice_logs", "preventive_events",
    "procedures", "protein_daily_totals", "protocols", "routine_days",
    "routines", "sessions", "skin_lesions", "stool_events",
    "substance_daily_totals", "substance_log_events", "symptom_logs",
})
# No auth, integration credentials, medical document payloads, photos, videos,
# genomic variants, narrative free text, or unreviewed tables.
# Keep free-text columns out of the generic reader as well.
DENIED_COLUMNS = frozenset({
    "notes", "raw_extraction", "import_report", "stored_path", "filename",
    "patient_name", "content", "body", "description", "components",
    "metadata", "payload", "external_id", "source_payload", "title",
    "address", "email", "phone", "photo", "image", "url", "secret", "token",
})
IDENT = re.compile(r"^[a-z][a-z0-9_]*$")
DATE_COLUMNS = ("date", "ts", "occurred_at", "started_at", "start_time", "logged_at", "created_at")


class AllosDB:
    def __init__(self, path: str, profile_id: int):
        self.path = Path(path).resolve()
        self.profile_id = int(profile_id)
        if self.profile_id < 1:
            raise ValueError("ALLOS_PROFILE_ID must be positive")
        if not self.path.is_file():
            raise FileNotFoundError(f"Allos database not found: {self.path}")

    def connect(self):
        uri = f"file:{quote(str(self.path), safe='/')}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=3)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        conn.execute("PRAGMA busy_timeout=3000")
        return conn

    @staticmethod
    def _columns(conn, table):
        # table is always in the reviewed TABLES allowlist.
        return {row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')}

    @staticmethod
    def _safe_columns(columns):
        return sorted(c for c in columns if IDENT.fullmatch(c) and c not in DENIED_COLUMNS
                      and not any(word in c for word in ("password", "secret", "token", "photo", "video", "path")))

    def catalog(self):
        with self.connect() as conn:
            present = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            result = []
            for table in sorted(TABLES & present):
                columns = self._columns(conn, table)
                if "profile_id" not in columns:
                    continue
                result.append({"table": table, "fields": self._safe_columns(columns),
                               "date_field": next((x for x in DATE_COLUMNS if x in columns), None)})
            return result

    def query(self, table: str, *, fields=None, start=None, end=None, limit=50, offset=0):
        if table not in TABLES:
            raise ValueError("Table is not available")
        limit, offset = int(limit), int(offset)
        if not 1 <= limit <= 100 or not 0 <= offset <= 10000:
            raise ValueError("Limit must be 1..100 and offset 0..10000")
        for val in (start, end):
            if val is not None:
                date.fromisoformat(val)  # Only ISO dates, not arbitrary filter expressions.
        with self.connect() as conn:
            columns = self._columns(conn, table)
            if "profile_id" not in columns:
                raise ValueError("Table is missing or not profile-scoped")
            allowed = set(self._safe_columns(columns))
            selected = list(fields) if fields is not None else sorted(allowed)
            if not selected or len(selected) > 40 or any(f not in allowed for f in selected):
                raise ValueError("Invalid or disallowed fields")
            date_col = next((x for x in DATE_COLUMNS if x in columns), None)
            if (start or end) and not date_col:
                raise ValueError("Table has no supported date field")
            # date(timestamp) handles ISO timestamps; dates are parameterized.
            clauses = ['"profile_id" = ?']
            params = [self.profile_id]
            if start:
                clauses.append(f'date("{date_col}") >= date(?)')
                params.append(start)
            if end:
                clauses.append(f'date("{date_col}") <= date(?)')
                params.append(end)
            col_sql = ", ".join(f'"{c}"' for c in selected)
            where_sql = " AND ".join(clauses)
            order_sql = f' ORDER BY "{date_col}" DESC' if date_col else ''
            sql = f'SELECT {col_sql} FROM "{table}" WHERE {where_sql}{order_sql} LIMIT ? OFFSET ?'
            rows = [dict(r) for r in conn.execute(sql, [*params, limit, offset])]
            return {"table": table, "profile_id": self.profile_id, "rows": rows,
                    "count_returned": len(rows), "limit": limit, "offset": offset}

    def metrics(self):
        with self.connect() as conn:
            cols = self._columns(conn, "metric_samples")
            if not {"profile_id", "metric"} <= cols:
                return []
            return [dict(r) for r in conn.execute(
                'SELECT metric, COUNT(*) AS sample_count FROM metric_samples '
                'WHERE profile_id = ? GROUP BY metric ORDER BY metric', (self.profile_id,))]

    def trend(self, metric: str, start: str, end: str):
        if not metric or len(metric) > 100:
            raise ValueError("Invalid metric")
        date.fromisoformat(start)
        date.fromisoformat(end)
        if start > end:
            raise ValueError("Start must be before end")
        with self.connect() as conn:
            columns = self._columns(conn, "metric_samples")
            if not {"profile_id", "metric", "date", "value"} <= columns:
                raise ValueError("Metric sample schema not supported")
            return [dict(r) for r in conn.execute(
                'SELECT date, COUNT(*) AS samples, ROUND(AVG(value), 3) AS average, '
                'MIN(value) AS minimum, MAX(value) AS maximum '
                'FROM metric_samples WHERE profile_id = ? AND metric = ? '
                'AND date >= ? AND date <= ? GROUP BY date ORDER BY date LIMIT 366',
                (self.profile_id, metric, start, end))]
