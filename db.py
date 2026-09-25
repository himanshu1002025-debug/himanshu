"""
Database helpers for the Family Care project.

Uses Python's built-in sqlite3 module — no external ORM, no magic.
Every query in the app goes through one of these four functions:
    query_one()    → returns a single row as a dict, or None
    query_all()    → returns a list of dicts
    execute()      → runs INSERT/UPDATE/DELETE, returns last row id
    init_db()      → creates tables if they don't already exist
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'elderly.db')


def get_conn():
    """Open a connection with row_factory so rows behave like dicts."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')  # enforce FK constraints
    return conn


def query_one(sql, params=()):
    with get_conn() as conn:
        row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None


def query_all(sql, params=()):
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


def execute(sql, params=()):
    with get_conn() as conn:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.lastrowid


def init_db():
    """
    Create all tables if they don't exist yet.
    Safe to run multiple times — nothing is dropped or modified.
    """
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS elderly_people (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS user_elderly_access (
                userId INTEGER NOT NULL,
                elderlyId INTEGER NOT NULL,
                FOREIGN KEY (userId) REFERENCES users(id),
                FOREIGN KEY (elderlyId) REFERENCES elderly_people(id)
            );

            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                elderlyId INTEGER NOT NULL,
                day INTEGER NOT NULL,
                date TEXT,
                wakeUpTime INTEGER,
                mealsEaten INTEGER,
                movementCount INTEGER,
                sleepHours REAL,
                timesWokenAtNight INTEGER,
                medicineTaken INTEGER,
                FOREIGN KEY (elderlyId) REFERENCES elderly_people(id)
            );

            CREATE TABLE IF NOT EXISTS devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                apiKey TEXT UNIQUE NOT NULL,
                elderlyId INTEGER NOT NULL,
                FOREIGN KEY (elderlyId) REFERENCES elderly_people(id)
            );

            CREATE TABLE IF NOT EXISTS doctors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                specialty TEXT NOT NULL,
                hospital TEXT,
                email TEXT,
                experience_years INTEGER
            );

            CREATE TABLE IF NOT EXISTS report_shares (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                elderlyId INTEGER NOT NULL,
                doctorId INTEGER NOT NULL,
                sharedAt TEXT NOT NULL,
                summary TEXT,
                FOREIGN KEY (elderlyId) REFERENCES elderly_people(id),
                FOREIGN KEY (doctorId) REFERENCES doctors(id)
            );
        """)
        conn.commit()