import sqlite3

import pytest

from oafc.metadata import IntegratorStore


@pytest.fixture
def source_root(tmp_path):
    source = tmp_path / "commerce.sqlite"
    with sqlite3.connect(source) as conn:
        conn.executescript("""
            PRAGMA foreign_keys=ON;
            CREATE TABLE products (
                product_id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                category TEXT,
                unit_price REAL,
                created_at TEXT
            );
            CREATE TABLE orders (
                order_id INTEGER PRIMARY KEY,
                product_id INTEGER NOT NULL REFERENCES products(product_id),
                quantity INTEGER,
                total_amount REAL,
                order_status TEXT
            );
            CREATE VIEW product_titles AS SELECT product_id,title FROM products;
        """)
    return tmp_path, source


@pytest.fixture
def store(source_root):
    root, _source = source_root
    instance = IntegratorStore(root / "integrator-meta.db", [root])
    yield instance
    instance.close_thread_connection()
