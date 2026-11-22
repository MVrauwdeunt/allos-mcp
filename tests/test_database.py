import sqlite3

import pytest
from allos_mcp.db import AllosDB


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "allos.db"
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            CREATE TABLE metric_samples (
                id INTEGER, profile_id INTEGER, metric TEXT,
                date TEXT, value REAL, notes TEXT
            );
            INSERT INTO metric_samples VALUES
                (1, 2, 'sleep_min', '2026-11-20', 450, 'private'),
                (2, 3, 'sleep_min', '2026-11-20', 120, 'other profile');
            CREATE TABLE api_tokens (profile_id INTEGER, token TEXT);
            INSERT INTO api_tokens VALUES (2, 'must-not-leak');
        """)
    return AllosDB(str(path), 2)


def test_scope_and_sensitive_columns(db):
    result = db.query("metric_samples")
    assert result["count_returned"] == 1
    assert result["rows"][0]["value"] == 450
    assert "notes" not in result["rows"][0]
    assert "api_tokens" not in [item["table"] for item in db.catalog()]


def test_no_sql_injection_or_denied_tables(db):
    with pytest.raises(ValueError):
        db.query("api_tokens")
    with pytest.raises(ValueError):
        db.query("metric_samples", fields=["value; DROP TABLE metric_samples"])
    with pytest.raises(ValueError):
        db.query("metric_samples", fields=["notes"])
    with pytest.raises(ValueError):
        db.query("metric_samples", limit=1000)


def test_metrics_and_trend(db):
    assert db.metrics() == [{"metric": "sleep_min", "sample_count": 1}]
    result = db.trend("sleep_min", "2026-11-01", "2026-11-30")
    assert result[0]["average"] == 450


def test_sqlite_read_only(db):
    with db.connect() as conn:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("DELETE FROM metric_samples")


def test_profile_id_required(tmp_path):
    path = tmp_path / "valid.db"
    sqlite3.connect(path).close()
    with pytest.raises(ValueError):
        AllosDB(str(path), 0)
