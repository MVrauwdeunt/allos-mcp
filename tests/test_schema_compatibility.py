
"""Ensure schema changes do not bypass the reviewed-table and profile rules."""

import sqlite3

import pytest

from allos_mcp.db import AllosDB


def test_unreviewed_table_stays_hidden(sample_database):
    with sqlite3.connect(sample_database) as conn:
        conn.execute(
            "CREATE TABLE private_measurements "
            "(profile_id INTEGER, value REAL)"
        )
        conn.execute(
            "INSERT INTO private_measurements VALUES (1, 123.0)"
        )

    db = AllosDB(str(sample_database), 1)

    assert "private_measurements" not in {
        row["table"] for row in db.catalog()
    }

    with pytest.raises(ValueError, match="not available"):
        db.query("private_measurements")


def test_new_sensitive_columns_remain_hidden(sample_database):
    with sqlite3.connect(sample_database) as conn:
        conn.execute(
            "ALTER TABLE metric_samples "
            "ADD COLUMN password_hash TEXT"
        )
        conn.execute(
            "ALTER TABLE metric_samples "
            "ADD COLUMN source_payload TEXT"
        )
        conn.execute(
            "UPDATE metric_samples "
            "SET password_hash = 'do-not-leak', "
            "source_payload = 'private'"
        )

    db = AllosDB(str(sample_database), 1)

    fields = next(
        row["fields"]
        for row in db.catalog()
        if row["table"] == "metric_samples"
    )

    assert "password_hash" not in fields
    assert "source_payload" not in fields

    assert all(
        "password_hash" not in row
        and "source_payload" not in row
        for row in db.query("metric_samples")["rows"]
    )


def test_profile_scope_removed_fails_closed(sample_database):
    with sqlite3.connect(sample_database) as conn:
        conn.execute(
            "ALTER TABLE metric_samples "
            "RENAME TO old_metric_samples"
        )

        conn.execute("""
            CREATE TABLE metric_samples (
                id INTEGER,
                metric TEXT,
                date TEXT,
                value REAL
            )
        """)

        conn.execute(
            "INSERT INTO metric_samples VALUES "
            "(1, 'weight', '2026-11-01', 75.0)"
        )

    db = AllosDB(str(sample_database), 1)

    assert "metric_samples" not in {
        row["table"] for row in db.catalog()
    }

    with pytest.raises(ValueError, match="not profile-scoped"):
        db.query("metric_samples")

    assert db.metrics() == []

    with pytest.raises(ValueError, match="not supported"):
        db.trend(
            "weight",
            "2026-11-01",
            "2026-11-30",
        )


def test_missing_approved_table_is_not_exposed(tmp_path):
    path = tmp_path / "empty-schema.db"

    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE unrelated (id INTEGER PRIMARY KEY)"
        )

    db = AllosDB(str(path), 1)

    assert db.catalog() == []
    assert db.metrics() == []

    with pytest.raises(ValueError):
        db.query("metric_samples")
