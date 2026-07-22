"""Tests for database helpers and migrations."""

from __future__ import annotations

import json

from mailintel import db
from mailintel.guardrail.db import migrate_guardrail


def test_import_contacts_json(conn, tmp_path):
    migrate_guardrail(conn)
    path = tmp_path / "contacts.json"
    path.write_text(
        json.dumps(
            {
                "contacts": [
                    {"addr": "alice@example.com", "name": "Alice", "tier": "trusted"},
                    {"addr": "bob@example.com", "tier": "known"},
                    {"addr": ""},  # skipped
                ]
            }
        )
    )
    count = db.import_contacts_json(conn, path)
    assert count == 2
    rows = conn.execute("SELECT addr, name, tier FROM contacts ORDER BY addr").fetchall()
    assert rows[0]["addr"] == "alice@example.com"
    assert rows[0]["tier"] == "trusted"
    assert rows[1]["addr"] == "bob@example.com"
    assert rows[1]["tier"] == "known"


def test_import_contacts_json_update_existing(conn, tmp_path):
    migrate_guardrail(conn)
    conn.execute(
        "INSERT INTO contacts (addr, name, tier, notes) VALUES (?, ?, ?, ?)",
        ("alice@example.com", "Old", "unknown", ""),
    )
    conn.commit()
    path = tmp_path / "contacts.json"
    path.write_text(
        json.dumps({"contacts": [{"addr": "alice@example.com", "tier": "trusted", "notes": "new"}]})
    )
    count = db.import_contacts_json(conn, path)
    assert count == 1
    row = conn.execute(
        "SELECT tier, notes FROM contacts WHERE addr = ?", ("alice@example.com",)
    ).fetchone()
    assert row["tier"] == "trusted"
    assert row["notes"] == "new"


def test_import_contacts_json_malformed(conn, tmp_path):
    migrate_guardrail(conn)
    path = tmp_path / "contacts.json"
    path.write_text("[1, 2, 3]")
    assert db.import_contacts_json(conn, path) == 0
    path.write_text("{bad json")
    assert db.import_contacts_json(conn, path) == 0
    assert db.import_contacts_json(conn, tmp_path / "missing.json") == 0


def test_connect_does_not_import_contacts(tmp_path):
    db_path = tmp_path / "mail.db"
    conn = db.connect(db_path)
    try:
        rows = conn.execute("SELECT COUNT(*) AS n FROM contacts").fetchone()
        assert rows["n"] == 0
    finally:
        conn.close()
