
"""Synthetic Allos fixtures; never use real medical records in tests."""

import sqlite3

import pytest


@pytest.fixture
def sample_database(tmp_path):
    path = tmp_path / "allos-synthetic.db"

    with sqlite3.connect(path) as conn:
        conn.executescript("""
            CREATE TABLE metric_samples (
                id INTEGER PRIMARY KEY,
                profile_id INTEGER NOT NULL,
                metric TEXT NOT NULL,
                date TEXT NOT NULL,
                value REAL NOT NULL,
                notes TEXT,
                token TEXT
            );

            INSERT INTO metric_samples VALUES
                (1, 1, 'weight', '2026-11-01', 75.0, 'private', 'secret'),
                (2, 1, 'weight', '2026-11-02', 76.0, 'private', 'secret'),
                (3, 2, 'weight', '2026-11-01', 99.0, 'other', 'other-secret');

            CREATE TABLE api_tokens (
                id INTEGER PRIMARY KEY,
                token TEXT
            );

            INSERT INTO api_tokens VALUES (
                1, 'never-return-this'
            );
        """)

    return path
