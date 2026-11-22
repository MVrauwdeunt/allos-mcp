
"""Security regression tests using synthetic health data only."""

import sqlite3

import pytest

from allos_mcp.db import AllosDB


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "synthetic.db"

    with sqlite3.connect(path) as conn:
        conn.executescript("""
            CREATE TABLE metric_samples (
                id INTEGER PRIMARY KEY,
                profile_id INTEGER NOT NULL,
                metric TEXT NOT NULL,
                date TEXT NOT NULL,
                value REAL,
                notes TEXT,
                token TEXT
            );

            INSERT INTO metric_samples VALUES
                (1, 1, 'weight', '2026-11-01', 75.0, 'private note', 'secret-1'),
                (2, 1, 'weight', '2026-11-02', 76.0, 'private note', 'secret-2'),
                (3, 2, 'weight', '2026-11-01', 99.0, 'other profile', 'secret-3'),
                (4, 1, 'sleep', '2026-11-01', 420.0, 'private note', 'secret-4');

            CREATE TABLE api_tokens (
                profile_id INTEGER,
                token TEXT
            );

            INSERT INTO api_tokens VALUES (1, 'sensitive-key');

            CREATE TABLE appointments (
                profile_id INTEGER,
                id INTEGER,
                date TEXT
            );

            INSERT INTO appointments VALUES (1, 1, '2026-11-01');

            CREATE TABLE activities (
                id INTEGER,
                date TEXT
            );

            INSERT INTO activities VALUES (1, '2026-11-01');
        """)

    return AllosDB(str(path), 1)


def test_profile_isolation_for_rows_metrics_and_trends(db):
    rows = db.query(
        "metric_samples",
        fields=["id", "profile_id", "value"],
        limit=100,
    )

    assert rows["count_returned"] == 3
    assert {row["profile_id"] for row in rows["rows"]} == {1}
    assert {row["value"] for row in rows["rows"]} == {
        75.0, 76.0, 420.0
    }

    assert db.metrics() == [
        {"metric": "sleep", "sample_count": 1},
        {"metric": "weight", "sample_count": 2},
    ]

    trend = db.trend("weight", "2026-11-01", "2026-11-30")

    assert sum(row["samples"] for row in trend) == 2
    assert all(row["maximum"] < 99 for row in trend)


def test_sensitive_columns_never_appear_in_default_response(db):
    rows = db.query("metric_samples")["rows"]

    assert rows
    assert all(
        "notes" not in row and "token" not in row
        for row in rows
    )

    catalog = {
        item["table"]: item
        for item in db.catalog()
    }

    assert "metric_samples" in catalog
    assert "notes" not in catalog["metric_samples"]["fields"]
    assert "token" not in catalog["metric_samples"]["fields"]
    assert "api_tokens" not in catalog


@pytest.mark.parametrize("table", [
    "api_tokens",
    "sqlite_master",
    "metric_samples; DROP TABLE api_tokens",
])
def test_unreviewed_or_malicious_tables_rejected(db, table):
    with pytest.raises(ValueError):
        db.query(table)


@pytest.mark.parametrize("fields", [
    ["notes"],
    ["token"],
    ["value; DROP TABLE api_tokens"],
    [],
    ["value"] * 41,
])
def test_sensitive_or_invalid_field_lists_rejected(db, fields):
    with pytest.raises(ValueError):
        db.query("metric_samples", fields=fields)


def test_table_without_profile_scope_is_rejected(db):
    catalog = {
        item["table"] for item in db.catalog()
    }

    assert "activities" not in catalog

    with pytest.raises(ValueError):
        db.query("activities")


@pytest.mark.parametrize("limit,offset", [
    (0, 0),
    (101, 0),
    (1, -1),
    (1, 10001),
])
def test_pagination_boundaries_rejected(db, limit, offset):
    with pytest.raises(ValueError):
        db.query(
            "metric_samples",
            limit=limit,
            offset=offset,
        )


def test_date_filters_and_pagination(db):
    result = db.query(
        "metric_samples",
        fields=["id", "date"],
        start="2026-11-02",
        end="2026-11-02",
    )

    assert [row["id"] for row in result["rows"]] == [2]

    first_page = db.query(
        "metric_samples",
        fields=["id"],
        limit=1,
        offset=0,
    )

    second_page = db.query(
        "metric_samples",
        fields=["id"],
        limit=1,
        offset=1,
    )

    assert first_page["count_returned"] == 1
    assert second_page["count_returned"] == 1
    assert first_page["rows"] != second_page["rows"]


@pytest.mark.parametrize("start,end", [
    ("2026-11-01' OR 1=1 --", None),
    ("2026-13-01", None),
    (None, "not-a-date"),
])
def test_bad_dates_rejected(db, start, end):
    with pytest.raises(ValueError):
        db.query(
            "metric_samples",
            start=start,
            end=end,
        )


def test_date_filter_requires_date_column(db):
    with sqlite3.connect(db.path) as conn:
        conn.execute("""
            CREATE TABLE goals (
                id INTEGER,
                profile_id INTEGER
            )
        """)

    with pytest.raises(ValueError, match="date field"):
        db.query("goals", start="2026-11-01")


def test_trend_rejects_invalid_range_and_metric(db):
    with pytest.raises(ValueError):
        db.trend(
            "weight",
            "2026-11-30",
            "2026-11-01",
        )

    with pytest.raises(ValueError):
        db.trend(
            "",
            "2026-11-01",
            "2026-11-30",
        )

    assert db.trend(
        "weight' OR 1=1 --",
        "2026-11-01",
        "2026-11-30",
    ) == []


def test_database_is_read_only(db):
    with db.connect() as conn:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute(
                "UPDATE metric_samples SET value = 0"
            )

    result = db.query(
        "metric_samples",
        fields=["value"],
        limit=100,
    )

    assert result["count_returned"] == 3
