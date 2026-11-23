import os
import sqlite3
import subprocess
import sys

import pytest

from allos_mcp.db import AllosDB


def test_unknown_fields_are_hidden_by_default(sample_database):
    with sqlite3.connect(sample_database) as conn:
        conn.execute("ALTER TABLE metric_samples ADD COLUMN extra_context TEXT")
        conn.execute("UPDATE metric_samples SET extra_context = 'synthetic context'")

    db = AllosDB(str(sample_database), 1)
    fields = next(item['fields'] for item in db.catalog() if item['table'] == 'metric_samples')
    assert 'extra_context' not in fields
    assert all('extra_context' not in row for row in db.query('metric_samples')['rows'])
    with pytest.raises(ValueError, match='disallowed fields'):
        db.query('metric_samples', fields=['extra_context'])


def test_approved_name_cannot_read_a_view(sample_database):
    with sqlite3.connect(sample_database) as conn:
        conn.execute('ALTER TABLE metric_samples RENAME TO source_metrics')
        conn.execute('CREATE VIEW metric_samples AS SELECT * FROM source_metrics')

    db = AllosDB(str(sample_database), 1)
    assert db.catalog() == []
    assert db.metrics() == []
    with pytest.raises(ValueError, match='not profile-scoped'):
        db.query('metric_samples')
    with pytest.raises(ValueError, match='not supported'):
        db.trend('weight', '2026-11-01', '2026-11-02')


def test_pagination_for_same_date_and_without_date(tmp_path):
    path = tmp_path / 'pages.db'
    with sqlite3.connect(path) as conn:
        conn.executescript('''
            CREATE TABLE metric_samples (profile_id INTEGER, id INTEGER, date TEXT);
            INSERT INTO metric_samples VALUES (1, 2, '2026-11-01'), (1, 1, '2026-11-01');
            CREATE TABLE goals (profile_id INTEGER, id INTEGER, target_value REAL);
            INSERT INTO goals VALUES (1, 2, 20), (1, 1, 10);
        ''')
    db = AllosDB(str(path), 1)
    for table in ('metric_samples', 'goals'):
        pages = [db.query(table, fields=['id'], limit=1, offset=offset)['rows'] for offset in (0, 1)]
        assert pages == [[{'id': 1}], [{'id': 2}]]


def test_trend_range_and_response_shape(sample_database):
    db = AllosDB(str(sample_database), 1)
    assert len(db.trend('weight', '2026-01-01', '2027-01-01')) == 2
    with pytest.raises(ValueError, match='366 days'):
        db.trend('weight', '2026-01-01', '2027-01-02')
    assert db.trend('weight', '20261101', '20261101') == [
        {'date': '2026-11-01', 'samples': 1, 'average': 75.0, 'minimum': 75.0, 'maximum': 75.0},
    ]


def test_invalid_database_is_rejected_at_startup(tmp_path):
    path = tmp_path / 'invalid.db'
    path.write_text('not a SQLite file')
    result = subprocess.run(
        [sys.executable, '-m', 'allos_mcp'], input='', text=True, capture_output=True,
        env={**os.environ, 'ALLOS_DB_PATH': str(path), 'ALLOS_PROFILE_ID': '1'}, timeout=10,
    )
    assert result.returncode == 2
    assert 'Invalid Allos database configuration' in result.stderr
