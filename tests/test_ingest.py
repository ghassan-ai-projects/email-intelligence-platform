from pathlib import Path

from mailintel.ingest import ingest

from conftest import write_message


def test_ingest_counts_and_exclusions(conn, cfg):
    stats = ingest(conn, cfg)
    assert stats.new == 5  # trash excluded
    assert any("Trash" in f for f in stats.skipped_folders)
    folders = {r["folder"] for r in conn.execute("SELECT folder FROM emails")}
    assert folders == {"INBOX", "Projects", "Sent"}


def test_html_body_extracted(conn, cfg):
    ingest(conn, cfg)
    row = conn.execute(
        "SELECT body_text FROM emails WHERE message_id = '<m3@example.com>'"
    ).fetchone()
    assert "Invoice July" in row["body_text"]
    assert "$420" in row["body_text"]
    assert "<html>" not in row["body_text"]


def test_attachments_recorded(conn, cfg):
    ingest(conn, cfg)
    row = conn.execute(
        "SELECT e.id, e.has_attachments FROM emails e WHERE message_id = '<m4@example.com>'"
    ).fetchone()
    assert row["has_attachments"] == 1
    att = conn.execute(
        "SELECT * FROM attachments WHERE email_id = ?", (row["id"],)
    ).fetchone()
    assert att["filename"] == "doc.pdf"
    assert att["mime"] == "application/pdf"


def test_sent_flag_and_read_flag(conn, cfg):
    ingest(conn, cfg)
    sent = conn.execute(
        "SELECT is_sent FROM emails WHERE message_id = '<m5@example.com>'"
    ).fetchone()
    assert sent["is_sent"] == 1
    unread = conn.execute(
        "SELECT is_read FROM emails WHERE message_id = '<m2@example.com>'"
    ).fetchone()
    assert unread["is_read"] == 0


def test_reingest_is_idempotent(conn, cfg):
    ingest(conn, cfg)
    stats = ingest(conn, cfg)
    assert stats.new == 0
    assert conn.execute("SELECT COUNT(*) FROM emails").fetchone()[0] == 5


def test_flag_rename_updates_read_without_reparse(conn, cfg, maildir: Path):
    ingest(conn, cfg)
    old = maildir / "cur" / "1001.k8sreply.host:2,"
    old.rename(maildir / "cur" / "1001.k8sreply.host:2,S")
    stats = ingest(conn, cfg)
    assert stats.new == 0
    assert stats.updated_flags == 1
    row = conn.execute(
        "SELECT is_read FROM emails WHERE message_id = '<m2@example.com>'"
    ).fetchone()
    assert row["is_read"] == 1


def test_deleted_file_removes_email(conn, cfg, maildir: Path):
    ingest(conn, cfg)
    (maildir / "cur" / "1002.invoice.host:2,").unlink()
    stats = ingest(conn, cfg)
    assert stats.deleted == 1
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM emails WHERE message_id = '<m3@example.com>'"
        ).fetchone()[0]
        == 0
    )
    # FTS row is gone too
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM emails_fts WHERE emails_fts MATCH '\"invoice\"'"
        ).fetchone()[0]
        == 0
    )


def test_duplicate_message_id_across_folders(conn, cfg, maildir: Path):
    ingest(conn, cfg)
    # Same message copied to Projects (like a Gmail label)
    data = (maildir / "cur" / "1000.k8s.host:2,S").read_bytes()
    write_message(maildir / "Projects", "2000.k8scopy.host:2,S", data)
    stats = ingest(conn, cfg)
    assert stats.new == 0
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM emails WHERE message_id = '<m1@example.com>'"
        ).fetchone()[0]
        == 1
    )
    # Deleting one copy keeps the email; deleting both removes it
    (maildir / "cur" / "1000.k8s.host:2,S").unlink()
    stats = ingest(conn, cfg)
    assert stats.deleted == 0
    (maildir / "Projects" / "cur" / "2000.k8scopy.host:2,S").unlink()
    stats = ingest(conn, cfg)
    assert stats.deleted == 1


def test_pipeline_jobs_enqueued(conn, cfg):
    ingest(conn, cfg)
    jobs = {
        (r["stage"],): r["n"]
        for r in conn.execute(
            "SELECT stage, COUNT(*) AS n FROM pipeline_jobs GROUP BY stage"
        )
    }
    assert jobs[("enrich",)] == 5
    assert jobs[("embed",)] == 5
    assert jobs[("attachments",)] == 1  # only the PDF email
