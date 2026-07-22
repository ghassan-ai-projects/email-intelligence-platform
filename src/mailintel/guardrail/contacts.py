"""Contact database: tiered contact management for the guardrail system.

Contacts have three tiers:
  - **trusted**: the owner and known contacts (warnings still shown, no block)
  - **known**: previously interacted with (full scanning applies)
  - **unknown**: never seen before (full scanning applies)

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
        name: str = "",
        tier: str = "unknown",
        notes: str = "",
    ) -> ContactInfo:
        """Register a new contact or update an existing one.

        If the address already exists, only *name*, *notes* and *tier* are
        updated when the provided values are non-empty/non-default.
        """
        addr = addr.lower().strip()
        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        existing = self._conn.execute("SELECT id FROM contacts WHERE addr = ?", (addr,)).fetchone()

        if existing:
            updates: list[str] = []
            params: list[Any] = []
            if tier != "unknown":
                updates.append("tier = ?")
                params.append(tier)
            if name:
                updates.append("name = ?")
                params.append(name)
            if notes:
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
                (addr, name, tier, notes, now, now),
            )
            contact_id = cur.lastrowid
            assert contact_id is not None

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
        data = json.loads(path.read_text())
        count = 0
        for entry in data.get("contacts", []):
            self.register_contact(
                addr=entry.get("addr", entry.get("sender", "")),
                name=entry.get("name", ""),
                tier=entry.get("tier", "unknown"),
                notes=entry.get("notes", ""),
            )
            count += 1
        return count
