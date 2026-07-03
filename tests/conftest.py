"""Shared fixtures: a synthetic Maildir and a Config pointing at temp storage."""

from __future__ import annotations

from email.message import EmailMessage
from pathlib import Path

import pytest

from mailintel import db as db_mod
from mailintel.config import Config


def make_email(
    msgid: str,
    subject: str,
    from_: str = "Alice Smith <alice@example.com>",
    to: str = "Me <me@example.com>",
    date: str = "Thu, 05 Jun 2025 10:00:00 +0000",
    body: str = "hello",
    html: str | None = None,
    refs: list[str] | None = None,
    pdf: bytes | None = None,
) -> bytes:
    m = EmailMessage()
    m["Message-ID"] = msgid
    m["Subject"] = subject
    m["From"] = from_
    m["To"] = to
    m["Date"] = date
    if refs:
        m["References"] = " ".join(refs)
        m["In-Reply-To"] = refs[-1]
    if html is not None:
        m.set_content(html, subtype="html")
    else:
        m.set_content(body)
    if pdf is not None:
        m.add_attachment(pdf, maintype="application", subtype="pdf", filename="doc.pdf")
    return m.as_bytes()


def maildir_folder(root: Path, name: str = "") -> Path:
    folder = root / name if name else root
    for sub in ("cur", "new", "tmp"):
        (folder / sub).mkdir(parents=True, exist_ok=True)
    return folder


def write_message(folder: Path, filename: str, data: bytes) -> Path:
    sub = "cur" if ":" in filename else "new"
    path = folder / sub / filename
    path.write_bytes(data)
    return path


@pytest.fixture
def maildir(tmp_path: Path) -> Path:
    """INBOX at root, Maildir++ .Sent/.Trash, nested Projects folder."""
    root = tmp_path / "Mail"
    inbox = maildir_folder(root)
    sent = maildir_folder(root, ".Sent")
    trash = maildir_folder(root, ".Trash")
    projects = maildir_folder(root, "Projects")

    write_message(
        inbox,
        "1000.k8s.host:2,S",
        make_email(
            "<m1@example.com>",
            "Kubernetes cluster upgrade",
            body="We need to plan the Kubernetes cluster upgrade for June 10. Acme Corp "
            "expects zero downtime.",
            date="Thu, 05 Jun 2025 10:00:00 +0000",
        ),
    )
    write_message(
        inbox,
        "1001.k8sreply.host:2,",
        make_email(
            "<m2@example.com>",
            "Re: Kubernetes cluster upgrade",
            from_="Bob Jones <bob@example.com>",
            refs=["<m1@example.com>"],
            body="Sounds good, I'll prepare the migration checklist.",
            date="Thu, 05 Jun 2025 12:30:00 +0000",
        ),
    )
    write_message(
        inbox,
        "1002.invoice.host:2,",
        make_email(
            "<m3@example.com>",
            "Invoice July",
            from_="Billing <billing@vendor.com>",
            html="<html><body><h1>Invoice July</h1><p>Amount due: <b>$420</b> by "
            "July 12.</p></body></html>",
            date="Fri, 06 Jun 2025 08:00:00 +0000",
        ),
    )
    write_message(
        projects,
        "1003.report.host:2,S",
        make_email(
            "<m4@example.com>",
            "Quarterly report attached",
            from_="Carol <carol@acme.com>",
            body="Please find the quarterly report attached.",
            pdf=b"%PDF-1.4 fake pdf bytes",
            date="Sat, 07 Jun 2025 09:00:00 +0000",
        ),
    )
    write_message(
        sent,
        "1004.followup.host:2,S",
        make_email(
            "<m5@example.com>",
            "Follow-up on contract",
            from_="Me <me@example.com>",
            to="Dave <dave@client.example>",
            body="Just following up on the contract draft I sent last week.",
            date="Sun, 08 Jun 2025 15:00:00 +0000",
        ),
    )
    write_message(
        trash,
        "1005.spam.host:2,S",
        make_email("<m6@example.com>", "You won a prize", body="Click here."),
    )
    return root


@pytest.fixture
def cfg(maildir: Path, tmp_path: Path) -> Config:
    c = Config()
    c.maildir.path = maildir
    c.storage.db_path = tmp_path / "mail.db"
    c.embeddings.dimensions = 8
    return c


@pytest.fixture
def conn(cfg: Config):
    connection = db_mod.connect(cfg.storage.db_path)
    yield connection
    connection.close()
