"""Minimal, read-only Allos SQLite adapter. Never accepts model-written SQL."""
import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path
from urllib.parse import quote

from .fields import READABLE_FIELDS

DATE_COLUMNS = (
    "date", "ts", "occurred_at", "started_at", "start_time", "logged_at",
    "recorded_at", "created_at",
)
MAX_TREND_DAYS = 366
REQUIRED_METRIC_FIELDS = frozenset({"profile_id", "metric", "date", "value"})
BUILTIN_SUBSTANCES = ("alcohol", "nicotine", "cannabis")


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

    def validate(self):
        with closing(self.connect()) as conn:
            missing = REQUIRED_METRIC_FIELDS - self._table_info(conn, "metric_samples").keys()
            if missing:
                raise ValueError(
                    "Unsupported Allos schema: metric_samples requires "
                    + ", ".join(sorted(missing))
                )

    @staticmethod
    def _table_info(conn, table) -> dict[str, int]:
        # Use the same table rule in discovery and direct reads. Do not read views.
        present = conn.execute(
            "SELECT 1 FROM main.sqlite_schema WHERE type='table' AND name=? "
            "AND sql NOT LIKE 'CREATE VIRTUAL TABLE %'",
            (table,),
        ).fetchone()
        if not present:
            return {}
        return {row['name']: row['pk'] for row in conn.execute(
            "SELECT name, pk FROM pragma_table_info(?, 'main')", (table,),
        )}

    def catalog(self):
        with closing(self.connect()) as conn:
            result = []
            for table, reviewed in sorted(READABLE_FIELDS.items()):
                allowed = reviewed & self._table_info(conn, table).keys()
                if not self._readable(table, allowed):
                    continue
                result.append({"table": table, "fields": sorted(allowed),
                               "date_field": next((x for x in DATE_COLUMNS if x in allowed), None)})
            return result

    @staticmethod
    def _readable(table, allowed):
        if table == "substance_daily_totals":
            return {"profile_id", "substance", "units"} <= allowed
        return "profile_id" in allowed and len(allowed) >= 2

    def query(self, table: str, *, fields=None, start=None, end=None, limit=50, offset=0):
        if table not in READABLE_FIELDS:
            raise ValueError("Table is not available")
        limit, offset = int(limit), int(offset)
        if not 1 <= limit <= 100 or not 0 <= offset <= 10000:
            raise ValueError("Limit must be 1..100 and offset 0..10000")
        start = date.fromisoformat(start).isoformat() if start is not None else None
        end = date.fromisoformat(end).isoformat() if end is not None else None
        if start and end and start > end:
            raise ValueError("Start must not be after end")
        with closing(self.connect()) as conn:
            info = self._table_info(conn, table)
            allowed = READABLE_FIELDS[table] & info.keys()
            if "profile_id" not in allowed:
                raise ValueError("Table is missing or not profile-scoped")
            if not self._readable(table, allowed):
                raise ValueError("Table has no supported data fields")
            selected = list(fields) if fields is not None else sorted(allowed)
            if not selected or len(selected) > 40 or any(f not in allowed for f in selected):
                raise ValueError("Invalid or disallowed fields")
            date_col = next((x for x in DATE_COLUMNS if x in allowed), None)
            if (start or end) and not date_col:
                raise ValueError("Table has no supported date field")
            # date(timestamp) handles ISO timestamps; dates are parameterized.
            clauses = ['"profile_id" = ?']
            params: list[int | str] = [self.profile_id]
            if table == "substance_daily_totals":
                # Custom keys may contain personal labels; only expose built-in categories.
                clauses.append('"substance" COLLATE BINARY IN (?, ?, ?)')
                params.extend(BUILTIN_SUBSTANCES)
            if start:
                clauses.append(f'date("{date_col}") >= date(?)')
                params.append(start)
            if end:
                clauses.append(f'date("{date_col}") <= date(?)')
                params.append(end)
            col_sql = ", ".join(f'"{c}"' for c in selected)
            where_sql = " AND ".join(clauses)
            pk_fields = sorted((c for c in info if info[c]), key=info.__getitem__)
            order = [f'"{date_col}" DESC'] if date_col else []
            # Prefer a reviewed primary key. Break any remaining ties using
            # all reviewed values, independently of the requested projection.
            sort_fields = pk_fields if pk_fields and set(pk_fields) <= allowed else []
            sort_fields += sorted(allowed - set(sort_fields))
            order.extend(f'"{c}" COLLATE BINARY' for c in sort_fields)
            order.extend(f'typeof("{c}")' for c in sort_fields)
            order_sql = ", ".join(order)
            sql = (f'SELECT {col_sql} FROM main."{table}" WHERE {where_sql} '
                   f'ORDER BY {order_sql} LIMIT ? OFFSET ?')
            rows = [dict(r) for r in conn.execute(sql, [*params, limit, offset])]
            return {"table": table, "profile_id": self.profile_id, "rows": rows,
                    "count_returned": len(rows), "limit": limit, "offset": offset}

    def metrics(self):
        with closing(self.connect()) as conn:
            cols = READABLE_FIELDS['metric_samples'] & self._table_info(conn, "metric_samples").keys()
            if not {"profile_id", "metric"} <= cols:
                return []
            return [dict(r) for r in conn.execute(
                'SELECT metric, COUNT(*) AS sample_count FROM main.metric_samples '
                'WHERE profile_id = ? GROUP BY metric ORDER BY metric', (self.profile_id,))]

    def trend(self, metric: str, start: str, end: str):
        if not metric or len(metric) > 100:
            raise ValueError("Invalid metric")
        start_day, end_day = date.fromisoformat(start), date.fromisoformat(end)
        if start_day > end_day:
            raise ValueError("Start must not be after end")
        if (end_day - start_day).days >= MAX_TREND_DAYS:
            raise ValueError(f"Trend range must not exceed {MAX_TREND_DAYS} days inclusive")
        with closing(self.connect()) as conn:
            columns = READABLE_FIELDS['metric_samples'] & self._table_info(conn, "metric_samples").keys()
            if not REQUIRED_METRIC_FIELDS <= columns:
                raise ValueError("Metric sample schema not supported")
            return [dict(r) for r in conn.execute(
                'SELECT date(date) AS date, COUNT(*) AS samples, ROUND(AVG(value), 3) AS average, '
                'MIN(value) AS minimum, MAX(value) AS maximum '
                'FROM main.metric_samples WHERE profile_id = ? AND metric = ? '
                'AND date(date) BETWEEN ? AND ? GROUP BY date(date) ORDER BY 1',
                (self.profile_id, metric, start_day.isoformat(), end_day.isoformat()))]
