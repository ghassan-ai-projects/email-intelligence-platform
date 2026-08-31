"""Contact database: tiered contact management for the guardrail system.

Contacts have three persisted tiers: trusted, known, and unknown. All email
content remains untrusted and is scanned regardless of tier; the tier is
metadata for contact-management workflows until a separate policy explicitly
defines a safe effect on scanning.

Tier data is persisted in the SQLite contacts table inside the main mail.db.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass
class ContactInfo:
    """Information about a known contact."""

    sender: str
    tier: str  # "trusted" | "known" | "unknown"
    name: str = ""
    notes: str = ""
    contact_id: int | None = None


class ContactsDB:
    """Manage the contacts table via the shared mail.db connection.

    Args:
        conn: An open connection to the mailintel SQLite database.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def lookup(self, addr: str) -> ContactInfo:
        """Look up a contact by email address.

        Returns ContactInfo with tier defaulting to "unknown" when the
        address has never been registered.
        """
        row = self._conn.execute(
            "SELECT id, addr, name, tier, notes FROM contacts WHERE addr = ?",
            (addr.lower().strip(),),
        ).fetchone()
        if row is None:
            return ContactInfo(sender=addr, tier="unknown")

        return ContactInfo(
            sender=row["addr"],
            tier=row["tier"],
            name=row["name"],
            notes=row["notes"],
            contact_id=row["id"],
        )

    def list_contacts(self, tier: str | None = None) -> list[dict[str, Any]]:
        """Return all contacts, optionally filtered by tier."""
        if tier:
            rows = self._conn.execute(
                "SELECT id, addr, name, tier, notes, created_at, updated_at "
                "FROM contacts WHERE tier = ? ORDER BY addr",
                (tier,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id, addr, name, tier, notes, created_at, updated_at "
                "FROM contacts ORDER BY tier, addr"
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def register_contact(
        self,
        addr: str,
        name: str | None = None,
        tier: str | None = None,
        notes: str | None = None,
        *,
        commit: bool = True,
    ) -> ContactInfo:
        """Register a new contact or update an existing one.

        If the address already exists, only non-None fields are updated.
        Pass tier="unknown" explicitly to demote a contact.
        """
        addr = addr.lower().strip()
        if tier is not None and tier not in ("trusted", "known", "unknown"):
            msg = f"invalid tier: {tier!r} (choose: trusted, known, unknown)"
            raise ValueError(msg)
        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        existing = self._conn.execute("SELECT id FROM contacts WHERE addr = ?", (addr,)).fetchone()

        if existing:
            updates: list[str] = []
            params: list[Any] = []
            if tier is not None:
                updates.append("tier = ?")
                params.append(tier)
            if name is not None:
                updates.append("name = ?")
                params.append(name)
            if notes is not None:
                updates.append("notes = ?")
                params.append(notes)
            if updates:
                updates.append("updated_at = ?")
                params.append(now)
                params.append(existing["id"])
                self._conn.execute(
                    f"UPDATE contacts SET {', '.join(updates)} WHERE id = ?",
                    params,
                )
            contact_id = existing["id"]
        else:
            cur = self._conn.execute(
                "INSERT INTO contacts (addr, name, tier, notes, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    addr,
                    name or "",
                    tier or "unknown",
                    notes or "",
                    now,
                    now,
                ),
            )
            contact_id = cur.lastrowid
            assert contact_id is not None

        if commit:
            self._conn.commit()
        return self.lookup(addr)

    def update_tier(self, addr: str, tier: str) -> ContactInfo:
        """Change the tier of an existing contact (trusted / known / unknown)."""
        if tier not in ("trusted", "known", "unknown"):
            msg = f"invalid tier: {tier!r} (choose: trusted, known, unknown)"
            raise ValueError(msg)
        return self.register_contact(addr, tier=tier)

    def log_interaction(
        self,
        addr: str,
        email_id: int | None = None,
        direction: str = "inbound",
        summary: str = "",
    ) -> None:
        """Record that an interaction with this contact occurred."""
        addr = addr.lower().strip()
        contact = self.lookup(addr)
        if contact.contact_id is None:
            contact = self.register_contact(addr)
            assert contact.contact_id is not None
        self._conn.execute(
            "INSERT INTO contact_interactions "
            "(contact_id, email_id, direction, summary) "
            "VALUES (?, ?, ?, ?)",
            (contact.contact_id, email_id, direction, summary),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Bulk import from contacts.json
    # ------------------------------------------------------------------

    def import_json(self, path: Path | str) -> int:
        """Import contacts from a JSON file.

        File format:
            {
                "contacts": [
                    {"addr": "...", "name": "...", "tier": "trusted", "notes": "..."},
                    ...
                ]
            }

        Returns the number of contacts imported (inserted or updated).
        """
        path = Path(path)
        if not path.exists():
            return 0
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return 0
        if not isinstance(data, dict):
            return 0
        entries = data.get("contacts", [])
        if not isinstance(entries, list):
            return 0
        count = 0
        self._conn.execute("SAVEPOINT contacts_import")
        try:
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                addr = entry.get("addr", entry.get("sender", ""))
                if not isinstance(addr, str) or not addr.strip():
                    continue
                tier = entry.get("tier", "unknown")
                if not isinstance(tier, str) or tier not in ("trusted", "known", "unknown"):
                    continue
                self.register_contact(
                    addr=addr,
                    name=str(entry.get("name", "")),
                    tier=tier,
                    notes=str(entry.get("notes", "")),
                    commit=False,
                )
                count += 1
        except Exception:
            self._conn.execute("ROLLBACK TO SAVEPOINT contacts_import")
            self._conn.execute("RELEASE SAVEPOINT contacts_import")
            raise
        self._conn.execute("RELEASE SAVEPOINT contacts_import")
        self._conn.commit()
        return count
