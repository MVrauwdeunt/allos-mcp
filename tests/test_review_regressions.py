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


def test_body_metrics_supports_recorded_at(tmp_path):
    path = tmp_path / 'body.db'
    with sqlite3.connect(path) as conn:
        conn.executescript('''
            CREATE TABLE body_metrics (id INTEGER PRIMARY KEY, profile_id INTEGER,
                                       recorded_at TEXT, weight_kg REAL);
            INSERT INTO body_metrics VALUES (1, 1, '2026-11-01T08:00:00', 75),
                                            (2, 1, '2026-11-02T08:00:00', 76),
                                            (3, 2, '2026-11-02T08:00:00', 99);
        ''')
    db = AllosDB(str(path), 1)
    assert db.catalog()[0]['date_field'] == 'recorded_at'
    assert db.query('body_metrics', fields=['id', 'recorded_at'],
                    start='2026-11-02', end='2026-11-02')['rows'] == [
        {'id': 2, 'recorded_at': '2026-11-02T08:00:00'},
    ]


@pytest.mark.parametrize('schema', [
    '',
    'CREATE TABLE unrelated (id INTEGER)',
    'CREATE TABLE metric_samples (profile_id INTEGER, metric TEXT, date TEXT)',
    'CREATE VIEW metric_samples AS SELECT 1 AS profile_id, 2 AS metric, 3 AS date, 4 AS value',
])
def test_startup_rejects_unsupported_sqlite_schema(tmp_path, schema):
    path = tmp_path / 'schema.db'
    with sqlite3.connect(path) as conn:
        conn.executescript(schema)
    with pytest.raises(ValueError, match='Unsupported Allos schema: metric_samples requires'):
        AllosDB(str(path), 1).validate()


def test_startup_accepts_supported_schema_without_rows(tmp_path):
    path = tmp_path / 'empty-metrics.db'
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE metric_samples (profile_id INTEGER, metric TEXT, date TEXT, value REAL)')
    db = AllosDB(str(path), 1)
    db.validate()
    assert db.metrics() == []


def test_pagination_ties_do_not_depend_on_projection(tmp_path):
    path = tmp_path / 'ties.db'
    with sqlite3.connect(path) as conn:
        conn.executescript('''
            CREATE TABLE metric_samples (id INTEGER, profile_id INTEGER, date TEXT, metric TEXT, value REAL);
            INSERT INTO metric_samples VALUES (1, 1, '2026-11-01', 'Z', 90),
                                             (1, 1, '2026-11-01', 'a', 10),
                                             (1, 1, '2026-11-01', 'Z', 90),
                                             (1, 2, '2026-11-01', 'A', 99);
            CREATE INDEX sample_values ON metric_samples(profile_id, value DESC);
        ''')
    db = AllosDB(str(path), 1)
    for offset, expected in enumerate((90, 90, 10)):
        full = db.query('metric_samples', limit=1, offset=offset)['rows']
        projected = db.query('metric_samples', fields=['value'], limit=1, offset=offset)['rows']
        assert projected == [{'value': full[0]['value']}] == [{'value': expected}]


@pytest.mark.parametrize('table, definition, allowed, mine, other', [
    ('food_daily_totals', 'group_key TEXT, servings REAL', ['group_key', 'servings'], "'fruit', 2", "'fruit', 9"),
    ('protein_daily_totals', 'grams REAL', ['grams'], '20', '99'),
    ('substance_daily_totals', 'substance TEXT COLLATE NOCASE, units INTEGER', ['substance', 'units'], "'alcohol', 1", "'alcohol', 9"),
])
def test_daily_totals_are_profile_scoped(tmp_path, table, definition, allowed, mine, other):
    path = tmp_path / 'totals.db'
    with sqlite3.connect(path) as conn:
        conn.execute(f'CREATE TABLE {table} (id INTEGER, profile_id INTEGER, date TEXT, {definition}, notes TEXT)')
        conn.execute(f"INSERT INTO {table} VALUES (1, 1, '2026-11-01', {mine}, 'private')")
        conn.execute(f"INSERT INTO {table} VALUES (2, 2, '2026-11-01', {other}, 'private')")
        if table == 'substance_daily_totals':
            conn.execute(f"INSERT INTO {table} VALUES (3, 1, '2026-11-01', 'custom', 2, 'private')")
            conn.execute(f"INSERT INTO {table} VALUES (4, 1, '2026-11-01', 'ALCOHOL', 3, 'private')")
    db = AllosDB(str(path), 1)
    assert set(db.catalog()[0]['fields']) == {'id', 'profile_id', 'date', *allowed}
    assert db.query(table, fields=['id'], start='2026-11-01')['rows'] == [{'id': 1}]
    with pytest.raises(ValueError, match='disallowed fields'):
        db.query(table, fields=['notes'])
